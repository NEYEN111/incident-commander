"""Store ML predictions independently from the registered accident severity."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0020_incident_predictions"
down_revision = "0019_incident_ml_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incident_predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("predicted_severity", sa.String(16), nullable=False),
        sa.Column("prob_fatal", sa.Float(), nullable=False),
        sa.Column("prob_grave", sa.Float(), nullable=False),
        sa.Column("prob_leve", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("input_data", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("predicted_severity IN ('Fatal', 'Grave', 'Leve')", name="ck_incident_predictions_severity"),
        sa.CheckConstraint("prob_fatal BETWEEN 0 AND 1 AND prob_grave BETWEEN 0 AND 1 AND prob_leve BETWEEN 0 AND 1", name="ck_incident_predictions_probabilities"),
    )
    op.create_index("ix_incident_predictions_history", "incident_predictions", ["incident_id", "created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_incident_predictions_history", table_name="incident_predictions")
    op.drop_table("incident_predictions")
