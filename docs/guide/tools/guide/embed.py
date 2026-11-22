#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Deterministic parts of an embedded guide (specs/005-embedded-guide, research R3, R12).

An embedded guide lives in one subdirectory of the repository it documents (the host);
the host's root README is the guide's front page. The create skill classifies the
host's existing documentation and writes a move plan; this script does the rest.

  inventory [--format yaml|json]   documentation candidates in the host at HEAD (read-only)
  apply --plan FILE [--dry-run]    execute an approved move plan
  retarget OLD=NEW ...             point stubs (and front page links) at moved pages
  front-page-status [--record]     detect hand edits of the front page since the baseline
  stage --out DIR                  DIR/docs: docs/ with the front page as README.md, links
                                   rewritten, for the site and PDF builds

Every git call runs as `git -C <host toplevel>`; nothing changes the working directory.
Exit status: 0 success, 10 a reported difference (front-page-status), 2 refused
(configuration, usage, or a plan that does not pass its checks; nothing is changed).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import yaml

import fetch
import guidecfg
import region

README_RE = re.compile(r"^README(\.[A-Za-z0-9]+)?$", re.I)
COMMUNITY_RE = re.compile(r"^(CONTRIBUTING|CODE_OF_CONDUCT|SECURITY|SUPPORT|GOVERNANCE|FUNDING)(\.[A-Za-z0-9]+)?$", re.I)
DOC_FILE_RE = re.compile(r"^(INSTALL|INSTALLATION|USAGE)(\.[A-Za-z0-9]+)?$", re.I)
CHANGELOG_RE = re.compile(r"^(CHANGELOG|CHANGES|HISTORY|NEWS)(\.[A-Za-z0-9]+)?$", re.I)
LICENSE_RE = re.compile(r"^(LICENSE|LICENCE|COPYING|NOTICE)([.-][A-Za-z0-9.-]+)?$", re.I)
DOC_DIRS = ("docs", "doc", "documentation")
DOC_SUFFIXES = {".md", ".markdown", ".rst", ".adoc", ".asciidoc", ".txt"}
SITE_CONFIGS = ("mkdocs.yml", "mkdocs.yaml", "antora.yml", "antora-playbook.yml")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
# Markdown inline links and images, and href/src attributes; group 2 is the target.
LINK_RE = re.compile(r"(\]\(\s*<?)([^)\s>]+)(>?(?:\s+\"[^\"]*\")?\s*\))|((?:href|src)=\")([^\"]+)(\")")
# A Markdown inline link that is not an image: group 1 the text, group 2 the target.
INLINE_LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
# Reference definitions; footnote definitions (`[^1]: text`) are not links.
REFDEF_RE = re.compile(r"^(\s{0,3}\[(?!\^)[^\]]+\]:\s*<?)(\S+?)(>?(?:\s.*)?)$")
SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)
DESTINATIONS = ("input", "developer", "author-region", "keep", "remove", "relocate")
MOVED_HEADING = "Moved from the README"
STUB_MARKER = "<!-- guide: moved -->"


class Refused(Exception):
    """A request the script refuses; nothing has been changed."""


# --- host access ----------------------------------------------------------------


