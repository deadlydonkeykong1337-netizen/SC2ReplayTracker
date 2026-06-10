"""Extract structured data from .SC2Replay files using sc2reader."""
import hashlib
import os

import sc2reader
from sc2reader.engine.plugins import APMTracker

sc2reader.engine.register_plugin(APMTracker())

# Units that pollute build orders (auto-spawned, projections, ability effects)
_BO_EXCLUDE = (
    "Larva", "Egg", "Broodling", "Locust", "MULE", "Interceptor",
    "AutoTurret", "Beacon", "Changeling", "InfestedTerran", "Cocoon",
    "CreepTumor", "Phoenix-Anion",  # anion pulse variants
    "AdeptPhaseShift", "DisruptorPhased", "KD8Charge", "ParasiticBomb",
    "OracleStasisTrap",
)
_BO_MAX_SECONDS = 480  # first 8 minutes of game time
_BO_MAX_ENTRIES = 80


def file_sha1(path, chunk=1 << 20):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _build_order_for(replay, player):
    entries = []
    try:
        events = replay.tracker_events
    except AttributeError:
        return entries
    for ev in events:
        name = type(ev).__name__
        if name not in ("UnitBornEvent", "UnitInitEvent"):
            continue
        if ev.second == 0:  # starting workers / main building
            continue
        if ev.second > _BO_MAX_SECONDS or len(entries) >= _BO_MAX_ENTRIES:
            break
        unit = getattr(ev, "unit", None)
        if unit is None or unit.owner is None or unit.owner.pid != player.pid:
            continue
        if getattr(unit, "hallucinated", False):
            continue
        uname = unit.name or ""
        if any(x in uname for x in _BO_EXCLUDE):
            continue
        entries.append({"second": ev.second, "name": uname})
    return entries


def _player_metrics(replay, player):
    """Performance metrics: screens/min, supply block time, economy stats."""
    metrics = {
        "spm": None,
        "supply_blocked_seconds": None,
        "avg_unspent_minerals": None,
        "avg_unspent_gas": None,
        "collection_rate": None,
        "timeseries": [],
    }
    try:
        real_seconds = replay.real_length.seconds
        game_seconds = replay.game_length.seconds
    except Exception:
        return metrics
    if not real_seconds:
        return metrics
    speed = (game_seconds / real_seconds) if real_seconds else 1.4

    # Screens per minute: camera events that actually moved the view
    try:
        moves = 0
        last = None
        for ev in replay.game_events:
            if type(ev).__name__ != "CameraEvent":
                continue
            p = getattr(ev, "player", None)
            if p is None or getattr(p, "pid", None) != player.pid:
                continue
            pos = (ev.x, ev.y)
            if last is None or abs(pos[0] - last[0]) + abs(pos[1] - last[1]) > 6:
                moves += 1
                last = pos
        metrics["spm"] = round(moves / (real_seconds / 60), 1)
    except Exception:
        pass

    # Economy + supply block + in-game-style graphs from PlayerStatsEvents
    # (one sample per 10 game seconds)
    try:
        minerals, gas, rates = [], [], []
        blocked_samples = 0
        timeseries = []
        for ev in replay.tracker_events:
            if type(ev).__name__ != "PlayerStatsEvent":
                continue
            if getattr(ev, "pid", None) != player.pid:
                continue
            rate = ev.minerals_collection_rate + ev.vespene_collection_rate
            minerals.append(ev.minerals_current)
            gas.append(ev.vespene_current)
            rates.append(rate)
            if ev.food_made < 200 and ev.food_used >= ev.food_made:
                blocked_samples += 1
            army = ((getattr(ev, "minerals_used_active_forces", 0) or 0)
                    + (getattr(ev, "vespene_used_active_forces", 0) or 0))
            tech = ((getattr(ev, "minerals_used_current_technology", 0) or 0)
                    + (getattr(ev, "vespene_used_current_technology", 0) or 0))
            timeseries.append({
                "t": round(ev.second / speed),  # real seconds
                "army": army,
                "income": rate,
                "tech": tech,
                "workers": getattr(ev, "workers_active_count", None),
            })
        metrics["timeseries"] = timeseries
        if minerals:
            metrics["avg_unspent_minerals"] = round(sum(minerals) / len(minerals))
            metrics["avg_unspent_gas"] = round(sum(gas) / len(gas))
            metrics["collection_rate"] = round(sum(rates) / len(rates))
            metrics["supply_blocked_seconds"] = round(blocked_samples * 10 / speed)
    except Exception:
        pass
    return metrics


# Fight detection: cluster unit deaths in time + space
_FIGHT_GAP = 15        # max game-seconds between deaths in the same fight
_FIGHT_RADIUS = 30     # max map distance from the fight's center
_FIGHT_MIN_DEATHS = 3
_FIGHT_MIN_VALUE = 500  # total resources destroyed (both players)


