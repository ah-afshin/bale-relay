from bale_relay.core.errors import ServiceError

class AmbiguousDelivery(ServiceError): pass

class Bale:
    def __init__(self, token, http):
        if not token: raise ValueError("BALE_TOKEN is required")
        self.base = "https://tapi.bale.ai/bot" + token
        self.http = http
    def call(self, method, payload=None, files=None, *, deadline=None, active=None):
        allowed = {"getMe", "sendMessage", "sendVideo", "sendDocument", "getUpdates", "setWebhook", "deleteWebhook", "getWebhookInfo", "answerCallbackQuery"}
        if method not in allowed: raise ValueError("Unsupported method")
        sending = method in {"sendMessage", "sendVideo", "sendDocument"}
        try:
            timeout=90 if files else 40
            if deadline is not None:
                import time
                from bale_relay.adapters.youtube import MediaPaused
                remaining=deadline-time.monotonic()
                if remaining<=0:raise MediaPaused()
                timeout=min(timeout,remaining)
            if files:
                import time
                from bale_relay.adapters.multipart import MultipartStream
                from bale_relay.adapters.youtube import MediaPaused,MediaCancelled
                last_check=[0.0]
                def check():
                    now=time.monotonic()
                    if deadline is not None and now>=deadline:raise MediaPaused()
                    if active is not None and now-last_check[0]>=0.5:
                        last_check[0]=now
                        if not active():raise MediaCancelled()
                body=MultipartStream(payload,files,check)
                options={"data":body,"headers":{"Content-Type":"multipart/form-data; boundary="+body.boundary,"Content-Length":str(len(body))}}
            else:options={"json":payload or {}}
            response = self.http.request("POST", self.base + "/" + method,
                    timeout=timeout, retries=False, allow_redirects=False, **options)
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