def _git(top: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", "-C", str(top), *args], capture_output=True, text=True, env=fetch.GIT_ENV)
    if check and proc.returncode != 0:
        raise Refused(f"git {' '.join(args)}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


@dataclass
class Host:
    root: Path          # guide root
    top: Path           # host toplevel
    guide_dir: str      # guide subdirectory, relative to the host

    def host_rel(self, guide_rel: str) -> str:
        """Host-relative path of a guide-relative path (../README.md -> README.md)."""
        path = guidecfg._norm(self.root, guide_rel)
        return Path(os.path.relpath(path.resolve(), self.top.resolve())).as_posix()

    def guide_rel(self, host_rel: str) -> str:
        """Guide-relative path of a host-relative path (README.md -> ../README.md)."""
        return Path(os.path.relpath((self.top / host_rel).resolve(), self.root.resolve())).as_posix()

    def in_guide(self, host_rel: str) -> bool:
        return host_rel == self.guide_dir or host_rel.startswith(self.guide_dir + "/")

    def rel(self, path: Path) -> str:
        """Host-relative path of an absolute (or working-directory-relative) path."""
        return Path(os.path.relpath(Path(path).resolve(), self.top.resolve())).as_posix()

    def front_host(self) -> str:
        """Host-relative path of the front page (embedded.front_page or its default)."""
        front = guidecfg.embedded_front_page(self.root)
        return self.rel(front) if front is not None else self.host_rel(guidecfg.DEFAULT_FRONT_PAGE)


def host_of(root: Path) -> Host:
    root = Path(root)
    top = guidecfg.host_toplevel(root)
    if top is None:
        raise Refused(f"{root} is not inside a git repository")
    guide_dir = Path(os.path.relpath(root.resolve(), top.resolve())).as_posix()
    if guide_dir == "." or guide_dir.startswith(".."):
        raise Refused("an embedded guide lives in a subdirectory of its host repository")
    return Host(root=root, top=top, guide_dir=guide_dir)


def _require_embedded(root: Path) -> None:
    if guidecfg.embedded_front_page(root) is None:
        raise Refused("this guide is not embedded (guide.yaml has no embedded block)")


# --- inventory ------------------------------------------------------------------


def headings(text: str) -> list[dict]:
    """ATX headings outside fenced code blocks."""
    out, fence = [], None
    for line in text.splitlines():
        m = FENCE_RE.match(line)
        if fence is None and m:
            fence = m.group(1)
            continue
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            continue
        h = HEADING_RE.match(line)
        if h:
            out.append({"level": len(h.group(1)), "text": h.group(2).strip()})
    return out


def _show(host: Host, rev: str, path: str) -> str | None:
    proc = _git(host.top, "show", f"{rev}:{path}", check=False)
    return proc.stdout if proc.returncode == 0 else None


def inventory(root: Path, rev: str = "HEAD") -> dict:
    """Documentation candidates in the host at rev, by the FR-016 rules (read-only)."""
    host = host_of(root)
    commit = _git(host.top, "rev-parse", "--verify", f"{rev}^{{commit}}").stdout.strip()
    files = [f for f in _git(host.top, "ls-tree", "-r", "--name-only", "-z", commit).stdout.split("\0") if f]
    files = [f for f in files if not host.in_guide(f)]
    fileset = set(files)
    entries: dict[str, dict] = {}

    def add(path: str, kind: str, **extra) -> None:
        if path not in entries:
            entries[path] = {"path": path, "kind": kind, **extra}

    # directories holding a documentation generator configuration; a configuration at the
    # repository root (the usual MkDocs, Docusaurus, or Antora layout) marks its content
    # directory instead of the whole repository
    sites: dict[str, str] = {}
    for f in files:
        d, name = posixpath.split(f)
        is_config = name in SITE_CONFIGS or name.startswith("docusaurus.config.") or (
            name == "conf.py" and any(posixpath.join(d, n) in fileset for n in ("index.rst", "index.md")))
        if not is_config:
            continue
        if d:
            sites.setdefault(d, f)
            continue
        content = _root_site_content(host, commit, name)
        if content and any(x.startswith(content + "/") for x in files):
            sites.setdefault(content, f)
    by_depth = sorted(sites, key=len, reverse=True)   # the innermost site wins
    for f in files:
        d, name = posixpath.split(f)
        top_dir = f.split("/", 1)[0] if "/" in f else ""
        if d == "":
            if README_RE.match(name):
                add(f, "readme")
            elif LICENSE_RE.match(name):
                add(f, "license")
            elif COMMUNITY_RE.match(name):
                add(f, "community")
            elif CHANGELOG_RE.match(name):
                add(f, "changelog")
            elif DOC_FILE_RE.match(name):
                add(f, "doc-file")
            continue
        if d == ".github" and README_RE.match(name):
            add(f, "github-readme")
            continue
        if d in (".github", "docs") and COMMUNITY_RE.match(name):
            add(f, "community")
            continue
        if d == "docs" and README_RE.match(name):
            add(f, "docs-readme")
            continue
        site = next((s for s in by_depth if s and (d == s or d.startswith(s + "/"))), None)
        if site is not None:
            add(site + "/", "doc-site", config=sites[site])
        elif top_dir in DOC_DIRS:
            add(top_dir + "/", "doc-dir")
        if (site is not None or top_dir in DOC_DIRS) and posixpath.splitext(name)[1].lower() in DOC_SUFFIXES:
            add(f, "doc-file")
    for entry in entries.values():
        if entry["kind"] in ("readme", "github-readme", "docs-readme", "doc-file") \
                and entry["path"].lower().endswith((".md", ".markdown")):
            entry["headings"] = headings(_show(host, commit, entry["path"]) or "")
    return {
        "self_revision": commit,
        "guide_dir": host.guide_dir,
        "files": sorted(entries.values(), key=lambda e: (e["path"].count("/"), e["path"])),
        "manifests": _manifests(host, commit, fileset),
    }


def _root_site_content(host: Host, commit: str, name: str) -> str:
    """Content directory of a documentation site configured at the repository root."""
    if name in ("mkdocs.yml", "mkdocs.yaml"):
        try:
            data = yaml.safe_load(_show(host, commit, name) or "") or {}
        except yaml.YAMLError:
            data = {}
        value = data.get("docs_dir") if isinstance(data, dict) else None
        return str(value).strip("/") if isinstance(value, str) and value.strip("/") else "docs"
    if name in ("antora.yml", "antora-playbook.yml"):
        return "modules"
    if name.startswith("docusaurus.config."):
        return "docs"
    return ""


def _manifests(host: Host, commit: str, files: set[str]) -> list[dict]:
    """Package manifests that publish the README to a registry (FR-010a)."""
    out = []
    if "pyproject.toml" in files:
        try:
            data = tomllib.loads(_show(host, commit, "pyproject.toml") or "")
        except tomllib.TOMLDecodeError:
            data = {}
        readme = (data.get("project") or {}).get("readme") or ((data.get("tool") or {}).get("poetry") or {}).get("readme")
        if readme:
            out.append({"path": "pyproject.toml", "publishes_readme": True})
    if "package.json" in files:
        try:
            data = json.loads(_show(host, commit, "package.json") or "{}")
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict) and not data.get("private"):
            out.append({"path": "package.json", "publishes_readme": True})
    if "Cargo.toml" in files:
        try:
            data = tomllib.loads(_show(host, commit, "Cargo.toml") or "")
        except tomllib.TOMLDecodeError:
            data = {}
        package = data.get("package") or {}
        if package and package.get("publish", True) is not False and package.get("readme", True) is not False:
            out.append({"path": "Cargo.toml", "publishes_readme": True})
    return out


# --- Markdown helpers -------------------------------------------------------------


def _fence_mask(lines: list[str]) -> list[bool]:
    mask, fence = [], None
    for line in lines:
        m = FENCE_RE.match(line)
        if fence is None and m:
            fence = m.group(1)
            mask.append(True)
        elif fence is not None:
            mask.append(True)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
        else:
            mask.append(False)
    return mask


def section_span(text: str, title: str) -> tuple[int, int, int] | None:
    """(first line, end line, heading level) of the section titled title: the heading line
    up to the next heading of the same or a higher level (fenced code blocks are skipped)."""
    lines = text.splitlines(keepends=True)
    mask = _fence_mask([l.rstrip("\n") for l in lines])
    start = level = None
    for i, line in enumerate(lines):
        if mask[i]:
            continue
        h = HEADING_RE.match(line.rstrip("\n"))
        if not h:
            continue
        if start is None:
            if h.group(2).strip() == title:
                start, level = i, len(h.group(1))
        elif len(h.group(1)) <= level:
            return start, i, level
    if start is None:
        return None
    return start, len(lines), level


def extract_section(text: str, title: str) -> tuple[str, int] | None:
    """(section text, heading level) of the section titled title (see section_span)."""
    span = section_span(text, title)
    if span is None:
        return None
    start, end, level = span
    lines = text.splitlines(keepends=True)
    return "".join(lines[start:end]).rstrip("\n") + "\n", level


def shift_headings(text: str, shift: int) -> str:
    if not shift:
        return text
    lines = text.splitlines(keepends=True)
    mask = _fence_mask([l.rstrip("\n") for l in lines])
    out = []
    for i, line in enumerate(lines):
        h = None if mask[i] else re.match(r"^(#{1,6})(\s)", line)
        if h:
            level = max(1, min(6, len(h.group(1)) + shift))
            line = "#" * level + line[len(h.group(1)):]
        out.append(line)
    return "".join(out)


def rewrite_links(text: str, mapper) -> str:
    """Apply mapper(target) -> new target to every relative link target outside code fences."""
    lines = text.splitlines(keepends=True)
    mask = _fence_mask([l.rstrip("\n") for l in lines])

    def one(target: str) -> str:
        if not target or SCHEME_RE.match(target) or target.startswith(("#", "/", "{{")):
            return target
        path, sep, frag = target.partition("#")
        if not path:
            return target
        new = mapper(path)
        return new + sep + frag if new is not None else target

    out = []
    for i, line in enumerate(lines):
        if mask[i]:
            out.append(line)
            continue
        line = LINK_RE.sub(lambda m: (m.group(1) + one(m.group(2)) + m.group(3)) if m.group(1) is not None
                           else (m.group(4) + one(m.group(5)) + m.group(6)), line)
        d = REFDEF_RE.match(line.rstrip("\n"))
        if d:
            line = d.group(1) + one(d.group(2)) + d.group(3) + ("\n" if line.endswith("\n") else "")
        out.append(line)
    return "".join(out)


def relink(text: str, from_dir: str, to_dir: str) -> str:
    """Rewrite relative links of text moved from host dir from_dir to host dir to_dir."""
    def mapper(path: str) -> str:
        target = posixpath.normpath(posixpath.join(from_dir, path))
        return posixpath.relpath(target, to_dir or ".")
    if posixpath.normpath(from_dir or ".") == posixpath.normpath(to_dir or "."):
        return text
    return rewrite_links(text, mapper)


# --- guide.yaml and inputs.yaml updates --------------------------------------------


def embedded_keys_text(root: Path, updates: dict) -> str:
    """The guide.yaml text with keys of the `embedded` block set in place, keeping the rest
    of the file (comments included) as it is. A list value is written as a block sequence.

    Raises Refused when the block is not a block mapping it can edit, before anything is
    written (apply computes it first)."""
    path = Path(root) / "guide.yaml"
    lines = path.read_text().splitlines(keepends=True)
    start = next((i for i, l in enumerate(lines) if re.match(r"^embedded:\s*(#.*)?$", l.rstrip("\n"))), None)
    if start is None:
        raise Refused("guide.yaml has no embedded block")
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith((" ", "\t"))):
        end += 1
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    block = lines[start + 1:end]
    indent = next((re.match(r"^(\s+)", l).group(1) for l in block if l.strip() and not l.lstrip().startswith("#")),
                  "  ")
    kept: list[str] = []
    skip = False
    for line in block:
        key = re.match(rf"^{indent}([A-Za-z_]+):", line)
        if key:
            skip = key.group(1) in updates
        elif line.strip() and not line.startswith(indent + " ") and not line.startswith(indent + "-"):
            skip = False
        if not skip:
            kept.append(line)
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, list):
            kept.append(f"{indent}{key}:" + (" []\n" if not value else "\n"))
            kept.extend(f"{indent}  - {v}\n" for v in value)
        else:
            kept.append(f"{indent}{key}: {value}\n")
    new = lines[:start + 1] + kept + lines[end:]
    return "".join(new)


