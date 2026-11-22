#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Load and validate a guide project's configuration files.

  guide.yaml     project configuration (format, personas, sections, internal part,
                 optional Antora branding block, optional gfm publish block)
  baseline.yaml  pinned sources and change requests
  inputs.yaml    input register (references only, never raw content)

  confidential.local.yaml  (embedded guides, git-ignored) confidential terms, patterns,
                 and the real locations of `local:<id>` inputs (specs/005-embedded-guide R9)

Usage: uv run tools/guide/guidecfg.py validate [--allow-missing-front-page] [--root DIR]
         exits 1 and prints one `file:key: message` line per problem; the branding
         block and the overlay directory ui/supplemental/ are checked by
         tools/guide/branding.py (its lines name their own location, for example
         `ui/supplemental:css/x.css: ...`), and its warnings print as
         `location: warning: ...` without changing the exit status
       uv run tools/guide/guidecfg.py get KEY [--root DIR]
         prints one value: title, slug, format, rigor, internal.enabled,
         drift.schedule, baseline.captured, or embedded.front_page,
         embedded.developer_readme, embedded.stubs, embedded.pr_check (empty when
         the guide is not embedded), pages.enabled, pages.url
       uv run tools/guide/guidecfg.py discover [--dir DIR]
         prints the guide root: DIR when it holds guide.yaml, otherwise the one
         guide project found in the shallowest of the directories up to three levels
         below DIR (hidden, node_modules, build, dist, target, and symlinked
         directories are skipped); exit 3 when several are equally shallow (they are
         listed), exit 4 when there is none
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

import branding

FORMATS = ("antora", "mkdocs", "gfm")
RIGORS = ("fast", "standard", "strict")
SOURCE_STATUSES = ("verified", "unverified")
CR_STATES = ("open", "merged", "closed")
CR_TIERS = ("in-review", "on-main")
INPUT_KINDS = ("transcript", "ticket", "link", "notes", "document")
FINDING_KINDS = ("doc-drift", "stale-reference", "dead-config", "missing-doc", "naming-ux", "bug")
FINDING_STATUSES = ("collected", "reverified", "drafted", "approved", "filed",
                    "dropped", "merged", "rejected", "needs-review")

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://")
FINDING_ID_RE = re.compile(r"^UF-\d+$")
SELF_ID = "self"                       # the reserved id of the host repository source
DEFAULT_FRONT_PAGE = "../README.md"    # embedded.front_page when guide.yaml does not set it
LOCAL_FILE = "confidential.local.yaml"  # git-ignored confidential data of an embedded guide
PR_CHECK = ("off", "on")


class ConfigError(Exception):
    """A configuration file failed validation.

    `problems` holds (key, message) pairs; str() renders `file:key: message` lines.
    """

    def __init__(self, path: Path | str, message: str, problems: list[tuple[str, str]] | None = None):
        self.path = Path(path)
        self.message = message
        self.problems = problems or [("", message)]
        super().__init__(str(self))

    def lines(self) -> list[str]:
        return [f"{self.path.name}:{key}: {msg}" if key else f"{self.path.name}: {msg}"
                for key, msg in self.problems]

    def __str__(self) -> str:
        return "\n".join(self.lines())


# --- entities -------------------------------------------------------------


@dataclass
class Persona:
    id: str
    title: str
    start: str


@dataclass
class Section:
    id: str
    title: str
    voice: str


@dataclass
class Cluster:
    name: str
    kubeconfig: str
    context: str | None = None
    disposable: bool = False


@dataclass
class Embedded:
    """The guide.yaml `embedded` block; paths are resolved against the guide root."""
    front_page: Path
    developer_readme: Path | None = None
    stubs: list[Path] = field(default_factory=list)
    pr_check: bool = False


@dataclass
class Publish:
    """The guide.yaml `publish` block (specs/006, FR-006): render `page` into the
    guide-owned region of `target`. Both paths are resolved against the guide root;
    gfm guides only, one block per guide in v1."""
    page: Path      # the source page, inside the content root
    target: Path    # the author-owned README, outside the content root


@dataclass
class Pages:
    """The guide.yaml `pages` block: the shareable view is published with GitHub Pages
    by .github/workflows/guide-pages.yml (antora and mkdocs guides only)."""
    enabled: bool = False
    url: str = ""   # https://<owner>.github.io/<repo>/, empty while the remote is unknown


@dataclass
class Guide:
    root: Path
    schema: int
    title: str
    format: str
    personas: list[Persona]
    sections: list[Section]
    rigor: str = "standard"
    internal_enabled: bool = False
    confidential_terms: list[str] = field(default_factory=list)
    confidential_patterns: list[str] = field(default_factory=list)
    clusters: dict[str, Cluster] = field(default_factory=dict)
    extra_queries: list[str] = field(default_factory=list)
    drift_schedule: str = "off"
    upstream_target: str = "github"
    # The raw guide.yaml `branding` block (None without one, or when it is not a mapping).
    # load_guide does not check it: the checks live in branding.check_guide (run by
    # validate and playbook.py), so `get` keeps working for an invalid block and the
    # build reaches the step that reports it (FR-010).
    branding: dict | None = None
    # The `embedded` block (None for a guide in its own repository).
    embedded: Embedded | None = None
    # The `publish` block (None when the guide publishes no README region).
    publish: Publish | None = None
    # The `pages` block (None when the guide is not published with GitHub Pages).
    pages: Pages | None = None

    @property
    def slug(self) -> str:
        return slugify(self.title)


