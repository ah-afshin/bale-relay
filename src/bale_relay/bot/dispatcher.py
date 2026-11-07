import time
from datetime import datetime, timezone
from sqlalchemy import select, delete, update
from bale_relay.storage.models import User, Update, Job, Message
from bale_relay.core.errors import ServiceError

HELP = "سلام! یکی از فرمان‌ها را انتخاب کنید:\n/ai چت با هوش مصنوعی\n/model انتخاب مدل\n/new گفت‌وگوی جدید\n/search عبارت جست‌وجو\n/youtube جست‌وجوی ویدیو\n/status وضعیت کارها\n/cancel لغو\n/forget حذف تاریخچه\n/privacy حریم خصوصی"
PRIVACY = "پیام‌ها از بله و ارائه‌دهندهٔ AI عبور می‌کنند. تاریخچهٔ بات هفت روز نگهداری می‌شود. /forget فقط دادهٔ تحت کنترل بات را حذف می‌کند."

class Cancelled(Exception): pass

class Dispatcher:
    def __init__(self, queue, services): self.queue, self.services = queue, services
    def check(self, job):
        if not self.queue.live(job): raise Cancelled()
    def handle(self, job):
        self.check(job)
        db = self.queue.db
        with db.session_scope() as s:
            payload = s.get(Update, job.update_id).payload
            user = s.get(User, job.user_id)
            model, mode = user.model, user.mode
        if payload.get("callback_query"):
            return "این دکمه پشتیبانی نمی‌شود؛ از فرمان‌ها استفاده کنید."
        text = payload.get("message", {}).get("text", "")
        if not isinstance(text, str) or not text.strip(): return "لطفاً پیام متنی بفرستید."
        command, _, argument = text.strip().partition(" ")
        argument = argument.strip()
        if command in {"/start", "/help"}: return HELP
        if command == "/privacy": return PRIVACY
        if command in {"/forget", "/new", "/cancel"}: return "انجام شد."
        if command == "/status":
            with db.session_scope() as s:
                s.execute(update(Job).where(Job.user_id == job.user_id, Job.generation == job.generation, Job.state == "paused").values(state="queued"))
            with db.session_scope() as s:
                jobs = s.scalars(select(Job).where(Job.user_id == job.user_id, Job.id != job.id).order_by(Job.id.desc()).limit(5)).all()
                return "\n".join(f"{j.id}: {j.state}" for j in jobs) or "کاری ثبت نشده است."
        if command == "/model":
            models = self.services.models()
            if not argument: return "مدل‌های مجاز:\n" + ("\n".join(models) or "هنوز مدلی تنظیم نشده است.") + "\n/model provider/model"
            if argument not in models: return "این مدل مجاز یا در دسترس نیست."
            self._update_user(job, model=argument)
            return "مدل انتخاب شد: " + argument
        if command == "/ai":
            self._update_user(job, mode="ai")
            return "پیام خود را بفرستید؛ با /model مدل را انتخاب کنید."
        if command == "/search" or mode == "search" and not command.startswith("/"):
            query = argument if command == "/search" else text
            if not query:
                self._update_user(job, mode="search")
                return "عبارت جست‌وجو را بفرستید."
            self._quota(job, "search", self.services.config.search_daily, 100)
            result = self.services.search(query)
            return "\n\n".join(f"{i}. {r['title']}\n{r['snippet']}\n{r['url']}" for i,r in enumerate(result["results"],1)) or "نتیجه‌ای پیدا نشد."
        if command in {"/youtube", "/video"}:
            from bale_relay.adapters.youtube import YouTube, video_id
            yt = YouTube()
            if not argument: return "برای جست‌وجو /youtube عبارت و برای انتخاب /video شناسه را بفرستید."
            if command == "/video":
                info = yt.metadata(argument, active=lambda: self.queue.live(job))
                return f"{info['title']}\n{info['duration']:.0f} ثانیه | 360p\nبرای دریافت: /download {info['id']}"
            results = yt.search(argument, active=lambda: self.queue.live(job))
            return "\n\n".join(f"{i}. {r['title']}\n{r['duration']:.0f}s\n/video {r['id']}" for i,r in enumerate(results,1)) or "نتیجه‌ای پیدا نشد."
        if command == "/download": return "فرمت فرمان: /download شناسهٔ معتبر ویدیو"
        if command.startswith("/"): return HELP
        if not model: return "ابتدا با /model یک مدل انتخاب کنید."
        self._quota(job, "ai", self.services.config.ai_daily, 200)
        now = time.time()
        with db.session_scope() as s:
            messages = s.scalars(select(Message).where(Message.user_id == job.user_id, Message.generation == job.generation,
                            Message.created > now-7*86400).order_by(Message.id.desc()).limit(40)).all()
            history = [{"role": m.role, "content": m.content} for m in reversed(messages)]
        if len(text) > 8000: return "پیام بیش از حد طولانی است."
        history.append({"role": "user", "content": text})
        while len(history) > 1 and sum(len(m["content"]) for m in history) > 60000: history.pop(0)
        response = self.services.complete(model, history)
        # Lock the owner before persisting; /forget takes the same lock at receipt.
        with db.session_scope() as s:
            owner = s.scalar(select(User).where(User.id == job.user_id).with_for_update())
            self.check(job)
            if owner.generation != job.generation: raise Cancelled()
            s.add_all([Message(user_id=job.user_id, generation=job.generation, role=role, content=content, created=now)
                       for role,content in (("user", text), ("assistant", response))])
        return response or "پاسخ خالی بود."
    def _update_user(self, job, **values):
        with self.queue.db.session_scope() as s:
            owner = s.scalar(select(User).where(User.id == job.user_id).with_for_update())
            self.check(job)
            for key,value in values.items(): setattr(owner,key,value)
    def _quota(self, job, feature, daily, total):
        self.check(job)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.queue.reserve(f"{feature}:{day}:{job.user_id}", daily)
        self.queue.reserve(f"{feature}:{day}:global", total)
