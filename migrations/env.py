from alembic import context
from bale_relay.core.config import Config
from bale_relay.storage.database import Database
from bale_relay.storage.models import Base
from dotenv import load_dotenv
load_dotenv()
if context.is_offline_mode():
    context.configure(url=Config.from_env().database_url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction(): context.run_migrations()
else:
    with Database(Config.from_env().database_url).engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction(): context.run_migrations()
