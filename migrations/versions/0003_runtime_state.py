from alembic import op
import sqlalchemy as sa
revision = "0003"
down_revision = "0002"
def upgrade():
    op.create_table("media_cache", sa.Column("key",sa.String(100),primary_key=True),sa.Column("value",sa.JSON(),nullable=False),sa.Column("created",sa.Float(),nullable=False))
    op.create_table("receiver",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("mode",sa.String(20),nullable=False),sa.Column("offset",sa.BigInteger(),nullable=False),sa.Column("owner",sa.String(64)),sa.Column("lease_until",sa.Float(),nullable=False))
def downgrade():
    op.drop_table("receiver")
    op.drop_table("media_cache")
