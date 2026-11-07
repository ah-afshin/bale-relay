from types import SimpleNamespace
from bale_relay.core.cache import MemoryCache
from bale_relay.core.http_client import HttpClient
from bale_relay.core.errors import ServiceError
from bale_relay.services.ai import AIService
from bale_relay.services.google_search import GoogleSearchService

class Services:
    def __init__(self, config, database):
        self.config = config
        ctx = SimpleNamespace(config=config, database=database,
                              http=HttpClient(10, 5_000_000, "BaleRelay/0.1"), cache=MemoryCache())
        self.ai = AIService(ctx)
        from bale_relay.storage.cache import DatabaseCache
        search_ctx=SimpleNamespace(config=config,database=database,http=ctx.http,
            cache=DatabaseCache(database,namespace=config.secret("SERPAPI_API_KEY")))
        self.google = GoogleSearchService(search_ctx)
    def models(self):
        allowed = set(self.config.ai_allowed_models)
        return [row["id"] for row in self.ai.models()["data"] if row["id"] in allowed]
    def complete(self, model, messages):
        if model not in self.models():
            raise ServiceError("مدل انتخاب‌شده مجاز یا در دسترس نیست.", 403)
        result = self.ai.complete({"model": model, "messages": messages, "max_tokens": 2048})
        return result["choices"][0]["message"]["content"] or ""
    def search(self, query):
        if self.config.secret("SERPAPI_INDEPENDENT_QUOTA") != "1":
            raise ServiceError("سهمیهٔ مستقل سرچ هنوز تأیید نشده است.", 503)
        return self.google.search(query, limit=5)