@dataclass
class Source:
    id: str
    repo: str
    commit: str
    ref: str | None = None
    status: str = "verified"
    attributes: dict[str, str] = field(default_factory=dict)
    # `self` only: browsable repository URL, cited path -> blob id, front page blob id
    web: str = ""
    fingerprints: dict[str, str] = field(default_factory=dict)
    front_page_blob: str = ""

    @property
    def web_url(self) -> str:
        """Browsable URL of the repository (GitHub shorthand expanded, .git stripped)."""
        return web_url(self.repo)

    @property
    def github_slug(self) -> str | None:
        """`owner/name` when the repository is on GitHub, else None."""
        m = re.match(r"^(?:https?://github\.com/|git@github\.com:)?([\w.-]+/[\w.-]+?)(?:\.git)?/?$", self.repo)
        if m and ("github.com" in self.repo or not URL_RE.match(self.repo)) and not self.repo.startswith("/"):
            return m.group(1)
        return None


@dataclass
class ChangeRequest:
    source: str
    number: int
    head: str
    state: str
    tier: str
    anchor: str


@dataclass
class Baseline:
    root: Path
    captured: str
    sources: list[Source]
    change_requests: list[ChangeRequest] = field(default_factory=list)

    def source(self, source_id: str) -> Source | None:
        return next((s for s in self.sources if s.id == source_id), None)

    def change_request(self, number: int) -> ChangeRequest | None:
        return next((c for c in self.change_requests if c.number == number), None)


@dataclass
class Input:
    id: str
    kind: str
    location: str
    role: str = ""
    sha256: str = ""
    confidential: bool = False
    registered: str = ""
    revision: str = ""   # `self:` inputs: the commit the input was read at
    blob: str = ""       # `self:` inputs: the blob id at that commit
    resolved: str = ""   # `local:` inputs: the real location from confidential.local.yaml

    @property
    def is_url(self) -> bool:
        return bool(URL_RE.match(self.location))

    @property
    def is_self(self) -> bool:
        return self.location.startswith("self:")

    @property
    def is_local(self) -> bool:
        return self.location.startswith("local:")

    def path(self, root: Path) -> Path | None:
        """Filesystem path of the input (relative locations resolve against root).

        None for links and for `self:` inputs, which are recorded at a revision of the
        host repository; `local:` inputs resolve through confidential.local.yaml.
        """
        if self.is_url or self.is_self:
            return None
        location = self.location
        if self.is_local:
            if not self.resolved:
                return None
            location = self.resolved
        p = Path(location).expanduser()
        return p if p.is_absolute() else (root / p)


@dataclass
class Inputs:
    root: Path
    inputs: list[Input] = field(default_factory=list)

    def get(self, input_id: str) -> Input | None:
        return next((i for i in self.inputs if i.id == input_id), None)


@dataclass
class Adapter:
    format: str
    content_root: str = "content"
    internal_root: str = "internal"
    page_glob: str = "**/*"
    comment: str = "line"
    requires: dict[str, str] = field(default_factory=dict)
    admonitions: dict[str, str] = field(default_factory=dict)
    experimental: dict[str, str] = field(default_factory=dict)
    attributes: str = ""
    preview_port: int = 8000
    image_dir: str = ""
    branding: list[str] = field(default_factory=list)   # supported branding keys
    extra: dict[str, Any] = field(default_factory=dict)


# --- helpers ----------------------------------------------------------------


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "guide"


def web_url(repo: str) -> str:
    if repo.startswith("git@github.com:"):
        repo = "https://github.com/" + repo.split(":", 1)[1]
    elif not URL_RE.match(repo) and re.match(r"^[\w.-]+/[\w.-]+$", repo):
        repo = "https://github.com/" + repo
    return re.sub(r"\.git/?$", "", repo.rstrip("/"))


def _read_yaml(path: Path) -> Any:
    if not path.is_file():
        raise ConfigError(path, "file not found")
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(path, f"invalid YAML: {exc}") from exc


def _date(value: Any) -> str | None:
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str) and DATE_RE.match(value):
        return value
    return None


# --- embedded mode helpers (specs/005-embedded-guide) --------------------------


def host_toplevel(root: Path) -> Path | None:
    """The top level of the git repository that contains root (None outside a repository)."""
    try:
        proc = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = proc.stdout.strip()
    return Path(out) if proc.returncode == 0 and out else None


def _norm(root: Path, rel: str) -> Path:
    """A guide-relative path joined to root and normalized (no `..` segments left over)."""
    return Path(os.path.normpath(Path(root) / rel))


def _embedded_raw(root: Path) -> dict | None:
    """The raw `embedded` mapping of guide.yaml, tolerant of a missing or invalid file."""
    path = Path(root) / "guide.yaml"
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict) or "embedded" not in data:
        return None
    raw = data.get("embedded")
    return raw if isinstance(raw, dict) else {}


def _front_page_rel(raw: dict) -> str:
    """The guide-relative front page of a raw `embedded` mapping (DEFAULT_FRONT_PAGE when unset)."""
    return str(raw.get("front_page") or DEFAULT_FRONT_PAGE)


def embedded_front_page(root: Path) -> Path | None:
    """The front page of an embedded guide (None when the guide is not embedded).

    Reads only `embedded.front_page` (default DEFAULT_FRONT_PAGE) and never fails, so the
    page enumerator and other readers work before or without a valid guide.yaml.
    """
    raw = _embedded_raw(root)
    if raw is None:
        return None
    return _norm(root, _front_page_rel(raw))


