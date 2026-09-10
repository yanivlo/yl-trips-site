#!/usr/bin/env python3
"""
===============================================================================
File: check_limits.py
Purpose:
  Says how much room this site has left before it hits a limit that would
  actually stop a deployment or annoy GitHub.

  Read-only. Runs no git command that writes, and touches no file.

Usage:
  ./check_limits.py            the report
  ./check_limits.py --quiet    one line per limit, no explanations

WHICH LIMITS ARE REAL
  Only two of the numbers below are enforced by anything. The file count and
  the per-file size are Cloudflare Pages rules, and a deployment that breaks
  either one fails. Everything else is guidance, and the site can pass it and
  keep working.

  In particular there is NO total-size limit on Cloudflare Pages. A site of
  800 MB is not close to anything Cloudflare enforces. The "1 GB" figure that
  circulates is old GitHub advice about repository size.
===============================================================================
"""

from __future__ import annotations

import os
import subprocess
import sys

# Cloudflare Pages, free plan. Both are enforced: breaking either fails the
# whole deployment, not just the offending file.
# https://developers.cloudflare.com/pages/platform/limits/
PAGES_MAX_FILES = 20_000
PAGES_MAX_FILE_BYTES = 25 * 1024 * 1024

# GitHub. The 100 MB one is a hard block on push; the rest is guidance.
# https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits
GITHUB_BLOCKED_FILE_BYTES = 100 * 1024 * 1024
GITHUB_RECOMMENDED_GIT_BYTES = 10 * 1024 * 1024 * 1024

# Each photo costs this many files: one display image, one grid thumbnail.
FILES_PER_PHOTO = 2

BAR_WIDTH = 32


def repository_root() -> str:
    """The top of the git working tree this script sits in."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    if result.returncode != 0:
        raise SystemExit("not inside a git repository")
    return result.stdout.strip()


def tracked_files(root: str) -> list[tuple[str, int]]:
    """Every file git tracks, as (path relative to root, size in bytes).

    Tracked files are the right population to count: that is what gets pushed
    and therefore what Cloudflare builds from. Untracked scratch files in the
    working copy are invisible to a deployment."""
    result = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, text=True, cwd=root
    )
    files = []
    for name in result.stdout.split("\0"):
        if not name:
            continue
        path = os.path.join(root, name)
        # A tracked symlink (the /<slug>/ family links) is followed by stat,
        # so measure the link itself, not the page it points at - otherwise
        # every promoted version is counted twice.
        if os.path.islink(path):
            files.append((name, len(os.readlink(path))))
        elif os.path.exists(path):
            files.append((name, os.path.getsize(path)))
    return files


def untracked_photo_files(root: str) -> list[tuple[str, int]]:
    """Files under photos/ that git does not track yet, as (path, bytes).

    Worth reporting separately during a format change: the new images sit in
    the working copy untracked for a while, counting against nothing, and a
    report that ignored them would look reassuring right up until they were
    staged."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--others", "--exclude-standard", "photos/"],
        capture_output=True, text=True, cwd=root,
    )
    found = []
    for name in result.stdout.split("\0"):
        if not name:
            continue
        path = os.path.join(root, name)
        if os.path.exists(path) and not os.path.islink(path):
            found.append((name, os.path.getsize(path)))
    return found


def directory_bytes(path: str) -> int:
    """Total size on disk of `path`, or 0 when it is missing."""
    if not os.path.isdir(path):
        return 0
    total = 0
    for root, _dirs, names in os.walk(path):
        for name in names:
            full = os.path.join(root, name)
            if not os.path.islink(full) and os.path.exists(full):
                total += os.path.getsize(full)
    return total


def human(num_bytes: float) -> str:
    """Bytes as a short string: 1.4 GiB, 812 MiB, 40 KiB."""
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(num_bytes) < 1024 or unit == "GiB":
            return f"{num_bytes:,.0f} {unit}" if unit in ("B", "KiB") else f"{num_bytes:,.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GiB"


def bar(fraction: float) -> str:
    """A [####----] gauge. Clamped, so an over-limit value still renders."""
    filled = max(0, min(BAR_WIDTH, round(fraction * BAR_WIDTH)))
    return "[" + "#" * filled + "-" * (BAR_WIDTH - filled) + "]"


def report_limit(label: str, used: float, limit: float, shown: str,
                 note: str, is_quiet: bool) -> None:
    """One limit: a gauge, the percentage, and what it means."""
    fraction = used / limit if limit else 0
    flag = "  <-- OVER" if fraction >= 1 else ("  <-- close" if fraction >= 0.8 else "")
    print(f"  {label:<26} {bar(fraction)} {fraction*100:5.1f}%   {shown}{flag}")
    if not is_quiet and note:
        print(f"  {'':<26} {note}")


