"""store.py - SQLite watchlist: the durable store and CLI<->daemon channel.

Library module, not a CLI. WAL + busy_timeout let the daemon read while the
CLI writes. Watches are unique on (symbol, level, timeframe, conditions,
provider) so add is atomically idempotent. Dedup state and the daemon
heartbeat live in sibling tables.

  import store; conn = store.connect(); store.init_db(conn)
"""
import json
import sqlite3
import time
from dataclasses import dataclass

import paths

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    id           INTEGER PRIMARY KEY,
    symbol       TEXT NOT NULL,
    level        REAL NOT NULL,
    timeframe    TEXT NOT NULL,
    conditions   TEXT NOT NULL,
    provider     TEXT NOT NULL,
    provider_arg TEXT,
    created_at   INTEGER NOT NULL,
    UNIQUE(symbol, level, timeframe, conditions, provider)
);
CREATE TABLE IF NOT EXISTS watch_state (
    watch_id   INTEGER PRIMARY KEY REFERENCES watches(id) ON DELETE CASCADE,
    state_json TEXT NOT NULL DEFAULT '{}',
    updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS daemon_meta (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    started_at INTEGER,
    last_cycle INTEGER
);
CREATE TABLE IF NOT EXISTS alerts (
    id      INTEGER PRIMARY KEY,
    ts      INTEGER NOT NULL,
    message TEXT NOT NULL
);
"""

_ALERTS_KEEP = 1000  # the broadcast log is for live `monitor`, not history


@dataclass
class Watch:
    id: int
    symbol: str
    level: float
    timeframe: str
    conditions: str  # canonical JSON list of condition names
    provider: str
    provider_arg: str | None  # e.g. output path for the file provider


def connect() -> sqlite3.Connection:
    paths.ensure_data_dir()
    conn = sqlite3.connect(paths.DB, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    _migrate(conn)
    conn.commit()


def _migrate(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(watches)")}
    if "provider_arg" not in cols:
        conn.execute("ALTER TABLE watches ADD COLUMN provider_arg TEXT")


def canonical_conditions(condition_names: list[str]) -> str:
    return json.dumps(sorted(condition_names))


def add_watch(conn, symbol: str, level: float, timeframe: str,
              condition_names: list[str], provider: str, provider_arg: str | None) -> tuple[int, bool]:
    conds = canonical_conditions(condition_names)
    cur = conn.execute(
        "INSERT INTO watches(symbol, level, timeframe, conditions, provider, provider_arg, created_at) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
        (symbol, level, timeframe, conds, provider, provider_arg, int(time.time())),
    )
    conn.commit()
    created = cur.rowcount > 0
    row = conn.execute(
        "SELECT id FROM watches WHERE symbol=? AND level=? AND timeframe=? AND conditions=? AND provider=?",
        (symbol, level, timeframe, conds, provider),
    ).fetchone()
    return row["id"], created


def list_watches(conn) -> list[Watch]:
    rows = conn.execute(
        "SELECT id, symbol, level, timeframe, conditions, provider, provider_arg "
        "FROM watches ORDER BY symbol, level"
    ).fetchall()
    return [Watch(**dict(row)) for row in rows]


def record_alert(conn, message: str) -> None:
    conn.execute("INSERT INTO alerts(ts, message) VALUES(?, ?)", (int(time.time()), message))
    conn.execute("DELETE FROM alerts WHERE id <= (SELECT MAX(id) FROM alerts) - ?", (_ALERTS_KEEP,))
    conn.commit()


def latest_alert_id(conn) -> int:
    return conn.execute("SELECT COALESCE(MAX(id), 0) AS n FROM alerts").fetchone()["n"]


def alerts_after(conn, after_id: int) -> list[tuple[int, int, str]]:
    rows = conn.execute(
        "SELECT id, ts, message FROM alerts WHERE id > ? ORDER BY id", (after_id,)
    ).fetchall()
    return [(r["id"], r["ts"], r["message"]) for r in rows]


def remove_by_id(conn, watch_id: int) -> int:
    cur = conn.execute("DELETE FROM watches WHERE id=?", (watch_id,))
    conn.commit()
    return cur.rowcount


def remove_by_symbol(conn, symbol: str) -> int:
    cur = conn.execute("DELETE FROM watches WHERE symbol=?", (symbol,))
    conn.commit()
    return cur.rowcount


def count_watches(conn) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM watches").fetchone()["n"]


def load_state(conn, watch_id: int) -> dict:
    row = conn.execute(
        "SELECT state_json FROM watch_state WHERE watch_id=?", (watch_id,)
    ).fetchone()
    if row is None:
        return {}
    return json.loads(row["state_json"] or "{}")


def save_state(conn, watch_id: int, state: dict) -> None:
    conn.execute(
        "INSERT INTO watch_state(watch_id, state_json, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(watch_id) DO UPDATE SET "
        "state_json=excluded.state_json, updated_at=excluded.updated_at",
        (watch_id, json.dumps(state), int(time.time())),
    )
    conn.commit()


def set_started(conn) -> None:
    now = int(time.time())
    conn.execute(
        "INSERT INTO daemon_meta(id, started_at, last_cycle) VALUES(1, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET started_at=excluded.started_at",
        (now, now),
    )
    conn.commit()


def set_heartbeat(conn) -> None:
    conn.execute(
        "INSERT INTO daemon_meta(id, last_cycle) VALUES(1, ?) "
        "ON CONFLICT(id) DO UPDATE SET last_cycle=excluded.last_cycle",
        (int(time.time()),),
    )
    conn.commit()


def get_meta(conn) -> dict:
    row = conn.execute("SELECT started_at, last_cycle FROM daemon_meta WHERE id=1").fetchone()
    return dict(row) if row else {}
