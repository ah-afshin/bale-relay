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
