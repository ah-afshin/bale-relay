import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import requests
from tests import test_ingress as fixtures
from bale_relay.services.ai import AIService, AIError
from bale_relay.services.runtime import Services
from bale_relay.core.config import Config
from bale_relay.core.cache import MemoryCache
from bale_relay.core.errors import ServiceError
from bale_relay.storage.models import GoogleSearchUsage


def response(payload,status=200):
    r=requests.Response();r.status_code=status;r._content=json.dumps(payload).encode();return r

class ProviderTests(unittest.TestCase):
    def service(self, keys):
        ctx=SimpleNamespace(config=Config(),http=Mock(),cache=MemoryCache())
        return AIService(ctx)
    def test_four_openai_adapters(self):
        for provider,key in [("groq","GROQ_API_KEY"),("openrouter","OPENROUTER_API_KEY"),("cerebras","CEREBRAS_API_KEY"),("mistral","MISTRAL_API_KEY")]:
            with self.subTest(provider=provider),patch.dict(os.environ,{key:"private-key"}):
                ai=self.service({});ai.http.request.return_value=response({"choices":[{"message":{"role":"assistant","content":"answer"},"finish_reason":"stop"}]})
                result=ai.complete({"model":provider+"/test","messages":[{"role":"user","content":"question"}]})
                self.assertEqual(result["choices"][0]["message"]["content"],"answer")
                args,kwargs=ai.http.request.call_args
                self.assertTrue(args[1].startswith("https://"));self.assertFalse(kwargs["allow_redirects"])
                self.assertFalse(kwargs["retries"])
                self.assertNotIn("private-key",json.dumps(result))
    def test_gemini_normalizes_native_response(self):
        with patch.dict(os.environ,{"GEMINI_API_KEY":"private-key"}):
            ai=self.service({});ai.http.request.return_value=response({"candidates":[{"content":{"parts":[{"text":"answer"}]},"finishReason":"STOP"}]})
            result=ai.complete({"model":"gemini/test","messages":[{"role":"user","content":"question"}]})
            self.assertEqual(result["choices"][0]["message"]["content"],"answer")
            self.assertTrue(ai.http.request.call_args.args[1].endswith(":generateContent"))
            self.assertNotIn("private-key",ai.http.request.call_args.args[1])
    def test_no_automatic_provider_fallback(self):
        with patch.dict(os.environ,{"GROQ_API_KEY":"a","MISTRAL_API_KEY":"b"}):
            ai=self.service({});ai.http.request.return_value=response({},429)
            with self.assertRaises(AIError): ai.complete({"model":"groq/test","messages":[{"role":"user","content":"hello"}]})
            ai.http.request.assert_called_once()
    def test_unapproved_model_never_generates(self):
        services=object.__new__(Services);services.config=Config(ai_allowed_models=("groq/free",));services.ai=Mock()
        services.ai.models.return_value={"data":[{"id":"groq/free"},{"id":"groq/paid"}]}
        with self.assertRaises(ServiceError): services.complete("groq/paid",[{"role":"user","content":"test"}])
        services.ai.complete.assert_not_called()

class SearchTests(unittest.TestCase):
    setUp=fixtures.IngressTests.setUp
    def service(self):
        return Services(Config(),self.db)
    def test_key_attestation_required(self):
        with patch.dict(os.environ,{"SERPAPI_API_KEY":"private","SERPAPI_INDEPENDENT_QUOTA":"0"}):
            service=self.service()
            with patch.object(service.google.http,"request") as upstream:
                with self.assertRaises(ServiceError):service.search("query")
                upstream.assert_not_called()
    def test_shared_cache_consumes_one_provider_attempt(self):
        with patch.dict(os.environ,{"SERPAPI_API_KEY":"private","SERPAPI_INDEPENDENT_QUOTA":"1"}):
            first=self.service()
            with patch.object(first.google.http,"request",return_value=response({"organic_results":[{"title":"Test","link":"https://example.org","snippet":"Example"}]})) as upstream:
                self.assertEqual(first.search("query")["count"],1);upstream.assert_called_once()
            second=self.service()
            with patch.object(second.google.http,"request") as upstream:
                self.assertEqual(second.search("query")["count"],1);upstream.assert_not_called()
            month=datetime.now(timezone.utc).strftime("%Y-%m")
            with self.db.session_scope() as s:self.assertEqual(s.get(GoogleSearchUsage,month).requests_used,1)
    def test_monthly_quota_fails_closed(self):
        month=datetime.now(timezone.utc).strftime("%Y-%m")
        with self.db.session_scope() as s:s.add(GoogleSearchUsage(month=month,requests_used=200))
        with patch.dict(os.environ,{"SERPAPI_API_KEY":"private","SERPAPI_INDEPENDENT_QUOTA":"1"}):
            service=self.service()
            with patch.object(service.google.http,"request") as upstream:
                with self.assertRaises(ServiceError):service.search("uncached query")
                upstream.assert_not_called()