def _input_id(host_path: str, taken: dict[str, str | None]) -> str:
    """The inputs.yaml id of a host file: host-<slug of its path>, with -2, -3, ... appended
    while another entry holds the id. taken maps id -> host path of its entry (None when the
    entry is not a host file); the chosen id is added to it. An entry of the same file keeps
    its id, so a second apply updates it instead of adding another."""
    base = "host-" + guidecfg.slugify(host_path)
    candidate, n = base, 1
    while candidate in taken and taken[candidate] != host_path:
        n += 1
        candidate = f"{base}-{n}"
    taken[candidate] = host_path
    return candidate


def _registered_inputs(root: Path, host: Host) -> dict[str, str | None]:
    """id -> host path of every inputs.yaml entry (None for one that is not a host file)."""
    path = Path(root) / "inputs.yaml"
    try:
        data = yaml.safe_load(path.read_text()) if path.is_file() else {}
    except yaml.YAMLError as err:
        raise Refused(f"cannot read inputs.yaml: {err}") from err
    entries = (data.get("inputs") if isinstance(data, dict) else None) or []
    out: dict[str, str | None] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        loc = str(entry.get("location") or "")
        if loc.startswith(guidecfg.SELF_ID + ":"):
            hp: str | None = loc.split(":", 1)[1]
        elif loc and not SCHEME_RE.match(loc) and not loc.startswith("/"):
            hp = host.host_rel(loc)
        else:
            hp = None
        out[str(entry["id"])] = hp
    return out


def register_inputs(root: Path, items: list[dict]) -> None:
    """Add or update entries in inputs.yaml (matched by id)."""
    path = Path(root) / "inputs.yaml"
    header = ""
    data: dict = {}
    if path.is_file():
        text = path.read_text()
        header = "".join(_leading_comments(text))
        data = yaml.safe_load(text) or {}
    entries = data.get("inputs") or []
    for item in items:
        current = next((e for e in entries if e.get("id") == item["id"]), None)
        if current is None:
            entries.append(item)
        else:
            current.clear()
            current.update(item)
    data["inputs"] = entries
    path.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def _leading_comments(text: str) -> list[str]:
    out = []
    for line in text.splitlines(keepends=True):
        if line.startswith("#"):
            out.append(line)
        else:
            break
    return out


# --- apply ------------------------------------------------------------------------


@dataclass
class Plan:
    revision: str
    developer_readme: str            # guide-relative
    entries: list[dict]
    absolute_links: bool = False


