#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Publish a guide page into an author-owned region of a target README (specs/006, story 1).

The guide declares, in guide.yaml:

    publish:
      page: docs/intro.md      # a page inside the content root (gfm guides only)
      target: ../README.md     # a file outside the content root

The target keeps one marker pair; everything between the markers is guide-owned
and everything outside them is the author's:

    author text
    <!-- guide:region -->
    guide-owned content
    <!-- /guide:region -->
    more author text

Usage (from a guide project, where this file is tools/guide/publish.py):

    uv run tools/guide/publish.py [--root DIR] --write   # splice the rendered page in
    uv run tools/guide/publish.py [--root DIR] --check   # compare, exit 1 on difference

Both modes render the page with links rebased from the page's directory to the
target's directory. --check compares the rendered page with the current region
content (author text is never touched) and prints a unified diff on difference.
A missing or malformed marker pair is an error; nothing is ever written outside
the region. Exit status: 0 clean or no-op, 1 error or difference.
"""
from __future__ import annotations

import argparse
import difflib
import os
import sys
from pathlib import Path

import embed
import guidecfg
import region


class PublishError(Exception):
    """A refusal; nothing has been written."""


def _rel(path: Path, root: Path) -> str:
    """A short, stable display name: relative to root when possible, else absolute."""
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return str(path)


def render(root: Path, guide: guidecfg.Guide) -> str:
    """The page as it belongs between the markers: links rebased to the target's location."""
    page, target = guide.publish.page, guide.publish.target
    if not page.is_file():
        raise PublishError(f"publish page {_rel(page, root)} not found")
    text = page.read_text()
    rendered = embed.relink(text, page.parent.as_posix(), target.parent.as_posix())
    # keep the end marker on its own line even for a page without a trailing newline
    if rendered and not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def _target_region(root: Path, guide: guidecfg.Guide) -> region.Region:
    """The parsed target, refusing anything without exactly one balanced marker pair."""
    target = guide.publish.target
    if not target.is_file():
        raise PublishError(
            f"publish target {_rel(target, root)} not found; create it with a "
            f"{region.MARKER_BEGIN} / {region.MARKER_END} pair where the guide content belongs")
    try:
        parsed = region.parse(target.read_text())
    except region.RegionError as err:
        raise PublishError(f"{_rel(target, root)}: {err}") from err
    if not parsed.marked:
        raise PublishError(
            f"{_rel(target, root)}: no {region.MARKER_BEGIN} / {region.MARKER_END} pair; "
            "insert the two marker lines where the guide content belongs")
    return parsed


def run_write(root: Path, guide: guidecfg.Guide) -> int:
    target = guide.publish.target
    parsed = _target_region(root, guide)
    rendered = render(root, guide)
    text = target.read_text()
    updated = region.splice(text, rendered)
    if updated == text:
        print(f"publish: {_rel(target, root)} up to date")
        return 0
    target.write_text(updated)
    print(f"publish: {_rel(target, root)} updated")
    return 0


def run_check(root: Path, guide: guidecfg.Guide) -> int:
    target = guide.publish.target
    parsed = _target_region(root, guide)
    rendered = render(root, guide)
    if parsed.content == rendered:
        print(f"publish: {_rel(target, root)} up to date")
        return 0
    diff_lines = list(difflib.unified_diff(
        parsed.content.splitlines(keepends=True), rendered.splitlines(keepends=True),
        fromfile=f"{_rel(target, root)} (region)", tofile=f"{_rel(guide.publish.page, root)} (rendered)"))
    changed = sum(1 for l in diff_lines if l[:1] in "+-" and not l.startswith(("+++", "---")))
    print(f"publish: {_rel(target, root)} differs ({changed} lines); run with --write to update")
    sys.stdout.writelines(diff_lines)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish a guide page into the author-owned region of a target file.")
    parser.add_argument("--root", type=Path, default=Path("."), help="guide project root (default: cwd)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="splice the rendered page into the region")
    mode.add_argument("--check", action="store_true", help="compare the region, exit 1 on difference")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    try:
        guide = guidecfg.load_guide(root)
    except guidecfg.ConfigError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    if guide.publish is None:
        print("publish: no publish block in guide.yaml; nothing to do")
        return 0
    try:
        return run_write(root, guide) if args.write else run_check(root, guide)
    except PublishError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
