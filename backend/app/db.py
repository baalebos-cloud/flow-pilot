import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from app.config import settings


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY,
              email TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL,
              password_hash TEXT NOT NULL,
              bmoni_user_id TEXT UNIQUE,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wallets (
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL UNIQUE REFERENCES users(id),
              bmoni_wallet_id TEXT,
              wallet_address TEXT NOT NULL UNIQUE,
              currency TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS action_plans (
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL REFERENCES users(id),
              action_type TEXT NOT NULL,
              amount_minor INTEGER NOT NULL,
              currency TEXT NOT NULL,
              recipient_name TEXT NOT NULL,
              reason TEXT NOT NULL,
              available_balance_minor INTEGER NOT NULL,
              expected_balance_minor INTEGER NOT NULL,
              risk_status TEXT NOT NULL,
              approval_status TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transactions (
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL REFERENCES users(id),
              action_plan_id TEXT NOT NULL UNIQUE REFERENCES action_plans(id),
              bmoni_proposal_id TEXT NOT NULL UNIQUE,
              amount_minor INTEGER NOT NULL,
              currency TEXT NOT NULL,
              status TEXT NOT NULL,
              bmoni_status TEXT NOT NULL,
              idempotency_key TEXT NOT NULL,
              created_at TEXT NOT NULL,
              completed_at TEXT,
              UNIQUE(user_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS webhook_events (
              id TEXT PRIMARY KEY,
              event_type TEXT NOT NULL,
              external_id TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              processed INTEGER NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pockets (
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL REFERENCES users(id),
              name TEXT NOT NULL,
              purpose TEXT NOT NULL,
              allocated_minor INTEGER NOT NULL CHECK(allocated_minor >= 0),
              spent_minor INTEGER NOT NULL DEFAULT 0 CHECK(spent_minor >= 0),
              currency TEXT NOT NULL,
              protected INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              UNIQUE(user_id, name)
            );
            CREATE TABLE IF NOT EXISTS recommendations (
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL REFERENCES users(id),
              pocket_id TEXT REFERENCES pockets(id),
              type TEXT NOT NULL,
              status TEXT NOT NULL,
              source_currency TEXT,
              target_currency TEXT,
              amount_minor INTEGER,
              rationale TEXT NOT NULL,
              risk_disclosure TEXT NOT NULL,
              evidence_json TEXT NOT NULL,
              expires_at TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fx_conversions (
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL REFERENCES users(id),
              recommendation_id TEXT NOT NULL UNIQUE REFERENCES recommendations(id),
              bmoni_conversion_id TEXT NOT NULL UNIQUE,
              status TEXT NOT NULL,
              source_amount_minor INTEGER NOT NULL,
              source_currency TEXT NOT NULL,
              target_currency TEXT NOT NULL,
              quote_json TEXT NOT NULL,
              idempotency_key TEXT NOT NULL,
              created_at TEXT NOT NULL,
              completed_at TEXT,
              UNIQUE(user_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS investment_opportunities (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              provider TEXT NOT NULL,
              regulatory_status TEXT NOT NULL,
              risk_level TEXT NOT NULL,
              liquidity TEXT NOT NULL,
              fee_minor INTEGER NOT NULL DEFAULT 0,
              currency TEXT NOT NULL,
              description TEXT NOT NULL,
              verified_at TEXT NOT NULL
            );
            """
        )


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def json_text(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)
