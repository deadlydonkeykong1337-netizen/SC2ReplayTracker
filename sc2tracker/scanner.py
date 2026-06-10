"""Scan replay folders, import new files, and watch for freshly played games."""
import os
import threading
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import db, parser


class ScanState:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.total = 0
        self.done = 0
        self.last_error = None
        self.last_finished = None

    def snapshot(self):
        with self.lock:
            return {
                "running": self.running,
                "total": self.total,
                "done": self.done,
                "last_error": self.last_error,
                "last_finished": self.last_finished,
            }


state = ScanState()


def _find_replay_files(dirs):
    files = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, names in os.walk(d):
            for n in names:
                if n.lower().endswith(".sc2replay"):
                    files.append(os.path.join(root, n))
    return files


def import_file(path):
    """Parse and store a single replay. Returns True if newly imported."""
    try:
        data, players = parser.parse_replay(path)
    except Exception as e:
        db.insert_replay(parser.error_record(path, e), [])
        return False
    if data["file_hash"] and db.hash_exists(data["file_hash"]):
        return False
    return db.insert_replay(data, players) is not None


def scan_all():
    """Full scan of configured folders. Runs in a worker thread."""
    with state.lock:
        if state.running:
            return
        state.running = True
        state.total = 0
        state.done = 0
        state.last_error = None

    try:
        dirs = db.get_replay_dirs()
        known = db.known_paths()
        files = [f for f in _find_replay_files(dirs) if f not in known]
        with state.lock:
            state.total = len(files)
        for f in files:
            import_file(f)
            with state.lock:
                state.done += 1
        # First run: figure out who the user is
        if not db.get_player_names():
            names = db.auto_detect_player_names()
            if names:
                db.set_setting("player_names", names)
    except Exception as e:
        with state.lock:
            state.last_error = str(e)
    finally:
        with state.lock:
            state.running = False
            state.last_finished = time.time()


def start_scan_async():
    t = threading.Thread(target=scan_all, daemon=True)
    t.start()
    return t


class _NewReplayHandler(FileSystemEventHandler):
    def _handle(self, path):
        if not path.lower().endswith(".sc2replay"):
            return
        # SC2 may still be writing the file; wait until its size is stable.
        def worker():
            last = -1
            for _ in range(30):
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = -1
                if size > 0 and size == last:
                    break
                last = size
                time.sleep(1)
            import_file(path)
        threading.Thread(target=worker, daemon=True).start()

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle(event.dest_path)


_observer = None


def start_watcher():
    """Watch all configured replay dirs for new games. Safe to call again
    after settings change (restarts the observer)."""
    global _observer
    if _observer is not None:
        _observer.stop()
        _observer = None
    dirs = [d for d in db.get_replay_dirs() if os.path.isdir(d)]
    if not dirs:
        return
    obs = Observer()
    handler = _NewReplayHandler()
    for d in dirs:
        obs.schedule(handler, d, recursive=True)
    obs.daemon = True
    obs.start()
    _observer = obs
