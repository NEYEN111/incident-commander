"""Add the minimal STATS19 accident fields without altering existing records."""

from alembic import op
import sqlalchemy as sa

revision = "0018_road_accident_fields"
down_revision = "0017_meet_service_account"
branch_labels = None
depends_on = None

_COLUMNS = {
    "date": sa.Date(),
    "time": sa.Time(),
    "latitude": sa.Float(),
    "longitude": sa.Float(),
    "road_type": sa.Integer(),
    "speed_limit": sa.Integer(),
    "urban_or_rural_area": sa.Integer(),
    "light_conditions": sa.Integer(),
    "weather_conditions": sa.Integer(),
    "road_surface_conditions": sa.Integer(),
}
_CHECKS = {
    "latitude": "latitude BETWEEN -90 AND 90",
    "longitude": "longitude BETWEEN -180 AND 180",
    "road_type": "road_type IN (1, 2, 3, 6, 7, 9)",
    "speed_limit": "speed_limit BETWEEN 1 AND 200",
    "urban_or_rural_area": "urban_or_rural_area IN (1, 2, 3)",
    "light_conditions": "light_conditions IN (1, 4, 5, 6, 7)",
    "weather_conditions": "weather_conditions IN (1, 2, 3, 4, 5, 6, 7, 8, 9)",
    "road_surface_conditions": "road_surface_conditions IN (1, 2, 3, 4, 5)",
}


def upgrade() -> None:
    for name, type_ in _COLUMNS.items():
        op.add_column("incidents", sa.Column(name, type_, nullable=True))
    for name, condition in _CHECKS.items():
        op.create_check_constraint(f"ck_incidents_{name}", "incidents", condition)


def downgrade() -> None:
    for name in reversed(_CHECKS):
        op.drop_constraint(f"ck_incidents_{name}", "incidents", type_="check")
    for name in reversed(_COLUMNS):
        op.drop_column("incidents", name)
