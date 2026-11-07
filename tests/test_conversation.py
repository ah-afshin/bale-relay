import unittest
from unittest.mock import Mock
from sqlalchemy import select
from tests import test_ingress as fixtures
from bale_relay.core.config import Config
from bale_relay.core.errors import ServiceError
from bale_relay.storage.models import Job, User, Message, Usage
from bale_relay.storage.cache import DatabaseCache
from bale_relay.entrypoints.worker import Worker

class ConversationTests(unittest.TestCase):
    setUp=fixtures.IngressTests.setUp
    def worker(self):
        services=Mock(); services.config=Config(); services.complete.return_value="پاسخ"; services.models.return_value=["groq/test"]
        bale=Mock(); bale.send_text.return_value={"message_id":1}
        return Worker(self.q,services,bale)
    def callback(self,number,target,index=0,uid=123):
        return {"update_id":number,"callback_query":{"id":"callback","from":{"id":uid},"data":f"{target}:{index}","message":{"chat":{"id":uid,"type":"private"}}}}
    def test_start_menu_callback_changes_mode(self):
        self.q.ingest(fixtures.incoming(text="/start")); worker=self.worker(); worker.once()
        with self.db.session_scope() as s: target=s.scalar(select(Job)).id
        self.assertEqual(self.q.ingest(self.callback(2,target,2)),"accepted")
        worker.once()
        with self.db.session_scope() as s: self.assertEqual(s.get(User,123).mode,"search")
    def test_foreign_and_old_callbacks_denied(self):
        self.q.allow(456); self.q.ingest(fixtures.incoming(text="/start")); worker=self.worker(); worker.once()
        with self.db.session_scope() as s: target=s.scalar(select(Job)).id
        self.assertEqual(self.q.ingest(self.callback(2,target,uid=456)),"denied")
        self.q.ingest(fixtures.incoming(3,text="/new"))
        self.assertEqual(self.q.ingest(self.callback(4,target)),"denied")
    def test_forged_internal_command_ignored(self):
        payload=fixtures.incoming(text="hello"); payload["bot_command"]="/forget"
        self.q.ingest(payload); worker=self.worker(); worker.once()
        with self.db.session_scope() as s: self.assertEqual(s.get(User,123).generation,0)
    def set_model(self):
        with self.db.session_scope() as s: s.get(User,123).model="groq/test"
    def test_ai_reply_and_history_persisted(self):
        self.set_model(); self.q.ingest(fixtures.incoming()); worker=self.worker(); worker.once()
        worker.services.complete.assert_called_once()
        with self.db.session_scope() as s:
            self.assertEqual(len(s.scalars(select(Message)).all()),2)
            self.assertEqual(s.scalar(select(Job)).result["generation_state"],"complete")
    def test_generation_in_flight_not_repeated(self):
        self.set_model(); self.q.ingest(fixtures.incoming())
        with self.db.session_scope() as s: s.scalar(select(Job)).result={"generation_state":"in_flight"}
        worker=self.worker(); worker.once(); worker.services.complete.assert_not_called()
        with self.db.session_scope() as s: self.assertEqual(s.scalar(select(Job)).state,"unknown")
    def test_checkpoint_reply_not_regenerated(self):
        self.set_model(); self.q.ingest(fixtures.incoming())
        with self.db.session_scope() as s: s.scalar(select(Job)).result={"generation_state":"complete","reply":"saved"}
        worker=self.worker(); worker.once(); worker.services.complete.assert_not_called()
        self.assertEqual(worker.bale.send_text.call_args.args[1],"saved")
    def test_quota_reserved_once_per_job(self):
        self.q.ingest(fixtures.incoming()); job=self.q.claim()
        for _ in range(2): self.q.reserve_job(job,"ai",[("user",1),("global",2)])
        with self.db.session_scope() as s:
            self.assertEqual(s.get(Usage,"user").used,1); self.assertEqual(s.get(Usage,"global").used,1)
    def test_quota_rollback_is_atomic(self):
        self.q.reserve("global",1)
        self.q.ingest(fixtures.incoming()); job=self.q.claim()
        with self.assertRaises(ServiceError): self.q.reserve_job(job,"ai",[("user",1),("global",1)])
        with self.db.session_scope() as s: self.assertIsNone(s.get(Usage,"user"))
    def test_shared_cache_survives_new_instance(self):
        first=DatabaseCache(self.db,"key-a"); first.set("query",{"results":["public"]})
        self.assertEqual(DatabaseCache(self.db,"key-a").get("query"),{"results":["public"]})
        self.assertIsNone(DatabaseCache(self.db,"key-b").get("query"))
    def test_forget_during_generation_does_not_restore_history(self):
        self.set_model(); self.q.ingest(fixtures.incoming()); worker=self.worker()
        def generation(*_):
            self.q.ingest(fixtures.incoming(2,text="/forget")); return "secret"
        worker.services.complete.side_effect=generation
        worker.once()
        with self.db.session_scope() as s:
            self.assertIsNone(s.scalar(select(Message)))
            self.assertEqual(s.scalar(select(Job).order_by(Job.id)).state,"cancelled")
        worker.bale.send_text.assert_not_called()
