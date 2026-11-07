import json
import unittest
from tests import test_ingress as fixtures
from bale_relay.storage.models import Job

class MetricsTests(unittest.TestCase):
    setUp=fixtures.IngressTests.setUp
    def test_processing_metrics_have_no_private_payload(self):
        self.q.ingest(fixtures.incoming(text="private phrase should never leak"))
        job=self.q.claim()
        self.q.metric(job,"uploaded_bytes",100)
        self.q.metric(job,"downloaded_bytes",200)
        self.q.metric(job,"service_errors")
        self.q.finish(job,{"reply":"another private phrase"})
        report=self.q.statistics()
        self.assertEqual(report["attempts"],1)
        self.assertEqual(report["uploaded_bytes"],100)
        self.assertEqual(report["downloaded_bytes"],200)
        self.assertEqual(report["service_errors"],1)
        self.assertGreaterEqual(report["processing_seconds"],0)
        self.assertNotIn("private",json.dumps(report))
        self.assertNotIn("123",json.dumps(report))
    def test_cancelled_work_cannot_change_metrics(self):
        self.q.ingest(fixtures.incoming());job=self.q.claim()
        self.q.ingest(fixtures.incoming(2,text="/cancel"))
        self.q.metric(job,"uploaded_bytes",1000)
        self.assertEqual(self.q.statistics()["uploaded_bytes"],0)
    def test_reject_unknown_metric_names(self):
        self.q.ingest(fixtures.incoming());job=self.q.claim()
        with self.assertRaises(ValueError):self.q.metric(job,"user_message",1)
