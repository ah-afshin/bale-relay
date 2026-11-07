import argparse
from dotenv import load_dotenv
from bale_relay.core.config import Config
from bale_relay.storage.database import Database
from bale_relay.storage.queue import Queue

def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("allow-user", "block-user"):
        sub.add_parser(name).add_argument("id", type=int)
    sub.add_parser("serve")
    sub.add_parser("worker")
    sub.add_parser("media-worker")
    sub.add_parser("poll")
    sub.add_parser("delete-webhook")
    sub.add_parser("webhook-info")
    sub.add_parser("set-webhook").add_argument("origin")
    sub.add_parser("doctor").add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.command == "doctor":
        import json
        from bale_relay.entrypoints.doctor import examine
        try: cfg=Config.from_env()
        except Exception:
            print(json.dumps({"configuration":False})); raise SystemExit(1)
        checks=examine(cfg,live=args.live)
        print(json.dumps(checks,ensure_ascii=False))
        raise SystemExit(0 if all(checks.values()) else 1)
    cfg = Config.from_env()
    if args.command in {"poll", "set-webhook", "delete-webhook", "webhook-info"}:
        from bale_relay.adapters.bale import Bale
        from bale_relay.core.http_client import HttpClient
        from bale_relay.storage.models import Receiver
        from bale_relay.entrypoints.polling import Poller
        from sqlalchemy import select
        import time
        db = Database(cfg.database_url)
        bale = Bale(cfg.token, HttpClient(10, 5_000_000, "BaleRelay/0.1"))
        if args.command == "poll":
            if cfg.receiver_mode != "polling": raise RuntimeError("Set RECEIVER_MODE=polling first")
            Poller(Queue(db,cfg),bale).run()
        elif args.command == "webhook-info":
            print("Webhook configured:", bool(bale.call("getWebhookInfo").get("url")))
        else:
            with db.session_scope() as session:
                receiver = session.scalar(select(Receiver).where(Receiver.id==1).with_for_update())
                if receiver and receiver.lease_until > time.time(): raise RuntimeError("Stop the active poller first")
                if args.command == "set-webhook":
                    if cfg.receiver_mode != "webhook" or len(cfg.webhook_secret)<32: raise RuntimeError("Configure webhook mode and secret first")
                    from urllib.parse import urlsplit
                    from bale_relay.core.security import assert_public_url
                    origin=args.origin.rstrip("/")
                    url=urlsplit(origin)
                    if url.scheme!="https" or url.path or url.query or url.fragment: raise RuntimeError("Provide only an HTTPS origin")
                    assert_public_url(origin)
                    bale.call("setWebhook", {"url":origin+"/webhooks/bale/"+cfg.webhook_secret})
                    mode="webhook"
                else:
                    bale.call("deleteWebhook")
                    mode="polling"
                if receiver: receiver.mode=mode; receiver.owner=None; receiver.lease_until=0
                else: session.add(Receiver(id=1,mode=mode,offset=0,owner=None,lease_until=0))
            print("Receiver configuration updated")
    elif args.command in {"worker", "media-worker"}:
        from bale_relay.services.runtime import Services
        from bale_relay.adapters.bale import Bale
        from bale_relay.core.http_client import HttpClient
        from bale_relay.entrypoints.worker import Worker
        db = Database(cfg.database_url)
        bale = Bale(cfg.token, HttpClient(10, 5_000_000, "BaleRelay/0.1"))
        if args.command == "media-worker":
            from bale_relay.entrypoints.media_worker import MediaWorker
            from bale_relay.storage.media_cache import FileCache
            MediaWorker(Queue(db,cfg), bale, cache=FileCache(db,cfg.token)).run()
        else:
            Worker(Queue(db,cfg), Services(cfg, db), bale).run()
    elif args.command == "serve":
        from bale_relay.entrypoints.web import create_app
        create_app(cfg).run(host="127.0.0.1", port=5000)
    else:
        Queue(Database(cfg.database_url),cfg).allow(args.id, args.command == "allow-user")
        print("Updated access")

if __name__ == "__main__": main()