def _embedded_paths(root: Path) -> list[Path]:
    """Resolved front page, developer README, and stubs of an embedded guide."""
    raw = _embedded_raw(root)
    if raw is None:
        return []
    out = [_norm(root, _front_page_rel(raw))]
    if isinstance(raw.get("developer_readme"), str) and raw["developer_readme"]:
        out.append(_norm(root, raw["developer_readme"]))
    for stub in raw.get("stubs") or []:
        if isinstance(stub, str):
            out.append(_norm(root, stub))
    return [p.resolve() for p in out]


def is_guide_owned(root: Path, host_path: str) -> bool:
    """True when a host-relative path is guide material: anything inside the guide
    subdirectory, the front page, the developer README, or a stub (FR-012)."""
    root = Path(root)
    top = host_toplevel(root)
    if top is None:
        return False
    target = (top / host_path).resolve()
    guide_root = root.resolve()
    if target == guide_root or guide_root in target.parents:
        return True
    return target in _embedded_paths(root)


def _inside(path: Path, base: Path) -> bool:
    path, base = path.resolve(), base.resolve()
    return path == base or base in path.parents


DISCOVER_MAX_DEPTH = 3
DISCOVER_PRUNED = frozenset({"node_modules", "build", "dist", "target"})


def discover(directory: Path) -> Path:
    """The guide root for a command run in directory (FR-031, amended by spec 007).

    directory itself when it holds guide.yaml. Otherwise the directories below it are
    searched level by level, from depth 1 up to DISCOVER_MAX_DEPTH, for guide projects
    (a directory holding a regular file guide.yaml, embedded or standalone). Hidden
    directories, the names in DISCOVER_PRUNED, directories reached through a symbolic
    link, and unreadable directories are skipped, and nothing below a guide project is
    searched. The shallowest depth with a guide project decides: one returns it, several
    raise DiscoverError with code 3 (candidates sorted by resolved path), none up to the
    maximum depth raises DiscoverError with code 4.
    """
    directory = Path(directory)
    try:
        if (directory / "guide.yaml").is_file():
            return directory
    except OSError:   # DIR itself cannot be entered: nothing to find
        raise DiscoverError(4, []) from None
    if not directory.is_dir():
        raise DiscoverError(4, [])
    level = [directory]
    for _depth in range(DISCOVER_MAX_DEPTH):
        found: list[Path] = []
        nxt: list[Path] = []
        for parent in level:
            subdirs: list[Path] = []
            try:
                with os.scandir(parent) as entries:
                    for entry in entries:
                        if entry.name.startswith(".") or entry.name in DISCOVER_PRUNED:
                            continue
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                subdirs.append(Path(entry.path))
                        except OSError:   # one entry that cannot be inspected does not hide its siblings
                            continue
            except OSError:   # parent cannot be listed (or the listing broke off): keep what was read
                pass
            for sub in subdirs:
                if not os.access(sub, os.R_OK | os.X_OK):   # unreadable directories are skipped (FR-007)
                    continue
                try:
                    holds_guide = (sub / "guide.yaml").is_file()
                except OSError:
                    continue
                (found if holds_guide else nxt).append(sub)
        if len(found) == 1:
            return found[0]
        if found:
            raise DiscoverError(3, sorted(found, key=lambda p: str(p.resolve())))
        level = nxt
    raise DiscoverError(4, [])


class DiscoverError(Exception):
    def __init__(self, code: int, candidates: list[Path]):
        self.code = code
        self.candidates = candidates
        super().__init__("several guide projects" if code == 3 else "no guide project found")


class _Checker:
    """Collects (key, message) problems while reading one file."""

    def __init__(self, path: Path):
        self.path = path
        self.problems: list[tuple[str, str]] = []

    def add(self, key: str, message: str) -> None:
        self.problems.append((key, message))

    def mapping(self, value: Any, key: str, allowed: set[str], required: set[str] = frozenset()) -> dict:
        if value is None:
            value = {}
        if not isinstance(value, dict):
            self.add(key, "must be a mapping")
            return {}
        for k in value:
            if k not in allowed:
                self.add(f"{key}.{k}" if key else str(k), "unknown key")
        for k in sorted(required):
            if k not in value or value[k] in (None, ""):
                self.add(f"{key}.{k}" if key else k, "required")
        return value

    def str_list(self, value: Any, key: str) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            self.add(key, "must be a list of strings")
            return []
        return value

    def enum(self, value: Any, key: str, choices: tuple[str, ...], default: str | None = None) -> str:
        if value is None and default is not None:
            return default
        if value not in choices:
            self.add(key, f"must be one of {', '.join(choices)} (got {value!r})")
            return default or ""
        return value

    def boolean(self, value: Any, key: str, default: bool = False) -> bool:
        if value is None:
            return default
        if not isinstance(value, bool):
            self.add(key, "must be true or false")
            return default
        return value

    def slug(self, value: Any, key: str) -> str:
        if not isinstance(value, str) or not SLUG_RE.match(value):
            self.add(key, f"must be a lowercase slug (got {value!r})")
            return str(value)
        return value

    def raise_if_any(self) -> None:
        if self.problems:
            raise ConfigError(self.path, self.problems[0][1], self.problems)


# --- loaders ----------------------------------------------------------------

GUIDE_KEYS = {"schema", "title", "format", "personas", "sections", "rigor", "internal",
              "clusters", "validate", "drift", "upstream", "branding", "embedded", "publish",
              "pages"}
EMBEDDED_KEYS = {"front_page", "developer_readme", "stubs", "pr_check"}
PUBLISH_KEYS = {"page", "target"}
PAGES_KEYS = {"enabled", "url"}
PAGES_FORMATS = ("antora", "mkdocs")


