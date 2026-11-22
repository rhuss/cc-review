#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Pin, fetch, and re-pin the sources recorded in baseline.yaml.

  pin --source ID=REPO[@REF]...   resolve REF (default HEAD) to a full SHA and write baseline.yaml
  fetch [--allow-unverified]      blobless bare clones plus worktrees at the pinned commits
  rebaseline --to ID=REF...       move pins to new revisions, refresh change-request states
  where ID [--commit SHA]         print the readable snapshot directory of a source

Layout under the guide project:
  .guide/cache/<id>.git   blobless bare clone
  .guide/cache/<id>/      detached worktree at the pinned commit

The `self` source of an embedded guide (specs/005-embedded-guide, research R4, R5) is
the host repository itself (`repo: ..`). It is read with `git -C <host toplevel>`, never
cloned into .guide/cache/, and its snapshot is exported (read-tree and checkout-index) to
${XDG_CACHE_HOME:-~/.cache}/cc-guide/self/<hash of the host path>/<commit>/, outside the
host. `pin` records the host's default branch as `ref` and the `web` URL of a GitHub
`origin`; `pin` and `rebaseline` record `fingerprints` (cited path -> blob id at the
pinned commit), so drift survives squash merges; `rebaseline` also stores the front page
blob.

Every git call runs as `git -C <path>` from the current directory; nothing here
changes the working directory or runs commands inside the cache.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

import yaml

import guidecfg
import region
import sources as sources_mod

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
GITHUB_SHORT_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
DEFAULT_HEADER = "# Pinned sources and change requests (the baseline). Written by tools/guide/fetch.py.\n"
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


class FetchError(Exception):
    """A source could not be pinned or fetched."""


# --- helpers ----------------------------------------------------------------


GIT_TIMEOUT = int(os.environ.get("GUIDE_GIT_TIMEOUT", "600"))