def _load_plan(path: Path) -> Plan:
    try:
        data = yaml.safe_load(Path(path).read_text()) or {}
    except (OSError, yaml.YAMLError) as err:
        raise Refused(f"cannot read the move plan {path}: {err}") from err
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise Refused("the move plan needs an entries list")
    rev = str(data.get("self_revision") or "")
    if not guidecfg.SHA_RE.match(rev):
        raise Refused("the move plan needs self_revision (the full host commit the inventory ran at)")
    return Plan(revision=rev, developer_readme=str(data.get("developer_readme") or "../DEVELOPMENT.md"),
                entries=data["entries"], absolute_links=bool(data.get("absolute_links")))


def _is_root_readme(host_path: str) -> bool:
    return "/" not in host_path and bool(README_RE.match(host_path))


def _is_github_readme(host_path: str) -> bool:
    d, name = posixpath.split(host_path)
    return d == ".github" and bool(README_RE.match(name))


def _dirty(host: Host) -> list[str]:
    proc = _git(host.top, "status", "--porcelain", "--untracked-files=all", "--", ".",
                f":(exclude){host.guide_dir}")
    return [l for l in proc.stdout.splitlines() if l.strip()]


def _documentation(inv: dict, host_path: str) -> bool:
    """True when the inventory lists the file or a documentation directory that holds it."""
    for entry in inv["files"]:
        p = entry["path"]
        if p == host_path:
            return True
        if p.endswith("/") and host_path.startswith(p):
            return True
    return False


def check_plan(root: Path, plan: Plan) -> tuple[Host, list[dict]]:
    """Validate a move plan (data-model.md); return the host and the normalized entries."""
    host = host_of(root)
    _require_embedded(root)
    head = _git(host.top, "rev-parse", "HEAD").stdout.strip()
    if head != plan.revision:
        raise Refused(f"the host moved since the inventory (HEAD {head[:7]}, plan {plan.revision[:7]}); "
                      "run the inventory again")
    dirty = _dirty(host)
    if dirty:
        raise Refused("the host repository has uncommitted changes outside the guide subdirectory; "
                      "commit or set them aside first:\n  " + "\n  ".join(dirty))
    inv = inventory(root, plan.revision)
    front_host = host.front_host()
    problems: list[str] = []
    entries: list[dict] = []
    by_path: dict[str, list[dict]] = {}
    for i, raw in enumerate(plan.entries):
        where = f"entries[{i}]"
        if not isinstance(raw, dict) or not raw.get("path"):
            problems.append(f"{where}: needs a path")
            continue
        unknown = set(raw) - {"path", "section", "destination", "stub", "to"}
        if unknown:
            problems.append(f"{where}: unknown keys {sorted(unknown)}")
        hp = host.host_rel(str(raw["path"])).rstrip("/")
        dest = raw.get("destination")
        entry = {"path": hp, "section": raw.get("section"), "destination": dest,
                 "stub": bool(raw.get("stub")), "to": raw.get("to")}
        if hp.startswith("..") or host.in_guide(hp):
            problems.append(f"{where}: {raw['path']} lies outside the host or inside the guide subdirectory")
            continue
        if _git(host.top, "cat-file", "-e", f"{plan.revision}:{hp}", check=False).returncode != 0:
            problems.append(f"{where}: {hp} does not exist at {plan.revision[:7]}")
            continue
        if dest not in DESTINATIONS:
            problems.append(f"{where}: destination must be one of {', '.join(DESTINATIONS)} (got {dest!r})")
            continue
        if entry["stub"] and dest in ("relocate", "keep", "author-region"):
            problems.append(f"{where}: stub: true cannot be combined with destination {dest}; a stub "
                            f"replaces a removed path, and {hp} stays in the host"
                            + (f" (at {entry['to']})" if dest == "relocate" and entry["to"] else ""))
            continue
        if dest == "author-region":
            # specs/006, contracts/move-plan-destination.md: a section of the root Markdown
            # README stays in place as author-owned text above the guide region
            if hp != front_host or posixpath.splitext(hp)[1].lower() not in (".md", ".markdown"):
                problems.append(f"{where}: author-region keeps a section of the root Markdown README "
                                f"({front_host}) as author text; it cannot apply to {hp}")
                continue
            if entry["section"] is None:
                problems.append(f"{where}: author-region entries name a section of {hp}")
                continue
        name = posixpath.basename(hp)
        if (dest == "remove" or entry["stub"] or dest == "relocate") and LICENSE_RE.match(name):
            problems.append(f"{where}: {hp} is a license file; it stays where GitHub detects it (FR-022)")
            continue
        entry["files"] = _tree_files(host, plan.revision, hp)
        if entry["files"] is not None:
            # a directory (a documentation directory or site from the inventory)
            if dest in ("remove", "relocate", "developer") or entry["stub"]:
                problems.append(f"{where}: {hp} is a directory; name its files one by one for "
                                f"{'stubs' if entry['stub'] else dest}")
                continue
            if entry["section"] is not None:
                problems.append(f"{where}: {hp} is a directory and has no sections")
                continue
        if (dest == "remove" or entry["stub"]) and not _documentation(inv, hp):
            problems.append(f"{where}: {hp} is not a documentation file in the inventory; it cannot be removed")
            continue
        if COMMUNITY_RE.match(name) and (dest == "remove" or entry["stub"] or (
                dest == "relocate" and not _github_detects(entry.get("to") and host.host_rel(str(entry["to"])), name))):
            problems.append(f"{where}: {hp} is a community health file; it stays where GitHub detects it "
                            "(the root, .github/, or docs/) and the developer README links to it (FR-022)")
            continue
        if dest == "remove" and entry["section"] is None and not entry["stub"] \
                and not (_is_root_readme(hp) or _is_github_readme(hp)):
            problems.append(f"{where}: {hp} is removed without a stub; every removed documentation path keeps "
                            "a stub (stub: true) so old links keep working (FR-023)")
            continue
        if entry["stub"] and (_is_root_readme(hp) or _is_github_readme(hp)):
            problems.append(f"{where}: no stub for {hp}: a stub there would shadow the front page or leave "
                            "two root READMEs (remove or relocate it instead)")
            continue
        if dest == "relocate":
            to = entry["to"]
            if not to:
                problems.append(f"{where}: relocate needs a 'to' path")
                continue
            entry["to"] = host.host_rel(str(to))
            if entry["to"].startswith("..") or host.in_guide(entry["to"]) or (host.top / entry["to"]).exists():
                problems.append(f"{where}: cannot relocate to {to} (exists, outside the host, or in the guide)")
                continue
            if _is_root_readme(entry["to"]):
                problems.append(f"{where}: cannot relocate to a root README")
                continue
        if entry["section"] is not None:
            if dest not in ("developer", "input", "keep", "author-region"):
                problems.append(f"{where}: a section can only go to the developer README, stay in the "
                                "author region, or be input")
                continue
            text = _show(host, plan.revision, hp) or ""
            span = section_span(text, str(entry["section"]))
            if span is None:
                problems.append(f"{where}: section {entry['section']!r} not found in {hp}")
                continue
            # sections of one file are moved one after another: a section named twice, or
            # one nested in another, would be moved twice or no longer be found
            clash = None if dest != "developer" else next(
                (o for o in by_path.get(hp, []) if o["destination"] == "developer" and o.get("span")
                 and o["span"][0] < span[1] and span[0] < o["span"][1]), None)
            if clash is not None:
                problems.append(f"{where}: section {entry['section']!r} of {hp} overlaps section "
                                f"{clash['section']!r} (name only the outer one)")
                continue
            entry["span"] = span[:2]
        elif dest == "developer":
            problems.append(f"{where}: developer entries name a section")
            continue
        entries.append(entry)
        by_path.setdefault(hp, []).append(entry)
    root_readmes = [e["path"] for e in inv["files"] if e["kind"] == "readme"]
    for hp in root_readmes:
        by_path.setdefault(hp, [])
    for hp, items in by_path.items():
        if not _is_root_readme(hp):
            continue
        dests = {e["destination"] for e in items}
        if hp == front_host:
            bad = dests - {"input", "developer", "author-region"}
            if bad:
                problems.append(f"{hp}: the root README becomes the front page; its sections become guide "
                                f"input, move to the developer README, or stay in the author region "
                                f"(got {', '.join(sorted(bad))})")
            if "author-region" in dests:
                # apply removes the input/developer sections and keeps the author-region ones
                # byte-identical: no two section entries of this README may overlap
                spans = sorted((e["span"][0], e["span"][1], str(e["section"]))
                               for e in items if e.get("span"))
                for (s1, e1, t1), (s2, _, t2) in zip(spans, spans[1:]):
                    if s2 < e1:
                        problems.append(f"{hp}: section {t2!r} overlaps section {t1!r} (name only the "
                                        "outer one, or give the sections different destinations)")
                        break
        else:
            bad = dests - {"input", "remove", "relocate"}
            if bad or not dests & {"remove", "relocate"}:
                problems.append(f"{hp}: a root README other than the front page ({front_host}) becomes guide "
                                "input and is removed or relocated, so there is never a second root README")
    if any(e["destination"] == "developer" for e in entries):
        dev = host.host_rel(plan.developer_readme)
        planned = {e["path"] for e in entries if e["destination"] != "keep"} | \
            {e["to"] for e in entries if e.get("to")}
        if dev.startswith("..") or host.in_guide(dev) or dev.startswith(".git/"):
            problems.append(f"developer_readme: {plan.developer_readme} must lie in the host repository and "
                            "outside the guide subdirectory (paths are relative to the guide root, for "
                            "example ../DEVELOPMENT.md)")
        elif not dev.endswith(".md"):
            problems.append(f"developer_readme: {plan.developer_readme} must be a Markdown file (.md)")
        elif dev == front_host or _is_root_readme(dev) or _is_github_readme(dev) or dev in planned:
            problems.append(f"developer_readme: {plan.developer_readme} is the front page, a README, or a "
                            "file the move plan changes; choose another path")
        elif (host.top / dev).exists() and not (host.top / dev).is_file():
            problems.append(f"developer_readme: {plan.developer_readme} exists and is not a file")
    if problems:
        raise Refused("the move plan was refused:\n  " + "\n  ".join(problems))
    return host, entries


