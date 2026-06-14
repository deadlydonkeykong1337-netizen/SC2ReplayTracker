"""In-app update check: compares the local VERSION file with the one on GitHub."""
import urllib.request

from .config import GITHUB_REPO, GITHUB_BRANCH, app_version


def _version_tuple(v):
    parts = []
    for chunk in str(v).split("."):
        num = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts)


def _remote_version():
    url = (f"https://raw.githubusercontent.com/{GITHUB_REPO}/"
           f"{GITHUB_BRANCH}/VERSION")
    req = urllib.request.Request(url, headers={"User-Agent": "sc2tracker"})
    with urllib.request.urlopen(req, timeout=6) as resp:
        return resp.read().decode("utf-8").strip()


def check():
    current = app_version()
    repo_url = f"https://github.com/{GITHUB_REPO}"
    try:
        latest = _remote_version()
    except Exception as e:
        return {
            "current": current,
            "latest": None,
            "update_available": False,
            "repo_url": repo_url,
            "error": str(e)[:200],
        }
    available = _version_tuple(latest) > _version_tuple(current)
    return {
        "current": current,
        "latest": latest,
        "update_available": available,
        "repo_url": repo_url,
        "error": None,
    }
