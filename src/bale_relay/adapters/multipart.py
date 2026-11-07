"""Bounded-memory multipart upload body for requests, with cancellation checkpoints."""
import re
import secrets
import time

class MultipartStream:
    def __init__(self,fields,files,check=lambda:None):
        self.boundary="bale-"+secrets.token_hex(16)
        self.check=check
        self.sections=[]
        for name,value in (fields or {}).items():
            self._safe(name)
            body=str(value).encode("utf-8")
            self.sections.append((f'--{self.boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),body))
        for name,(filename,file,mime) in files.items():
            self._safe(name);self._safe(filename)
            if mime not in {"video/mp4","application/octet-stream"}:raise ValueError("Unsupported MIME type")
            header=f'--{self.boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
            self.sections.append((header,file))
        self.end=f'--{self.boundary}--\r\n'.encode()
        self.length=len(self.end)
        for header,body in self.sections:
            if isinstance(body,bytes):size=len(body)
            else:
                position=body.tell();body.seek(0,2);size=body.tell()-position;body.seek(position)
            self.length+=len(header)+size+2
    @staticmethod
    def _safe(value):
        if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9_.-]+",value): raise ValueError("Invalid multipart field")
    def __len__(self):return self.length
    def __iter__(self):
        for header,body in self.sections:
            self.check();yield header
            if isinstance(body,bytes):yield body
            else:
                while True:
                    self.check()
                    chunk=body.read(65536)
                    if not chunk:break
                    yield chunk
            yield b"\r\n"
        self.check();yield self.end
