import tempfile
import time
from pathlib import Path
from sqlalchemy import select, update
from bale_relay.adapters.youtube import YouTube, MediaPaused, MediaCancelled
from bale_relay.adapters.bale import AmbiguousDelivery
from bale_relay.storage.models import Job, Update
from bale_relay.core.errors import ServiceError

class MediaWorker:
    def __init__(self, queue, bale, youtube=None, cache=None):
        self.queue, self.bale = queue, bale
        self.youtube = youtube or YouTube()
        self.cache = cache
    def save(self, job, result):
        with self.queue.db.session_scope() as s:
            changed = s.execute(update(Job).where(Job.id == job.id, Job.lease == job.lease, Job.state == "running").values(result=result)).rowcount
            if not changed: raise MediaCancelled()
        job.result = result
    def once(self):
        job = self.queue.claim("media", ttl=600)
        if job is None: return False
        result = dict(job.result)
        active = lambda: self.queue.live(job)
        deadline = time.monotonic()+480
        try:
            with self.queue.db.session_scope() as s: payload = s.get(Update, job.update_id).payload
            identifier = payload.get("bot_command", payload.get("message",{}).get("text","")).split(maxsplit=1)[1].strip()
            from bale_relay.adapters.youtube import video_id
            identifier = video_id(identifier)
            cached = self.cache.get(identifier) if self.cache else None
            if cached and not result.get("parts"):
                result = {"video": cached["video"], "parts": [dict(part, state="pending") for part in cached["parts"]]}
                self.save(job,result)
            if result.get("parts") and all(part.get("file_id") for part in result["parts"]):
                self.send_cached(job,result,active,deadline)
                return True
            info = self.youtube.metadata(identifier, active=active)
            result.setdefault("video", info)
            result.setdefault("parts", [])
            self.save(job,result)
            if any(part.get("state") in {"sending", "unknown"} for part in result["parts"]):
                self.queue.finish(job, result, "unknown"); return True
            with tempfile.TemporaryDirectory(prefix="bale-media-") as directory:
                source = self.youtube.download(identifier, directory, deadline=deadline, active=active)
                if isinstance(source,(str,Path)) and Path(source).is_file(): self.queue.metric(job,"downloaded_bytes",Path(source).stat().st_size)
                parts = self.youtube.split(source, directory, deadline=deadline, active=active)
                if result["parts"] and len(result["parts"]) != len(parts):
                    raise ServiceError("تقسیم فایل نسبت به تلاش قبل تغییر کرده است.")
                if not result["parts"]:
                    result["parts"] = [{"state": "pending", "start": part.start, "end": part.end} for part in parts]
                    self.save(job, result)
                for index, part in enumerate(parts):
                    if not active(): raise MediaCancelled()
                    if time.monotonic() >= deadline: raise MediaPaused()
                    row = result["parts"][index]
                    if row["state"] == "sent": continue
                    if abs(row["start"]-part.start)>0.1 or abs(row["end"]-part.end)>0.1:
                        raise ServiceError("مرزبندی قطعه‌ها تغییر کرده است.")
                    row["state"] = "sending"
                    self.save(job, result)
                    caption = f"{info['title']}\n{index+1}/{len(parts)} | {part.start:.0f}–{part.end:.0f}s"
                    try:
                        with part.path.open("rb") as video:
                            sent = self.bale.call("sendVideo", {"chat_id": job.user_id, "caption": caption}, files={"video": ("video.mp4",video,"video/mp4")},deadline=deadline,active=active)
                    except AmbiguousDelivery:
                        row["state"] = "unknown"; self.save(job, result)
                        self.queue.finish(job, result, "unknown"); return True
                    row["state"] = "sent"
                    row["bytes"] = part.path.stat().st_size
                    self.queue.metric(job,"uploaded_bytes",row["bytes"])
                    row["file_id"] = sent.get("video", {}).get("file_id") if isinstance(sent,dict) else None
                    self.save(job,result)
            if self.cache: self.cache.put(identifier,result)
            self.queue.finish(job, result)
        except MediaPaused: self.queue.finish(job, result, "paused")
        except MediaCancelled: self.queue.finish(job, {}, "cancelled")
        except Exception:
            self.queue.metric(job,"service_errors")
            self.queue.finish(job, result, "failed")
        return True
    def send_cached(self, job, result, active, deadline):
        for index, part in enumerate(result["parts"]):
            if not active(): raise MediaCancelled()
            if time.monotonic() >= deadline: raise MediaPaused()
            if part["state"] == "sent": continue
            if part["state"] in {"sending", "unknown"}:
                self.queue.finish(job,result,"unknown"); return
            part["state"] = "sending"
            self.save(job,result)
            try:
                self.bale.call("sendVideo", {"chat_id": job.user_id, "video": part["file_id"],
                    "caption": f"{result['video']['title']} | {index+1}/{len(result['parts'])}"},deadline=deadline)
            except AmbiguousDelivery:
                part["state"] = "unknown"; self.save(job,result)
                self.queue.finish(job,result,"unknown"); return
            part["state"] = "sent"
            self.save(job,result)
        self.queue.finish(job,result)
    def run(self):
        while True:
            if not self.once(): time.sleep(2)