def load_adapter(root: Path, required: bool = True) -> Adapter | None:
    """Read tools/guide/adapter.yaml (the vendored adapter descriptor)."""
    path = Path(root) / "tools" / "guide" / "adapter.yaml"
    if not path.is_file():
        if required:
            raise ConfigError(path, "adapter descriptor not found (is the toolkit installed in tools/guide/?)")
        return None
    data = _read_yaml(path)
    known = {f for f in Adapter.__dataclass_fields__ if f != "extra"}
    kwargs = {k: v for k, v in data.items() if k in known}
    extra = {k: v for k, v in data.items() if k not in known}
    if "format" not in kwargs:
        raise ConfigError(path, "format is required")
    if not isinstance(kwargs.get("branding", []), list):
        raise ConfigError(path, "branding must be a list of branding keys")
    return Adapter(**kwargs, extra=extra)


def load_guide(root: Path) -> Guide:
    root = Path(root)
    path = root / "guide.yaml"
    c = _Checker(path)
    data = c.mapping(_read_yaml(path), "", GUIDE_KEYS, {"schema", "title", "format", "personas"})

    schema = data.get("schema")
    if schema is not None and schema != 1:
        c.add("schema", f"unsupported schema version {schema!r} (expected 1)")
    title = data.get("title")
    if title is not None and not isinstance(title, str):
        c.add("title", "must be a string")

    fmt = data.get("format")
    if fmt is not None and fmt not in FORMATS:
        c.add("format", f"no adapter for format {fmt!r} (available: {', '.join(FORMATS)})")
    adapter_path = root / "tools" / "guide" / "adapter.yaml"
    if fmt in FORMATS and adapter_path.is_file():
        vendored = (yaml.safe_load(adapter_path.read_text()) or {}).get("format")
        if vendored != fmt:
            c.add("format", f"{fmt!r} does not match the vendored adapter {vendored!r} in tools/guide/adapter.yaml")

    personas = []
    raw = data.get("personas")
    if raw is not None and (not isinstance(raw, list) or not raw):
        c.add("personas", "must be a non-empty list")
        raw = []
    for i, p in enumerate(raw or []):
        key = f"personas[{i}]"
        p = c.mapping(p, key, {"id", "title", "start"}, {"id", "title", "start"})
        personas.append(Persona(c.slug(p.get("id"), f"{key}.id"), str(p.get("title", "")), str(p.get("start", ""))))
    _unique(c, "personas", [p.id for p in personas])

    sections = []
    raw = data.get("sections") or []
    if not isinstance(raw, list):
        c.add("sections", "must be a list")
        raw = []
    for i, s in enumerate(raw):
        key = f"sections[{i}]"
        s = c.mapping(s, key, {"id", "title", "voice"}, {"id", "title", "voice"})
        sections.append(Section(c.slug(s.get("id"), f"{key}.id"), str(s.get("title", "")), str(s.get("voice", ""))))
    _unique(c, "sections", [s.id for s in sections])

    rigor = c.enum(data.get("rigor"), "rigor", RIGORS, "standard")

    internal = c.mapping(data.get("internal"), "internal", {"enabled", "confidential_terms", "confidential_patterns"})
    terms = c.str_list(internal.get("confidential_terms"), "internal.confidential_terms")
    patterns = c.str_list(internal.get("confidential_patterns"), "internal.confidential_patterns")
    for i, pat in enumerate(patterns):
        try:
            re.compile(pat)
        except re.error as exc:
            c.add(f"internal.confidential_patterns[{i}]", f"invalid regex: {exc}")

    clusters = {}
    raw = c.mapping(data.get("clusters"), "clusters", set(data.get("clusters") or {}))
    for name, cl in raw.items():
        key = f"clusters.{name}"
        cl = c.mapping(cl, key, {"kubeconfig", "context", "disposable"}, {"kubeconfig"})
        clusters[name] = Cluster(name, str(cl.get("kubeconfig", "")), cl.get("context"),
                                 c.boolean(cl.get("disposable"), f"{key}.disposable"))

    validate = c.mapping(data.get("validate"), "validate", {"extra_queries"})
    extra = c.str_list(validate.get("extra_queries"), "validate.extra_queries")

    drift = c.mapping(data.get("drift"), "drift", {"schedule"})
    schedule = drift.get("schedule", "off")
    if schedule is False or schedule is None:
        schedule = "off"
    if not isinstance(schedule, str) or (schedule != "off" and len(schedule.split()) != 5):
        c.add("drift.schedule", f"must be 'off' or a five-field cron expression (got {schedule!r})")

    upstream = c.mapping(data.get("upstream"), "upstream", {"target"})
    target = c.enum(upstream.get("target"), "upstream.target", ("github",), "github")

    brand = data.get("branding")
    if not isinstance(brand, dict):
        brand = None   # reported by branding.check_guide, not here (see Guide.branding)

    internal_enabled = c.boolean(internal.get("enabled"), "internal.enabled")
    embedded = None
    if "embedded" in data:
        embedded = _load_embedded(c, root, data.get("embedded"), fmt, internal_enabled, terms, patterns)
    publish = None
    if "publish" in data:
        publish = _load_publish(c, root, data.get("publish"), fmt)
    pages = None
    if "pages" in data:
        pages = _load_pages(c, data.get("pages"), fmt)

    c.raise_if_any()
    # confidential.local.yaml belongs to embedded guides only; a separate guide keeps its
    # terms in guide.yaml and ignores a stray copy (FR-029)
    local_terms, local_patterns = _load_local_confidential(root) if embedded is not None else ([], [])
    return Guide(root=root, schema=int(schema), title=title, format=fmt, personas=personas,
                 sections=sections, rigor=rigor, internal_enabled=internal_enabled,
                 confidential_terms=terms + local_terms, confidential_patterns=patterns + local_patterns,
                 clusters=clusters, extra_queries=extra, drift_schedule=schedule, upstream_target=target,
                 branding=brand, embedded=embedded, publish=publish, pages=pages)


