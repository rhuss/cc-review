#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "fonttools[woff]==4.67.0"]
# ///
"""The Antora playbook a build uses: branding, overlay, and linked worktrees (FR-016a).

Every Antora build (the Makefile BUILD macro behind site, site-internal, check, pdf,
dist, and the preview) asks this script for its playbook before Antora runs:

- It first checks the guide.yaml branding block and the overlay directory
  ui/supplemental/ (tools/guide/branding.py). Problems and warnings go to stderr; on a
  problem nothing is printed and the exit status is 1, so the build stops before Antora.
- For a branded guide, or one with ui/supplemental/, it renders the view's overlay into
  build/branding/<view>/ui/ and writes build/playbook.yml (or playbook-internal.yml): a
  copy of site.yml (site-internal.yml) with ui.supplemental_files pointing at that
  directory, output.clean: true (no page of an earlier build survives), and, when
  branded, site.keys.navbar_logo: guide (Antora camelCases playbook keys, so the UI
  templates see site.keys.navbarLogo and show img/logo-guide.svg).
- Antora cannot read `url: .` inside a linked worktree, where `.git` is a file. There
  the generated playbook points every `url: .` content source at the main repository
  with `branches: <worktree branch>` and `worktrees: <worktree name>`.
- Antora reads a local content source only from the top of a git working tree. For a
  guide kept in a subdirectory of a repository (for example docs/guide/), the generated
  playbook points every `url: .` source at that top level (the main repository in a
  linked worktree) and prefixes its start_path with the guide's path (docs/guide/content).
- Antora resolves `.` and `./` paths against the playbook's own directory, which is
  build/ for a generated playbook, so in a main checkout every `url: .` becomes the
  absolute guide root, and other local content sources, output.dir, output
  destinations, a local UI bundle, Antora and AsciiDoc extensions, and runtime.cache_dir
  become absolute in every generated playbook.

Without branding, overlay, or linked worktree the committed site.yml / site-internal.yml
is used as is and nothing is written.

Usage: uv run tools/guide/playbook.py path [--internal] [--root DIR]   (prints the path)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

import branding
import guidecfg

URL_RE = guidecfg.URL_RE


class BrandingProblems(Exception):
    """The branding block or the overlay directory is invalid; lines holds the report."""

    def __init__(self, lines: list[str]):
        self.lines = lines
        super().__init__("\n".join(lines))


def _git_ok(root: Path, *args: str) -> str | None:
    """git output, or None when git fails (outside a repository, or no git binary)."""
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    except OSError:
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _git_dir(root: Path) -> Path | None:
    out = _git_ok(root, "rev-parse", "--absolute-git-dir")
    return Path(out) if out else None


def _common_dir(git_dir: Path) -> Path:
    """The main repository's git directory: a linked worktree's git directory names it in
    its `commondir` file (git 2.5 on; no --path-format, which git before 2.31 lacks)."""
    commondir = git_dir / "commondir"
    if not commondir.is_file():
        return git_dir
    return (git_dir / commondir.read_text().strip()).resolve()


def is_linked_worktree(root: Path) -> bool:
    """True inside a linked worktree, also in a subdirectory of one; False outside git."""
    git_dir = _git_dir(root)
    return git_dir is not None and _common_dir(git_dir) != git_dir.resolve()


def _repo_prefix(root: Path) -> str:
    """The guide root's path inside its working tree ("docs/guide/"), "" at the top or outside git."""
    return _git_ok(root, "rev-parse", "--show-prefix") or ""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def _absolute(value: str, base: Path) -> str:
    if URL_RE.match(value) or value.startswith("@") or Path(value).is_absolute():
        return value
    if value.startswith((".", "/")) or "/" in value:
        return str((base / value).resolve())
    return value


