import json
import unittest
from tests import test_ingress as fixtures
from bale_relay.entrypoints.doctor import examine
from bale_relay.core.config import Config

class DoctorTests(unittest.TestCase):
    setUp=fixtures.IngressTests.setUp
    def test_missing_keys_are_reported_without_values(self):
        secret="private-token-must-never-appear"
        checks=examine(Config(token=secret,webhook_secret="s"*40),self.db)
        output=json.dumps(checks)
        self.assertNotIn(secret,output)
        self.assertTrue(checks["bale_token"])
        self.assertFalse(checks["approved_models"])
        self.assertFalse(checks["migrations"])
        self.assertTrue(checks["database"])

    def test_readiness_does_not_create_missing_database(self):
        from pathlib import Path
        path=Path(self.temp.name)/"missing.sqlite3"
        checks=examine(Config(database_url="sqlite:///"+str(path)))
        self.assertFalse(checks["database"])
        self.assertFalse(path.exists())
