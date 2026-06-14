"""Paths and default configuration."""
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "sc2tracker.sqlite3"

HOST = "127.0.0.1"
PORT = 8642

# GitHub repository used for in-app update checks and update.bat.
# Change these if you fork/rename the repo.
GITHUB_REPO = "deadlydonkeykong1337-netizen/SC2ReplayTracker"
GITHUB_BRANCH = "main"


def app_version():
    """Local app version, read from the VERSION file at the project root."""
    try:
        return (PROJECT_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


def default_replay_dirs():
    """Find likely SC2 replay folders on this machine."""
    home = Path.home()
    candidates = [
        home / "Documents" / "StarCraft II" / "Accounts",
        home / "OneDrive" / "Documents" / "StarCraft II" / "Accounts",
    ]
    dirs = []
    for base in candidates:
        if not base.is_dir():
            continue
        # Accounts/<account-id>/<region-toon>/Replays/Multiplayer
        for multi in base.glob("*/*/Replays/Multiplayer"):
            if multi.is_dir():
                dirs.append(str(multi))
    return dirs


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
