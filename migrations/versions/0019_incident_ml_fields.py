"""Add nullable STATS19 model inputs, preserving existing accident records."""

from alembic import op
import sqlalchemy as sa

revision = "0019_incident_ml_fields"
down_revision = "0018_road_accident_fields"
branch_labels = None
depends_on = None

_CHECKS = {
    "number_of_vehicles": "number_of_vehicles BETWEEN 1 AND 17",
    "junction_detail": "junction_detail IN (-1, 0, 13, 16, 17, 18, 19, 99)",
    "first_road_class": "first_road_class IN (-1, 1, 2, 3, 4, 5, 6)",
}


def upgrade() -> None:
    for name, condition in _CHECKS.items():
        op.add_column("incidents", sa.Column(name, sa.Integer(), nullable=True))
        op.create_check_constraint(f"ck_incidents_{name}", "incidents", condition)


def downgrade() -> None:
    for name in reversed(_CHECKS):
        op.drop_constraint(f"ck_incidents_{name}", "incidents", type_="check")
        op.drop_column("incidents", name)