def _detect_fights(replay, speed):
    """Cluster unit deaths into engagements. Returns a list of fights with
    per-player losses (resource value + unit counts) and the trade winner."""
    deaths = []
    try:
        events = replay.tracker_events
    except AttributeError:
        return []
    for ev in events:
        if type(ev).__name__ != "UnitDiedEvent":
            continue
        unit = getattr(ev, "unit", None)
        if unit is None or unit.owner is None:
            continue
        if getattr(unit, "hallucinated", False):
            continue
        value = ((getattr(unit, "minerals", 0) or 0)
                 + (getattr(unit, "vespene", 0) or 0))
        if value <= 0:  # larvae, eggs, broodlings, MULEs, etc.
            continue
        deaths.append({
            "second": ev.second,
            "x": getattr(ev, "x", 0) or 0,
            "y": getattr(ev, "y", 0) or 0,
            "pid": unit.owner.pid,
            "name": unit.name or "?",
            "value": value,
        })

    clusters = []
    for d in deaths:  # tracker events are already time-ordered
        placed = False
        for c in clusters:
            if d["second"] - c["last"] > _FIGHT_GAP:
                continue
            cx, cy = c["sx"] / c["n"], c["sy"] / c["n"]
            if (d["x"] - cx) ** 2 + (d["y"] - cy) ** 2 > _FIGHT_RADIUS ** 2:
                continue
            c["items"].append(d)
            c["last"] = d["second"]
            c["n"] += 1
            c["sx"] += d["x"]
            c["sy"] += d["y"]
            c["value"] += d["value"]
            placed = True
            break
        if not placed:
            clusters.append({
                "items": [d], "start": d["second"], "last": d["second"],
                "n": 1, "sx": d["x"], "sy": d["y"], "value": d["value"],
            })

    fights = []
    for c in clusters:
        if c["n"] < _FIGHT_MIN_DEATHS or c["value"] < _FIGHT_MIN_VALUE:
            continue
        losses = {}
        for d in c["items"]:
            side = losses.setdefault(str(d["pid"]), {"value": 0, "units": {}})
            side["value"] += d["value"]
            side["units"][d["name"]] = side["units"].get(d["name"], 0) + 1
        winner = None
        pids = list(losses)
        if len(pids) == 2:
            a, b = pids
            if losses[a]["value"] < losses[b]["value"]:
                winner = int(a)
            elif losses[b]["value"] < losses[a]["value"]:
                winner = int(b)
        fights.append({
            "start": round(c["start"] / speed),
            "end": round(c["last"] / speed),
            "losses": losses,
            "winner_pid": winner,
        })
    return fights


def _trade_efficiency(fights, pid, opp_pid):
    """Resources destroyed / resources lost across all detected fights."""
    lost = sum(f["losses"].get(str(pid), {}).get("value", 0) for f in fights)
    killed = sum(f["losses"].get(str(opp_pid), {}).get("value", 0) for f in fights)
    if lost <= 0:
        return 9.99 if killed > 0 else None
    return round(min(killed / lost, 9.99), 2)


def _matchup(replay):
    try:
        if replay.type != "1v1" or len(replay.players) != 2:
            teams = []
            for t in replay.teams:
                teams.append("".join(p.play_race[0] for p in t.players))
            return "v".join(teams)
        a, b = replay.players
        return f"{a.play_race[0]}v{b.play_race[0]}"
    except Exception:
        return None


def parse_replay(path):
    """Returns (replay_dict, players_list). Raises on unreadable files."""
    try:
        replay = sc2reader.load_replay(path, load_level=4)
        full = True
    except Exception:
        # Fall back to metadata-only parse (no APM / build orders)
        replay = sc2reader.load_replay(path, load_level=2)
        full = False

    played_at = None
    if getattr(replay, "end_time", None):
        played_at = replay.end_time.isoformat()
    elif getattr(replay, "start_time", None):
        played_at = replay.start_time.isoformat()

    duration = None
    try:
        duration = replay.real_length.seconds
    except Exception:
        try:
            duration = replay.game_length.seconds
        except Exception:
            pass

    speed = 1.4
    try:
        if duration:
            speed = replay.game_length.seconds / duration
    except Exception:
        pass
    fights = _detect_fights(replay, speed) if full else []

    data = {
        "path": path,
        "fights": fights,
        "filename": os.path.basename(path),
        "file_hash": file_sha1(path),
        "map_name": getattr(replay, "map_name", None),
        "played_at": played_at,
        "duration_seconds": duration,
        "game_type": getattr(replay, "type", None),
        "category": getattr(replay, "category", None),
        "expansion": getattr(replay, "expansion", None),
        "version": getattr(replay, "release_string", None),
        "region": getattr(replay, "region", None),
        "matchup": _matchup(replay),
        "parse_error": None,
    }

    players = []
    for p in getattr(replay, "players", []):
        apm = None
        if full:
            apm = getattr(p, "avg_apm", None)
            if apm is not None:
                apm = round(float(apm), 1)
        mmr = None
        try:
            mmr = (p.init_data or {}).get("scaled_rating")
            if mmr is not None and mmr <= 0:
                mmr = None  # AI / custom games report 0
        except Exception:
            pass
        metrics = _player_metrics(replay, p) if full else {}
        players.append({
            "name": p.name,
            "pid": p.pid,
            "mmr": mmr,
            "race": getattr(p, "play_race", None),
            "team": getattr(p, "team_id", None),
            "result": getattr(p, "result", None),
            "apm": apm,
            "is_human": getattr(p, "is_human", True),
            "highest_league": getattr(p, "highest_league", None),
            "build_order": _build_order_for(replay, p) if full else [],
            **metrics,
        })

    if len(players) == 2 and fights:
        a, b = players
        a["trade_efficiency"] = _trade_efficiency(fights, a["pid"], b["pid"])
        b["trade_efficiency"] = _trade_efficiency(fights, b["pid"], a["pid"])
    return data, players


def error_record(path, error):
    """Minimal record so a broken file is remembered and not re-parsed forever."""
    try:
        file_hash = file_sha1(path)
    except OSError:
        file_hash = None
    return {
        "path": path,
        "filename": os.path.basename(path),
        "file_hash": file_hash,
        "fights": [],
        "map_name": None,
        "played_at": None,
        "duration_seconds": None,
        "game_type": None,
        "category": None,
        "expansion": None,
        "version": None,
        "region": None,
        "matchup": None,
        "parse_error": str(error)[:500],
    }