def _load_embedded(c: _Checker, root: Path, value: Any, fmt: Any, internal_enabled: bool,
                   terms: list[str], patterns: list[str]) -> Embedded | None:
    """Parse and check the `embedded` block (FR-004, data-model.md)."""
    raw = c.mapping(value, "embedded", EMBEDDED_KEYS)
    if fmt is not None and fmt != "gfm":
        c.add("format", f"an embedded guide must use the gfm format (got {fmt!r})")
    if internal_enabled:
        c.add("internal.enabled", "an embedded guide has no internal part; it must be false")
    if terms:
        c.add("internal.confidential_terms", f"must be empty in an embedded guide (use {LOCAL_FILE})")
    if patterns:
        c.add("internal.confidential_patterns", f"must be empty in an embedded guide (use {LOCAL_FILE})")
    top = host_toplevel(root)
    if top is None:
        c.add("embedded", "an embedded guide must live inside a git repository")

    def host_path(key: str, rel: Any, markdown: bool = False) -> Path | None:
        if not isinstance(rel, str) or not rel:
            c.add(f"embedded.{key}", "must be a path relative to the guide root")
            return None
        path = _norm(root, rel)
        if _inside(path, root):
            c.add(f"embedded.{key}", f"{rel} lies inside the guide subdirectory; it must be outside it")
        elif top is not None and not _inside(path, top):
            c.add(f"embedded.{key}", f"{rel} lies outside the host repository")
        if markdown and path.suffix != ".md":
            c.add(f"embedded.{key}", f"{rel} must be a Markdown file (.md)")
        return path

    front = host_path("front_page", raw.get("front_page", DEFAULT_FRONT_PAGE), markdown=True)
    dev = None
    if raw.get("developer_readme") not in (None, ""):
        dev = host_path("developer_readme", raw.get("developer_readme"))
    stubs = []
    raw_stubs = c.str_list(raw.get("stubs"), "embedded.stubs")
    for stub in raw_stubs:
        path = host_path("stubs", stub)
        if path is not None:
            stubs.append(path)
    pr = raw.get("pr_check")
    if pr is False or pr is None:
        pr = "off"
    elif pr is True:
        pr = "on"
    pr = c.enum(pr, "embedded.pr_check", PR_CHECK, "off")
    if front is None:
        return None
    return Embedded(front_page=front, developer_readme=dev, stubs=stubs, pr_check=pr == "on")


def _load_pages(c: _Checker, value: Any, fmt: Any) -> Pages:
    """Parse and check the `pages` block (brainstorm/08-pages-deploy).

    `enabled` is a boolean (default false); `url`, when given, is an https URL ending
    in a slash, because it becomes the site URL of the build. Antora and MkDocs only:
    a gfm guide (embedded guides included) renders on GitHub without a site build.
    """
    raw = c.mapping(value, "pages", PAGES_KEYS)
    if fmt is not None and fmt not in PAGES_FORMATS:
        c.add("pages", f"GitHub Pages needs the antora or mkdocs format (got {fmt!r})")
    enabled = c.boolean(raw.get("enabled"), "pages.enabled")
    url = raw.get("url")
    if url is None or url == "":
        url = ""
    elif not isinstance(url, str) or not url.startswith("https://") or not url.endswith("/"):
        c.add("pages.url", f"must be an https URL ending in a slash (got {url!r})")
        url = ""
    return Pages(enabled=enabled, url=url)


def _load_publish(c: _Checker, root: Path, value: Any, fmt: Any) -> Publish | None:
    """Parse and check the `publish` block (FR-006, data-model.md).

    Both keys are required, non-empty guide-root-relative paths; `page` must resolve
    inside the content root, `target` outside it; gfm guides only. Page existence is
    checked by validate (a load must not fail on a page create has not written yet).
    """
    raw = c.mapping(value, "publish", PUBLISH_KEYS, PUBLISH_KEYS)
    if fmt is not None and fmt != "gfm":
        c.add("publish", f"publishing a README region requires the gfm format (got {fmt!r})")
    adapter = load_adapter(root, required=False)
    content = adapter.content_root if adapter is not None else ("docs" if fmt == "gfm" else "content")
    paths: dict[str, Path] = {}
    for key, rel in (("page", raw.get("page")), ("target", raw.get("target"))):
        if not isinstance(rel, str) or not rel:
            c.add(f"publish.{key}", "must be a path relative to the guide root")
            continue
        paths[key] = _norm(root, rel).resolve()
    if "page" in paths and not _inside(paths["page"], root / content):
        c.add("publish.page", f"{raw.get('page')} must lie inside the content root {content}/")
    if "target" in paths and _inside(paths["target"], root / content):
        c.add("publish.target", f"{raw.get('target')} must lie outside the content root {content}/")
    if len(paths) != 2:
        return None
    return Publish(page=paths["page"], target=paths["target"])


def _load_local_raw(root: Path) -> tuple[dict, _Checker]:
    path = Path(root) / LOCAL_FILE
    c = _Checker(path)
    if not path.is_file():
        return {}, c
    data = c.mapping(_read_yaml(path), "", {"confidential_terms", "confidential_patterns", "inputs"})
    return data, c


