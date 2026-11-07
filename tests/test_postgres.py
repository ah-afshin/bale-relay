"""Runs only against an explicitly supplied disposable PostgreSQL test database."""
import os
import uuid
import unittest
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from tests.test_ingress import incoming
from bale_relay.storage.database import Database
from bale_relay.storage.models import Base, Usage
from bale_relay.storage.queue import Queue
from bale_relay.core.errors import ServiceError

@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"),"TEST_POSTGRES_URL is required")
class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.db=Database(os.environ["TEST_POSTGRES_URL"])
        self.schema="test_"+uuid.uuid4().hex
        self.engine=self.db.engine
        with self.engine.begin() as c:c.execute(text('CREATE SCHEMA '+self.schema))
        self.db.engine=self.engine.execution_options(schema_translate_map={None:self.schema})
        self.db.sessions.configure(bind=self.db.engine)
        Base.metadata.create_all(self.db.engine)
        self.q=Queue(self.db);self.q.allow(123)
    def tearDown(self):
        with self.engine.begin() as c:c.execute(text('DROP SCHEMA '+self.schema+' CASCADE'))
        self.engine.dispose()
    def test_concurrent_duplicate_ingress_creates_one_job(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.q.ingest(incoming()),range(16)))
        self.assertEqual(results.count("accepted"),1)
        self.assertEqual(results.count("duplicate"),15)
    def test_concurrent_quota_never_exceeds_limit(self):
        def reserve(_):
            try:self.q.reserve("global",5);return True
            except ServiceError:return False
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(reserve,range(20)))
        self.assertEqual(sum(results),5)
        with self.db.session_scope() as s:self.assertEqual(s.get(Usage,"global").used,5)
    def test_concurrent_claims_only_one_user_message(self):
        for number in range(1,5):self.q.ingest(incoming(number))
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.q.claim(),range(4)))
        self.assertEqual(sum(j is not None for j in results),1)
