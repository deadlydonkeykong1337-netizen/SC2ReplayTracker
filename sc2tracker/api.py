"""FastAPI backend: JSON API + static frontend."""
import os
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, scanner, stats, updates

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="SC2 Replay Tracker")


SCHEMA_VERSION = 4


@app.on_event("startup")
def _startup():
    db.init_db()
    # New metrics require re-parsing: clear imported data once per schema bump.
    if db.get_setting("schema_version") != SCHEMA_VERSION:
        db.clear_replays()
        db.set_setting("schema_version", SCHEMA_VERSION)
    scanner.start_scan_async()
    scanner.start_watcher()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/summary")
def api_summary():
    return stats.summary()


@app.get("/api/trends")
def api_trends():
    return stats.trends()


@app.get("/api/latest")
def api_latest():
    return stats.latest_game()


@app.get("/api/mmr")
def api_mmr(bucket: int = 200):
    return stats.mmr_breakdown(bucket=max(50, min(bucket, 1000)))


@app.get("/api/mapstats")
def api_mapstats():
    return stats.map_breakdown()


@app.get("/api/vs")
def api_vs(name: str):
    return stats.head_to_head(name)


@app.get("/api/duration")
def api_duration():
    return stats.duration_distribution()


@app.post("/api/reveal/{replay_id}")
def api_reveal(replay_id: int):
    detail = db.replay_detail(replay_id)
    if detail is None:
        raise HTTPException(404, "Replay not found")
    path = detail["path"]
    if not os.path.exists(path):
        raise HTTPException(404, "File no longer exists on disk")
    # Opens Explorer with the replay file selected
    subprocess.Popen(["explorer", f"/select,{path}"])
    return {"ok": True}


@app.get("/api/replays")
def api_replays(limit: int = 50, offset: int = 0, matchup: str = None,
                map_name: str = None, result: str = None, search: str = None):
    rows, total = db.list_replays(
        limit=min(limit, 200), offset=offset, matchup=matchup or None,
        map_name=map_name or None, result=result or None, search=search or None)
    return {"replays": rows, "total": total}


@app.get("/api/replay/{replay_id}")
def api_replay(replay_id: int):
    detail = db.replay_detail(replay_id)
    if detail is None:
        raise HTTPException(404, "Replay not found")
    return detail


@app.get("/api/filters")
def api_filters():
    return db.distinct_filters()


class Settings(BaseModel):
    replay_dirs: list[str]
    player_names: list[str]
    excluded_maps: list[str] = []


@app.get("/api/settings")
def api_get_settings():
    return {
        "replay_dirs": db.get_replay_dirs(),
        "player_names": db.get_player_names(),
        "excluded_maps": db.get_excluded_maps(),
        "dirs_exist": {d: os.path.isdir(d) for d in db.get_replay_dirs()},
    }


@app.post("/api/settings")
def api_set_settings(s: Settings):
    db.set_setting("replay_dirs", [d.strip() for d in s.replay_dirs if d.strip()])
    db.set_setting("player_names", [n.strip() for n in s.player_names if n.strip()])
    db.set_setting("excluded_maps", [m.strip() for m in s.excluded_maps if m.strip()])
    scanner.start_watcher()
    return {"ok": True}


@app.post("/api/scan")
def api_scan():
    scanner.start_scan_async()
    return {"ok": True}


@app.get("/api/scan/status")
def api_scan_status():
    return scanner.state.snapshot()


@app.get("/api/update")
def api_update():
    return updates.check()


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
