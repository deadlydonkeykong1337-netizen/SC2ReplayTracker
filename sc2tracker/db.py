"""SQLite data layer. Per-call connections with WAL so multiple threads are safe."""
import json
import sqlite3
from datetime import datetime, timezone

from .config import DB_PATH, ensure_data_dir, default_replay_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS replays (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    filename TEXT,
    file_hash TEXT,
    map_name TEXT,
    played_at TEXT,
    duration_seconds INTEGER,
    game_type TEXT,
    category TEXT,
    expansion TEXT,
    version TEXT,
    region TEXT,
    matchup TEXT,
    fights TEXT,
    parse_error TEXT,
    imported_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_replays_played_at ON replays(played_at);
CREATE INDEX IF NOT EXISTS idx_replays_hash ON replays(file_hash);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    replay_id INTEGER NOT NULL REFERENCES replays(id) ON DELETE CASCADE,
    name TEXT,
    race TEXT,
    team INTEGER,
    result TEXT,
    apm REAL,
    is_human INTEGER,
    highest_league INTEGER,
    build_order TEXT,
    spm REAL,
    supply_blocked_seconds REAL,
    avg_unspent_minerals REAL,
    avg_unspent_gas REAL,
    collection_rate REAL,
    mmr REAL,
    timeseries TEXT,
    pid INTEGER,
    trade_efficiency REAL
);
CREATE INDEX IF NOT EXISTS idx_players_replay ON players(replay_id);
CREATE INDEX IF NOT EXISTS idx_players_name ON players(name);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect():
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_PLAYER_MIGRATIONS = [
    "ALTER TABLE players ADD COLUMN spm REAL",
    "ALTER TABLE players ADD COLUMN supply_blocked_seconds REAL",
    "ALTER TABLE players ADD COLUMN avg_unspent_minerals REAL",
    "ALTER TABLE players ADD COLUMN avg_unspent_gas REAL",
    "ALTER TABLE players ADD COLUMN collection_rate REAL",
    "ALTER TABLE players ADD COLUMN mmr REAL",
    "ALTER TABLE players ADD COLUMN timeseries TEXT",
    "ALTER TABLE players ADD COLUMN pid INTEGER",
    "ALTER TABLE players ADD COLUMN trade_efficiency REAL",
    "ALTER TABLE replays ADD COLUMN fights TEXT",
]


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        for stmt in _PLAYER_MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists


def clear_replays():
    """Drop all imported data (settings are kept) so files get re-parsed."""
    with connect() as conn:
        conn.execute("DELETE FROM players")
        conn.execute("DELETE FROM replays")


# ---------- settings ----------

def get_setting(key, default=None):
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    return json.loads(row["value"])


def set_setting(key, value):
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )


def get_replay_dirs():
    dirs = get_setting("replay_dirs")
    if not dirs:
        dirs = default_replay_dirs()
        if dirs:
            set_setting("replay_dirs", dirs)
    return dirs or []


def get_player_names():
    return get_setting("player_names") or []


# ---------- replays ----------

def known_paths():
    with connect() as conn:
        rows = conn.execute("SELECT path FROM replays").fetchall()
    return {r["path"] for r in rows}


def hash_exists(file_hash):
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM replays WHERE file_hash=? LIMIT 1", (file_hash,)
        ).fetchone()
    return row is not None


def insert_replay(data, players):
    """data: dict of replay columns, players: list of player dicts."""
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO replays
               (path, filename, file_hash, map_name, played_at, duration_seconds,
                game_type, category, expansion, version, region, matchup,
                fights, parse_error, imported_at)
               VALUES (:path, :filename, :file_hash, :map_name, :played_at,
                       :duration_seconds, :game_type, :category, :expansion,
                       :version, :region, :matchup, :fights, :parse_error,
                       :imported_at)""",
            {**data, "fights": json.dumps(data.get("fights") or []),
             "imported_at": now},
        )
        if cur.rowcount == 0:
            return None
        replay_id = cur.lastrowid
        for p in players:
            conn.execute(
                """INSERT INTO players
                   (replay_id, name, race, team, result, apm, is_human,
                    highest_league, build_order, spm, supply_blocked_seconds,
                    avg_unspent_minerals, avg_unspent_gas, collection_rate,
                    mmr, timeseries, pid, trade_efficiency)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    replay_id,
                    p.get("name"),
                    p.get("race"),
                    p.get("team"),
                    p.get("result"),
                    p.get("apm"),
                    1 if p.get("is_human") else 0,
                    p.get("highest_league"),
                    json.dumps(p.get("build_order") or []),
                    p.get("spm"),
                    p.get("supply_blocked_seconds"),
                    p.get("avg_unspent_minerals"),
                    p.get("avg_unspent_gas"),
                    p.get("collection_rate"),
                    p.get("mmr"),
                    json.dumps(p.get("timeseries") or []),
                    p.get("pid"),
                    p.get("trade_efficiency"),
                ),
            )
        return replay_id