def _load_local_confidential(root: Path) -> tuple[list[str], list[str]]:
    """Terms and patterns from confidential.local.yaml (none when the file is missing)."""
    data, c = _load_local_raw(root)
    terms = c.str_list(data.get("confidential_terms"), "confidential_terms")
    patterns = c.str_list(data.get("confidential_patterns"), "confidential_patterns")
    for i, pat in enumerate(patterns):
        try:
            re.compile(pat)
        except re.error as exc:
            c.add(f"confidential_patterns[{i}]", f"invalid regex: {exc}")
    c.raise_if_any()
    return terms, patterns


def _local_inputs(root: Path) -> dict[str, str]:
    """Real locations of `local:<id>` inputs from confidential.local.yaml."""
    data, c = _load_local_raw(root)
    raw = data.get("inputs") or {}
    if not isinstance(raw, dict) or not all(isinstance(v, str) for v in raw.values()):
        c.add("inputs", "must map input ids to locations")
        c.raise_if_any()
    return {str(k): v for k, v in raw.items()}


def load_baseline(root: Path) -> Baseline:
    root = Path(root)
    path = root / "baseline.yaml"
    c = _Checker(path)
    data = c.mapping(_read_yaml(path), "", {"captured", "sources", "change_requests"}, {"captured", "sources"})

    captured = _date(data.get("captured"))
    if data.get("captured") is not None and captured is None:
        c.add("captured", "must be a date (YYYY-MM-DD)")

    sources = []
    raw = data.get("sources")
    if raw is not None and (not isinstance(raw, list) or not raw):
        c.add("sources", "must be a non-empty list")
        raw = []
    embedded = _embedded_raw(root) is not None
    for i, s in enumerate(raw or []):
        key = f"sources[{i}]"
        s = c.mapping(s, key, {"id", "repo", "ref", "commit", "status", "attributes",
                               "web", "fingerprints", "front_page_blob"}, {"id", "repo", "commit"})
        is_self = s.get("id") == SELF_ID
        if is_self and not embedded:
            c.add(f"{key}.id", "the source id 'self' is reserved for embedded guides")
        fingerprints = s.get("fingerprints") or {}
        if "fingerprints" in s and not is_self:
            c.add(f"{key}.fingerprints", "allowed only on the 'self' source")
        if not isinstance(fingerprints, dict):
            c.add(f"{key}.fingerprints", "must map cited paths to blob ids")
            fingerprints = {}
        for path, blob_id in fingerprints.items():
            if not isinstance(blob_id, str) or not SHA_RE.match(blob_id):
                c.add(f"{key}.fingerprints.{path}", f"must be a 40-character blob id (got {blob_id!r})")
        front_blob = s.get("front_page_blob")
        if front_blob is not None:
            if not is_self:
                c.add(f"{key}.front_page_blob", "allowed only on the 'self' source")
            elif not isinstance(front_blob, str) or not SHA_RE.match(front_blob):
                c.add(f"{key}.front_page_blob", f"must be a 40-character blob id (got {front_blob!r})")
        web = s.get("web")
        if web is not None and not isinstance(web, str):
            c.add(f"{key}.web", "must be a URL")
        if is_self and embedded and isinstance(s.get("repo"), str):
            top = host_toplevel(root)
            if top is not None and _norm(root, s["repo"]).resolve() != top.resolve():
                c.add(f"{key}.repo", "the 'self' source must point at the host repository (repo: ..)")
        repo = s.get("repo")
        if isinstance(repo, str) and repo.startswith("-"):
            c.add(f"{key}.repo", "must not start with '-' (it would be read as a git option)")
        commit = s.get("commit")
        if commit is not None and (not isinstance(commit, str) or not SHA_RE.match(commit)):
            c.add(f"{key}.commit", f"must be a full 40-character commit SHA (got {commit!r})")
        attrs = s.get("attributes") or {}
        if not isinstance(attrs, dict):
            c.add(f"{key}.attributes", "must be a mapping")
            attrs = {}
        for name, value in attrs.items():
            if isinstance(value, (dict, list)):
                c.add(f"{key}.attributes.{name}", "must be a scalar value")
        sources.append(Source(
            id=c.slug(s.get("id"), f"{key}.id"), repo=str(s.get("repo", "")), commit=str(commit or ""),
            ref=None if s.get("ref") is None else str(s.get("ref")),
            status=c.enum(s.get("status"), f"{key}.status", SOURCE_STATUSES, "verified"),
            attributes={str(k): _scalar(v) for k, v in attrs.items()},
            web=web if isinstance(web, str) else "",
            fingerprints={str(k): str(v) for k, v in fingerprints.items()},
            front_page_blob=front_blob if isinstance(front_blob, str) else "",
        ))
    _unique(c, "sources", [s.id for s in sources])
    ids = {s.id for s in sources}

    crs = []
    raw = data.get("change_requests") or []
    if not isinstance(raw, list):
        c.add("change_requests", "must be a list")
        raw = []
    for i, cr in enumerate(raw):
        key = f"change_requests[{i}]"
        cr = c.mapping(cr, key, {"source", "number", "head", "state", "tier", "anchor"},
                       {"source", "number", "head", "state", "tier", "anchor"})
        if cr.get("source") is not None and cr.get("source") not in ids:
            c.add(f"{key}.source", f"unknown source {cr.get('source')!r}")
        number = cr.get("number")
        if number is not None and (not isinstance(number, int) or isinstance(number, bool)):
            c.add(f"{key}.number", "must be an integer")
        head = cr.get("head")
        if head is not None and (not isinstance(head, str) or not SHA_RE.match(head)):
            c.add(f"{key}.head", "must be a full 40-character commit SHA")
        crs.append(ChangeRequest(
            source=str(cr.get("source", "")), number=number if isinstance(number, int) else 0,
            head=str(head or ""), state=c.enum(cr.get("state"), f"{key}.state", CR_STATES),
            tier=c.enum(cr.get("tier"), f"{key}.tier", CR_TIERS), anchor=str(cr.get("anchor", "")),
        ))

    c.raise_if_any()
    return Baseline(root=root, captured=captured, sources=sources, change_requests=crs)


