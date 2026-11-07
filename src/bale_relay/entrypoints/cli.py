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
    args = parser.parse_args()
    cfg = Config.from_env()
    if args.command == "worker":
        from bale_relay.services.runtime import Services
        from bale_relay.adapters.bale import Bale
        from bale_relay.core.http_client import HttpClient
        from bale_relay.entrypoints.worker import Worker
        db = Database(cfg.database_url)
        Worker(Queue(db), Services(cfg, db), Bale(cfg.token, HttpClient(10, 5_000_000, "BaleRelay/0.1"))).run()
    elif args.command == "serve":
        from bale_relay.entrypoints.web import create_app
        create_app(cfg).run(host="127.0.0.1", port=5000)
    else:
        Queue(Database(cfg.database_url)).allow(args.id, args.command == "allow-user")
        print("Updated access")

if __name__ == "__main__": main()
