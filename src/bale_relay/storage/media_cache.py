import hashlib
import time
from bale_relay.storage.models import MediaCache

class FileCache:
    def __init__(self, database, token):
        self.db = database
        self.namespace = hashlib.sha256(token.encode()).hexdigest()[:32]
    def key(self, identifier): return self.namespace+":"+identifier+":360p-v1"
    def get(self, identifier):
        with self.db.session_scope() as s:
            row = s.get(MediaCache,self.key(identifier))
            return row.value if row and row.created > time.time()-7*86400 else None
    def put(self, identifier, value):
        parts = value.get("parts", [])
        if not parts or not all(p.get("state")=="sent" and p.get("file_id") for p in parts): return
        with self.db.session_scope() as s:
            row = s.get(MediaCache,self.key(identifier))
            if row is None: s.add(MediaCache(key=self.key(identifier),value=value,created=time.time()))
            else: row.value=value; row.created=time.time()
