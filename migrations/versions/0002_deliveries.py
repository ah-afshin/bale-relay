from alembic import op
import sqlalchemy as sa
revision = "0002"
down_revision = "0001"
def upgrade():
    op.create_table("deliveries", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False), sa.Column("ordinal", sa.Integer(), nullable=False), sa.Column("text", sa.Text(), nullable=False), sa.Column("state", sa.String(20), nullable=False), sa.Column("message_id", sa.String(64)), sa.UniqueConstraint("job_id", "ordinal"))
    op.create_index("ix_deliveries_job_id", "deliveries", ["job_id"])
def downgrade(): op.drop_table("deliveries")
