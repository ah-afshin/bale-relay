import hmac
from flask import Flask, request, jsonify
from sqlalchemy.exc import SQLAlchemyError
from bale_relay.storage.models import Receiver
from bale_relay.core.config import Config
from bale_relay.core.errors import ServiceError
from bale_relay.storage.database import Database
from bale_relay.storage.queue import Queue

def create_app(config=None, database=None):
    cfg = config or Config.from_env()
    cfg.validate()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1_000_000
    queue = Queue(database or Database(cfg.database_url))
    app.extensions["queue"] = queue
    @app.get("/healthz")
    def health(): return jsonify(status="ok")
    @app.post("/webhooks/bale/<secret>")
    def webhook(secret):
        if cfg.receiver_mode != "webhook" or not cfg.webhook_secret or not hmac.compare_digest(secret.encode(), cfg.webhook_secret.encode()):
            return jsonify(error="not found"), 404
        if not request.is_json: return jsonify(error="JSON required"), 400
        try:
            with queue.db.session_scope() as session:
                receiver = session.get(Receiver, 1)
                if receiver and receiver.mode != "webhook":
                    return jsonify(error="receiver disabled"), 409
            result = queue.ingest(request.get_json())
        except ServiceError as exc:
            return jsonify(error=exc.message), exc.status
        except ValueError:
            return jsonify(error="invalid update"), 400
        except SQLAlchemyError:
            return jsonify(error="temporarily unavailable"), 503
        return jsonify(status=result), 403 if result == "denied" else 200
    return app
