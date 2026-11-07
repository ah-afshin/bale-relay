import time
from unittest.mock import Mock, patch
import unittest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from tests import test_ingress as fixtures
from bale_relay.storage.models import Receiver, Update, Job, Message, Delivery
from bale_relay.storage.media_cache import FileCache
from bale_relay.entrypoints.polling import Poller
from bale_relay.entrypoints.media_worker import MediaWorker
from bale_relay.core.errors import ServiceError

VID="abcdefghijk"

class RecoveryTests(unittest.TestCase):
    setUp=fixtures.IngressTests.setUp
    def poller(self):
        bale=Mock(); bale.call.return_value={"url":""}
        poller=Poller(self.q,bale); poller.acquire()
        return poller
    def test_only_one_poller(self):
        first=self.poller()
        with self.assertRaises(ServiceError): self.poller()
        first.release(); self.poller().release()
    def test_webhook_blocks_polling(self):
        bale=Mock(); bale.call.return_value={"url":"https://example.org/hook"}
        with self.assertRaises(ServiceError): Poller(self.q,bale).acquire()
    def test_webhook_rejects_polling_mode_in_database(self):
        poller=self.poller()
        self.assertEqual(self.client.post("/webhooks/bale/"+"s"*40,json=fixtures.incoming()).status_code,409)
        poller.release()
    def test_polling_offset_survives_restart(self):
        first=self.poller(); first.bale.call.return_value=[fixtures.incoming(10)]
        first.once(); first.release()
        second=self.poller(); second.bale.call.return_value=[]; second.once()
        self.assertEqual(second.bale.call.call_args.args[1]["offset"],11)
    def test_failed_commit_does_not_advance_offset(self):
        poller=self.poller(); poller.bale.call.return_value=[fixtures.incoming(10)]
        with patch.object(self.q,"ingest",side_effect=OperationalError("safe",{},Exception())):
            with self.assertRaises(OperationalError): poller.once()
        with self.db.session_scope() as s: self.assertEqual(s.get(Receiver,1).offset,0)
    def test_file_cache_is_scoped_to_bot(self):
        cache=FileCache(self.db,"bot-a")
        value={"video":{"id":VID,"title":"Public"},"parts":[{"state":"sent","file_id":"file-1","start":0,"end":10}]}
        cache.put(VID,value)
        self.assertEqual(cache.get(VID),value)
        self.assertIsNone(FileCache(self.db,"bot-b").get(VID))
    def test_file_cache_skips_download(self):
        cache=FileCache(self.db,"bot-a")
        cache.put(VID,{"video":{"id":VID,"title":"Public"},"parts":[{"state":"sent","file_id":"file-1","start":0,"end":10}]})
        self.q.ingest(fixtures.incoming(text="/download "+VID))
        yt,bale=Mock(),Mock()
        MediaWorker(self.q,bale,yt,cache).once()
        yt.download.assert_not_called(); yt.metadata.assert_not_called()
        self.assertEqual(bale.call.call_args.args[1]["video"],"file-1")
        with self.db.session_scope() as s: self.assertEqual(s.scalar(select(Job)).state,"done")
    def test_retention_scrubs_all_private_containers(self):
        self.q.ingest(fixtures.incoming())
        with self.db.session_scope() as s:
            job=s.scalar(select(Job)); job.created=0; job.result={"private":"text"}
            s.get(Update,1).created=0
            s.add(Delivery(job_id=job.id,ordinal=0,text="secret"))
            s.add(Message(user_id=123,generation=0,role="user",content="secret",created=0))
        self.q.forget_expired()
        with self.db.session_scope() as s:
            self.assertEqual(s.get(Update,1).payload,{})
            self.assertEqual(s.scalar(select(Delivery)).text,"")
            self.assertEqual(s.scalar(select(Job)).result,{})
            self.assertEqual(s.scalar(select(Job)).state,"expired")
            self.assertIsNone(s.scalar(select(Message)))
