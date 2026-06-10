"""Aggregate statistics computed from the user's 1v1 games."""
import math
from collections import defaultdict
from datetime import datetime

from . import db


def _parse_dt(iso):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def _streaks(games):
    """games come newest-first; walk oldest-first to build streaks."""
    seq = [g["my_result"] for g in reversed(games)
           if g["my_result"] in ("Win", "Loss")]
    longest_win = longest_loss = 0
    cur = 0
    cur_type = None
    for r in seq:
        if r == cur_type:
            cur += 1
        else:
            cur_type = r
            cur = 1
        if r == "Win":
            longest_win = max(longest_win, cur)
        else:
            longest_loss = max(longest_loss, cur)
    return {
        "longest_win": longest_win,
        "longest_loss": longest_loss,
        "current": {"type": cur_type, "length": cur} if cur_type else None,
    }


def summary():
    games = db.my_games()
    total = len(games)
    wins = sum(1 for g in games if g["my_result"] == "Win")
    losses = sum(1 for g in games if g["my_result"] == "Loss")
    apms = [g["my_apm"] for g in games if g["my_apm"]]
    durations = [g["duration_seconds"] for g in games if g["duration_seconds"]]

    by_matchup = defaultdict(lambda: {"games": 0, "wins": 0})
    by_map = defaultdict(lambda: {"games": 0, "wins": 0})
    by_my_race = defaultdict(lambda: {"games": 0, "wins": 0})
    for g in games:
        if g["my_race"] and g["opp_race"]:
            key = f"{g['my_race'][0]}v{g['opp_race'][0]}"
            by_matchup[key]["games"] += 1
            if g["my_result"] == "Win":
                by_matchup[key]["wins"] += 1
        if g["map_name"]:
            by_map[g["map_name"]]["games"] += 1
            if g["my_result"] == "Win":
                by_map[g["map_name"]]["wins"] += 1
        if g["my_race"]:
            by_my_race[g["my_race"]]["games"] += 1
            if g["my_result"] == "Win":
                by_my_race[g["my_race"]]["wins"] += 1

    def fmt(d):
        out = []
        for k, v in d.items():
            wr = round(100 * v["wins"] / v["games"], 1) if v["games"] else 0
            out.append({"key": k, "games": v["games"], "wins": v["wins"],
                        "losses": v["games"] - v["wins"], "winrate": wr})
        out.sort(key=lambda x: -x["games"])
        return out

    return {
        "player_names": db.get_player_names(),
        "total_games": total,
        "wins": wins,
        "losses": losses,
        "winrate": round(100 * wins / total, 1) if total else 0,
        "avg_apm": round(sum(apms) / len(apms), 1) if apms else None,
        "avg_duration": round(sum(durations) / len(durations)) if durations else None,
        "by_matchup": fmt(by_matchup),
        "by_map": fmt(by_map),
        "by_my_race": fmt(by_my_race),
        "streaks": _streaks(games),
        "counts": db.counts(),
        "recent": games[:10],
    }


def map_breakdown():
    """Win rates per map, broken down by matchup."""
    games = db.my_games()
    rows = defaultdict(lambda: defaultdict(lambda: {"games": 0, "wins": 0}))
    matchups = set()
    for g in games:
        if not g.get("map_name") or g.get("my_result") not in ("Win", "Loss"):
            continue
        if not g.get("my_race") or not g.get("opp_race"):
            continue
        mu = f"{g['my_race'][0]}v{g['opp_race'][0]}"
        matchups.add(mu)
        cell = rows[g["map_name"]][mu]
        cell["games"] += 1
        if g["my_result"] == "Win":
            cell["wins"] += 1

    matchups = sorted(matchups)
    out = []
    for map_name, cells in rows.items():
        entry = {"map": map_name, "cells": {}}
        total_g = total_w = 0
        for mu in matchups:
            c = cells.get(mu)
            if c and c["games"]:
                entry["cells"][mu] = {
                    "games": c["games"], "wins": c["wins"],
                    "winrate": round(100 * c["wins"] / c["games"], 1),
                }
                total_g += c["games"]
                total_w += c["wins"]
        entry["total"] = {
            "games": total_g, "wins": total_w,
            "winrate": round(100 * total_w / total_g, 1) if total_g else 0,
        }
        out.append(entry)
    out.sort(key=lambda e: -e["total"]["games"])
    return {"matchups": matchups, "rows": out}


