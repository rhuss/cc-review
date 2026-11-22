#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Compare the baseline with the current state of every source and input (FR-025, FR-025a).

Check-only: nothing in the guide project changes except the fetch cache under
.guide/cache/. Runs without an AI session, so the scheduled workflow can call it.

Per source: fetch the tracked branch (the baseline `ref` when it names a branch,
otherwise the default branch), diff the pinned commit against its head, and keep
only files cited in source blocks. Affected pages are the pages citing a changed
file plus the pages linking to them. Change requests are re-read through `gh api`;
inputs are compared by checksum.

The `self` source of an embedded guide (specs/005-embedded-guide, research R5) uses
fingerprint mode: the blob id of every cited host file, recorded in the baseline, is
compared with the same file at the checked-out head (the default branch in the
scheduled workflow). Only cited files count,
so commits that change only guide files are never drift, and a pinned commit that a
squash merge removed is never `pin-missing`. Inputs recorded at a revision of the host
(`self:` locations) report `recorded`; `local:` inputs are shown by id only.

Pull request mode (`--pr --base SHA [--head SHA]`, research R7) checks only `self`: it
passes when the pull request changes no cited file; otherwise only when the `self` entry
of baseline.yaml changed and every cited file at the head matches its fingerprint.
GUIDE_SKIP=1 (the guide-skip label) passes with a note. It needs no network and no other
source.

Usage: uv run tools/guide/drift.py --check [--source ID] [--format markdown|json] [--root DIR]
       uv run tools/guide/drift.py --pr --base SHA [--head SHA] [--format markdown|json] [--root DIR]
Exit status: 0 no drift, 10 drift or something that needs attention (changed cited
files, change-request transitions, pin-missing or unchecked sources, changed or
unreadable inputs), 2 on configuration errors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import yaml

import fetch
import guidecfg
import sources

GhCallable = Callable[[str, int], "dict | None"]

XREF_RE = sources.XREF_RE
SCHEME_RE = sources.SCHEME_RE
CHANGE_NAMES = {"M": "modified", "D": "deleted", "R": "renamed", "A": "added", "C": "copied", "T": "type-changed"}


# --- report entities ---------------------------------------------------------


@dataclass
class SourceStatus:
    id: str
    status: str  # current | moved | unchecked | pin-missing
    pinned: str
    mode: str = "commit"  # commit | fingerprint (the `self` source)
    head: str = ""
    branch: str = ""
    commits_since: int = 0
    log: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class ChangedFile:
    source: str
    path: str
    change: str  # modified | renamed | deleted | added | copied | type-changed
    new_path: str = ""
    pages: list[str] = field(default_factory=list)

    def describe(self) -> str:
        if self.change in ("renamed", "copied"):
            return f"{self.change} {self.path} -> {self.new_path}"
        return f"{self.change} {self.path}"


@dataclass
class ChangeRequestStatus:
    source: str
    number: int
    anchor: str
    recorded_state: str
    recorded_head: str
    tier: str
    state: str = ""
    head: str = ""
    transition: str = "unchecked"  # unchanged | head-moved | merged | closed | unchecked
    suggested_tier: str = ""
    message: str = ""


@dataclass
class InputStatus:
    id: str
    location: str
    status: str  # unchanged | changed | unreadable | skipped | recorded
    message: str = ""


