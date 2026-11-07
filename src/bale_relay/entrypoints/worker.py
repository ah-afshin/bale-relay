import time
from sqlalchemy import select
from bale_relay.storage.models import Delivery
from bale_relay.bot.formatting import chunks
from bale_relay.bot.dispatcher import Dispatcher, Cancelled
from bale_relay.core.errors import ServiceError
from bale_relay.services.ai import AIError
from bale_relay.adapters.bale import AmbiguousDelivery

class Worker:
    def __init__(self, queue, services, bale):
        self.queue, self.services, self.bale = queue, services, bale
        self.dispatcher = Dispatcher(queue, services)
    def once(self):
        job = self.queue.claim(ttl=300)
        if job is None: return False
        try:
            with self.queue.db.session_scope() as s:
                deliveries = s.scalars(select(Delivery).where(Delivery.job_id == job.id).order_by(Delivery.ordinal)).all()
            if not deliveries:
                try: text = self.dispatcher.handle(job)
                except (ServiceError, AIError): text = "سرویس در دسترس نیست یا سهمیه تمام شده است؛ بعداً تلاش کنید."
                with self.queue.db.session_scope() as s:
                    if not self.queue.live(job): raise Cancelled()
                    s.add_all(Delivery(job_id=job.id, ordinal=i, text=part) for i,part in enumerate(chunks(text)))
                with self.queue.db.session_scope() as s:
                    deliveries = s.scalars(select(Delivery).where(Delivery.job_id == job.id).order_by(Delivery.ordinal)).all()
            for delivery in deliveries:
                if not self.queue.live(job): raise Cancelled()
                if delivery.state == "sent": continue
                if delivery.state in {"sending", "unknown"}:
                    self.queue.finish(job, {"delivery": "unknown"}, "unknown")
                    return True
                with self.queue.db.session_scope() as s: s.get(Delivery, delivery.id).state = "sending"
                try: result = self.bale.send_text(job.user_id, delivery.text)
                except AmbiguousDelivery:
                    with self.queue.db.session_scope() as s: s.get(Delivery, delivery.id).state = "unknown"
                    self.queue.finish(job, {"delivery": "unknown"}, "unknown")
                    return True
                with self.queue.db.session_scope() as s:
                    row = s.get(Delivery, delivery.id)
                    row.state = "sent"
                    row.message_id = str(result.get("message_id", "")) if isinstance(result, dict) else ""
            self.queue.finish(job, {})
        except Cancelled:
            self.queue.finish(job, {}, "cancelled")
        except Exception:
            # No exception repr: upstream errors may include credentials or private content.
            self.queue.finish(job, {"error": "processing_failed"}, "failed")
        return True
    def run(self):
        while True:
            self.queue.forget_expired()
            if not self.once(): time.sleep(2)