def photo_statistics(root: str, files: list[tuple[str, int]]) -> dict:
    """What the photo sets cost. Returns a dict with keys: set_names
    (list[str]), photo_file_count (int), photo_bytes (int),
    bytes_per_photo (float)."""
    photo_files = [(n, s) for n, s in files if n.startswith("photos/")]
    images = [(n, s) for n, s in photo_files if not n.endswith(".json")]
    set_names = sorted({n.split("/")[1] for n, _ in photo_files if "/" in n[7:]})
    photo_count = len(images) / FILES_PER_PHOTO if images else 0
    total = sum(s for _, s in images)
    return {
        "set_names": set_names,
        "photo_file_count": len(images),
        "photo_bytes": total,
        "photo_count": photo_count,
        "bytes_per_photo": (total / photo_count) if photo_count else 0.0,
    }


def main() -> None:
    is_quiet = "--quiet" in sys.argv
    root = repository_root()
    files = tracked_files(root)
    total_bytes = sum(size for _, size in files)
    largest_name, largest_bytes = max(files, key=lambda f: f[1], default=("", 0))
    git_bytes = directory_bytes(os.path.join(root, ".git"))
    photos = photo_statistics(root, files)

    print("==============================================================================")
    print("=== Cloudflare ===============================================================")
    print("==============================================================================")
    print()
    print(f"  {os.path.basename(root)} - {len(files):,} tracked files, {human(total_bytes)}")
    print()
    print("  CLOUDFLARE PAGES (free plan) - these two are enforced")
    report_limit(
        "files per site", len(files), PAGES_MAX_FILES,
        f"{len(files):,} of {PAGES_MAX_FILES:,}",
        "a deployment over this fails outright", is_quiet)
    report_limit(
        "largest single file", largest_bytes, PAGES_MAX_FILE_BYTES,
        f"{human(largest_bytes)} of {human(PAGES_MAX_FILE_BYTES)}",
        f"{largest_name}", is_quiet)
    if not is_quiet:
        print()
        print("  Cloudflare publishes NO total-size limit. Site size is not a")
        print("  Cloudflare problem; it is a git problem.")

    print("==============================================================================")
    print("=== GitHub ===================================================================")
    print("==============================================================================")
    print()
    print("  GITHUB - guidance, not enforced (except the 100 MB file block)")
    report_limit(
        "largest file vs 100 MB", largest_bytes, GITHUB_BLOCKED_FILE_BYTES,
        f"{human(largest_bytes)} of {human(GITHUB_BLOCKED_FILE_BYTES)}",
        "a push containing a file over this is rejected", is_quiet)
    report_limit(
        ".git on disk", git_bytes, GITHUB_RECOMMENDED_GIT_BYTES,
        f"{human(git_bytes)} of {human(GITHUB_RECOMMENDED_GIT_BYTES)}",
        "history is permanent - deleting files does not shrink this", is_quiet)
    print()
    print("==============================================================================")
    print("=== HEADROOM ===================================================================")
    print("==============================================================================")
    print()
    print("  HEADROOM")
    if photos["photo_count"]:
        files_left = PAGES_MAX_FILES - len(files)
        photos_left = files_left // FILES_PER_PHOTO
        print(f"  photo sets      : {', '.join(photos['set_names'])}")
        print(f"  photos published: {photos['photo_count']:,.0f} "
              f"({photos['photo_file_count']:,} files, {human(photos['photo_bytes'])})")
        print(f"  cost per photo  : {human(photos['bytes_per_photo'])} "
              f"across {FILES_PER_PHOTO} files")
        print(f"  room for        : ~{photos_left:,} more photos before the file")
        print(f"                    limit, about {human(photos_left * photos['bytes_per_photo'])} more")
        if not is_quiet:
            print()
            print("  The file limit is the one that binds, and no image format")
            print("  changes it - every photo costs 2 files whatever its size.")
    else:
        print("  no photo sets found under photos/")

    untracked = untracked_photo_files(root)
    if untracked:
        untracked_bytes = sum(size for _, size in untracked)
        print()
        print(f"  NOT COUNTED: {len(untracked):,} untracked file(s) under photos/, "
              f"{human(untracked_bytes)}")
        print("  Untracked files are not pushed and not deployed, so they count")
        print("  against no limit yet. Staging them would add the above to every")
        print("  figure in this report.")
    print()


if __name__ == "__main__":
    main()
