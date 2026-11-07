"""Initial durable bot state."""
from alembic import op
import sqlalchemy as sa
revision = "0001"
down_revision = None

def upgrade():
    op.create_table("bot_users", sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("generation", sa.Integer(), nullable=False), sa.Column("model", sa.String(255), nullable=False), sa.Column("mode", sa.String(20), nullable=False))
    op.create_table("bot_updates", sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False), sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("bot_users.id"), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("created", sa.Float(), nullable=False))
    op.create_table("jobs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("update_id", sa.BigInteger(), sa.ForeignKey("bot_updates.id"), nullable=False, unique=True), sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("bot_users.id"), nullable=False), sa.Column("generation", sa.Integer(), nullable=False), sa.Column("lane", sa.String(20), nullable=False), sa.Column("state", sa.String(20), nullable=False), sa.Column("lease", sa.String(64)), sa.Column("lease_until", sa.Float(), nullable=False), sa.Column("created", sa.Float(), nullable=False), sa.Column("result", sa.JSON(), nullable=False))
    for col in ("user_id", "lane", "state"): op.create_index("ix_jobs_"+col, "jobs", [col])
    op.create_table("bot_messages", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("bot_users.id"), nullable=False), sa.Column("generation", sa.Integer(), nullable=False), sa.Column("role", sa.String(20), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("created", sa.Float(), nullable=False))
    for col in ("user_id", "created"): op.create_index("ix_bot_messages_"+col, "bot_messages", [col])
    op.create_table("usage", sa.Column("key", sa.String(255), primary_key=True), sa.Column("used", sa.Integer(), nullable=False))
    op.create_table("google_search_monthly_usage", sa.Column("month", sa.String(7), primary_key=True), sa.Column("requests_used", sa.Integer(), nullable=False))

def downgrade():
    for table in ("google_search_monthly_usage", "usage", "bot_messages", "jobs", "bot_updates", "bot_users"): op.drop_table(table)
