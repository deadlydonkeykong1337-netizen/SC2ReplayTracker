# SC2 Replay Tracker

A local desktop app (like sc2replaystats.com, but private and offline) that
parses your StarCraft II replay files and shows your statistics. Everything
runs and stays on your own computer — no uploads, no accounts.

## Features

- Automatically finds your replay folders (`Documents\StarCraft II\Accounts\...\Replays\Multiplayer`)
- Watches for new replays and imports them seconds after you finish a game
- Dashboard: win rate, APM, game length, per-matchup / per-race stats,
  win/loss streaks
- Latest-game performance breakdown (APM, screens/min, supply block time,
  unspent resources, collection rate) compared to your personal averages
- Win rates by opponent MMR bracket (e.g. PvZ vs 4600–4799 MMR opponents)
- Per-map win rates broken down by matchup
- Replay browser with filters (matchup, map, result, search) and per-replay
  detail view with both players' build orders
- In-game style graphs per replay: Army Value, Collection Rate, Upgrade
  Spending, Workers Active
- Head-to-head: click any opponent's name to see your full match history
  against them
- Trends: rolling win rate / APM / game length, plus win-rate and game-count
  distributions by game duration
- "Open file location" button to jump to the replay file on disk
- Everything stored locally in SQLite (`data/sc2tracker.sqlite3`)

## How to download and run (Windows)

1. **Install Python** from [python.org/downloads](https://www.python.org/downloads/).
   During installation, make sure to tick **"Add Python to PATH"**.
2. **Download the app**: on
   [this repository's page](https://github.com/deadlydonkeykong1337-netizen/SC2ReplayTracker),
   click the green **Code** button → **Download ZIP**, then right-click the
   downloaded ZIP → **Extract All** (anywhere you like, e.g. your user folder).

   *Or, if you have git:*
   `git clone https://github.com/deadlydonkeykong1337-netizen/SC2ReplayTracker.git`
3. **Run `setup.bat`** (double-click it) in the extracted folder. This is a
   one-time step that installs everything the app needs. Wait for "Done!".
4. **Run `Start SC2 Tracker.bat`** (double-click) to launch the app.
   Tip: right-click it → *Send to* → *Desktop (create shortcut)* for a
   desktop icon.

On first launch the app finds your StarCraft II replay folder automatically,
imports all your replays (a few minutes for large collections — progress is
shown in the header), and auto-detects your player name. You can adjust the
replay folders and player names in the **Settings** tab.

## Updating to the latest version

When a new version is released, the app shows an **"Update available"** flag in
the top-right corner (it checks GitHub automatically).

To install the update:

1. **Close the app.**
2. Run **`update.bat`** in the app folder (double-click it).
3. Start the app again.

`update.bat` pulls the latest code (via git if you cloned, otherwise by
downloading the newest version from GitHub) and updates dependencies. Your
stats database (`data\`) is preserved.

## Running from the command line (optional)

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run.py            # native desktop window
.venv\Scripts\python run.py --browser  # or open in your browser instead
```

## Tech

- Python, [sc2reader](https://github.com/ggtracker/sc2reader) for replay parsing
- FastAPI + SQLite backend
- pywebview (Edge WebView2) desktop shell
- Dependency-free vanilla JS frontend

## Releasing updates (for the maintainer)

The in-app update check compares the `VERSION` file in this repo against each
user's local copy. **When you push changes you want others to get, bump the
number in `VERSION`** (e.g. `0.2.0` -> `0.2.1`) and commit it. Users will then
see the "Update available" flag and can run `update.bat`.

The repo the app checks against is set in `sc2tracker/config.py`
(`GITHUB_REPO` / `GITHUB_BRANCH`).
