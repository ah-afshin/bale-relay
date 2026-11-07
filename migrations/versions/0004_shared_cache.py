from alembic import op
import sqlalchemy as sa
revision="0004"
down_revision="0003"
def upgrade():
    op.create_table("cache_entries",sa.Column("key",sa.String(64),primary_key=True),sa.Column("value",sa.JSON(),nullable=False),sa.Column("expires",sa.Float(),nullable=False))
    op.create_index("ix_cache_entries_expires","cache_entries",["expires"])
def downgrade(): op.drop_table("cache_entries")