def auto_detect_player_names():
    """Most frequent human player name across 1v1 games is almost surely the user."""
    with connect() as conn:
        row = conn.execute(
            """SELECT p.name, COUNT(*) AS n FROM players p
               JOIN replays r ON r.id = p.replay_id
               WHERE p.is_human = 1 AND r.parse_error IS NULL
               GROUP BY p.name ORDER BY n DESC LIMIT 1"""
        ).fetchone()
    return [row["name"]] if row else []


def my_games(names=None):
    """Rows joining my player record with its replay and the opponent (1v1)."""
    names = names if names is not None else get_player_names()
    if not names:
        return []
    qmarks = ",".join("?" for _ in names)
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT r.id AS replay_id, r.map_name, r.played_at,
                       r.duration_seconds, r.game_type, r.category, r.matchup,
                       me.name AS my_name, me.race AS my_race,
                       me.result AS my_result, me.apm AS my_apm,
                       me.spm AS my_spm,
                       me.supply_blocked_seconds AS my_supply_blocked,
                       me.avg_unspent_minerals AS my_unspent_minerals,
                       me.avg_unspent_gas AS my_unspent_gas,
                       me.collection_rate AS my_collection_rate,
                       me.trade_efficiency AS my_trade_eff,
                       me.mmr AS my_mmr,
                       opp.name AS opp_name, opp.race AS opp_race,
                       opp.apm AS opp_apm, opp.mmr AS opp_mmr
                FROM replays r
                JOIN players me ON me.replay_id = r.id AND me.name IN ({qmarks})
                LEFT JOIN players opp ON opp.replay_id = r.id AND opp.id != me.id
                WHERE r.parse_error IS NULL AND r.game_type = '1v1'
                ORDER BY r.played_at DESC""",
            names,
        ).fetchall()
    return [dict(r) for r in rows]


def list_replays(limit=50, offset=0, matchup=None, map_name=None,
                 result=None, search=None):
    names = get_player_names()
    where = ["r.parse_error IS NULL"]
    params = []
    join_me = ""
    opp_select = "NULL AS opp_name"
    if names:
        qmarks = ",".join("?" for _ in names)
        join_me = (f"LEFT JOIN players me ON me.replay_id = r.id AND me.name IN ({qmarks}) "
                   "LEFT JOIN players opp ON opp.replay_id = r.id AND opp.id != me.id")
        opp_select = "opp.name AS opp_name"
        params.extend(names)
    if matchup:
        where.append("r.matchup = ?")
        params.append(matchup)
    if map_name:
        where.append("r.map_name = ?")
        params.append(map_name)
    if result and names:
        where.append("me.result = ?")
        params.append(result)
    if search:
        where.append(
            "(r.map_name LIKE ? OR EXISTS (SELECT 1 FROM players px "
            " WHERE px.replay_id = r.id AND px.name LIKE ?))"
        )
        params.extend([f"%{search}%", f"%{search}%"])

    sql = f"""SELECT r.id, r.filename, r.map_name, r.played_at, r.duration_seconds,
                     r.game_type, r.matchup, {opp_select},
                     {"me.result AS my_result, me.race AS my_race, me.apm AS my_apm"
                      if names else
                      "NULL AS my_result, NULL AS my_race, NULL AS my_apm"}
              FROM replays r {join_me}
              WHERE {' AND '.join(where)}
              GROUP BY r.id
              ORDER BY r.played_at DESC
              LIMIT ? OFFSET ?"""
    with connect() as conn:
        rows = conn.execute(sql, params + [limit, offset]).fetchall()
        total = conn.execute(
            f"""SELECT COUNT(DISTINCT r.id) AS n FROM replays r {join_me}
                WHERE {' AND '.join(where)}""",
            params,
        ).fetchone()["n"]
    return [dict(r) for r in rows], total


def replay_detail(replay_id):
    with connect() as conn:
        rep = conn.execute("SELECT * FROM replays WHERE id=?", (replay_id,)).fetchone()
        if rep is None:
            return None
        players = conn.execute(
            "SELECT * FROM players WHERE replay_id=? ORDER BY team, id", (replay_id,)
        ).fetchall()
    out = dict(rep)
    out["fights"] = json.loads(out.get("fights") or "[]")
    out["players"] = []
    for p in players:
        d = dict(p)
        d["build_order"] = json.loads(d.get("build_order") or "[]")
        d["timeseries"] = json.loads(d.get("timeseries") or "[]")
        out["players"].append(d)
    return out


def distinct_filters():
    with connect() as conn:
        maps = [r["map_name"] for r in conn.execute(
            "SELECT DISTINCT map_name FROM replays WHERE parse_error IS NULL "
            "AND map_name IS NOT NULL ORDER BY map_name").fetchall()]
        matchups = [r["matchup"] for r in conn.execute(
            "SELECT DISTINCT matchup FROM replays WHERE parse_error IS NULL "
            "AND matchup IS NOT NULL ORDER BY matchup").fetchall()]
    return {"maps": maps, "matchups": matchups}


def counts():
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM replays").fetchone()["n"]
        errors = conn.execute(
            "SELECT COUNT(*) AS n FROM replays WHERE parse_error IS NOT NULL"
        ).fetchone()["n"]
    return {"total": total, "errors": errors}
