"""Isolated downloader. Only canonical IDs, no config, cookies or plugins."""
import sys
from pathlib import Path
from bale_relay.adapters.youtube import video_id, validate_info, MAX_DOWNLOAD

class Quiet:
    def debug(self, *_): pass
    def info(self, *_): pass
    def warning(self, *_): pass
    def error(self, *_): pass

def main():
    from yt_dlp import YoutubeDL
    identifier = video_id(sys.argv[1])
    directory = Path(sys.argv[2]).resolve()
    counts = {}
    def progress(event):
        name = event.get("filename", "unknown")
        counts[name] = max(counts.get(name, 0), event.get("downloaded_bytes", 0))
        # Account for multiple separate tracks, including unknown-size media.
        if sum(counts.values()) > MAX_DOWNLOAD:
            raise RuntimeError("download_limit")
    options = {"quiet": True, "no_warnings": True, "logger": Quiet(), "noplaylist": True,
               "format": "bv[height<=360][ext=mp4][vcodec^=avc1]+ba[ext=m4a][acodec^=mp4a]/b[height<=360][ext=mp4][vcodec^=avc1][acodec^=mp4a]",
               "outtmpl": str(directory/"video.%(ext)s"), "merge_output_format": "mp4",
               "socket_timeout": 10, "retries": 1, "fragment_retries": 1,
               "concurrent_fragment_downloads": 1, "buffersize": 65536,
               "max_filesize": MAX_DOWNLOAD, "progress_hooks": [progress],
               "cachedir": False, "js_runtimes": {"deno": {}},
               "remote_components": set()}
    with YoutubeDL(options) as downloader:
        url = "https://www.youtube.com/watch?v="+identifier
        info = downloader.extract_info(url, download=False)
        validate_info(info)
        formats = info.get("requested_formats") or [info]
        known = sum(f.get("filesize") or 0 for f in formats)
        if known > MAX_DOWNLOAD: raise RuntimeError("download_limit")
        downloader.process_ie_result(info, download=True)

if __name__ == "__main__":
    try: main()
    except Exception: sys.exit(1)
