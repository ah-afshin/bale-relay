import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import select, func
from sqlalchemy.exc import OperationalError
from bale_relay.core.config import Config
from bale_relay.core.errors import ServiceError
from bale_relay.storage.database import Database
from bale_relay.storage.models import Base, Job, Message, Update
from bale_relay.storage.queue import Queue
from bale_relay.entrypoints.web import create_app
from bale_relay.bot.formatting import chunks


def incoming(number=1, uid=123, text="hello"):
    return {"update_id": number, "message": {"from": {"id": uid}, "chat": {"id": uid, "type": "private"}, "text": text}}

class IngressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Database("sqlite:///" + str(Path(self.temp.name)/"test.db"))
        self.addCleanup(self.db.engine.dispose)
        Base.metadata.create_all(self.db.engine)
        self.q = Queue(self.db)
        self.q.allow(123)
        self.cfg = Config(webhook_secret="s"*40)
        self.client = create_app(self.cfg, self.db).test_client()
    def post(self, data): return self.client.post("/webhooks/bale/"+"s"*40, json=data)
    def test_secret_and_unknown_routes(self):
        self.assertEqual(self.client.post("/webhooks/bale/wrong", json=incoming()).status_code, 404)
        self.assertEqual(self.client.get("/anything").status_code, 404)
    def test_default_deny(self):
        self.assertEqual(self.post(incoming(uid=456)).status_code, 403)
        data = incoming(); data["message"]["chat"]["type"] = "group"
        self.assertEqual(self.post(data).status_code, 403)
    def test_sender_must_own_chat(self):
        data = incoming(); data["message"]["chat"]["id"] = 456
        self.assertEqual(self.post(data).status_code, 403)
    def test_duplicate_creates_one_job(self):
        self.assertEqual(self.post(incoming()).status_code, 200)
        self.assertEqual(self.post(incoming()).json["status"], "duplicate")
        with self.db.session_scope() as s: self.assertEqual(s.scalar(select(func.count(Job.id))), 1)
    def test_commit_failure_not_acknowledged(self):
        with patch.object(Queue, "ingest", side_effect=OperationalError("safe", {}, Exception())):
            self.assertEqual(self.post(incoming()).status_code, 503)
    def test_invalid_payload(self):
        for data in ([], {}, {"update_id": True}): self.assertEqual(self.post(data).status_code, 400)
    def test_polling_disables_webhook(self):
        client = create_app(replace(self.cfg, receiver_mode="polling"), self.db).test_client()
        self.assertEqual(client.post("/webhooks/bale/"+"s"*40, json=incoming()).status_code, 404)
    def test_lease_orders_user_messages(self):
        self.q.ingest(incoming()); self.q.ingest(incoming(2))
        job = self.q.claim(); self.assertTrue(self.q.live(job))
        self.assertIsNone(self.q.claim())
        self.q.finish(job, {})
        self.assertEqual(self.q.claim().update_id, 2)
    def test_cancel_invalidates_running_work(self):
        self.q.ingest(incoming()); job = self.q.claim()
        self.q.ingest(incoming(2, text="/cancel"))
        self.assertFalse(self.q.live(job))
        self.assertFalse(self.q.finish(job, {"stale": True}))
    def test_forget_removes_contents(self):
        self.q.ingest(incoming()); job = self.q.claim()
        with self.db.session_scope() as s: s.add(Message(user_id=123, generation=0, role="user", content="secret", created=1))
        self.q.ingest(incoming(2, text="/forget"))
        self.assertFalse(self.q.live(job))
        with self.db.session_scope() as s:
            self.assertEqual(s.scalar(select(func.count(Message.id))), 0)
            self.assertEqual(s.get(Update, 1).payload, {})
    def test_quota_fail_closed(self):
        self.q.reserve("test", 1)
        with self.assertRaises(ServiceError): self.q.reserve("test", 1)
    def test_block_cancels_work(self):
        self.q.ingest(incoming()); job = self.q.claim(); self.q.allow(123, False)
        self.assertFalse(self.q.live(job))
    def test_production_requires_persistent_database(self):
        with self.assertRaises(ValueError): replace(self.cfg, env="production").validate()
    def test_utf16_chunk_limit(self):
        parts = chunks("😀سلام" * 3000)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p.encode("utf-16-le"))//2 <= 3500 for p in parts))

if __name__ == "__main__": unittest.main()
