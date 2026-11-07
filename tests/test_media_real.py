"""Actual ffmpeg tests. Explicit skips mean the deployment gate remains unverified."""
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from bale_relay.adapters.youtube import YouTube

@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"ffmpeg and ffprobe are required")
class RealMediaTests(unittest.TestCase):
    def test_lossless_split_actual_file_caps_and_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"video.mp4"
            subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-f","lavfi","-i","testsrc2=size=640x360:rate=25",
                "-f","lavfi","-i","sine=frequency=500:sample_rate=48000","-t","12","-c:v","libx264","-preset","ultrafast",
                "-g","75","-keyint_min","75","-sc_threshold","0","-b:v","2M","-c:a","aac",str(source)],
                check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=60)
            yt=YouTube(); deadline=time.monotonic()+60
            cap=max(10000,source.stat().st_size//3)
            with patch("bale_relay.adapters.youtube.MAX_PART",cap):
                parts=yt.split(source,directory,deadline=deadline)
            self.assertGreater(len(parts),1)
            self.assertLessEqual(len(parts),10)
            for part in parts:
                self.assertLessEqual(part.path.stat().st_size,cap)
                actual=yt.duration(part.path,deadline=deadline,active=lambda:True)
                self.assertLess(abs(actual-(part.end-part.start)),0.2)
            self.assertAlmostEqual(parts[0].start,0)
            for previous,current in zip(parts,parts[1:]): self.assertAlmostEqual(previous.end,current.start)
            self.assertAlmostEqual(parts[-1].end,12,delta=0.2)
