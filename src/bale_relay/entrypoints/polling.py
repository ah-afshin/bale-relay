import time
import uuid
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from bale_relay.storage.models import Receiver
from bale_relay.core.errors import ServiceError

class Poller:
    def __init__(self, queue, bale):
        self.queue,self.bale=queue,bale
        self.owner=uuid.uuid4().hex
    def acquire(self):
        if self.bale.call("getWebhookInfo").get("url"):
            raise ServiceError("ابتدا webhook را با فرمان مدیریتی حذف کنید.",409)
        with self.queue.db.session_scope() as s:
            ins=sqlite_insert if self.queue.db.engine.dialect.name=="sqlite" else pg_insert
            s.execute(ins(Receiver).values(id=1,mode="polling",offset=0,owner=None,lease_until=0).on_conflict_do_nothing())
            row=s.execute(update(Receiver).where(Receiver.id==1,Receiver.lease_until<time.time()).values(mode="polling",owner=self.owner,lease_until=time.time()+90).returning(Receiver)).scalar_one_or_none()
            if row is None: raise ServiceError("یک دریافت‌کنندهٔ دیگر فعال است.",409)
    def once(self):
        with self.queue.db.session_scope() as s:
            row=s.execute(update(Receiver).where(Receiver.id==1,Receiver.owner==self.owner,Receiver.mode=="polling",Receiver.lease_until>time.time()).values(lease_until=time.time()+90).returning(Receiver)).scalar_one_or_none()
            if row is None: raise ServiceError("قفل دریافت پیام از دست رفت.",409)
            offset=row.offset
        updates=self.bale.call("getUpdates", {"offset":offset,"timeout":25,"limit":50})
        if not isinstance(updates,list): raise ServiceError("پاسخ دریافت پیام نامعتبر است.")
        for payload in updates:
            try: self.queue.ingest(payload)
            except ServiceError as exc:
                if exc.status != 429: raise
                # The quota rejection is final; do not let it poison the receive queue.
            if not isinstance(payload,dict) or type(payload.get("update_id")) is not int: raise ServiceError("آپدیت نامعتبر است.")
            offset=max(offset,payload["update_id"]+1)
            with self.queue.db.session_scope() as s:
                changed=s.execute(update(Receiver).where(Receiver.id==1,Receiver.owner==self.owner,Receiver.mode=="polling").values(offset=offset)).rowcount
                if not changed: raise ServiceError("قفل دریافت پیام از دست رفت.",409)
    def release(self):
        with self.queue.db.session_scope() as s:
            s.execute(update(Receiver).where(Receiver.id==1,Receiver.owner==self.owner).values(owner=None,lease_until=0))
    def run(self):
        self.acquire()
        try:
            delay=1
            while True:
                try:
                    self.once()
                    delay=1
                except ServiceError as exc:
                    if exc.status==409: raise
                    time.sleep(delay)
                    delay=min(delay*2,20)
        finally: self.release()