def load_inputs(root: Path) -> Inputs:
    root = Path(root)
    path = root / "inputs.yaml"
    if not path.is_file():
        return Inputs(root=root)
    c = _Checker(path)
    data = c.mapping(_read_yaml(path), "", {"inputs"})
    items = []
    raw = data.get("inputs") or []
    if not isinstance(raw, list):
        c.add("inputs", "must be a list")
        raw = []
    project = root.resolve()
    embedded = _embedded_raw(root) is not None
    local: dict[str, str] | None = None
    for i, it in enumerate(raw):
        key = f"inputs[{i}]"
        it = c.mapping(it, key, {"id", "kind", "location", "role", "sha256", "confidential", "registered",
                                 "revision", "blob"},
                       {"id", "kind", "location"})
        location = str(it.get("location", ""))
        resolved = ""
        if location.startswith("self:"):
            if not embedded:
                c.add(f"{key}.location", "self: locations are allowed only in embedded guides")
            for name in ("revision", "blob"):
                value = it.get(name)
                if not isinstance(value, str) or not SHA_RE.match(value):
                    c.add(f"{key}.{name}", f"required with a self: location (40 hex characters, got {value!r})")
        elif location.startswith("local:"):
            if not embedded:
                c.add(f"{key}.location", "local: locations are allowed only in embedded guides")
            else:
                if local is None:
                    try:
                        local = _local_inputs(root)
                    except ConfigError as err:
                        c.add(f"{key}.location", str(err))
                        local = {}
                resolved = local.get(location[len("local:"):], "")
                # Without the git-ignored file (a fresh clone, the scheduled workflow) the
                # location is simply unknown here; the input stays unresolved and is not
                # compared. A file that exists but lacks the id is a configuration error.
                if not resolved and (Path(root) / LOCAL_FILE).is_file():
                    c.add(f"{key}.location", f"{location} has no entry under inputs in {LOCAL_FILE}")
        else:
            for name in ("revision", "blob"):
                if it.get(name) not in (None, ""):
                    c.add(f"{key}.{name}", "allowed only with a self: location")
        if embedded and it.get("confidential") is True and not location.startswith("local:"):
            # FR-006: inputs.yaml is committed; a confidential location lives only in the
            # git-ignored confidential.local.yaml
            c.add(f"{key}.location", f"a confidential input of an embedded guide is registered as "
                                     f"local:<id>, with its real location in {LOCAL_FILE}")
        sha = it.get("sha256") or ""
        if sha and (not isinstance(sha, str) or not SHA256_RE.match(sha)):
            c.add(f"{key}.sha256", "must be a 64-character hex SHA-256 or empty")
        registered = it.get("registered")
        if registered is not None and _date(registered) is None:
            c.add(f"{key}.registered", "must be a date (YYYY-MM-DD)")
        item = Input(
            id=c.slug(it.get("id"), f"{key}.id"),
            kind=c.enum(it.get("kind"), f"{key}.kind", INPUT_KINDS),
            location=str(it.get("location", "")), role=str(it.get("role") or ""), sha256=sha,
            confidential=c.boolean(it.get("confidential"), f"{key}.confidential"),
            registered=_date(registered) or "",
            revision=str(it.get("revision") or ""), blob=str(it.get("blob") or ""), resolved=resolved,
        )
        p = item.path(root)
        if p is not None and item.location:
            resolved = p.resolve()
            if resolved == project or project in resolved.parents:
                c.add(f"{key}.location", "lies inside the guide project; raw inputs must stay where they live")
        items.append(item)
    _unique(c, "inputs", [i.id for i in items])
    c.raise_if_any()
    return Inputs(root=root, inputs=items)


def check_finding(finding: dict, sources: set[str] | None = None) -> list[str]:
    """Problems with one upstream finding entry (empty list when valid)."""
    c = _Checker(Path("findings/upstream.yaml"))
    allowed = {"id", "source", "kind", "locations", "summary", "evidence", "status",
               "reverified_commit", "filed", "merged_into", "note", "proposal"}
    f = c.mapping(finding, "", allowed, {"id", "source", "kind", "locations", "summary", "evidence", "status"})
    if f.get("id") is not None and not FINDING_ID_RE.match(str(f.get("id"))):
        c.add("id", "must look like UF-<n>")
    if sources is not None and f.get("source") is not None and f.get("source") not in sources:
        c.add("source", f"unknown source {f.get('source')!r}")
    if f.get("kind") is not None:
        c.enum(f.get("kind"), "kind", FINDING_KINDS)
    if f.get("status") is not None:
        c.enum(f.get("status"), "status", FINDING_STATUSES)
    locs = f.get("locations")
    if locs is not None:
        if not isinstance(locs, list) or not locs:
            c.add("locations", "must be a non-empty list")
        else:
            for i, loc in enumerate(locs):
                loc = c.mapping(loc, f"locations[{i}]", {"ref", "quote"}, {"ref"})
                ref = loc.get("ref")
                if ref is not None and not re.match(r"^[^:\s]+(:\d+(-\d+)?)?$", str(ref)):
                    c.add(f"locations[{i}].ref", "must be <path>[:<line>[-<line>]]")
    return [f"{k}: {m}" if k else m for k, m in c.problems]


