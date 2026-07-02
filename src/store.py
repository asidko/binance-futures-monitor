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

_WATCHES_DDL = """
CREATE TABLE IF NOT EXISTS watches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT NOT NULL,
    level        REAL NOT NULL,
    timeframe    TEXT NOT NULL,
    conditions   TEXT NOT NULL,
    provider     TEXT NOT NULL,
    provider_arg TEXT,
    created_at   INTEGER NOT NULL
)
"""

# COALESCE folds NULL args together (SQLite UNIQUE treats NULLs as distinct);
# provider_arg is part of the key so watches differing only in target coexist.
_WATCHES_UNIQUE = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_watches ON watches(
    symbol, level, timeframe, conditions, provider, COALESCE(provider_arg, '')
)
"""

_SCHEMA = f"""
{_WATCHES_DDL};
CREATE TABLE IF NOT EXISTS watch_state (
    watch_id   INTEGER PRIMARY KEY REFERENCES watches(id) ON DELETE CASCADE,
    state_json TEXT NOT NULL DEFAULT '{{}}',
    updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS daemon_meta (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    started_at INTEGER,
    last_cycle INTEGER,
    interval   REAL
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
    conn.execute(_WATCHES_UNIQUE)  # after _migrate: the index needs provider_arg
    conn.commit()


def _migrate(conn) -> None:
    for table, column, decl in (("watches", "provider_arg", "TEXT"),
                                ("daemon_meta", "interval", "REAL")):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            except sqlite3.OperationalError:
                pass  # a concurrent first-run process (e.g. the daemon) added it first
    _rebuild_watches_if_legacy(conn)


def _rebuild_watches_if_legacy(conn) -> None:
    """Pre-1.2 watches lack AUTOINCREMENT (deleted max ids get reused, so a
    stale daemon snapshot could retire the wrong watch) and bake provider_arg
    out of the unique key. Rebuild once, preserving ids and dedup state."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='watches'").fetchone()
    if row is None or "AUTOINCREMENT" in row["sql"]:
        return
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")  # keep watch_state rows through the swap
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='watches'").fetchone()
        if "AUTOINCREMENT" in row["sql"]:  # a concurrent process rebuilt first
            conn.rollback()
            return
        conn.execute(_WATCHES_DDL.replace("IF NOT EXISTS watches", "watches_new"))
        conn.execute("INSERT INTO watches_new(id, symbol, level, timeframe, conditions, provider, provider_arg, created_at) "
                     "SELECT id, symbol, level, timeframe, conditions, provider, provider_arg, created_at FROM watches")
        conn.execute("DROP TABLE watches")
        conn.execute("ALTER TABLE watches_new RENAME TO watches")
        conn.execute(_WATCHES_UNIQUE)
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def canonical_conditions(condition_names: list[str]) -> str:
    return json.dumps(sorted(condition_names))


def add_watch(conn, symbol: str, level: float, timeframe: str,
              condition_names: list[str], provider: str, provider_arg: str | None) -> tuple[int, bool]:
    """Atomically idempotent on the full unique key (incl. provider target).
    Returns (id, created)."""
    conds = canonical_conditions(condition_names)
    cur = conn.execute(
        "INSERT INTO watches(symbol, level, timeframe, conditions, provider, provider_arg, created_at) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
        (symbol, level, timeframe, conds, provider, provider_arg, int(time.time())),
    )
    conn.commit()
    created = cur.rowcount > 0
    row = conn.execute(
        "SELECT id FROM watches WHERE symbol=? AND level=? AND timeframe=? AND conditions=? AND provider=? "
        "AND COALESCE(provider_arg,'')=COALESCE(?,'')",
        (symbol, level, timeframe, conds, provider, provider_arg),
    ).fetchone()
    return row["id"], created


def retire_fired(conn, watch: Watch, remaining: list[str], state: dict) -> str:
    """Retire fired conditions in ONE transaction, guarded by the original
    conditions so a stale daemon snapshot never mutates a replaced watch.
    Returns 'deleted' | 'updated' | 'redundant' (identical watch already
    exists) | 'stale' (watch changed/removed underneath us)."""
    now = int(time.time())
    try:
        conn.execute("BEGIN IMMEDIATE")
        if not remaining:
            cur = conn.execute("DELETE FROM watches WHERE id=? AND conditions=?",
                               (watch.id, watch.conditions))
            conn.commit()
            return "deleted" if cur.rowcount else "stale"
        cur = conn.execute("UPDATE watches SET conditions=? WHERE id=? AND conditions=?",
                           (canonical_conditions(remaining), watch.id, watch.conditions))
        if cur.rowcount == 0:
            conn.rollback()
            return "stale"
        conn.execute(
            "INSERT INTO watch_state(watch_id, state_json, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(watch_id) DO UPDATE SET "
            "state_json=excluded.state_json, updated_at=excluded.updated_at",
            (watch.id, json.dumps(state), now),
        )
        conn.commit()
        return "updated"
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.execute("DELETE FROM watches WHERE id=? AND conditions=?", (watch.id, watch.conditions))
        conn.commit()
        return "redundant"


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


def remove_all(conn) -> int:
    cur = conn.execute("DELETE FROM watches")
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


def set_started(conn, interval: float) -> None:
    now = int(time.time())
    conn.execute(
        "INSERT INTO daemon_meta(id, started_at, last_cycle, interval) VALUES(1, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET started_at=excluded.started_at, interval=excluded.interval",
        (now, now, interval),
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
    row = conn.execute("SELECT started_at, last_cycle, interval FROM daemon_meta WHERE id=1").fetchone()
    return dict(row) if row else {}
