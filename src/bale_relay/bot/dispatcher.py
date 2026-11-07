import time
from datetime import datetime, timezone
from sqlalchemy import select, delete, update
from bale_relay.storage.models import User, Update, Job, Message, Delivery
from bale_relay.core.errors import ServiceError

HELP = "سلام! یکی از فرمان‌ها را انتخاب کنید:\n/ai چت با هوش مصنوعی\n/model انتخاب مدل\n/new گفت‌وگوی جدید\n/search عبارت جست‌وجو\n/youtube جست‌وجوی ویدیو\n/status وضعیت کارها\n/cancel لغو\n/forget حذف تاریخچه\n/privacy حریم خصوصی"
PRIVACY = "پیام‌ها از بله و ارائه‌دهندهٔ AI عبور می‌کنند. تاریخچهٔ بات هفت روز نگهداری می‌شود. /forget فقط دادهٔ تحت کنترل بات را حذف می‌کند."

class Cancelled(Exception): pass
class GenerationUnknown(Exception): pass

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
        text = payload.get("bot_command", payload.get("message", {}).get("text", ""))
        if not isinstance(text, str) or not text.strip(): return "لطفاً پیام متنی بفرستید."
        command, _, argument = text.strip().partition(" ")
        argument = argument.strip()
        if command in {"/start", "/help"}:
            return {"text":HELP,"actions":[{"label":label,"command":cmd} for label,cmd in [("چت AI","/ai"),("مدل‌ها","/model"),("سرچ گوگل","/search"),("یوتیوب","/youtube"),("وضعیت","/status")]]}
        if command == "/privacy": return PRIVACY
        if command in {"/forget", "/new", "/cancel"}: return "انجام شد."
        if command == "/status":
            with db.session_scope() as s:
                s.execute(update(Job).where(Job.user_id == job.user_id, Job.generation == job.generation, Job.state == "paused").values(state="queued"))
            with db.session_scope() as s:
                jobs = s.scalars(select(Job).where(Job.user_id == job.user_id, Job.id != job.id).order_by(Job.id.desc()).limit(5)).all()
                return "\n".join(f"{j.id}: {j.state}" for j in jobs) or "کاری ثبت نشده است."
        if command == "/retry":
            if not argument.isdigit(): return "برای تأیید ارسال دوباره: /retry شمارهٔ کار"
            with db.session_scope() as s:
                target=s.scalar(select(Job).where(Job.id==int(argument),Job.user_id==job.user_id,Job.generation==job.generation).with_for_update())
                if not target or target.state not in {"unknown", "paused", "failed"}: return "این کار قابل تلاش مجدد نیست."
                data=dict(target.result)
                if target.lane=="media":
                    data["parts"]=[dict(part,state="pending") if part.get("state") in {"unknown","sending"} else part for part in data.get("parts",[])]
                    target.result=data
                else:
                    if data.get("generation_state")=="in_flight":
                        data.pop("generation_state")
                        target.result=data
                    s.execute(update(Delivery).where(Delivery.job_id==target.id,Delivery.state.in_(["unknown","sending"])).values(state="pending"))
                target.state="queued"
            return "تلاش دوباره ثبت شد؛ ارسال نامشخص ممکن است تکراری باشد."
        if command == "/model":
            models = self.services.models()
            if not argument:
                return {"text":"مدل را انتخاب کنید." if models else "هنوز مدلی تنظیم نشده است.",
                        "actions":[{"label":m,"command":"/model "+m} for m in models[:30]]}
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
            self._quota(job, "search", self.services.config.search_daily, self.services.config.search_global_daily)
            result = self.services.search(query)
            return "\n\n".join(f"{i}. {r['title']}\n{r['snippet']}\n{r['url']}" for i,r in enumerate(result["results"],1)) or "نتیجه‌ای پیدا نشد."
        if mode=="youtube" and not command.startswith("/"):
            command,argument="/youtube",text
        if command in {"/youtube", "/video"}:
            from bale_relay.adapters.youtube import YouTube, video_id
            yt = YouTube()
            if not argument:
                self._update_user(job,mode="youtube")
                return "عبارت جست‌وجوی یوتیوب را بفرستید."
            if command == "/video":
                info = yt.metadata(argument, active=lambda: self.queue.live(job))
                return {"text":f"{info['title']}\n{info['duration']:.0f} ثانیه | 360p",
                        "actions":[{"label":"دریافت ویدیو","command":"/download "+info["id"]}]}
            results = yt.search(argument, active=lambda: self.queue.live(job))
            return {"text":"\n\n".join(f"{i}. {r['title']}\n{r['duration']:.0f}s" for i,r in enumerate(results,1)) or "نتیجه‌ای پیدا نشد.",
                    "actions":[{"label":r["title"][:60],"command":"/video "+r["id"]} for r in results]}
        if command == "/download": return "فرمت فرمان: /download شناسهٔ معتبر ویدیو"
        if command.startswith("/"): return HELP
        if not model: return "ابتدا با /model یک مدل انتخاب کنید."
        self._quota(job, "ai", self.services.config.ai_daily, self.services.config.ai_global_daily)
        now = time.time()
        with db.session_scope() as s:
            messages = s.scalars(select(Message).where(Message.user_id == job.user_id, Message.generation == job.generation,
                            Message.created > now-7*86400).order_by(Message.id.desc()).limit(40)).all()
            history = [{"role": m.role, "content": m.content} for m in reversed(messages)]
        if len(text) > 8000: return "پیام بیش از حد طولانی است."
        history.append({"role": "user", "content": text})
        while len(history) > 1 and sum(len(m["content"]) for m in history) > 60000: history.pop(0)
        with db.session_scope() as s:
            row=s.scalar(select(Job).where(Job.id==job.id).with_for_update())
            if row.result.get("generation_state")=="in_flight": raise GenerationUnknown()
            if row.result.get("generation_state")=="complete": return row.result["reply"]
            row.result=dict(row.result,generation_state="in_flight")
        response = self.services.complete(model, history)
        # Lock the owner before persisting; /forget takes the same lock at receipt.
        with db.session_scope() as s:
            owner = s.scalar(select(User).where(User.id == job.user_id).with_for_update())
            self.check(job)
            if owner.generation != job.generation: raise Cancelled()
            row=s.get(Job,job.id)
            row.result=dict(row.result,generation_state="complete",reply=response or "پاسخ خالی بود.")
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
        self.queue.reserve_job(job,feature,[(f"{feature}:{day}:{job.user_id}",daily),(f"{feature}:{day}:global",total)])
