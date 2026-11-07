from alembic import op
import sqlalchemy as sa
revision="0005"
down_revision="0004"
def upgrade():
    op.add_column("jobs",sa.Column("started",sa.Float(),nullable=False,server_default="0"))
    op.add_column("jobs",sa.Column("finished",sa.Float(),nullable=False,server_default="0"))
    op.add_column("jobs",sa.Column("metrics",sa.JSON(),nullable=False,server_default="{}"))
def downgrade():
    for name in ("metrics","finished","started"):op.drop_column("jobs",name)
