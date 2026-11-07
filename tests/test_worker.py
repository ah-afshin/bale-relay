from types import SimpleNamespace
from unittest.mock import Mock
from sqlalchemy import select
import unittest
from tests import test_ingress as fixtures
incoming = fixtures.incoming
from bale_relay.entrypoints.worker import Worker
from bale_relay.adapters.bale import AmbiguousDelivery
from bale_relay.storage.models import Delivery, Job

class WorkerTests(unittest.TestCase):
    setUp = fixtures.IngressTests.setUp
    def worker(self):
        services = SimpleNamespace(config=SimpleNamespace(ai_daily=20, search_daily=5))
        return Worker(self.q, services, Mock())
    def test_start_sends_once(self):
        self.q.ingest(incoming(text="/start"))
        worker = self.worker()
        worker.bale.send_text.return_value = {"message_id": 1}
        self.assertTrue(worker.once())
        self.assertFalse(worker.once())
        worker.bale.send_text.assert_called_once()
        with self.db.session_scope() as s:
            self.assertEqual(s.scalar(select(Job)).state, "done")
            self.assertEqual(s.scalar(select(Delivery)).state, "sent")
    def test_ambiguous_send_not_repeated(self):
        self.q.ingest(incoming(text="/start"))
        worker = self.worker()
        worker.bale.send_text.side_effect = AmbiguousDelivery("unknown")
        worker.once(); worker.once()
        worker.bale.send_text.assert_called_once()
        with self.db.session_scope() as s:
            self.assertEqual(s.scalar(select(Job)).state, "unknown")
    def test_crashed_send_not_repeated(self):
        self.q.ingest(incoming(text="/start"))
        job = self.q.claim()
        with self.db.session_scope() as s:
            s.add(Delivery(job_id=job.id, ordinal=0, text="hello", state="sending"))
            s.get(Job, job.id).lease_until = 0
        worker = self.worker(); worker.once()
        worker.bale.send_text.assert_not_called()
        with self.db.session_scope() as s: self.assertEqual(s.get(Job, job.id).state, "unknown")
    def test_forget_scrubs_delivery_text(self):
        self.q.ingest(incoming(text="/start"))
        worker = self.worker(); worker.bale.send_text.return_value = {"message_id": 1}; worker.once()
        self.q.ingest(incoming(2, text="/forget"))
        with self.db.session_scope() as s: self.assertEqual(s.scalar(select(Delivery)).text, "")
