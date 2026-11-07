import time
import uuid
from sqlalchemy import select, update, delete, exists, and_
from sqlalchemy.orm import aliased
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from bale_relay.storage.models import User, Update, Job, Message, Usage, Delivery
from bale_relay.core.errors import ServiceError

class Queue:
    def __init__(self, database): self.db = database
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
            text = message.get("text", "") if not callback else ""
            command = text.split(maxsplit=1)[0] if isinstance(text, str) and text else ""
            # Cancellation is applied at receipt, so it can interrupt an in-flight generation.
            if command in {"/forget", "/new", "/cancel"}:
                if command != "/cancel":
                    user.generation += 1
                s.execute(update(Job).where(Job.user_id == uid, Job.state.in_(["queued", "running", "paused"])).values(state="cancelled"))
                if command == "/forget":
                    s.execute(delete(Message).where(Message.user_id == uid))
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
                    for key, limit in ((f"youtube:{day}:{uid}", 1), (f"youtube:{day}:global", 10)):
                        stmt = ins(Usage).values(key=key, used=1).on_conflict_do_update(index_elements=[Usage.key], set_={"used": Usage.used+1}, where=Usage.used < limit).returning(Usage.key)
                        if s.execute(stmt).scalar_one_or_none() is None:
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
                state="running", lease=token, lease_until=now+ttl).returning(Job)).scalar_one_or_none()
            return job
    def live(self, job):
        with self.db.session_scope() as s:
            current = s.get(Job, job.id)
            user = s.get(User, job.user_id)
            return bool(current and user and user.enabled and current.state == "running" and
                        current.lease == job.lease and current.lease_until > time.time() and user.generation == job.generation)
    def finish(self, job, result, state="done"):
        with self.db.session_scope() as s:
            return s.execute(update(Job).where(Job.id == job.id, Job.lease == job.lease, Job.state == "running").values(
                state=state, result=result, lease=None, lease_until=0)).rowcount == 1
    def reserve(self, key, limit):
        ins = sqlite_insert if self.db.engine.dialect.name == "sqlite" else pg_insert
        with self.db.session_scope() as s:
            stmt = ins(Usage).values(key=key, used=1).on_conflict_do_update(index_elements=[Usage.key],
                    set_={"used": Usage.used+1}, where=Usage.used < limit).returning(Usage.key)
            if limit < 1 or s.execute(stmt).scalar_one_or_none() is None:
                raise ServiceError("سهمیه به پایان رسیده است.", 429)
    def forget_expired(self, days=7):
        with self.db.session_scope() as s:
            s.execute(delete(Message).where(Message.created < time.time()-days*86400))
