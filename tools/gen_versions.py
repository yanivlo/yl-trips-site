#!/usr/bin/env python3
"""Generate /versions/index.html - an unlisted, tappable index of every page
version on the site.

Nothing in the output is hand-maintained:

  * the version list comes from the directory names on disk (foo_v12)
  * which one is "live" comes from the root symlinks (oregon -> oregon_v13)
  * the dates come from the commit that first added each version
  * the sizes come from the files themselves

Photos are never listed.

Run from anywhere:  python3 tools/gen_versions.py
"""

import os
import re
import subprocess
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "versions" / "index.html"

# Top-level directories named like "adirondacks_v12".
VERSION_RE = re.compile(r"^(?P<trip>[a-z0-9][a-z0-9-]*)_v(?P<num>\d+)$")

# Directories that are real pages but not versioned trips.
EXTRA_PAGES = {"bikes": "Bikes"}

# Never listed, for size or privacy reasons.
SKIP = {"photos", "versions", "tools", ".git", ".claude"}


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------

def git(*args):
    """Run a git command, returning stdout, or "" if git is unavailable.

    Cloudflare Pages clones shallowly, so history-dependent lookups can come
    back empty. Every caller degrades gracefully when they do.
    """
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                           text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def first_added(relpath):
    """ISO timestamp of the commit that first added relpath, or None."""
    log = git("log", "--diff-filter=A", "--format=%cI", "--", relpath)
    if not log:
        log = git("log", "--format=%cI", "--", relpath)
    return log.splitlines()[-1] if log else None


# --------------------------------------------------------------------------
# filesystem
# --------------------------------------------------------------------------

def dir_size(d):
    return sum(p.stat().st_size for p in d.rglob("*")
               if p.is_file() and not p.is_symlink())


def human_size(n):
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def human_date(iso):
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%b %-d, %-I:%M %p")
    except ValueError:
        return ""


def live_targets():
    """{"oregon": "oregon_v13"} read from the root symlinks."""
    out = {}
    for p in ROOT.iterdir():
        if p.is_symlink():
            out[p.name] = os.path.basename(os.readlink(p))
    return out


def collect():
    """{"oregon": [(13, path), (12, path), ...]} newest first."""
    trips = {}
    for p in sorted(ROOT.iterdir()):
        if p.name in SKIP or p.is_symlink() or not p.is_dir():
            continue
        m = VERSION_RE.match(p.name)
        if m:
            trips.setdefault(m["trip"], []).append((int(m["num"]), p))
    for versions in trips.values():
        versions.sort(key=lambda v: v[0], reverse=True)
    return trips


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

CSS = """
:root{ --bg:#faf9f7; --text:#1f2320; --muted:#5c6560; --border:#dfe3df;
       --card-bg:#ffffff; --link:#1a5d3a; --live-bg:#1a5d3a; --live-fg:#ffffff; }
@media (prefers-color-scheme: dark){
  :root{ --bg:#1b1e1c; --text:#eceeec; --muted:#a9b0ab; --border:#3a3f3b;
         --card-bg:#222521; --link:#7bd1a4; --live-bg:#7bd1a4; --live-fg:#12241a; }
}
*{ box-sizing:border-box; }
body{ background:var(--bg); color:var(--text); margin:0; padding:24px 16px 64px;
      font:16px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
      -webkit-text-size-adjust:100%; }
main{ max-width:640px; margin:0 auto; }
h1{ font-size:1.5rem; margin:0 0 4px; }
p.sub{ color:var(--muted); font-size:0.85rem; margin:0 0 32px; }
h2{ font-size:1.05rem; margin:32px 0 8px; text-transform:capitalize; }
ul{ list-style:none; margin:0; padding:0; border:1px solid var(--border);
    border-radius:12px; overflow:hidden; background:var(--card-bg); }
li + li{ border-top:1px solid var(--border); }
a.row{ display:flex; align-items:center; gap:12px; min-height:56px;
       padding:12px 16px; text-decoration:none; color:var(--text);
       -webkit-tap-highlight-color:rgba(26,93,58,0.15); }
a.row:active{ background:rgba(127,127,127,0.12); }
.ver{ font-weight:600; font-size:1.05rem; color:var(--link);
      min-width:3.2em; font-variant-numeric:tabular-nums; }
.meta{ color:var(--muted); font-size:0.85rem; margin-left:auto; text-align:right;
       white-space:nowrap; }
.live{ background:var(--live-bg); color:var(--live-fg); font-size:0.68rem;
       font-weight:700; letter-spacing:0.04em; padding:3px 7px; border-radius:5px; }
footer{ color:var(--muted); font-size:0.78rem; margin-top:40px; text-align:center; }
"""


def row(href, label, live=False, meta=""):
    pill = '<span class="live">LIVE</span>' if live else ""
    return (f'<li><a class="row" href="{escape(href)}">'
            f'<span class="ver">{escape(label)}</span>{pill}'
            f'<span class="meta">{escape(meta)}</span></a></li>')


def render():
    live = live_targets()
    trips = collect()
    parts = []

    # Order trips by whichever has the most recent version first.
    for trip in sorted(trips, key=lambda t: -max(n for n, _ in trips[t])):
        live_dir = live.get(trip)
        if live_dir is None and trips[trip]:
            # No symlink (some checkouts drop them) - assume highest wins.
            live_dir = trips[trip][0][1].name
        rows = []
        for num, path in trips[trip]:
            meta = " · ".join(x for x in (human_date(first_added(path.name)),
                                          human_size(dir_size(path))) if x)
            rows.append(row(f"/{path.name}/", f"v{num}",
                            live=path.name == live_dir, meta=meta))
        parts.append(f"<h2>{escape(trip.replace('-', ' '))}</h2>"
                     f"<ul>{''.join(rows)}</ul>")

    others = [row("/", "Home", meta="index")]
    for name, label in sorted(EXTRA_PAGES.items()):
        d = ROOT / name
        if d.is_dir():
            others.append(row(f"/{name}/", label, meta=human_size(dir_size(d))))
    parts.append(f"<h2>Other pages</h2><ul>{''.join(others)}</ul>")

    # Stamp with the last commit rather than "now", so rebuilding an unchanged
    # tree produces an identical file instead of a noisy diff.
    stamp = human_date(git("log", "-1", "--format=%cI")) or "unknown"

    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<meta name="robots" content="noindex, nofollow">\n'
        "<title>All versions</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n<main>\n"
        "<h1>All versions</h1>\n"
        f'<p class="sub">Every page on the site. Updated {escape(stamp)}.</p>\n'
        f"{''.join(parts)}\n"
        "<footer>Generated by tools/gen_versions.py &middot; not linked from anywhere</footer>\n"
        "</main>\n</body>\n</html>\n"
    )


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render())
    print(f"wrote {OUT.relative_to(ROOT)}")
