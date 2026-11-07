import time
import uuid
from sqlalchemy import select, update, delete, exists, and_
from sqlalchemy.orm import aliased
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from bale_relay.storage.models import User, Update, Job, Message, Usage, Delivery
from bale_relay.core.errors import ServiceError

class Queue:
    def __init__(self, database, config=None):
        from bale_relay.core.config import Config
        self.db = database
        self.config=config or Config()
    def allow(self, user_id, enabled=True):
        with self.db.session_scope() as s:
            user = s.get(User, user_id)
            if user is None: s.add(User(id=user_id, enabled=enabled))
            else:
                user.enabled = enabled
                if not enabled:
                    s.execute(update(Job).where(Job.user_id == user_id, Job.state.in_(["queued", "running", "paused"])).values(state="cancelled"))
    def ingest(self, payload):
        if not isinstance(payload, dict) or type(payload.get("update_id")) is not int or payload["update_id"] < 0:
            raise ValueError("Invalid update")
        payload = dict(payload)
        payload.pop("bot_command", None)
        callback = payload.get("callback_query")
        message = callback.get("message") if isinstance(callback, dict) else payload.get("message")
        sender = callback.get("from") if isinstance(callback, dict) else message.get("from") if isinstance(message, dict) else None
        if not isinstance(message, dict) or not isinstance(sender, dict): return "ignored"
        chat = message.get("chat", {})
        uid = sender.get("id")
        if not isinstance(chat, dict): return "denied"
        if type(uid) is not int or chat.get("type") != "private" or chat.get("id") != uid:
            return "denied"
        with self.db.session_scope() as s:
            user = s.scalar(select(User).where(User.id == uid).with_for_update())
            if user is None or not user.enabled: return "denied"
            ins = sqlite_insert if self.db.engine.dialect.name == "sqlite" else pg_insert
            row = s.execute(ins(Update).values(id=payload["update_id"], user_id=uid, payload=payload, created=time.time()).on_conflict_do_nothing().returning(Update.id)).scalar_one_or_none()
            if row is None: return "duplicate"
            payload = dict(payload)
            payload.pop("bot_command", None)
            if callback:
                data = callback.get("data", "")
                try:
                    target_id, index = map(int, data.split(":"))
                    target = s.get(Job, target_id)
                    if not target or target.user_id != uid or target.generation != user.generation:
                        raise ValueError()
                    action = target.result.get("actions", [])[index] if index >= 0 else None
                    if not action: raise ValueError()
                    payload["bot_command"] = action["command"]
                except (ValueError, TypeError, AttributeError, IndexError, KeyError):
                    s.delete(s.get(Update, row))
                    return "denied"
                s.execute(update(Update).where(Update.id == row).values(payload=payload))
            text = payload.get("bot_command", message.get("text", "") if not callback else "")
            command = text.split(maxsplit=1)[0] if isinstance(text, str) and text else ""
            # Cancellation is applied at receipt, so it can interrupt an in-flight generation.
            if command in {"/forget", "/new", "/cancel"}:
                if command != "/cancel":
                    user.generation += 1
                s.execute(update(Job).where(Job.user_id == uid, Job.state.in_(["queued", "running", "paused"])).values(state="cancelled"))
                if command == "/forget":
                    s.execute(delete(Message).where(Message.user_id == uid))
                    s.execute(update(Job).where(Job.user_id == uid).values(result={}))
                    s.execute(update(Delivery).where(Delivery.job_id.in_(select(Job.id).where(Job.user_id == uid))).values(text=""))
                    s.execute(update(Update).where(Update.user_id == uid).values(payload={}))
                    s.execute(update(Update).where(Update.id == row).values(payload=payload))
            lane = "media" if command == "/download" else "text"
            if lane == "media":
                from bale_relay.adapters.youtube import video_id
                try: video_id(text.split(maxsplit=1)[1].strip())
                except (ServiceError, IndexError): lane = "text"
                if lane == "media":
                    from datetime import datetime, timezone
                    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    for key, limit in ((f"youtube:{day}:{uid}", self.config.youtube_daily), (f"youtube:{day}:global", self.config.youtube_global_daily)):
                        stmt = ins(Usage).values(key=key, used=1).on_conflict_do_update(index_elements=[Usage.key], set_={"used": Usage.used+1}, where=Usage.used < limit).returning(Usage.key)
                        if limit<1 or s.execute(stmt).scalar_one_or_none() is None:
                            raise ServiceError("سهمیهٔ یوتیوب به پایان رسیده است.", 429)
            s.add(Job(update_id=row, user_id=uid, generation=user.generation, lane=lane, created=time.time(), result={}))
        return "accepted"
    def claim(self, lane="text", ttl=120):
        now = time.time()
        with self.db.session_scope() as s:
            # Expired work is resumable; outbound sends must use the separate delivery ledger.
            s.execute(update(Job).where(Job.state == "running", Job.lease_until < now).values(state="queued", lease=None))
            earlier = aliased(Job)
            candidate = select(Job.id).where(Job.state == "queued", Job.lane == lane,
                ~exists(select(earlier.id).where(earlier.user_id == Job.user_id, earlier.lane == Job.lane, earlier.id < Job.id,
                         earlier.state.in_(["queued", "running"])))).order_by(Job.id).limit(1).scalar_subquery()
            token = uuid.uuid4().hex
            job = s.execute(update(Job).where(Job.id == candidate, Job.state == "queued").values(
                state="running", lease=token, lease_until=now+ttl, started=now, finished=0).returning(Job)).scalar_one_or_none()
            if job is not None:
                job.metrics=dict(job.metrics or {},attempts=(job.metrics or {}).get("attempts",0)+1)
            return job
    def live(self, job):
        with self.db.session_scope() as s:
            current = s.get(Job, job.id)
            user = s.get(User, job.user_id)
            return bool(current and user and user.enabled and current.state == "running" and
                        current.lease == job.lease and current.lease_until > time.time() and user.generation == job.generation)
    def finish(self, job, result, state="done"):
        with self.db.session_scope() as s:
            row=s.scalar(select(Job).where(Job.id==job.id).with_for_update())
            if row is None or row.lease!=job.lease or row.state!="running":return False
            now=time.time()
            row.metrics=dict(row.metrics or {},processing_seconds=(row.metrics or {}).get("processing_seconds",0)+max(0,now-row.started))
            row.state=state;row.result=result;row.lease=None;row.lease_until=0;row.finished=now
            return True
    def metric(self,job,key,value=1):
        if key not in {"service_errors","downloaded_bytes","uploaded_bytes"} or type(value) not in {int,float} or value<0:
            raise ValueError("Invalid metric")
        with self.db.session_scope() as s:
            row=s.scalar(select(Job).where(Job.id==job.id).with_for_update())
            if row is None or row.lease!=job.lease or row.state!="running":return
            row.metrics=dict(row.metrics or {},**{key:(row.metrics or {}).get(key,0)+value})
    def statistics(self):
        report={"states":{},"lanes":{},"attempts":0,"processing_seconds":0,"service_errors":0,"downloaded_bytes":0,"uploaded_bytes":0}
        with self.db.session_scope() as s:
            for lane,state,metrics in s.execute(select(Job.lane,Job.state,Job.metrics)):
                report["states"][state]=report["states"].get(state,0)+1
                report["lanes"][lane]=report["lanes"].get(lane,0)+1
                for key in ("attempts","processing_seconds","service_errors","downloaded_bytes","uploaded_bytes"):
                    report[key]+=(metrics or {}).get(key,0)
        return report
    def reserve(self, key, limit):
        ins = sqlite_insert if self.db.engine.dialect.name == "sqlite" else pg_insert
        with self.db.session_scope() as s:
            stmt = ins(Usage).values(key=key, used=1).on_conflict_do_update(index_elements=[Usage.key],
                    set_={"used": Usage.used+1}, where=Usage.used < limit).returning(Usage.key)
            if limit < 1 or s.execute(stmt).scalar_one_or_none() is None:
                raise ServiceError("سهمیه به پایان رسیده است.", 429)
    def forget_expired(self, days=7):
        with self.db.session_scope() as s:
            cutoff = time.time()-days*86400
            s.execute(delete(Message).where(Message.created < cutoff))
            expired = select(Job.id).where(Job.created < cutoff)
            s.execute(update(Delivery).where(Delivery.job_id.in_(expired)).values(text=""))
            s.execute(update(Update).where(Update.created < cutoff).values(payload={}))
            s.execute(update(Job).where(Job.created < cutoff).values(result={},state="expired",lease=None,lease_until=0))

    def reserve_job(self, job, feature, limits):
        ins = sqlite_insert if self.db.engine.dialect.name == "sqlite" else pg_insert
        with self.db.session_scope() as s:
            row = s.scalar(select(Job).where(Job.id==job.id).with_for_update())
            if row.state != "running" or row.lease != job.lease:
                raise ServiceError("کار دیگر فعال نیست.",409)
            data = dict(row.result)
            reserved = list(data.get("reserved", []))
            if feature in reserved: return
            for key, limit in limits:
                stmt=ins(Usage).values(key=key,used=1).on_conflict_do_update(index_elements=[Usage.key],set_={"used":Usage.used+1},where=Usage.used<limit).returning(Usage.key)
                if limit<1 or s.execute(stmt).scalar_one_or_none() is None:
                    raise ServiceError("سهمیه به پایان رسیده است.",429)
            row.result = dict(data,reserved=reserved+[feature])