@dataclass
class DriftReport:
    captured: str
    sources: list[SourceStatus] = field(default_factory=list)
    changed_files: list[ChangedFile] = field(default_factory=list)
    affected_pages: list[str] = field(default_factory=list)
    change_requests: list[ChangeRequestStatus] = field(default_factory=list)
    inputs: list[InputStatus] = field(default_factory=list)

    @property
    def has_drift(self) -> bool:
        return bool(
            self.changed_files
            or any(s.status in ("unchecked", "pin-missing") for s in self.sources)
            or any(c.transition in ("head-moved", "merged", "closed") for c in self.change_requests)
            or any(i.status in ("changed", "unreadable") for i in self.inputs)
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["has_drift"] = self.has_drift
        for change, entry in zip(self.changed_files, data["changed_files"]):
            entry["description"] = change.describe()
        return data


# --- git helpers ---------------------------------------------------------------


def _git(*args: str) -> subprocess.CompletedProcess:
    return fetch._git(*args, check=False)


def _rev(bare: Path, ref: str) -> str | None:
    proc = _git("-C", str(bare), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    out = proc.stdout.strip()
    return out if proc.returncode == 0 and fetch.SHA_RE.match(out) else None


def _tracked_branch(bare: Path, ref: str | None) -> str | None:
    """The branch to compare against: the baseline ref when it is a branch, else the default branch."""
    if ref and ref != "HEAD" and _rev(bare, f"refs/heads/{ref}"):
        return ref
    proc = _git("-C", str(bare), "symbolic-ref", "--quiet", "HEAD")
    head_ref = proc.stdout.strip()
    if proc.returncode == 0 and head_ref.startswith("refs/heads/") and _rev(bare, head_ref):
        return head_ref[len("refs/heads/"):]
    for candidate in ("main", "master"):
        if _rev(bare, f"refs/heads/{candidate}"):
            return candidate
    return None


def _pin_reachable(bare: Path, commit: str) -> bool:
    """True when some fetched branch, tag, or pull ref still contains the pinned commit."""
    proc = _git("-C", str(bare), "for-each-ref", "--contains", commit, "--format=%(refname)",
                "refs/heads", "refs/tags", "refs/pull")
    return proc.returncode == 0 and bool(proc.stdout.strip())


def _source_state(root: Path, source: guidecfg.Source,
                  crs: list[guidecfg.ChangeRequest]) -> tuple[SourceStatus, Path | None]:
    status = SourceStatus(id=source.id, status="unchecked", pinned=source.commit)
    try:
        bare = fetch._update_bare(root, source, crs)
    except fetch.FetchError as err:
        status.message = f"source could not be read: {err}"
        return status, None
    # drop branches deleted upstream so a force-pushed or removed pin is detected
    _git("-C", str(bare), "fetch", "--quiet", "--prune", "origin", "+refs/heads/*:refs/heads/*")
    branch = _tracked_branch(bare, source.ref)
    if branch is None:
        status.message = "no branch to compare against (the remote has no default branch)"
        return status, None
    head = _rev(bare, f"refs/heads/{branch}")
    status.branch = branch
    status.head = head or ""
    missing_msg = f"pinned commit {source.commit} no longer exists upstream; pin a new revision"
    try:
        fetch._ensure_commit(bare, source.commit)
    except fetch.FetchError:
        status.status = "pin-missing"
        status.message = missing_msg
        return status, None
    if not _pin_reachable(bare, source.commit):
        status.status = "pin-missing"
        status.message = missing_msg
        return status, None
    if head == source.commit:
        status.status = "current"
        return status, bare
    status.status = "moved"
    count = _git("-C", str(bare), "rev-list", "--count", f"{source.commit}..{head}").stdout.strip()
    status.commits_since = int(count) if count.isdigit() else 0
    log = _git("-C", str(bare), "log", "--oneline", "--no-decorate", "-50", f"{source.commit}..{head}")
    status.log = [line for line in log.stdout.splitlines() if line.strip()]
    return status, bare


def _self_state(root: Path, source: guidecfg.Source,
                cited: set[str]) -> tuple[SourceStatus, list[tuple[str, str, str]]]:
    """Status and changed cited files of the `self` source in fingerprint mode (research R5)."""
    status = SourceStatus(id=source.id, status="unchecked", pinned=source.commit, mode="fingerprint")
    top = guidecfg.host_toplevel(root)
    if top is None:
        status.message = "the host repository was not found"
        return status, []
    # Compare with the checked-out commit (spec FR-014 "current head"): the guide sits
    # beside this code, and the scheduled workflow checks out the default branch.
    head = fetch.self_head(top, None)
    if head is None:
        status.message = "the host repository has no commit to compare against"
        return status, []
    branch = _git("-C", str(top), "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    status.branch = branch if branch and branch != "HEAD" else (source.ref or "HEAD")
    status.head = head
    pinned = fetch.commit_exists(top, source.commit)
    changes: list[tuple[str, str, str]] = []
    for path in sorted(cited):
        recorded = source.fingerprints.get(path)
        if recorded is None and pinned:
            recorded = fetch.blob_at(top, source.commit, path)
        current = fetch.blob_at(top, head, path)
        if recorded is not None and recorded == current:
            continue
        changes.append(("deleted" if current is None else "modified", path, ""))
    status.status = "current" if head == source.commit else "moved"
    reachable = pinned and _git("-C", str(top), "merge-base", "--is-ancestor", source.commit, head).returncode == 0
    if reachable and head != source.commit:
        count = _git("-C", str(top), "rev-list", "--count", f"{source.commit}..{head}").stdout.strip()
        status.commits_since = int(count) if count.isdigit() else 0
        log = _git("-C", str(top), "log", "--oneline", "--no-decorate", "-50", f"{source.commit}..{head}")
        status.log = [line for line in log.stdout.splitlines() if line.strip()]
        renames = {old: new for change, old, new in _name_status(top, source.commit, head) if change == "renamed"}
        changes = [("renamed", p, renames[p]) if c == "deleted" and p in renames else (c, p, n)
                   for c, p, n in changes]
    elif not reachable and head != source.commit:
        shallow = _git("-C", str(top), "rev-parse", "--is-shallow-repository").stdout.strip() == "true"
        status.message = ("the history is not available in this shallow checkout; cited files were compared "
                          "by their fingerprints" if shallow else
                          "the pinned commit is not in the history of the tracked branch (a squash or rebase "
                          "merge); cited files were compared by their fingerprints")
    return status, changes


def _name_status(bare: Path, old: str, new: str) -> list[tuple[str, str, str]]:
    """(change, path, new_path) for every file that differs between two commits."""
    proc = _git("-C", str(bare), "diff", "--name-status", "-M", old, new)
    entries = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        code = parts[0][:1]
        change = CHANGE_NAMES.get(code, "modified")
        if code in ("R", "C") and len(parts) >= 3:
            entries.append((change, parts[1], parts[2]))
        else:
            entries.append((change, parts[1], ""))
    return entries


# --- pages and links -----------------------------------------------------------


def _style(adapter: guidecfg.Adapter) -> str:
    return "line" if adapter.comment == "line" else "html"


def _rel(root: Path, page: Path) -> str:
    # relpath, not relative_to: an embedded guide's front page lies outside the root (../README.md)
    return Path(os.path.relpath(page.resolve(), root.resolve())).as_posix()


def _citations(pages: list[Path], style: str) -> dict[Path, set[tuple[str, str]]]:
    cited: dict[Path, set[tuple[str, str]]] = {}
    for page in pages:
        block = sources.find_block(page.read_text(errors="replace"), style)
        refs = block.refs if block else []
        cited[page] = {(r.source_id, r.path) for r in refs if r.kind == "source"}
    return cited


def _antora_id(page: Path) -> tuple[str, str] | None:
    """(module, path inside the module's pages directory) for an Antora page."""
    parts = page.resolve().parts
    for i in range(len(parts) - 3, -1, -1):
        if parts[i] == "modules" and i + 2 < len(parts) and parts[i + 2] == "pages":
            return parts[i + 1], "/".join(parts[i + 3:])
    return None


def _xref_targets(page: Path, text: str) -> set[tuple[str, str]]:
    current = _antora_id(page)
    if current is None:
        return set()
    module, path = current
    targets = set()
    for raw in XREF_RE.findall(text):
        target = raw.split("#", 1)[0]
        if not target:
            continue
        parts = target.split(":")
        if len(parts) >= 3:
            mod, p = parts[-2], parts[-1]
        elif len(parts) == 2:
            mod, p = parts
        else:
            mod, p = module, parts[0]
        if p.startswith(("./", "../")):
            p = posixpath.normpath(posixpath.join(posixpath.dirname(path), p))
        if not p.endswith(".adoc"):
            p += ".adoc"
        targets.add((mod or module, p))
    return targets


def _md_targets(page: Path, text: str) -> set[Path]:
    targets = set()
    for raw in sources.link_targets(text):
        if SCHEME_RE.match(raw) or raw.startswith(("#", "/", "mailto:")):
            continue
        target = raw.split("#", 1)[0].split("?", 1)[0]
        if not target:
            continue
        resolved = (page.parent / target).resolve()
        candidates = [resolved]
        if resolved.suffix != ".md":
            candidates += [resolved / "README.md", resolved / "index.md", resolved.with_suffix(".md")]
        targets.update(candidates)
    return targets


def _linking_pages(pages: list[Path], targets: set[Path]) -> set[Path]:
    """Pages that link to any page in targets (Antora xrefs and Markdown links)."""
    by_id = {}
    for p in targets:
        aid = _antora_id(p)
        if aid:
            by_id[aid] = p
    resolved_targets = {p.resolve() for p in targets}
    linking = set()
    for page in pages:
        if page in targets:
            continue
        text = page.read_text(errors="replace")
        if page.suffix == ".adoc":
            if _xref_targets(page, text) & set(by_id):
                linking.add(page)
        elif page.suffix == ".md":
            if _md_targets(page, text) & resolved_targets:
                linking.add(page)
    return linking


# --- change requests and inputs -----------------------------------------------


def evaluate_change_requests(baseline: guidecfg.Baseline, gh: GhCallable = fetch._gh_pull) -> list[ChangeRequestStatus]:
    """Re-read every recorded change request (FR-027)."""
    results = []
    for cr in baseline.change_requests:
        status = ChangeRequestStatus(source=cr.source, number=cr.number, anchor=cr.anchor,
                                     recorded_state=cr.state, recorded_head=cr.head, tier=cr.tier)
        results.append(status)
        src = baseline.source(cr.source)
        slug = src.github_slug if src else None
        if not slug:
            status.message = "not a GitHub source; state not checked"
            continue
        info = gh(slug, cr.number)
        if not info:
            status.message = "gh unavailable or the request failed; state not checked"
            continue
        head = info.get("head") or ""
        status.head = head
        if info.get("merged"):
            status.state = "merged"
            if cr.state == "merged":
                status.transition = "unchanged"
            else:
                status.transition = "merged"
                status.suggested_tier = "on-main"
                status.message = "merged: move the label to the on-main tier, or remove it once released"
        elif info.get("state") == "closed":
            status.state = "closed"
            status.transition = "unchanged" if cr.state == "closed" else "closed"
            if status.transition == "closed":
                status.message = "closed without merge: remove or rework the experimental content"
        else:
            status.state = "open"
            if head and head != cr.head:
                status.transition = "head-moved"
                status.message = f"head moved from {cr.head[:7]} to {head[:7]}: re-verify the experimental content"
            else:
                status.transition = "unchanged"
    return results


def evaluate_inputs(inputs: guidecfg.Inputs) -> list[InputStatus]:
    """Compare input checksums with the register (FR-005a)."""
    results = []
    for item in inputs.inputs:
        if item.is_self:
            results.append(InputStatus(item.id, item.location, "recorded",
                                       f"read from the host at {item.revision[:7]}; not compared"))
            continue
        if item.is_local and not item.resolved:
            results.append(InputStatus(item.id, item.location, "skipped",
                                       f"confidential input; its location is only in {guidecfg.LOCAL_FILE} "
                                       "on the author's machine; not compared"))
            continue
        path = item.path(inputs.root)
        if path is None or not item.sha256:
            results.append(InputStatus(item.id, item.location, "skipped",
                                       "link or no checksum recorded; not compared"))
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as err:
            results.append(InputStatus(item.id, item.location, "unreadable", f"cannot read: {err.strerror or err}"))
            continue
        if digest != item.sha256:
            results.append(InputStatus(item.id, item.location, "changed", "checksum differs from the register"))
        else:
            results.append(InputStatus(item.id, item.location, "unchanged"))
    return results


# --- report --------------------------------------------------------------------


def report(root: Path, gh: GhCallable = fetch._gh_pull, only: str | None = None) -> DriftReport:
    """Drift between the baseline and the current state of sources, change requests, and inputs.

    only limits the report to one source (its change requests included, inputs left out).
    """
    root = Path(root)
    baseline = guidecfg.load_baseline(root)
    if only is not None:
        if baseline.source(only) is None:
            raise guidecfg.ConfigError(root / "baseline.yaml", f"unknown source {only!r}")
        baseline.sources = [s for s in baseline.sources if s.id == only]
        baseline.change_requests = [c for c in baseline.change_requests if c.source == only]
    inputs = guidecfg.load_inputs(root)
    adapter = guidecfg.load_adapter(root)
    pages = guidecfg.pages(root, adapter, "all")
    cited = _citations(pages, _style(adapter))

    rep = DriftReport(captured=baseline.captured)
    citing_changed: set[Path] = set()
    embedded = guidecfg.embedded_front_page(root) is not None
    for source in baseline.sources:
        if source.id == guidecfg.SELF_ID and embedded:
            cited_self = {path for refs in cited.values() for sid, path in refs if sid == source.id}
            status, changes = _self_state(root, source, cited_self)
            rep.sources.append(status)
            for change, path, new_path in changes:
                citing = sorted(_rel(root, p) for p, refs in cited.items() if (source.id, path) in refs)
                rep.changed_files.append(ChangedFile(source.id, path, change, new_path, citing))
                citing_changed.update(p for p, refs in cited.items() if (source.id, path) in refs)
            continue
        status, bare = _source_state(root, source, baseline.change_requests)
        rep.sources.append(status)
        if bare is None or status.status != "moved":
            continue
        for change, path, new_path in _name_status(bare, source.commit, status.head):
            citing = sorted(_rel(root, p) for p, refs in cited.items() if (source.id, path) in refs)
            if not citing:
                continue
            rep.changed_files.append(ChangedFile(source.id, path, change, new_path, citing))
            citing_changed.update(p for p, refs in cited.items() if (source.id, path) in refs)

    affected = set(citing_changed) | _linking_pages(pages, citing_changed)
    rep.affected_pages = sorted(_rel(root, p) for p in affected)
    rep.change_requests = evaluate_change_requests(baseline, gh)
    rep.inputs = evaluate_inputs(inputs) if only is None else []
    return rep


def to_markdown(rep: DriftReport) -> str:
    out = ["# Guide drift report", ""]
    verdict = "Drift found: the guide needs an evolve run (`/guide:evolve`)." if rep.has_drift else "No drift."
    out += [f"Baseline captured {rep.captured}. {verdict}", ""]
    for s in rep.sources:
        out.append(f"## Source `{s.id}`")
        out.append("")
        if s.status in ("unchecked", "pin-missing"):
            out += [f"Status: **{s.status}**. {s.message}", ""]
            continue
        if s.mode == "fingerprint":
            out += [f"Status: {s.status} (fingerprint mode). Pinned `{s.pinned[:7]}`, head of `{s.branch}` is "
                    f"`{s.head[:7]}`; cited files are compared by their recorded blob ids.", ""]
            if s.message:
                out += [s.message, ""]
            out += [f"- {line}" for line in s.log] + ([""] if s.log else [])
            mine = [c for c in rep.changed_files if c.source == s.id]
            if mine:
                out += ["Changed cited files:", ""]
                out += [f"- {c.describe()} (cited by {', '.join(f'`{p}`' for p in c.pages)})" for c in mine]
                out.append("")
            else:
                out += ["No cited file changed.", ""]
            continue
        if s.status == "current":
            out += [f"Status: current. The pin `{s.pinned[:7]}` is the head of `{s.branch}`.", ""]
            continue
        out += [f"Status: moved. Pinned `{s.pinned[:7]}`, head of `{s.branch}` is `{s.head[:7]}`, "
                f"{s.commits_since} commit(s) since the pin.", ""]
        out += [f"- {line}" for line in s.log] + [""]
        mine = [c for c in rep.changed_files if c.source == s.id]
        if mine:
            out.append("Changed cited files:")
            out.append("")
            for c in mine:
                out.append(f"- {c.describe()} (cited by {', '.join(f'`{p}`' for p in c.pages)})")
            out.append("")
        else:
            out += ["No cited file changed.", ""]
    out += ["## Affected pages", ""]
    if rep.affected_pages:
        out += [f"- `{p}`" for p in rep.affected_pages]
    else:
        out.append("None.")
    out.append("")
    out += ["## Change requests", ""]
    if rep.change_requests:
        out += ["| Source | Number | Recorded | Now | Transition | Note |", "|---|---|---|---|---|---|"]
        for c in rep.change_requests:
            recorded = f"{c.recorded_state} `{c.recorded_head[:7]}`"
            now = f"{c.state} `{c.head[:7]}`" if c.state else "unchecked"
            out.append(f"| {c.source} | {c.number} | {recorded} | {now} | {c.transition} | {c.message} |")
    else:
        out.append("None recorded.")
    out.append("")
    out += ["## Inputs", ""]
    if rep.inputs:
        for i in rep.inputs:
            note = f": {i.message}" if i.message and i.status != "unchanged" else ""
            # a local: input is confidential; its real location never appears in a report
            where = "local input" if i.location.startswith("local:") else i.location
            out.append(f"- `{i.id}` ({where}): {i.status}{note}")
    else:
        out.append("None registered.")
    out.append("")
    return "\n".join(out)


# --- pull request mode (research R7) --------------------------------------------------


@dataclass
class PrReport:
    base: str
    head: str
    cited_changed: list[str] = field(default_factory=list)
    affected_pages: list[str] = field(default_factory=list)
    baseline_updated: bool = False
    fingerprints_match: bool = False
    skipped: bool = False
    result: str = "pass"

    def to_dict(self) -> dict:
        return asdict(self)


class PrError(Exception):
    """The pull request check cannot run (configuration or a missing revision)."""


def _self_entry(top: Path, rev: str, guide_dir: str) -> dict | None:
    """The raw `self` entry of the guide's baseline.yaml at rev (None when the file or entry is missing)."""
    proc = _git("-C", str(top), "show", f"{rev}:{guide_dir}/baseline.yaml")
    if proc.returncode != 0:
        return None
    try:
        data = yaml.safe_load(proc.stdout) or {}
    except yaml.YAMLError:
        return None
    return next((s for s in data.get("sources") or [] if isinstance(s, dict) and s.get("id") == guidecfg.SELF_ID),
                None)


def pr_report(root: Path, base: str, head: str = "HEAD", skip: bool = False) -> PrReport:
    """The pull request check for the `self` source (FR-026 to FR-028).

    Changes are taken from the merge base of base and head to head, so commits that
    reached the base branch after the pull request branched off are not counted.
    """
    root = Path(root)
    if guidecfg.embedded_front_page(root) is None:
        raise PrError("the pull request check is for embedded guides only")
    top = guidecfg.host_toplevel(root)
    if top is None:
        raise PrError("the guide is not inside a git repository")
    shas = []
    for rev in (base, head):
        proc = _git("-C", str(top), "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
        if proc.returncode != 0 or not fetch.SHA_RE.match(proc.stdout.strip()):
            raise PrError(f"revision {rev} is not in this checkout (fetch the full history: fetch-depth 0)")
        shas.append(proc.stdout.strip())
    base_sha, head_sha = shas
    # Compare from the merge base, as GitHub's own pull request diff does: the base
    # branch may have moved since the pull request branched off, and its later changes
    # to cited files are not this pull request's changes.
    proc = _git("-C", str(top), "merge-base", base_sha, head_sha)
    if proc.returncode != 0 or not fetch.SHA_RE.match(proc.stdout.strip()):
        raise PrError(f"no merge base of {base_sha[:7]} and {head_sha[:7]} in this checkout "
                      "(fetch the full history: fetch-depth 0)")
    base_sha = proc.stdout.strip()
    guide_dir = Path(os.path.relpath(root.resolve(), top.resolve())).as_posix()
    adapter = guidecfg.load_adapter(root)
    pages = guidecfg.pages(root, adapter, "all")
    cited = _citations(pages, _style(adapter))
    cited_self = sorted({path for refs in cited.values() for sid, path in refs if sid == guidecfg.SELF_ID})
    rep = PrReport(base=base_sha, head=head_sha, skipped=skip)
    changed = [p for p in cited_self if fetch.blob_at(top, base_sha, p) != fetch.blob_at(top, head_sha, p)]
    rep.cited_changed = changed
    citing = {p for p, refs in cited.items() if any((guidecfg.SELF_ID, c) in refs for c in changed)}
    rep.affected_pages = sorted(_rel(root, p) for p in citing | _linking_pages(pages, citing))
    before, after = _self_entry(top, base_sha, guide_dir), _self_entry(top, head_sha, guide_dir)
    rep.baseline_updated = before is None or before != after
    fingerprints = (after or {}).get("fingerprints") or {}
    rep.fingerprints_match = all(fingerprints.get(p) is not None and fingerprints.get(p) == fetch.blob_at(top, head_sha, p)
                                 for p in cited_self)
    # result stays "pass" when the check is skipped or no cited file changed
    if changed and not skip:
        rep.result = "pass" if rep.baseline_updated and rep.fingerprints_match else "fail"
    return rep


def pr_markdown(rep: PrReport) -> str:
    out = ["# Guide check for this pull request", ""]
    if rep.skipped:
        out += ["**Pass.** The guide update was skipped by request (label `guide-skip`).", ""]
    elif not rep.cited_changed:
        out += ["**Pass.** This pull request changes no file that the guide cites.", ""]
    elif rep.result == "pass":
        out += ["**Pass.** Cited files changed, and the guide was re-verified against them "
                "(the `self` baseline entry changed and its fingerprints match this pull request).", ""]
    else:
        reason = ("the `self` entry of the guide baseline did not change" if not rep.baseline_updated else
                  "the cited files at this pull request's head do not match the fingerprints in the guide baseline")
        out += [f"**Fail.** Cited files changed, but {reason}. Run `/guide:evolve` on this branch and commit the "
                "result, or add the label `guide-skip` when the change does not touch documented behavior.", ""]
    out += [f"Base `{rep.base[:7]}`, head `{rep.head[:7]}`.", ""]
    if rep.cited_changed:
        out += ["Changed cited files:", ""] + [f"- `{p}`" for p in rep.cited_changed] + [""]
        out += ["Affected guide pages:", ""] + [f"- `{p}`" for p in rep.affected_pages] + [""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report drift between the baseline and the sources")
    parser.add_argument("--check", action="store_true", help="check only (nothing is changed)")
    parser.add_argument("--source", help="limit the check to one source id")
    parser.add_argument("--pr", action="store_true",
                        help="pull request mode for an embedded guide's self source (needs --base)")
    parser.add_argument("--base", help="pull request mode: the base commit")
    parser.add_argument("--head", default="HEAD", help="pull request mode: the head commit (default HEAD)")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    if args.pr:
        if not args.base:
            parser.error("--pr needs --base")
        try:
            pr = pr_report(args.root, args.base, args.head, os.environ.get("GUIDE_SKIP", "") == "1")
        except (PrError, guidecfg.ConfigError) as err:
            print(f"error: {err}", file=sys.stderr)
            return 2
        print(json.dumps(pr.to_dict(), indent=2) if args.format == "json" else pr_markdown(pr))
        return 0 if pr.result == "pass" else 10
    try:
        rep = report(args.root, only=args.source)
    except guidecfg.ConfigError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(rep.to_dict(), indent=2))
    else:
        print(to_markdown(rep))
    return 10 if rep.has_drift else 0


if __name__ == "__main__":
    sys.exit(main())
