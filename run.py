"""SC2 Replay Tracker - desktop entry point.

Usage:
    python run.py            # native desktop window (pywebview / WebView2)
    python run.py --browser  # open in default browser instead
"""
import argparse
import os
import socket
import sys
import threading
import time

# Under pythonw.exe there is no console: stdout/stderr are None and any
# write (e.g. uvicorn logging) raises. Redirect them to devnull.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import uvicorn

from sc2tracker.config import HOST, PORT


def start_server():
    config = uvicorn.Config("sc2tracker.api:app", host=HOST, port=PORT,
                            log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server


def wait_for_port(timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", action="store_true",
                    help="open in default browser instead of a native window")
    args = ap.parse_args()

    start_server()
    if not wait_for_port():
        raise SystemExit("Server failed to start on port %d" % PORT)

    url = f"http://{HOST}:{PORT}"
    if args.browser:
        import webbrowser
        webbrowser.open(url)
        print(f"SC2 Replay Tracker running at {url}  (Ctrl+C to quit)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    else:
        import webview
        webview.create_window("SC2 Replay Tracker", url,
                              width=1280, height=860, min_size=(960, 640))
        webview.start()


if __name__ == "__main__":
    main()