def _git(*args: str, check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess:
    """Run git with prompts disabled and a timeout (a hung remote must not hang a run or CI)."""
    try:
        proc = subprocess.run(["git", *args], capture_output=True, text=True, env=GIT_ENV,
                              timeout=timeout or GIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc = subprocess.CompletedProcess(["git", *args], 124, "",
                                           f"timed out after {timeout or GIT_TIMEOUT}s (set GUIDE_GIT_TIMEOUT to change)")
    if check and proc.returncode != 0:
        raise FetchError(f"git {' '.join(args)}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def parse_spec(spec: str) -> tuple[str, str, str | None]:
    """Split `ID=REPO[@REF]` into (id, repo, ref or None)."""
    if "=" not in spec:
        raise FetchError(f"bad source spec {spec!r} (expected ID=REPO[@REF])")
    source_id, rest = spec.split("=", 1)
    repo, ref = rest, None
    if "@" in rest:
        head, tail = rest.rsplit("@", 1)
        # git@host:owner/name has its only "@" before the host; refs never contain ":"
        if ":" not in tail and not (head == "git" or head.endswith("://git")):
            repo, ref = head, tail
    if not source_id or not repo:
        raise FetchError(f"bad source spec {spec!r} (expected ID=REPO[@REF])")
    return source_id, repo, ref or None


def clone_url(repo: str, root: Path) -> str:
    """URL or path git can clone for a baseline `repo` value."""
    if guidecfg.URL_RE.match(repo) or repo.startswith("git@"):
        return repo
    path = Path(repo).expanduser()
    if not path.is_absolute():
        path = Path(root) / path
    if path.exists():
        return str(path.resolve())
    if GITHUB_SHORT_RE.match(repo):
        return f"https://github.com/{repo}.git"
    return repo


def _today() -> str:
    return _dt.date.today().isoformat()


def _read_raw(root: Path) -> tuple[str, dict]:
    path = Path(root) / "baseline.yaml"
    if not path.is_file():
        return DEFAULT_HEADER, {"captured": _today(), "sources": [], "change_requests": []}
    text = path.read_text()
    header_lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith("#"):
            header_lines.append(line)
        else:
            break
    data = yaml.safe_load(text) or {}
    return "".join(header_lines) or DEFAULT_HEADER, data


def _write_raw(root: Path, header: str, data: dict) -> None:
    for key in ("captured",):
        value = data.get(key)
        if isinstance(value, (_dt.date, _dt.datetime)):
            data[key] = value.strftime("%Y-%m-%d")
    ordered = {k: data[k] for k in ("captured", "sources", "change_requests") if k in data}
    ordered.update({k: v for k, v in data.items() if k not in ordered})
    if not ordered.get("change_requests"):
        ordered.pop("change_requests", None)
    body = yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True)
    # Write atomically: an interrupted run must never leave a truncated baseline.
    target = Path(root) / "baseline.yaml"
    tmp = target.with_name(".baseline.yaml.tmp")
    tmp.write_text(header + body)
    os.replace(tmp, target)


def _ls_remote(url: str, ref: str | None) -> str:
    """Resolve a ref on a remote to a full commit SHA."""
    proc = _git("ls-remote", "--", url, check=False)
    if proc.returncode != 0:
        raise FetchError(f"cannot read {url}: {proc.stderr.strip()}")
    refs: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        sha, _, name = line.partition("\t")
        refs[name] = sha
    want = ref or "HEAD"
    for name in (want, f"refs/heads/{want}", f"refs/tags/{want}^{{}}", f"refs/tags/{want}"):
        if name in refs:
            return refs[name]
    raise FetchError(f"ref {want!r} not found in {url}")


def _cache(root: Path) -> Path:
    return Path(root) / ".guide" / "cache"


def _update_bare(root: Path, source: guidecfg.Source, change_requests: list[guidecfg.ChangeRequest]) -> Path:
    """Clone (blobless, bare) or update the source's cache; return the bare repository path."""
    url = clone_url(source.repo, root)
    bare = _cache(root) / f"{source.id}.git"
    if not bare.is_dir():
        bare.parent.mkdir(parents=True, exist_ok=True)
        proc = _git("clone", "--quiet", "--bare", "--filter=blob:none", "--", url, str(bare), check=False)
        if proc.returncode != 0:
            shutil.rmtree(bare, ignore_errors=True)
            raise FetchError(f"cannot clone {source.repo}: {proc.stderr.strip()}")
    else:
        _git("-C", str(bare), "config", "remote.origin.url", url)
    proc = _git("-C", str(bare), "fetch", "--quiet", "origin",
                "+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*", check=False)
    if proc.returncode != 0:
        raise FetchError(f"cannot fetch {source.repo}: {proc.stderr.strip()}")
    if source.github_slug:
        for cr in change_requests:
            if cr.source == source.id:
                _git("-C", str(bare), "fetch", "--quiet", "origin",
                     f"+refs/pull/{cr.number}/head:refs/pull/{cr.number}/head", check=False)
    return bare


def _ensure_commit(bare: Path, commit: str) -> None:
    if _git("-C", str(bare), "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode == 0:
        return
    _git("-C", str(bare), "fetch", "--quiet", "origin", commit, check=False)
    if _git("-C", str(bare), "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode != 0:
        raise FetchError(f"pinned commit {commit} no longer exists upstream; pin a new revision")


def _place_worktree(root: Path, source_id: str, bare: Path, commit: str) -> Path:
    worktree = (_cache(root) / source_id).resolve()
    if (worktree / ".git").exists():
        _git("-C", str(worktree), "-c", "advice.detachedHead=false", "checkout", "--quiet", "--detach", commit)
    else:
        if worktree.exists():
            shutil.rmtree(worktree)
        _git("-C", str(bare), "worktree", "prune")
        _git("-C", str(bare), "worktree", "add", "--quiet", "--detach", str(worktree), commit)
    return worktree


def _resolve_in_bare(bare: Path, ref: str) -> str | None:
    for name in (ref, f"refs/heads/{ref}", f"refs/tags/{ref}"):
        proc = _git("-C", str(bare), "rev-parse", "--verify", "--quiet", f"{name}^{{commit}}", check=False)
        if proc.returncode == 0 and SHA_RE.match(proc.stdout.strip()):
            return proc.stdout.strip()
    return None


# --- the `self` source (embedded guides) ----------------------------------------

SELF = guidecfg.SELF_ID


def host_toplevel(root: Path) -> Path:
    top = guidecfg.host_toplevel(root)
    if top is None:
        raise FetchError(f"{root} is not inside a git repository; the 'self' source needs the host repository")
    return top


def _cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")


def self_snapshot_dir(top: Path, commit: str) -> Path:
    """Export directory of a host commit, outside the host repository (research R4)."""
    key = hashlib.sha256(str(Path(top).resolve()).encode()).hexdigest()[:16]
    return _cache_home() / "cc-guide" / "self" / key / commit


def commit_exists(top: Path, commit: str) -> bool:
    return _git("-C", str(top), "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode == 0


def blob_at(top: Path, rev: str, path: str) -> str | None:
    """Blob id of path at rev in the host repository (None when the path does not exist there)."""
    proc = _git("-C", str(top), "rev-parse", "--verify", "--quiet", f"{rev}:{path}", check=False)
    out = proc.stdout.strip()
    return out if proc.returncode == 0 and SHA_RE.match(out) else None


def default_branch(top: Path) -> str:
    """The host's default branch: origin/HEAD, else main, else master (else the current branch)."""
    proc = _git("-C", str(top), "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", check=False)
    name = proc.stdout.strip()
    if proc.returncode == 0 and name.startswith("refs/remotes/origin/"):
        return name[len("refs/remotes/origin/"):]
    for candidate in ("main", "master"):
        if _git("-C", str(top), "rev-parse", "--verify", "--quiet", f"refs/heads/{candidate}",
                check=False).returncode == 0:
            return candidate
    current = _git("-C", str(top), "branch", "--show-current", check=False).stdout.strip()
    return current or "HEAD"


def self_head(top: Path, ref: str | None) -> str | None:
    """Commit at the head of the tracked branch (local branch, then origin's), else HEAD."""
    names = [f"refs/heads/{ref}", f"refs/remotes/origin/{ref}"] if ref and ref != "HEAD" else []
    for name in names + ["HEAD"]:
        proc = _git("-C", str(top), "rev-parse", "--verify", "--quiet", f"{name}^{{commit}}", check=False)
        if proc.returncode == 0 and SHA_RE.match(proc.stdout.strip()):
            return proc.stdout.strip()
    return None


def origin_web(top: Path) -> str:
    """Browsable URL of the host's origin when it is a GitHub repository, else empty."""
    proc = _git("-C", str(top), "remote", "get-url", "origin", check=False)
    url = proc.stdout.strip()
    if proc.returncode != 0 or not url:
        return ""
    if url.startswith("git@github.com:") or re.match(r"^(https?|ssh|git)://([^@/]+@)?github\.com/", url):
        web = guidecfg.web_url(re.sub(r"^(ssh|git)://([^@/]+@)?github\.com/", "https://github.com/", url))
        return re.sub(r"^https?://[^@/]+@github\.com/", "https://github.com/", web)
    return ""


def self_cited(root: Path) -> set[str]:
    """Host paths cited as self:<path> by the guide's pages (the front page included)."""
    adapter = guidecfg.load_adapter(root, required=False)
    if adapter is None:
        return set()
    style = "line" if adapter.comment == "line" else "html"
    return sources_mod.cited_files(guidecfg.pages(root, adapter, "all"), style).get(SELF, set())


def self_fingerprints(root: Path, top: Path, commit: str) -> dict[str, str]:
    """Cited path -> blob id at commit, for every self path the pages cite and the commit holds."""
    out = {}
    for path in sorted(self_cited(root)):
        blob = blob_at(top, commit, path)
        if blob:
            out[path] = blob
    return out


def normalized_front_page(text: str) -> str:
    """The comparison key of a front page (specs/006, research R5): the region content
    with the values of generated regions removed (make regions rewrites them), so author
    text outside the markers is invisible to hand-edit detection. The whole file when
    it carries no markers (FR-002)."""
    return region.normalized(text)


def store_front_page_blob(root: Path, top: Path) -> str:
    """Store the normalized front page in the host object database; return its blob id."""
    front = guidecfg.embedded_front_page(root)
    if front is None or not front.is_file():
        return ""
    proc = subprocess.run(["git", "-C", str(top), "hash-object", "-w", "--stdin"],
                          input=normalized_front_page(front.read_text()), capture_output=True, text=True,
                          env=GIT_ENV)
    if proc.returncode != 0:
        raise FetchError(f"cannot store the front page blob: {proc.stderr.strip()}")
    return proc.stdout.strip()


def export_snapshot(top: Path, rev: str, dest: Path) -> Path:
    """Export rev of the host into dest (created atomically, kept when present).

    A temporary index (read-tree) and checkout-index write the files straight to disk:
    every tracked file is exported as committed, `export-ignore` attributes do not drop
    any (git archive would), the repository is never held in memory, and symlinks stay
    symlinks. On failure the partial export is removed and FetchError is raised.
    """
    if dest.is_dir():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.tmp-{os.getpid()}")
    index = dest.with_name(f".{dest.name}.index-{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    env = {**GIT_ENV, "GIT_INDEX_FILE": str(index)}
    try:
        for args in (["read-tree", rev], ["checkout-index", "--all", f"--prefix={tmp}/"]):
            try:
                proc = subprocess.run(["git", "-C", str(top), *args], capture_output=True, text=True,
                                      env=env, timeout=GIT_TIMEOUT)
            except subprocess.TimeoutExpired as err:
                raise FetchError(f"git {args[0]} {rev}: timed out") from err
            if proc.returncode != 0:
                raise FetchError(f"git {args[0]} {rev}: {proc.stderr.strip()}")
        try:
            os.replace(tmp, dest)
        except OSError:
            if not dest.is_dir():
                raise
            # another run exported it first
    except (OSError, FetchError) as err:
        shutil.rmtree(tmp, ignore_errors=True)
        if isinstance(err, FetchError):
            raise
        raise FetchError(f"cannot export {rev} to {dest}: {err}") from err
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            index.unlink()
        except FileNotFoundError:
            pass
    return dest


def ensure_self_snapshot(root: Path, source: guidecfg.Source) -> tuple[Path | None, str]:
    """(snapshot directory, status) for the `self` source.

    The pinned commit is exported when the host has it. Without it (a fresh clone after a
    squash merge), the head of the tracked branch is exported in its place when every
    fingerprint matches it; otherwise the status is "pin unavailable" (research R5). The
    fallback export is keyed by the head commit it holds, never by the pinned commit, so
    the pinned commit's directory only ever holds that commit (it may become available
    again later, for example when it is fetched from a fork).
    """
    top = host_toplevel(root)
    if commit_exists(top, source.commit):
        return export_snapshot(top, source.commit, self_snapshot_dir(top, source.commit)), "verified"
    head = self_head(top, source.ref)
    # with no cited file (no fingerprints), nothing the guide states can differ at the head
    if head and all(blob_at(top, head, p) == b for p, b in source.fingerprints.items()):
        return export_snapshot(top, head, self_snapshot_dir(top, head)), "verified"
    return None, "pin unavailable"


def where(root: Path, source_id: str, commit: str | None = None) -> Path:
    """Readable snapshot directory of a source (exported on demand for `self`)."""
    root = Path(root)
    baseline = guidecfg.load_baseline(root)
    source = baseline.source(source_id)
    if source is None:
        raise KeyError(source_id)
    if source_id != SELF:
        return (_cache(root) / source_id).resolve()
    top = host_toplevel(root)
    if commit:
        proc = _git("-C", str(top), "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}", check=False)
        sha = proc.stdout.strip()
        if proc.returncode != 0 or not SHA_RE.match(sha):
            raise FetchError(f"commit {commit} not found in the host repository")
        return export_snapshot(top, sha, self_snapshot_dir(top, sha))
    path, status = ensure_self_snapshot(root, source)
    if path is None:
        raise FetchError(f"self: {status}, run /guide:evolve")
    return path


def _pin_self(root: Path, entry: dict, repo: str, ref: str | None) -> None:
    top = host_toplevel(root)
    if guidecfg._norm(root, repo).resolve() != top.resolve():
        raise FetchError(f"the 'self' source must point at the host repository (repo: ..), got {repo!r}")
    rev = ref or "HEAD"
    proc = _git("-C", str(top), "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", check=False)
    commit = proc.stdout.strip()
    if proc.returncode != 0 or not SHA_RE.match(commit):
        raise FetchError(f"ref {rev!r} not found in the host repository")
    rest = {k: v for k, v in entry.items() if k not in ("id", "repo", "ref", "commit", "web", "fingerprints")}
    entry.clear()
    entry.update({"id": SELF, "repo": repo, "ref": default_branch(top), "commit": commit, **rest})
    web = origin_web(top)
    if web:
        entry["web"] = web
    fingerprints = self_fingerprints(root, top, commit)
    if fingerprints:
        entry["fingerprints"] = fingerprints


# --- operations ---------------------------------------------------------------


def pin(root: Path, specs: list[str]) -> guidecfg.Baseline:
    """Resolve each `ID=REPO[@REF]` to a full SHA and record it in baseline.yaml."""
    root = Path(root)
    header, data = _read_raw(root)
    entries = data.setdefault("sources", []) or []
    data["sources"] = entries
    for spec in specs:
        source_id, repo, ref = parse_spec(spec)
        entry = next((e for e in entries if e.get("id") == source_id), None)
        if entry is None:
            entry = {"id": source_id}
            entries.append(entry)
        if source_id == SELF:
            _pin_self(root, entry, repo, ref)
            continue
        commit = ref if ref and SHA_RE.match(ref) else _ls_remote(clone_url(repo, root), ref)
        entry["repo"] = repo
        entry["ref"] = ref or "HEAD"
        entry["commit"] = commit
        # keep id, repo, ref, commit first; preserve status and attributes
        rest = {k: v for k, v in entry.items() if k not in ("id", "repo", "ref", "commit")}
        entry.clear()
        entry.update({"id": source_id, "repo": repo, "ref": ref or "HEAD", "commit": commit, **rest})
    data["captured"] = _today()
    _write_raw(root, header, data)
    return guidecfg.load_baseline(root)


def fetch(root: Path, allow_unverified: bool = False) -> dict[str, str]:
    """Fetch every source into .guide/cache and place a worktree at its pinned commit."""
    root = Path(root)
    baseline = guidecfg.load_baseline(root)
    status: dict[str, str] = {}
    failures: dict[str, str] = {}
    for source in baseline.sources:
        if source.id == SELF:
            try:
                _, state = ensure_self_snapshot(root, source)
            except FetchError as err:
                failures[source.id] = str(err)
                if allow_unverified:
                    status[source.id] = "unverified"
                continue
            status[source.id] = state
            if state != "verified":
                print(f"warning: self: {state}, run /guide:evolve (the pinned commit is gone and "
                      "cited files changed since)", file=sys.stderr)
            continue
        try:
            bare = _update_bare(root, source, baseline.change_requests)
            _ensure_commit(bare, source.commit)
            _place_worktree(root, source.id, bare, source.commit)
            status[source.id] = "verified"
        except FetchError as err:
            failures[source.id] = str(err)
            if allow_unverified:
                status[source.id] = "unverified"

    header, data = _read_raw(root)
    changed = False
    for entry in data.get("sources") or []:
        new = status.get(entry.get("id"))
        if new not in guidecfg.SOURCE_STATUSES:
            continue   # "pin unavailable" is reported, never written
        if entry.get("status", "verified") != new:
            entry["status"] = new
            changed = True
    if changed:
        _write_raw(root, header, data)

    if failures and not allow_unverified:
        lines = "; ".join(f"{sid}: {msg}" for sid, msg in failures.items())
        raise FetchError(f"cannot fetch source(s) {', '.join(failures)}: {lines}")
    for sid, msg in failures.items():
        print(f"warning: source {sid} marked unverified: {msg}", file=sys.stderr)
    return status


GH_TIMEOUT = int(os.environ.get("GUIDE_GH_TIMEOUT", "60"))


def run_gh(*args: str) -> subprocess.CompletedProcess | None:
    """Run the gh CLI with a timeout; None when gh is missing or does not answer in time."""
    if shutil.which("gh") is None:
        return None
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None


def _gh_pull(slug: str, number: int) -> dict | None:
    """State of a GitHub pull request through `gh api` (None when unavailable)."""
    proc = run_gh("api", f"repos/{slug}/pulls/{number}",
                  "--jq", "{state: .state, merged: .merged, head: .head.sha}")
    if proc is None or proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def refresh_change_requests(data: dict, slugs: dict[str, str | None],
                            gh: Callable[[str, int], dict | None] = _gh_pull) -> list[str]:
    """Update change-request entries in raw baseline data from GitHub; return warnings."""
    warnings = []
    for cr in data.get("change_requests") or []:
        slug = slugs.get(cr.get("source"))
        if not slug:
            continue
        info = gh(slug, cr.get("number"))
        if not info:
            warnings.append(f"change request {cr.get('source')}#{cr.get('number')}: state not refreshed (gh unavailable or failed)")
            continue
        if info.get("merged"):
            cr["state"] = "merged"
            cr["tier"] = "on-main"
        elif info.get("state") == "closed":
            cr["state"] = "closed"
        else:
            cr["state"] = "open"
        head = info.get("head")
        if isinstance(head, str) and SHA_RE.match(head) and cr["state"] == "open":
            cr["head"] = head
    return warnings


def rebaseline(root: Path, targets: list[str],
               gh: Callable[[str, int], dict | None] = _gh_pull) -> guidecfg.Baseline:
    """Move the pins of the named sources to new revisions and refresh change requests."""
    root = Path(root)
    baseline = guidecfg.load_baseline(root)
    wanted: dict[str, str] = {}
    for spec in targets:
        if "=" not in spec:
            raise FetchError(f"bad target {spec!r} (expected ID=REF)")
        source_id, ref = spec.split("=", 1)
        if baseline.source(source_id) is None:
            raise FetchError(f"unknown source {source_id!r} (not in baseline.yaml)")
        wanted[source_id] = ref

    commits: dict[str, str] = {}
    for source_id, ref in wanted.items():
        source = baseline.source(source_id)
        if source_id == SELF:
            top = host_toplevel(root)
            proc = _git("-C", str(top), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
            commit = proc.stdout.strip()
            if proc.returncode != 0 or not SHA_RE.match(commit):
                raise FetchError(f"ref {ref!r} not found in the host repository")
            commits[source_id] = commit
            continue
        bare = _update_bare(root, source, baseline.change_requests)
        commit = _resolve_in_bare(bare, ref) if not SHA_RE.match(ref) else ref
        if commit is None:
            commit = _ls_remote(clone_url(source.repo, root), ref)
        _ensure_commit(bare, commit)
        _place_worktree(root, source_id, bare, commit)
        commits[source_id] = commit

    header, data = _read_raw(root)
    for entry in data.get("sources") or []:
        sid = entry.get("id")
        if sid == SELF and sid in commits:
            top = host_toplevel(root)
            entry["commit"] = commits[sid]
            entry["status"] = "verified"
            fingerprints = self_fingerprints(root, top, commits[sid])
            if fingerprints:
                entry["fingerprints"] = fingerprints
            else:
                entry.pop("fingerprints", None)
            blob = store_front_page_blob(root, top)
            if blob:
                entry["front_page_blob"] = blob
            export_snapshot(top, commits[sid], self_snapshot_dir(top, commits[sid]))
        elif sid in commits:
            entry["commit"] = commits[sid]
            if not SHA_RE.match(wanted[sid]):
                entry["ref"] = wanted[sid]
            entry["status"] = "verified"
    slugs = {s.id: s.github_slug for s in baseline.sources}
    for warning in refresh_change_requests(data, slugs, gh):
        print(f"warning: {warning}", file=sys.stderr)
    data["captured"] = _today()
    _write_raw(root, header, data)
    return guidecfg.load_baseline(root)


# --- CLI --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pin and fetch the sources in baseline.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pin")
    p.add_argument("--source", action="append", required=True, metavar="ID=REPO[@REF]")
    p.add_argument("--root", type=Path, default=Path("."))
    f = sub.add_parser("fetch")
    f.add_argument("--allow-unverified", action="store_true")
    f.add_argument("--root", type=Path, default=Path("."))
    r = sub.add_parser("rebaseline")
    r.add_argument("--to", action="append", required=True, metavar="ID=REF")
    r.add_argument("--root", type=Path, default=Path("."))
    w = sub.add_parser("where", help="print the readable snapshot directory of a source")
    w.add_argument("id")
    w.add_argument("--commit", help="self only: export and print a snapshot of this commit")
    w.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    if args.cmd == "where":
        try:
            print(where(args.root, args.id, args.commit))
        except KeyError:
            print(f"error: unknown source {args.id!r} (not in baseline.yaml)", file=sys.stderr)
            return 2
        except guidecfg.ConfigError as err:
            print(f"error: {err}", file=sys.stderr)
            return 2
        except FetchError as err:
            print(f"error: {err}", file=sys.stderr)
            return 1
        return 0

    try:
        if args.cmd == "pin":
            baseline = pin(args.root, args.source)
            for s in baseline.sources:
                print(f"{s.id}: {s.commit} ({s.ref})")
        elif args.cmd == "fetch":
            status = fetch(args.root, args.allow_unverified)
            for sid, st in status.items():
                print(f"{sid}: {st}")
        else:
            baseline = rebaseline(args.root, args.to)
            for s in baseline.sources:
                print(f"{s.id}: {s.commit}")
            print(f"captured: {baseline.captured}")
    except (FetchError, guidecfg.ConfigError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
