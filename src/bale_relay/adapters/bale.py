from bale_relay.core.errors import ServiceError

class AmbiguousDelivery(ServiceError): pass

class Bale:
    def __init__(self, token, http):
        if not token: raise ValueError("BALE_TOKEN is required")
        self.base = "https://tapi.bale.ai/bot" + token
        self.http = http
    def call(self, method, payload=None, files=None):
        allowed = {"getMe", "sendMessage", "sendVideo", "sendDocument", "getUpdates", "setWebhook", "deleteWebhook", "getWebhookInfo", "answerCallbackQuery"}
        if method not in allowed: raise ValueError("Unsupported method")
        sending = method in {"sendMessage", "sendVideo", "sendDocument"}
        try:
            options = {"data": payload, "files": files} if files else {"json": payload or {}}
            response = self.http.request("POST", self.base + "/" + method,
                    timeout=90 if files else 40, retries=False, allow_redirects=False, **options)
        except ServiceError:
            if sending: raise AmbiguousDelivery("وضعیت ارسال نامشخص است؛ پیش از ارسال دوباره بررسی کنید.", 504) from None
            raise ServiceError("ارتباط با بله برقرار نشد.", 503) from None
        try: data = response.json()
        except ValueError:
            if sending: raise AmbiguousDelivery("وضعیت ارسال نامشخص است.", 502) from None
            raise ServiceError("پاسخ نامعتبر بله", 502) from None
        if not isinstance(data, dict) or data.get("ok") is not True:
            if response.status_code >= 500 and sending:
                raise AmbiguousDelivery("وضعیت ارسال نامشخص است.", 502)
            raise ServiceError("بله درخواست را نپذیرفت.", 429 if isinstance(data, dict) and data.get("error_code") == 429 else 502)
        return data.get("result")
    def send_text(self, chat_id, text, markup=None):
        return self.call("sendMessage", {"chat_id": chat_id, "text": text, **({"reply_markup": markup} if markup else {})})
