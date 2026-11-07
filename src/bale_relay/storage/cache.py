import hashlib
import time
from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from bale_relay.storage.models import CacheEntry

class DatabaseCache:
    def __init__(self, database, namespace="", default_ttl=300):
        self.db,self.namespace,self.default_ttl=database,namespace,default_ttl
    def key(self,key): return hashlib.sha256((self.namespace+":"+key).encode()).hexdigest()
    def get(self,key,default=None):
        with self.db.session_scope() as s:
            entry=s.get(CacheEntry,self.key(key))
            return entry.value if entry and entry.expires>time.time() else default
    def set(self,key,value,ttl=None):
        ins=sqlite_insert if self.db.engine.dialect.name=="sqlite" else pg_insert
        with self.db.session_scope() as s:
            s.execute(delete(CacheEntry).where(CacheEntry.expires<time.time()))
            stmt=ins(CacheEntry).values(key=self.key(key),value=value,expires=time.time()+(self.default_ttl if ttl is None else ttl))
            s.execute(stmt.on_conflict_do_update(index_elements=[CacheEntry.key],set_={"value":stmt.excluded.value,"expires":stmt.excluded.expires}))
    def get_or_set(self,key,factory,ttl=None):
        missing=object(); value=self.get(key,missing)
        if value is missing:
            value=factory(); self.set(key,value,ttl)
        return value