_LATEST_METRICS = [
    # (column, label, good direction, format)
    ("my_apm", "APM", "up", "num"),
    ("my_spm", "Screens / min", "up", "num"),
    ("my_supply_blocked", "Supply blocked", "down", "time"),
    ("my_unspent_minerals", "Avg unspent minerals", "down", "num"),
    ("my_unspent_gas", "Avg unspent gas", "down", "num"),
    ("my_collection_rate", "Collection rate", "up", "num"),
    ("duration_seconds", "Game length", None, "time"),
]


def latest_game():
    """Most recent game with each metric compared to the player's average."""
    games = db.my_games()
    if not games:
        return {"game": None, "metrics": []}
    latest = games[0]
    rest = games[1:] or games

    def avg(key):
        vals = [g.get(key) for g in rest if g.get(key) is not None]
        return (sum(vals) / len(vals)) if vals else None

    metrics = []
    for key, label, good, fmt in _LATEST_METRICS:
        value = latest.get(key)
        average = avg(key)
        delta_pct = None
        if value is not None and average:
            delta_pct = round(100 * (value - average) / average, 1)
        metrics.append({
            "key": key,
            "label": label,
            "value": value,
            "avg": round(average, 1) if average is not None else None,
            "delta_pct": delta_pct,
            "good": good,
            "fmt": fmt,
        })
    return {"game": latest, "metrics": metrics}


def head_to_head(name):
    """Full match history and record against one opponent name."""
    target = (name or "").lower()
    games = [g for g in db.my_games()
             if (g.get("opp_name") or "").lower() == target]
    wins = sum(1 for g in games if g["my_result"] == "Win")
    losses = sum(1 for g in games if g["my_result"] == "Loss")

    by_matchup = defaultdict(lambda: {"games": 0, "wins": 0})
    for g in games:
        if g.get("my_race") and g.get("opp_race"):
            mu = f"{g['my_race'][0]}v{g['opp_race'][0]}"
            by_matchup[mu]["games"] += 1
            if g["my_result"] == "Win":
                by_matchup[mu]["wins"] += 1
    matchups = [
        {"key": k, "games": v["games"], "wins": v["wins"],
         "losses": v["games"] - v["wins"],
         "winrate": round(100 * v["wins"] / v["games"], 1)}
        for k, v in sorted(by_matchup.items(), key=lambda kv: -kv[1]["games"])
    ]

    mmrs = [g["opp_mmr"] for g in games if g.get("opp_mmr")]
    return {
        "name": games[0]["opp_name"] if games else name,
        "total": len(games),
        "wins": wins,
        "losses": losses,
        "winrate": round(100 * wins / len(games), 1) if games else 0,
        "avg_opp_mmr": round(sum(mmrs) / len(mmrs)) if mmrs else None,
        "by_matchup": matchups,
        "games": games,
    }


