"""Constrained yt-dlp/ffmpeg subprocess adapter; no user shell or arbitrary URL input."""
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import json
import math
import re
import os
import signal
import subprocess
import sys
import time

from bale_relay.core.errors import ServiceError

ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
MAX_DOWNLOAD = 250_000_000
MAX_PART = 45_000_000
MAX_DURATION = 3600
MAX_PARTS = 10

class MediaPaused(Exception): pass
class MediaCancelled(Exception): pass

@dataclass(frozen=True)
class Part:
    path: Path
    start: float
    end: float


def video_id(value):
    if not isinstance(value, str): raise ServiceError("شناسهٔ ویدیو نامعتبر است.", 400)
    if ID.fullmatch(value): return value
    try:
        url = urlsplit(value)
        if url.scheme != "https" or url.username or url.password or url.port not in (None, 443): raise ValueError()
        host = (url.hostname or "").lower()
        if host == "youtu.be": candidate = url.path.strip("/")
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if url.path == "/watch": candidate = parse_qs(url.query).get("v", [""])[0]
            elif url.path.startswith(("/shorts/", "/embed/")): candidate = url.path.split("/")[2]
            else: candidate = ""
        else: candidate = ""
        if ID.fullmatch(candidate): return candidate
    except ValueError: pass
    raise ServiceError("فقط لینک HTTPS معتبر یوتیوب پذیرفته می‌شود.", 400)


def validate_info(info):
    if not isinstance(info, dict) or not ID.fullmatch(str(info.get("id", ""))):
        raise ServiceError("اطلاعات ویدیو نامعتبر است.")
    duration = info.get("duration")
    if (isinstance(duration, bool) or not isinstance(duration, (int, float)) or
            not math.isfinite(duration) or not 0 < duration <= MAX_DURATION):
        raise ServiceError("مدت ویدیو باید حداکثر ۶۰ دقیقه باشد.", 400)
    if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming", "post_live"}:
        raise ServiceError("پخش زنده پشتیبانی نمی‌شود.", 400)
    if info.get("has_drm") or info.get("availability") in {"private", "premium_only", "subscriber_only", "needs_auth"} or info.get("age_limit", 0) > 0:
        raise ServiceError("ویدیوی محدود یا نیازمند ورود پشتیبانی نمی‌شود.", 400)
    return {"id": info["id"], "title": str(info.get("title", ""))[:300], "duration": float(duration), "quality": "360p"}

