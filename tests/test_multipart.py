import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler,HTTPServer
from bale_relay.adapters.multipart import MultipartStream
from bale_relay.adapters.bale import Bale
from bale_relay.core.http_client import HttpClient

class MultipartTests(unittest.TestCase):
    def test_exact_content_length_and_bounded_chunks(self):
        stream=MultipartStream({"chat_id":123,"caption":"سلام"},{"video":("video.mp4",io.BytesIO(b"x"*200000),"video/mp4")})
        chunks=list(stream)
        self.assertEqual(sum(map(len,chunks)),len(stream))
        self.assertLessEqual(max(map(len,chunks)),65536)
        body=b"".join(chunks)
        self.assertIn("سلام".encode(),body)
        self.assertIn(b'filename="video.mp4"',body)
    def test_cancellation_is_checked(self):
        def cancelled():raise RuntimeError("cancelled")
        body=MultipartStream({}, {"video":("video.mp4",io.BytesIO(b"x"),"video/mp4")},cancelled)
        with self.assertRaisesRegex(RuntimeError,"cancelled"):list(body)
    def test_real_requests_streams_multipart_to_local_server(self):
        received={}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                received["body"]=self.rfile.read(int(self.headers["Content-Length"]))
                received["type"]=self.headers["Content-Type"]
                payload=json.dumps({"ok":True,"result":{"video":{"file_id":"test"}}}).encode()
                self.send_response(200);self.send_header("Content-Length",str(len(payload)));self.end_headers();self.wfile.write(payload)
        server=HTTPServer(("127.0.0.1",0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            bale=Bale("fake-test-token",HttpClient(3,10000,"test"))
            bale.base=f"http://127.0.0.1:{server.server_port}"
            result=bale.call("sendVideo",{"chat_id":123},{"video":("video.mp4",io.BytesIO(b"x"*100000),"video/mp4")})
            self.assertEqual(result["video"]["file_id"],"test")
            self.assertEqual(received["body"].count(b"x"*100000),1)
            self.assertTrue(received["type"].startswith("multipart/form-data; boundary="))
        finally:server.shutdown();server.server_close();thread.join(timeout=3)