def load_findings(root: Path) -> list[dict]:
    path = Path(root) / "findings" / "upstream.yaml"
    if not path.is_file():
        return []
    data = _read_yaml(path)
    return list(data.get("findings") or []) if isinstance(data, dict) else []


def pages(root: Path, adapter: Adapter, view: str = "all") -> list[Path]:
    """Content pages of a guide project for a view: shareable, internal, or all."""
    root = Path(root)
    content = root / adapter.content_root
    internal = root / adapter.internal_root
    found: set[Path] = set()
    if view in ("shareable", "all") and content.is_dir():
        found.update(p for p in content.glob(adapter.page_glob) if p.is_file())
    if view in ("internal", "all") and internal.is_dir():
        found.update(p for p in internal.glob(adapter.page_glob) if p.is_file())
    if view == "shareable":
        found = {p for p in found if not is_internal(p, root, adapter)}
    elif view == "internal":
        found = {p for p in found if is_internal(p, root, adapter)}
    out = sorted(found)
    # An embedded guide's front page (the host README) is a shareable page (FR-009).
    front = embedded_front_page(root) if view in ("shareable", "all") else None
    if front is not None and front.is_file():
        out.append(front)
    return out


def is_internal(page: Path, root: Path, adapter: Adapter) -> bool:
    internal = (Path(root) / adapter.internal_root).resolve()
    resolved = Path(page).resolve()
    return resolved == internal or internal in resolved.parents


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.strftime("%Y-%m-%d")
    return "" if value is None else str(value)


def _unique(c: _Checker, key: str, ids: list[str]) -> None:
    seen = set()
    for i in ids:
        if i in seen:
            c.add(key, f"duplicate id {i!r}")
        seen.add(i)


# --- CLI --------------------------------------------------------------------


def validate(root: Path, allow_missing_front_page: bool = False) -> tuple[list[str], list[str]]:
    """Problem and warning lines of guide.yaml, baseline.yaml, inputs.yaml, and the branding.

    For an embedded guide the front page must exist, unless allow_missing_front_page is
    set (create validates before it writes the front page).
    """
    problems: list[str] = []
    for loader in (load_guide, load_baseline, load_inputs):
        try:
            result = loader(root)
        except ConfigError as err:
            problems.extend(err.lines())
            continue
        if isinstance(result, Guide) and result.embedded and not allow_missing_front_page \
                and not result.embedded.front_page.is_file():
            rel = os.path.relpath(result.embedded.front_page, Path(root))
            problems.append(f"guide.yaml:embedded.front_page: {rel} not found")
        if isinstance(result, Guide) and result.publish is not None and not result.publish.page.is_file():
            rel = os.path.relpath(result.publish.page, Path(root))
            problems.append(f"guide.yaml:publish.page: {rel} not found")
    brand_problems, warnings = branding.check_guide(root)
    problems.extend(line for line in brand_problems if line not in problems)
    return problems, warnings


GET_KEYS = {
    "title": lambda g: g.title,
    "slug": lambda g: g.slug,
    "format": lambda g: g.format,
    "rigor": lambda g: g.rigor,
    "internal.enabled": lambda g: "true" if g.internal_enabled else "false",
    "drift.schedule": lambda g: g.drift_schedule,
    "embedded.front_page": lambda g: _rel_cfg(g, g.embedded.front_page) if g.embedded else "",
    "embedded.developer_readme": lambda g: _rel_cfg(g, g.embedded.developer_readme)
    if g.embedded and g.embedded.developer_readme else "",
    "embedded.stubs": lambda g: " ".join(_rel_cfg(g, s) for s in g.embedded.stubs) if g.embedded else "",
    "embedded.pr_check": lambda g: ("on" if g.embedded.pr_check else "off") if g.embedded else "",
    "pages.enabled": lambda g: "true" if g.pages and g.pages.enabled else "false",
    "pages.url": lambda g: g.pages.url if g.pages else "",
}


def _rel_cfg(g: Guide, path: Path) -> str:
    return os.path.relpath(path.resolve(), Path(g.root).resolve())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate guide.yaml, baseline.yaml, and inputs.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--allow-missing-front-page", action="store_true",
                   help="embedded guides: do not require the front page yet (create runs before writing it)")
    v.add_argument("--root", type=Path, default=Path("."))
    d = sub.add_parser("discover", help="print the guide root for a command run in DIR (FR-031)")
    d.add_argument("--dir", type=Path, default=Path("."))
    g = sub.add_parser("get", help="print one guide.yaml value (for Makefiles)")
    g.add_argument("key", choices=sorted(GET_KEYS) + ["baseline.captured"])
    g.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    if args.cmd == "discover":
        try:
            print(discover(args.dir).resolve())
        except DiscoverError as err:
            if err.code == 3:
                print("several guide projects found; name one with --dir:", file=sys.stderr)
                for cand in err.candidates:   # already sorted by resolved path in discover()
                    print(cand.resolve())
            else:
                print(f"no guide project in {args.dir} or the directories below it "
                      f"(up to {DISCOVER_MAX_DEPTH} levels)", file=sys.stderr)
            return err.code
        return 0
    if args.cmd == "get":
        try:
            if args.key == "baseline.captured":
                print(load_baseline(args.root).captured)
            else:
                print(GET_KEYS[args.key](load_guide(args.root)))
        except ConfigError as err:
            print(err, file=sys.stderr)
            return 1
        return 0
    problems, warnings = validate(args.root, args.allow_missing_front_page)
    for line in problems + warnings:
        print(line)
    if problems:
        return 1
    print("guide configuration OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