def mmr_breakdown(bucket=200):
    """Win rates per matchup, grouped by opponent MMR bracket."""
    games = db.my_games()
    rows = defaultdict(lambda: defaultdict(lambda: {"games": 0, "wins": 0}))
    matchups = set()
    for g in games:
        mmr = g.get("opp_mmr")
        if not mmr or not g.get("my_race") or not g.get("opp_race"):
            continue
        if g.get("my_result") not in ("Win", "Loss"):
            continue
        low = int(mmr // bucket) * bucket
        mu = f"{g['my_race'][0]}v{g['opp_race'][0]}"
        matchups.add(mu)
        cell = rows[low][mu]
        cell["games"] += 1
        if g["my_result"] == "Win":
            cell["wins"] += 1

    matchups = sorted(matchups)
    out = []
    for low in sorted(rows.keys(), reverse=True):
        entry = {"low": low, "range": f"{low}\u2013{low + bucket - 1}", "cells": {}}
        total_g = total_w = 0
        for mu in matchups:
            c = rows[low].get(mu)
            if c and c["games"]:
                entry["cells"][mu] = {
                    "games": c["games"], "wins": c["wins"],
                    "winrate": round(100 * c["wins"] / c["games"], 1),
                }
                total_g += c["games"]
                total_w += c["wins"]
        entry["total"] = {
            "games": total_g, "wins": total_w,
            "winrate": round(100 * total_w / total_g, 1) if total_g else 0,
        }
        out.append(entry)
    return {"matchups": matchups, "rows": out, "bucket": bucket}


def duration_distribution(max_minutes=30, sigma=1.5, min_games=20):
    """Kernel-smoothed win rate and game count by game duration, per matchup."""
    games = db.my_games()
    by_mu = defaultdict(list)
    for g in games:
        if not g.get("duration_seconds") or g.get("my_result") not in ("Win", "Loss"):
            continue
        if not g.get("my_race") or not g.get("opp_race"):
            continue
        mu = f"{g['my_race'][0]}v{g['opp_race'][0]}"
        minutes = min(g["duration_seconds"] / 60, max_minutes)
        by_mu[mu].append((minutes, 1 if g["my_result"] == "Win" else 0))

    density_norm = sigma * math.sqrt(2 * math.pi)
    out = []
    for mu, pts in sorted(by_mu.items()):
        if len(pts) < min_games:
            continue
        series = []
        for x in range(0, max_minutes + 1):
            wsum = gsum = 0.0
            for m, win in pts:
                w = math.exp(-((m - x) ** 2) / (2 * sigma * sigma))
                wsum += w * win
                gsum += w
            if gsum >= 3:  # skip durations with too little effective data
                series.append({
                    "m": x,
                    "winrate": round(100 * wsum / gsum, 1),
                    "count": round(gsum / density_norm, 1),  # games per minute
                })
        if len(series) >= 2:
            out.append({"key": mu, "games": len(pts), "points": series})
    return {"matchups": out}


def trends():
    games = [g for g in db.my_games() if _parse_dt(g["played_at"])]
    games.sort(key=lambda g: g["played_at"])

    # Win rate per ISO week
    weeks = defaultdict(lambda: {"games": 0, "wins": 0})
    for g in games:
        dt = _parse_dt(g["played_at"])
        iso = dt.isocalendar()
        key = f"{iso[0]}-W{iso[1]:02d}"
        weeks[key]["games"] += 1
        if g["my_result"] == "Win":
            weeks[key]["wins"] += 1
    winrate_weekly = [
        {"week": k, "games": v["games"],
         "winrate": round(100 * v["wins"] / v["games"], 1)}
        for k, v in sorted(weeks.items())
    ]

    apm_series = [
        {"played_at": g["played_at"], "apm": g["my_apm"],
         "result": g["my_result"], "matchup": g["matchup"]}
        for g in games if g["my_apm"]
    ]
    duration_series = [
        {"played_at": g["played_at"],
         "minutes": round(g["duration_seconds"] / 60, 1)}
        for g in games if g["duration_seconds"]
    ]
    games_series = [
        {"played_at": g["played_at"], "win": 1 if g["my_result"] == "Win" else 0}
        for g in games if g["my_result"] in ("Win", "Loss")
    ]
    return {
        "winrate_weekly": winrate_weekly,
        "apm_series": apm_series,
        "duration_series": duration_series,
        "games_series": games_series,
    }
