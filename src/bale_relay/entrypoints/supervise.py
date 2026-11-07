"""One Render service, separately supervised HTTP, text and media processes."""
import os
import signal
import subprocess
import sys
import time


def main():
    from bale_relay.core.config import Config
    cfg = Config.from_env()
    if cfg.receiver_mode != "webhook": raise RuntimeError("Render supervisor requires webhook mode")
    # Do not print exceptions: DSNs and request URLs contain secrets.
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    port = int(os.getenv("PORT", "10000"))
    commands = [
        [sys.executable, "-m", "gunicorn", "bale_relay.entrypoints.wsgi:app", "--bind", f"0.0.0.0:{port}", "--workers", "1", "--threads", "2", "--error-logfile", "/dev/null"],
        [sys.executable, "-m", "bale_relay.entrypoints.cli", "worker"],
        [sys.executable, "-m", "bale_relay.entrypoints.cli", "media-worker"],
    ]
    children = []
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        children = [subprocess.Popen(command) for command in commands]
        while not stopped:
            if any(child.poll() is not None for child in children): break
            time.sleep(0.5)
    finally:
        for child in children:
            if child.poll() is None: child.terminate()
        for child in children:
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
    return 0 if stopped else 1

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception:
        print("Startup failed; check configuration, database and installed tools.", file=sys.stderr)
        sys.exit(1)