def _tree_files(host: Host, rev: str, path: str) -> list[str] | None:
    """Documentation files under path at rev when path is a directory, else None."""
    proc = _git(host.top, "cat-file", "-t", f"{rev}:{path}", check=False)
    if proc.stdout.strip() != "tree":
        return None
    out = _git(host.top, "ls-tree", "-r", "--name-only", "-z", rev, "--", path).stdout.split("\0")
    return [f for f in out if f and posixpath.splitext(f)[1].lower() in DOC_SUFFIXES]


def _github_detects(target: str | None, name: str) -> bool:
    """True when GitHub detects a community health file at target (root, .github/, docs/)."""
    if not target:
        return False
    d, base = posixpath.split(target)
    return d in ("", ".github", "docs") and base.split(".")[0].upper() == name.split(".")[0].upper()


def _blob(host: Host, rev: str, path: str) -> str:
    return _git(host.top, "rev-parse", f"{rev}:{path}").stdout.strip()


def apply(root: Path, plan_path: Path, dry_run: bool = False) -> list[str]:
    """Execute an approved move plan; return the file operations (performed or, dry, planned)."""
    root = Path(root)
    plan = _load_plan(plan_path)
    host, entries = check_plan(root, plan)
    ops: list[str] = []
    today = _dt.date.today().isoformat()
    front_host = host.front_host()
    gone = {e["path"] for e in entries if e["stub"] or e["destination"] in ("remove", "relocate")}
    # development sections move out of files that stay (without author-region entries the root
    # README is replaced by the front page as a whole, so it is left as it is until then)
    trimmed: dict[str, str] = {}
    for e in entries:
        hp = e["path"]
        if e["destination"] == "developer" and not _is_root_readme(hp) and hp not in gone:
            text = trimmed.get(hp, _show(host, plan.revision, hp) or "")
            found = extract_section(text, str(e["section"]))
            if found is None:   # check_plan refuses overlapping sections; never trim blindly
                raise Refused(f"section {e['section']!r} of {hp} not found while moving it")
            section, _ = found
            body = section if section in text else section.rstrip("\n")
            trimmed[hp] = text.replace(body, "", 1)
    # specs/006, research R9: with author-region entries the front README survives; its moved
    # (input/developer) sections leave it, the retained landing text stays byte-identical, and
    # the empty guide region lands immediately below the last retained section
    region_text: str | None = None
    if any(e["destination"] == "author-region" for e in entries):
        text = _show(host, plan.revision, front_host) or ""
        moved = sorted((e for e in entries if e["path"] == front_host
                        and e["destination"] in ("input", "developer") and e.get("span")),
                       key=lambda e: e["span"][0], reverse=True)
        for e in moved:
            found = extract_section(text, str(e["section"]))
            if found is None:   # check_plan refuses overlapping sections; never trim blindly
                raise Refused(f"section {e['section']!r} of {front_host} not found while moving it")
            section, _ = found
            body = section if section in text else section.rstrip("\n")
            text = text.replace(body, "", 1)
        last = 0
        for e in entries:
            if e["path"] == front_host and e["destination"] == "author-region":
                span = section_span(text, str(e["section"]))
                if span is None:
                    raise Refused(f"section {e['section']!r} of {front_host} not found while keeping it")
                last = max(last, span[1])
        lines = text.splitlines(keepends=True)
        head = "".join(lines[:last])
        if head and not head.endswith("\n"):
            head += "\n"
        tail = "".join(lines[last:])
        region_text = (head + "\n" + region.MARKER_BEGIN + "\n" + region.MARKER_END + "\n"
                       + (("\n" + tail) if tail.strip() else ""))
        ops.append(f"keep the landing sections of {front_host} as the author region "
                   "(markers below the retained text)")
    rewritten = ({e["path"] for e in entries if _is_root_readme(e["path"])} | gone | set(trimmed)
                 | ({front_host} if region_text is not None else set()))

    # inputs: recorded at the revision when consolidation rewrites or removes the file (FR-020);
    # a directory registers each of its documentation files
    inputs: list[dict] = []
    seen: set[str] = set()
    taken = _registered_inputs(root, host)
    for e in entries:
        if e["destination"] != "input":
            continue
        for hp in (e["files"] if e.get("files") is not None else [e["path"]]):
            if hp in seen:
                continue
            seen.add(hp)
            item = {"id": _input_id(hp, taken), "kind": "document", "role": "host documentation",
                    "registered": today}
            if hp in rewritten:
                item.update(location=f"self:{hp}", revision=plan.revision, blob=_blob(host, plan.revision, hp))
            else:
                item.update(location=host.guide_rel(hp),
                            sha256=hashlib.sha256((host.top / hp).read_bytes()).hexdigest())
            inputs.append(item)
            ops.append(f"register input {item['id']} ({item['location']})")

    # developer README
    dev_sections = [e for e in entries if e["destination"] == "developer"]
    dev_host = host.host_rel(plan.developer_readme) if dev_sections else None
    dev_text = None
    if dev_sections:
        dev_path = host.top / dev_host
        exists = dev_path.is_file()
        target_level = 3 if exists else 2
        parts = []
        for e in dev_sections:
            text = _show(host, plan.revision, e["path"]) or ""
            section, level = extract_section(text, str(e["section"]))
            section = shift_headings(section, target_level - level)
            section = relink(section, posixpath.dirname(e["path"]), posixpath.dirname(dev_host))
            parts.append(section.rstrip("\n") + "\n")
        body = "\n".join(parts)
        if exists:
            dev_text = dev_path.read_text().rstrip("\n") + f"\n\n## {MOVED_HEADING}\n\n" + body
            ops.append(f"append {len(dev_sections)} section(s) to {dev_host} under '## {MOVED_HEADING}'")
        else:
            dev_text = "# Development\n\n" + body
            ops.append(f"write {dev_host} with {len(dev_sections)} section(s)")

    # stubs, relocations, removals
    stubs: list[str] = []
    stub_texts: dict[str, str] = {}
    for e in entries:
        hp = e["path"]
        if e["stub"]:
            if hp in stub_texts:
                continue
            original = _show(host, plan.revision, hp) or ""
            title = _title(original, hp)
            stub_texts[hp] = stub_text(title, posixpath.relpath(front_host, posixpath.dirname(hp) or "."))
            stubs.append(hp)
            ops.append(f"replace {hp} with a stub linking to {front_host}")
        elif e["destination"] == "relocate":
            ops.append(f"move {hp} to {e['to']}")
        elif e["destination"] == "remove" and e["section"] is None:
            ops.append(f"remove {hp}")
    for hp in trimmed:
        ops.append(f"remove the moved development sections from {hp}")

    updates: dict = {}
    if dev_text is not None:
        updates["developer_readme"] = host.guide_rel(dev_host)
    if stubs:
        current = [host.host_rel(os.path.relpath(p, root)) for p in _current_stubs(root)]
        updates["stubs"] = [host.guide_rel(p) for p in sorted(set(current) | set(stubs))]
    guide_text = embedded_keys_text(root, updates) if updates else None   # refuses before any write

    if dry_run:
        return ops

    if inputs:
        register_inputs(root, inputs)
    for hp, text in trimmed.items():
        (host.top / hp).write_text(text)
    if region_text is not None:
        (host.top / front_host).write_text(region_text)
    if dev_text is not None:
        (host.top / dev_host).parent.mkdir(parents=True, exist_ok=True)
        (host.top / dev_host).write_text(dev_text)
    for e in entries:
        hp = e["path"]
        if e["stub"]:
            continue
        if e["destination"] == "relocate" and (host.top / hp).exists():
            (host.top / e["to"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(host.top / hp), str(host.top / e["to"]))
        elif e["destination"] == "remove" and e["section"] is None and (host.top / hp).exists():
            (host.top / hp).unlink()
    for hp, text in stub_texts.items():
        (host.top / hp).write_text(text)
    if guide_text is not None:
        (root / "guide.yaml").write_text(guide_text)
    return ops


def _current_stubs(root: Path) -> list[Path]:
    raw = guidecfg._embedded_raw(root) or {}
    return [guidecfg._norm(root, s) for s in raw.get("stubs") or [] if isinstance(s, str)]


def _title(text: str, path: str) -> str:
    for h in headings(text):
        if h["level"] == 1:
            return h["text"]
    for line in text.splitlines():   # reStructuredText or AsciiDoc titles
        s = line.strip()
        if s.startswith("= "):
            return s[2:].strip()
        if s and not set(s) <= set("=-~#*"):
            return s
    return posixpath.splitext(posixpath.basename(path))[0]


def stub_text(title: str, target: str) -> str:
    return f"{STUB_MARKER}\n# {title}\n\nThis page moved to [{title}]({target}).\n"


# --- retarget ---------------------------------------------------------------------------


def _host_path(spec: str) -> str:
    spec = spec.strip()
    while spec.startswith("./"):
        spec = spec[2:]
    return posixpath.normpath(spec)


def retarget(root: Path, mappings: list[str]) -> list[str]:
    """Point stubs (and front page links) at moved pages; return the changed files.

    Each mapping is OLD=NEW with host-relative paths. OLD names a stub (its link is set to
    NEW, the page that now covers its content) or a page that was renamed or removed (every
    stub and front page link that points at OLD is rewritten to NEW). Links are written
    relative to the file that holds them. Nothing is written when a mapping matches nothing.
    """
    root = Path(root)
    _require_embedded(root)
    host = host_of(root)
    pairs: list[tuple[str, str]] = []
    for spec in mappings:
        if "=" not in spec:
            raise Refused(f"bad mapping {spec!r} (expected OLD=NEW with host-relative paths)")
        old, new = (_host_path(s) for s in spec.split("=", 1))
        if not (host.top / new).exists():
            raise Refused(f"{new} does not exist in the host repository")
        pairs.append((old, new))
    stubs = {host.rel(p): p for p in _current_stubs(root)}
    files = dict(stubs)
    front = guidecfg.embedded_front_page(root)
    if front is not None and front.is_file():
        files[host.rel(front)] = front
    texts = {rel: path.read_text() for rel, path in files.items() if path.is_file()}
    original = dict(texts)
    for old, new in pairs:
        hit = False
        for rel, text in texts.items():
            base = posixpath.dirname(rel)
            target = posixpath.relpath(new, base or ".")
            if rel == old and rel in stubs:
                hit = True
                texts[rel] = rewrite_links(text, lambda _p, target=target: target)
                continue
            new_text = rewrite_links(text, lambda p, base=base, target=target:
                                     target if posixpath.normpath(posixpath.join(base, p)) == old else None)
            if new_text != text:
                hit = True
                texts[rel] = new_text
        if not hit:
            raise Refused(f"no stub is {old}, and no stub or front page link points at it")
    changed = sorted(rel for rel in texts if texts[rel] != original[rel])
    for rel in changed:
        files[rel].write_text(texts[rel])
    return changed


# --- front-page-status ----------------------------------------------------------------


def front_page_status(root: Path, record: bool = False) -> tuple[str, str]:
    """("recorded" | "unchanged" | "edited" | "unrecorded", diff) for the front page (FR-009a).

    --record stores the normalized front page (generated regions emptied) in the host
    object database and writes its blob id as `front_page_blob` on the `self` baseline
    entry; create and evolve run it after the final `make check`. Without --record the
    current front page is compared with that blob, and a difference is a hand edit.

    The diff needs the recorded text. It is read from history: the front page in the
    commit that last changed baseline.yaml (pushed with the guide, kept by squash merges),
    accepted only when its normalized blob id equals `front_page_blob`. The loose object
    written by --record is the fallback before that commit exists; git gc may prune it.
    """
    root = Path(root)
    _require_embedded(root)
    front = guidecfg.embedded_front_page(root)
    if not front.is_file():
        raise Refused(f"front page {os.path.relpath(front, root)} not found")
    host = host_of(root)
    if record:
        blob = fetch.store_front_page_blob(root, host.top)
        header, data = fetch._read_raw(root)
        entry = next((e for e in data.get("sources") or [] if e.get("id") == guidecfg.SELF_ID), None)
        if entry is None:
            raise Refused("baseline.yaml has no self source; pin it first (fetch.py pin --source self=..)")
        entry["front_page_blob"] = blob
        fetch._write_raw(root, header, data)
        return "recorded", blob
    source = guidecfg.load_baseline(root).source(guidecfg.SELF_ID)
    recorded = source.front_page_blob if source else ""
    if not recorded:
        return "unrecorded", ""
    current = fetch.normalized_front_page(front.read_text())
    if _hash_text(host, current) == recorded:
        return "unchanged", ""
    rel = host.rel(front)
    old, note = _recorded_front_page(host, rel, recorded)
    if old is None:
        return "edited", f"({note}; no diff available)\n"
    diff = difflib.unified_diff(old.splitlines(keepends=True), current.splitlines(keepends=True),
                                fromfile=f"{rel} (baseline)", tofile=f"{rel} (now)")
    return "edited", "".join(diff)


def _hash_text(host: Host, text: str) -> str:
    """Blob id of text in the host repository (not written to the object database)."""
    proc = subprocess.run(["git", "-C", str(host.top), "hash-object", "--stdin"], input=text,
                          capture_output=True, text=True, env=fetch.GIT_ENV)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _recorded_front_page(host: Host, front_rel: str, recorded: str) -> tuple[str | None, str]:
    """Normalized front page text whose blob id is `recorded`, and a note when it is not found."""
    baseline_rel = f"{host.guide_dir}/baseline.yaml"
    log = _git(host.top, "log", "-1", "--format=%H", "--", baseline_rel, check=False)
    commit = log.stdout.strip() if log.returncode == 0 else ""
    separate = False
    if commit:
        shown = _git(host.top, "show", f"{commit}:{front_rel}", check=False)
        if shown.returncode == 0:
            text = fetch.normalized_front_page(shown.stdout)
            if _hash_text(host, text) == recorded:
                return text, ""
        separate = True
    loose = _git(host.top, "cat-file", "blob", recorded, check=False)
    if loose.returncode == 0:
        return loose.stdout, ""
    if separate:
        return None, ("the front page was not committed together with the baseline.yaml that recorded it, "
                      "so the recorded text is not in history")
    return None, "the recorded front page is not in history yet (commit the guide after --record)"


# --- stage ------------------------------------------------------------------------


def stage(root: Path, out: Path) -> Path:
    """Write out/docs: docs/ with README.md replaced by the front page, links rewritten (R3)."""
    root = Path(root)
    front = guidecfg.embedded_front_page(root)
    if front is None:
        raise Refused("stage is for embedded guides only (guide.yaml has no embedded block)")
    if not front.is_file():
        raise Refused(f"front page {os.path.relpath(front, root)} not found")
    adapter = guidecfg.load_adapter(root)
    docs = (root / adapter.content_root).resolve()
    out = out if out.is_absolute() else root / out
    dest = (out / "docs").resolve()
    host = guidecfg.host_toplevel(root)
    web, ref = "", ""
    try:
        src = guidecfg.load_baseline(root).source(guidecfg.SELF_ID)
        if src is not None:
            web, ref = src.web, src.ref or "main"
    except guidecfg.ConfigError:
        pass
    # dest is replaced as a whole: it must be a staging directory inside the guide root,
    # never the docs tree itself, a directory holding it, or anything outside the guide
    guide_root = root.resolve()
    if dest == docs or dest in docs.parents or docs in dest.parents or guide_root not in dest.parents:
        raise Refused(f"--out {out} would replace {dest}; choose a build directory inside the guide "
                      "root that does not overlap docs/ (for example build/stage)")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(docs, dest, ignore=shutil.ignore_patterns("node_modules"))
    front_res = front.resolve()

    host_res = host.resolve() if host is not None else None

    def outside(target: Path) -> bool:
        """A host file outside the docs tree (DEVELOPMENT.md, LICENSE, a stub, ...)."""
        return target != front_res and not (target == docs or docs in target.parents)

    def mapper_for(original_dir: Path, staged_dir: Path):
        def mapper(path: str) -> str | None:
            target = (original_dir / path).resolve()
            if target == front_res:
                return os.path.relpath(dest / "README.md", staged_dir)
            if target == docs or docs in target.parents:
                return os.path.relpath(dest / target.relative_to(docs), staged_dir)
            if host_res is not None and web and (target == host_res or host_res in target.parents):
                rel = target.relative_to(host_res).as_posix()
                kind = "tree" if target.is_dir() else "blob"
                return f"{web}/{kind}/{ref}/{rel}"
            return os.path.relpath(target, staged_dir)
        return mapper

    def unlink_host_files(text: str, original_dir: Path) -> str:
        """Without a web URL, a link to a host file has no target in the built site or the
        PDF; keep its text and drop the link."""
        if web:
            return text

        def one(m: re.Match) -> str:
            target = m.group(2).split("#", 1)[0]
            if not target or SCHEME_RE.match(target) or target.startswith(("#", "/")):
                return m.group(0)
            return m.group(1) if outside((original_dir / target).resolve()) else m.group(0)
        lines = text.splitlines(keepends=True)
        mask = _fence_mask([l.rstrip("\n") for l in lines])
        return "".join(l if mask[i] else INLINE_LINK_RE.sub(one, l) for i, l in enumerate(lines))

    def staged(text: str, original_dir: Path, staged_dir: Path) -> str:
        return rewrite_links(unlink_host_files(text, original_dir), mapper_for(original_dir, staged_dir))

    for page in sorted(dest.rglob("*.md")):
        rel = page.relative_to(dest)
        if rel.as_posix() == "README.md":
            continue
        original = docs / rel
        text = page.read_text()
        new = staged(text, original.parent, page.parent)
        if new != text:
            page.write_text(new)
    (dest / "README.md").write_text(staged(front.read_text(), front.parent, dest))
    return dest


# --- CLI --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consolidation and staging for embedded guides")
    sub = parser.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("inventory", help="list documentation candidates in the host (read-only)")
    i.add_argument("--format", choices=["yaml", "json"], default="yaml")
    a = sub.add_parser("apply", help="execute an approved move plan")
    a.add_argument("--plan", type=Path, required=True)
    a.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("stage", help="stage docs/ with the front page for the site and PDF builds")
    s.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("retarget", help="point stubs and front page links at moved pages")
    r.add_argument("mappings", nargs="+", metavar="OLD=NEW")
    f = sub.add_parser("front-page-status", help="report hand edits of the front page since the baseline")
    f.add_argument("--record", action="store_true", help="record the current front page in the baseline")
    for p in (i, a, s, r, f):
        p.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        if args.cmd == "inventory":
            data = inventory(args.root)
            if args.format == "json":
                print(json.dumps(data, indent=2))
            else:
                print(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), end="")
        elif args.cmd == "apply":
            ops = apply(args.root, args.plan, args.dry_run)
            prefix = "would " if args.dry_run else ""
            for op in ops:
                print(f"{prefix}{op}")
            print(f"apply: {len(ops)} operation(s){' (dry run, nothing changed)' if args.dry_run else ''}")
        elif args.cmd == "stage":
            dest = stage(args.root, args.out)
            print(f"staged {dest}")
        elif args.cmd == "retarget":
            changed = retarget(args.root, args.mappings)
            for rel in changed:
                print(f"retargeted {rel}")
            print(f"retarget: {len(changed)} file(s) changed")
        elif args.cmd == "front-page-status":
            state, detail = front_page_status(args.root, args.record)
            if state == "recorded":
                print(f"recorded front page blob {detail}")
            elif state == "unrecorded":
                print("unrecorded: baseline.yaml has no front_page_blob yet (front-page-status --record)")
            else:
                print(state)
                if detail:
                    print(detail, end="")
                if state == "edited":
                    return 10
    except Refused as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    except guidecfg.ConfigError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
