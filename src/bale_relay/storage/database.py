from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

class Database:
    def __init__(self, url):
        parsed = make_url(url)
        if parsed.drivername.startswith("sqlite") and parsed.database not in (None, ":memory:"):
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, pool_pre_ping=True)
        if parsed.drivername.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def setup(conn, _):
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA busy_timeout=10000")
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
    @contextmanager
    def session_scope(self):
        with self.sessions.begin() as session:
            yield session
