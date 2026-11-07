"""Read-only deployment checks. Results never contain keys, DSNs or request URLs."""
import importlib.util
import shutil
from pathlib import Path
from sqlalchemy.engine import make_url
from sqlalchemy import inspect, text
from bale_relay.storage.models import Base
from bale_relay.storage.database import Database


def examine(config, database=None, live=False):
    checks={}
    try: config.validate(); checks["configuration"]=True
    except Exception: checks["configuration"]=False
    checks["bale_token"]=bool(config.token)
    checks["webhook_secret"]=len(config.webhook_secret)>=32 and config.webhook_secret!=config.token
    checks["approved_models"]=bool(config.ai_allowed_models)
    checks["search_independent_quota"]=bool(config.secret("SERPAPI_API_KEY")) and config.secret("SERPAPI_INDEPENDENT_QUOTA")=="1"
    for executable in ("ffmpeg","ffprobe","deno"):
        checks[executable]=shutil.which(executable) is not None
    checks["yt_dlp"]=importlib.util.find_spec("yt_dlp") is not None
    checks["database"]=False
    db=None
    try:
        parsed=make_url(config.database_url)
        if database is None and parsed.drivername.startswith("sqlite") and parsed.database not in (None,":memory:") and not Path(parsed.database).is_file():
            raise RuntimeError("Database does not exist")
        db=database or Database(config.database_url)
        with db.engine.connect() as c:
            c.execute(text("SELECT 1"))
            names=set(inspect(c).get_table_names())
            checks["database"]=set(Base.metadata.tables).issubset(names)
            checks["migrations"]=c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()=="0004"
    except Exception: checks["migrations"]=False
    finally:
        if db is not None and database is None: db.engine.dispose()
    if live:
        from bale_relay.core.http_client import HttpClient
        from bale_relay.adapters.bale import Bale
        try:
            me=Bale(config.token,HttpClient(10,1_000_000,"BaleRelay/0.1")).call("getMe")
            checks["live_bale"]=isinstance(me,dict) and bool(me.get("id"))
        except Exception: checks["live_bale"]=False
    return checks