class YouTube:
    def __init__(self, clock=time.monotonic): self.clock = clock
    def run(self, arguments, *, deadline, active=lambda: True, cwd=None):
        # A file-backed output avoids pipe deadlock; monitor output size and child lifetime.
        import tempfile
        with tempfile.TemporaryFile() as output:
            try:
                child = subprocess.Popen(arguments, cwd=cwd, stdout=output, stderr=subprocess.DEVNULL,
                                         stdin=subprocess.DEVNULL, shell=False, start_new_session=os.name != "nt")
            except OSError: raise ServiceError("ابزار پردازش ویدیو نصب یا قابل اجرا نیست.", 503) from None
            try:
                while child.poll() is None:
                    if not active(): raise MediaCancelled()
                    if self.clock() >= deadline: raise MediaPaused()
                    if output.tell() > 5_000_000: raise ServiceError("پاسخ دانلودر بیش از حد بزرگ است.")
                    time.sleep(0.1)
                if child.returncode != 0: raise ServiceError("دریافت یا پردازش ویدیو ممکن نشد.", 502)
                output.seek(0)
                raw = output.read(5_000_001)
                if len(raw) > 5_000_000: raise ServiceError("پاسخ دانلودر بیش از حد بزرگ است.")
                return raw.decode("utf-8")
            finally:
                if child.poll() is None:
                    if os.name != "nt":
                        try: os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                    else: child.kill()
                child.wait()
    def metadata(self, identifier, *, active=lambda: True):
        vid = video_id(identifier)
        raw = self.run([sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist", "--skip-download", "--dump-single-json", "--no-warnings", "--socket-timeout", "10", "--retries", "1", "--", "https://www.youtube.com/watch?v="+vid], deadline=self.clock()+45, active=active)
        try: info = json.loads(raw)
        except ValueError: raise ServiceError("اطلاعات ویدیو نامعتبر است.") from None
        return validate_info(info)
    def search(self, query, *, active=lambda: True):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 300 or any(ord(c)<32 for c in query):
            raise ServiceError("عبارت جست‌وجو نامعتبر است.", 400)
        raw = self.run([sys.executable, "-m", "yt_dlp", "--ignore-config", "--flat-playlist", "--skip-download", "--dump-single-json", "--no-warnings", "--socket-timeout", "10", "--retries", "1", "--", "ytsearch5:"+query.strip()], deadline=self.clock()+45, active=active)
        try:
            info = json.loads(raw)
            results = []
            for entry in (info.get("entries") or [])[:5]:
                try: results.append(validate_info(entry))
                except ServiceError: continue
            return results
        except (ValueError, TypeError, AttributeError): raise ServiceError("نتایج جست‌وجوی ویدیو نامعتبر است.") from None
    def download(self, identifier, directory, *, deadline, active=lambda: True):
        vid = video_id(identifier)
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        self.run([sys.executable, "-m", "bale_relay.adapters.youtube_child", vid, str(directory)], deadline=deadline, active=active)
        target = directory/"video.mp4"
        if not target.is_file() or not 0 < target.stat().st_size <= MAX_DOWNLOAD:
            raise ServiceError("حجم دانلود از سقف مجاز عبور کرد یا فایل نامعتبر است.", 400)
        return target
    def duration(self, path, *, deadline, active):
        raw = self.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], deadline=deadline, active=active)
        try:
            duration = float(json.loads(raw)["format"]["duration"])
            if not math.isfinite(duration) or duration <= 0: raise ValueError()
            return duration
        except (KeyError, TypeError, ValueError): raise ServiceError("مدت فایل قابل خواندن نیست.") from None
    def split(self, source, directory, *, deadline, active=lambda: True):
        source, directory = Path(source).resolve(), Path(directory).resolve()
        duration = self.duration(source, deadline=deadline, active=active)
        if duration > MAX_DURATION+1: raise ServiceError("ویدیو طولانی‌تر از سقف مجاز است.", 400)
        pending = [(0.0, duration)]
        keyframes = None
        parts = []
        attempts = 0
        while pending:
            start, end = pending.pop(0)
            attempts += 1
            if attempts > 40 or len(parts)+len(pending)+1 > MAX_PARTS:
                raise ServiceError("تعداد قطعه‌ها از سقف مجاز بیشتر است.", 400)
            target = directory/f"segment-{attempts:03d}.mp4"
            self.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source), "-ss", str(start),
                      "-t", str(end-start), "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", str(target)], deadline=deadline, active=active)
            if not target.is_file() or target.stat().st_size == 0: raise ServiceError("تقسیم ویدیو ناموفق بود.")
            if target.stat().st_size <= MAX_PART:
                parts.append(Part(target, start, end))
            else:
                target.unlink()
                if keyframes is None:
                    raw=self.run(["ffprobe","-v","error","-select_streams","v:0","-skip_frame","nokey",
                                  "-show_entries","frame=best_effort_timestamp_time","-of","json",str(source)],
                                 deadline=deadline,active=active)
                    try:
                        keyframes=[float(frame["best_effort_timestamp_time"]) for frame in json.loads(raw)["frames"]]
                    except (KeyError,ValueError,TypeError): raise ServiceError("فریم‌های مرزی قابل خواندن نیستند.") from None
                candidates=[t for t in keyframes if start+0.01<t<end-0.01]
                if not candidates: raise ServiceError("تقسیم در فریم کلیدی در سقف حجم ممکن نیست.",400)
                midpoint=min(candidates,key=lambda t:abs(t-(start+end)/2))
                pending[0:0] = [(start,midpoint),(midpoint,end)]
        return parts
