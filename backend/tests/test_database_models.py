from sqlalchemy import create_engine, inspect

from app.models import Base


def test_platform_schema_builds_with_expected_tables():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    assert tables == {
        "action_plans",
        "audit_events",
        "fx_conversions",
        "pockets",
        "recommendations",
        "transactions",
        "users",
        "wallets",
        "webhook_events",
    }
