import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import unittest
from bale_relay.adapters.youtube import video_id, validate_info, YouTube, Part, MediaPaused
from bale_relay.core.errors import ServiceError
from bale_relay.entrypoints.media_worker import MediaWorker
from bale_relay.storage.models import Job
from sqlalchemy import select
from tests import test_ingress as fixtures

VID = "abcdefghijk"

def info(): return {"id": VID, "title": "Test", "duration": 60}

class YoutubeTests(unittest.TestCase):
    def test_only_canonical_youtube_urls(self):
        for value in (VID, "https://youtu.be/"+VID, "https://www.youtube.com/watch?v="+VID, "https://youtube.com/shorts/"+VID):
            self.assertEqual(video_id(value),VID)
        for value in ("https://youtube.com.attacker.test/watch?v="+VID, "file:///secret", "http://youtu.be/"+VID, "https://user:pass@youtu.be/"+VID, "https://youtu.be:444/"+VID, "--exec evil", "https://127.0.0.1/"+VID):
            with self.assertRaises(ServiceError): video_id(value)
    def test_reject_restricted_and_invalid_metadata(self):
        for extra in ({"duration": 3601},{"duration": float("nan")},{"duration": None},{"is_live": True},{"has_drm": True},{"availability": "private"},{"age_limit": 18}):
            with self.assertRaises(ServiceError): validate_info(info()|extra)
    def test_search_is_not_shell_or_unbounded(self):
        yt=YouTube(); yt.run=Mock(return_value=json.dumps({"entries": [info()]}))
        self.assertEqual(yt.search("test")[0]["id"],VID)
        command=yt.run.call_args.args[0]
        self.assertEqual(command[-2:], ["--", "ytsearch5:test"])
        with self.assertRaises(ServiceError): yt.search("a"*301)
    def test_split_rechecks_actual_bytes(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            yt=YouTube(); yt.duration=Mock(return_value=60)
            def run(args, **kwargs):
                if args[0]=="ffprobe": return json.dumps({"frames":[{"best_effort_timestamp_time":"30"}]})
                target=Path(args[-1]); target.write_bytes(b"x"*(20 if "segment-001" in target.name else 5))
            yt.run=run
            with patch("bale_relay.adapters.youtube.MAX_PART",10):
                parts=yt.split(Path(directory)/"video.mp4", directory, deadline=999999999)
            self.assertEqual([(p.start,p.end) for p in parts], [(0,30),(30,60)])
            self.assertTrue(all(p.path.stat().st_size<=10 for p in parts))

class MediaTests(unittest.TestCase):
    setUp=fixtures.IngressTests.setUp
    def worker(self):
        self.q.ingest(fixtures.incoming(text="/download "+VID))
        yt=Mock(); yt.metadata.return_value=info()
        def split(source, directory, **kwargs):
            path=Path(directory)/"part.mp4"; path.write_bytes(b"test"); return [Part(path,0,60)]
        yt.split.side_effect=split
        bale=Mock(); bale.call.return_value={"video": {"file_id":"cached"}}
        return MediaWorker(self.q,bale,yt)
    def test_media_uses_separate_lane(self):
        worker=self.worker()
        self.assertIsNone(self.q.claim("text"))
        worker.once()
        with self.db.session_scope() as s:
            job=s.scalar(select(Job)); self.assertEqual(job.state,"done")
            self.assertEqual(job.result["parts"][0]["file_id"],"cached")
        worker.bale.call.assert_called_once()
    def test_pause_is_persisted(self):
        worker=self.worker(); worker.youtube.download.side_effect=MediaPaused()
        worker.once()
        with self.db.session_scope() as s: self.assertEqual(s.scalar(select(Job)).state,"paused")
    def test_unknown_send_not_repeated(self):
        from bale_relay.adapters.bale import AmbiguousDelivery
        worker=self.worker(); worker.bale.call.side_effect=AmbiguousDelivery("unknown")
        worker.once(); worker.once()
        worker.bale.call.assert_called_once()
        with self.db.session_scope() as s: self.assertEqual(s.scalar(select(Job)).state,"unknown")