def path(root: Path, internal: bool = False) -> Path:
    """The playbook to build from; generated for branded, overlaid, or linked-worktree guides.

    Raises BrandingProblems when the branding block or the overlay is invalid; warnings
    are printed to stderr.
    """
    root = Path(root).resolve()
    name = "site-internal.yml" if internal else "site.yml"
    source = root / name
    problems, warnings = branding.check_guide(root)
    for line in warnings:
        print(line, file=sys.stderr)
    if problems:
        raise BrandingProblems(problems)
    raw, _ = branding.load_block(root)
    branded = raw is not None
    overlaid = os.path.lexists(root / branding.OVERLAY)
    linked = is_linked_worktree(root)
    prefix = _repo_prefix(root)
    if not (branded or overlaid or linked or prefix):
        return source

    data = yaml.safe_load(source.read_text()) or {}
    sources = [s for s in (data.get("content") or {}).get("sources") or []
               if isinstance(s, dict) and str(s.get("url", "")).rstrip("/") in (".", "./")]
    if linked:
        git_dir = _git_dir(root)
        common = _common_dir(git_dir)
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if branch == "HEAD":
            raise SystemExit(f"{root} is a linked worktree in detached HEAD state; check out a branch first")
        for src in sources:
            src["url"] = str(common.parent)
            src["branches"] = branch
            src["worktrees"] = git_dir.name
    else:
        top = _git_ok(root, "rev-parse", "--show-toplevel") if prefix else None
        for src in sources:
            src["url"] = top or str(root)
    if prefix:
        # Antora reads a local content source only from the top of a git working tree.
        for src in sources:
            src["start_path"] = (prefix + str(src.get("start_path") or "")).rstrip("/")
    for src in (data.get("content") or {}).get("sources") or []:
        url = src.get("url") if isinstance(src, dict) else None
        if isinstance(url, str) and url.startswith(".") and src not in sources:
            src["url"] = _absolute(url, root)       # a local repository next to the guide
    output = data.setdefault("output", {})
    output["dir"] = _absolute(output.get("dir") or ("./build/site-internal" if internal else "./build/site"), root)
    ui = data.get("ui") or {}
    bundle = ui.get("bundle")
    if isinstance(bundle, dict) and bundle.get("url"):
        bundle["url"] = _absolute(str(bundle["url"]), root)
    for section in (data.get("antora") or {}, data.get("asciidoc") or {}):
        if section.get("extensions"):
            section["extensions"] = [
                _absolute(e, root) if isinstance(e, str)
                else ({**e, "require": _absolute(e["require"], root)} if isinstance(e, dict) and "require" in e else e)
                for e in section["extensions"]
            ]
    runtime = data.get("runtime") or {}
    if isinstance(runtime.get("cache_dir"), str):
        runtime["cache_dir"] = _absolute(runtime["cache_dir"], root)
    for dest in output.get("destinations") or []:
        if isinstance(dest, dict) and isinstance(dest.get("path"), str):
            dest["path"] = _absolute(dest["path"], root)
    if isinstance(ui.get("supplemental_files"), str):
        ui["supplemental_files"] = _absolute(ui["supplemental_files"], root)

    reasons = []
    if branded or overlaid:
        overlay = branding.render(root, "internal" if internal else "shareable")
        data["ui"] = {**ui, "supplemental_files": str(overlay)}
        # Pages from earlier builds (renamed pages, a build from before the branding)
        # would keep the stock header and fail the branded-site check (check.py).
        output["clean"] = True
        if branded:
            site = data.setdefault("site", {})
            site["keys"] = {**(site.get("keys") or {}), "navbar_logo": "guide"}
            reasons.append("branding")
        else:
            reasons.append("ui/supplemental")
    if linked:
        reasons.append("linked git worktree")
    if prefix:
        reasons.append("guide in a repository subdirectory")

    out = root / "build" / ("playbook-internal.yml" if internal else "playbook.yml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# Generated by tools/guide/playbook.py from {name} ({', '.join(reasons)}); do not edit.\n"
                   + yaml.safe_dump(data, sort_keys=False))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Antora playbook path (branding and linked-worktree aware)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("path")
    p.add_argument("--internal", action="store_true")
    p.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        result = path(args.root, args.internal)
    except BrandingProblems as err:
        for line in err.lines:
            print(line, file=sys.stderr)
        print("playbook: fix the branding problems above (guide.yaml branding, ui/supplemental/)", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
