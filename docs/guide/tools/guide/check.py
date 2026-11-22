#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Content checks for a guide project's pages (contracts/page-conventions.md).

Built-in global checks: typographic dashes, one sentence per line (AsciiDoc),
typed versions and commits, source blocks (and their resolution at the pinned
commits when .guide/cache exists), stubs (strict only), input references,
confidential terms and links into the internal part on shareable pages, image
alt texts with unquoted commas (AsciiDoc), and role=expand on Antora diagrams.
For a branded Antora guide (a guide.yaml `branding` block), the built views
(build/site, and build/site-internal while the internal part is enabled) must show
the branded header logo with its alt text on every page, and no footer may still
carry the Red Hat Demo Platform notice unless `footer` is `rhdp` (FR-032, rule
`branding`). With `theme: neutral`, every page of those views must also load
css/theme-neutral.css and no Google Fonts stylesheet, and _/font/ must hold the
vendored fonts and OFL.txt (specs/003-neutral-branding FR-026).
Antora navigation files must have a blank line before every list title after the first
line (rule `nav-format`); a list title that repeats the item right below it is a warning.
For an embedded guide (specs/005-embedded-guide), the front page (the host README) is a
page like any other and must start with the ownership comment; `self:` citations must
not cite guide material (the guide subdirectory, the front page, the developer README,
or a stub), resolve in the host repository whether or not .guide/cache exists, and
warn when the baseline has no fingerprint for them; the developer README's relative
links must resolve (no page rules apply to it); --structure reads the section titles
from the front page.
Per-guide rules come from the optional guide-rules.yaml:

  rules:
    - glob: content/modules/ROOT/pages/admin/*.adoc
      require: ["regex", {pattern: "regex", message: "why"}]
      forbid: ["regex"]
      require_order: ["first", "second"]

Usage: uv run tools/guide/check.py [--strict] [--root DIR]   (STRICT=1 also enables strict)
Exits 1 and prints `path:line: [rule] message` for every violation.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import yaml

import branding
import guidecfg
import region
import sources

DASH_RE = re.compile("[" + chr(0x2013) + chr(0x2014) + "]")
TEXT_SUFFIXES = {".adoc", ".asciidoc", ".md", ".markdown", ".yml", ".yaml", ".txt", ".csv",
                 ".json", ".toml", ".html", ".htm", ".css", ".svg"}

# AsciiDoc structure
VERBATIM_DELIM_RE = re.compile(r"^(-{4,}|\.{4,}|\+{4,}|/{4,}|[|,:!]={3,}|`{3}.*)\s*$")
ATTR_ENTRY_RE = re.compile(r"^:[!\w][\w-]*!?:")
BLOCK_TITLE_RE = re.compile(r"^\.[^\s.]")
BLOCK_ATTR_RE = re.compile(r"^\[.*\]\s*$")
DIRECTIVE_RE = re.compile(r"^(include|ifdef|ifndef|ifeval|endif|image|toc|video|audio)::")
HEADING_RE = re.compile(r"^=+\s")
LIST_MARKER_RE = re.compile(r"^\s*(\*+|-|\.+|\d+\.|<\d+>|[A-Z]+:)\s+")
INLINE_CODE_RE = re.compile(r"`[^`]*`|\+[^+]+\+|https?://\S+")
BOUNDARY_RE = re.compile(r"([.!?])[\"')\]*_`]*\s+(?=[A-Z`*_\"'(\[])")
ABBREVIATIONS = {"e.g", "i.e", "etc", "vs", "cf", "approx", "fig", "no", "mr", "mrs", "ms", "dr",
                 "inc", "ltd", "st", "resp", "incl", "esp"}
IMAGE_RE = re.compile(r"image::?([^\s\[\]]+)\[([^\]]*)\]")
XREF_RE = sources.XREF_RE
MD_LINK_RE = sources.MD_LINK_RE
# Reference definitions (`[label]: target`) and src attributes, checked in the developer
# README, whose moved text keeps both forms (FR-024).
REFDEF_RE = re.compile(r"^\s{0,3}\[(?!\^)[^\]]+\]:\s*<?(\S+?)>?(?:\s.*)?$")   # not footnotes
SRC_ATTR_RE = re.compile(r"(?<![\w-])src=\"([^\"]+)\"")
CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")
SCHEME_RE = sources.SCHEME_RE
STUB_LINE_RE = re.compile(r"^//\s*STUB\b")
STUB_HTML_RE = re.compile(r"^<!--\s*STUB\b.*-->\s*$")
# Generated regions (gfm adapter) hold baseline values written by attrs.py, not typed ones.
# The first line of a redirect stub an embedded guide leaves at a removed documentation
# path (not the STUB marker of an unfinished page).
STUB_MARKER = "<!-- guide: moved -->"
REGION_RE = re.compile(r"(<!--\s*guide:attr\s+[^\s>]+\s*-->).*?(<!--\s*/guide:attr\s*-->)")


@dataclass
class Violation:
    path: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}"


def _rel(path: Path, root: Path) -> str:
    # relpath, so an embedded guide's front page prints as ../README.md
    try:
        return Path(os.path.relpath(Path(path).resolve(), Path(root).resolve())).as_posix()
    except ValueError:
        return str(path)


def _verbatim_mask(lines: list[str]) -> list[bool]:
    """True for AsciiDoc lines inside (or delimiting) listing, literal, passthrough, comment, or table blocks."""
    mask = []
    open_delim: str | None = None
    for line in lines:
        stripped = line.rstrip()
        m = VERBATIM_DELIM_RE.match(stripped)
        if open_delim is None:
            if m:
                open_delim = _delim_kind(stripped)
                mask.append(True)
            else:
                mask.append(False)
        else:
            mask.append(True)
            if m and _delim_kind(stripped) == open_delim:
                open_delim = None
    return mask


def _delim_kind(line: str) -> str:
    if line.startswith("```"):
        return "```"
    if "===" in line:
        return line[0] + "==="
    return line[0] * 4


def _block_span(lines: list[str], block: sources.Block | None, style: str) -> set[int]:
    """1-based line numbers occupied by the page's source block."""
    if block is None or not block.start_line:
        return set()
    i = block.start_line - 1
    span = {i + 1}
    if style == "line":
        j = i + 1
        while j < len(lines) and lines[j].startswith("//") and not lines[j].startswith("////"):
            span.add(j + 1)
            j += 1
    else:
        j = i
        while j < len(lines):
            span.add(j + 1)
            if "-->" in lines[j]:
                break
            j += 1
    return span


def _typed_value_re(baseline: guidecfg.Baseline) -> re.Pattern | None:
    values: set[str] = set()
    for src in baseline.sources:
        if src.commit:
            values.add(src.commit)
            values.add(src.commit[:7])
        for value in src.attributes.values():
            value = str(value).strip()
            # values without a digit (names, branches) are not versions or commits
            if len(value) >= 3 and re.search(r"\d", value):
                values.add(value)
    if not values:
        return None
    alts = "|".join(re.escape(v) for v in sorted(values, key=len, reverse=True))
    return re.compile(rf"(?<![\w.-])v?(?:{alts})(?![\w-]|\.\w)")


def _sentence_problem(line: str) -> bool:
    """True when an AsciiDoc prose line holds more than one sentence."""
    text = LIST_MARKER_RE.sub("", line, count=1)
    text = INLINE_CODE_RE.sub("x", text)
    for m in BOUNDARY_RE.finditer(text):
        before = text[:m.start(1)]
        token = before.split()[-1] if before.split() else ""
        token = token.lstrip("(\"'`*_[").lower()
        if token in ABBREVIATIONS or (len(token) == 1 and token.isalpha()):
            continue
        return True
    return False


def _prose_line(line: str) -> bool:
    s = line.strip()
    if not s or s == "+":
        return False
    if s.startswith("//") or ATTR_ENTRY_RE.match(s) or BLOCK_TITLE_RE.match(s):
        return False
    if BLOCK_ATTR_RE.match(s) or DIRECTIVE_RE.match(s) or HEADING_RE.match(s):
        return False
    return True


def _split_attrlist(attrlist: str) -> list[str]:
    items, cur, quote = [], "", None
    for ch in attrlist:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur += ch
        elif ch == ",":
            items.append(cur)
            cur = ""
        else:
            cur += ch
    items.append(cur)
    return items


def _alt_comma_unquoted(attrlist: str) -> bool:
    items = _split_attrlist(attrlist)
    first = items[0].strip()
    if not first or first[0] in "\"'":
        return False
    for item in items[1:]:
        item = item.strip()
        if not item or "=" in item:
            continue
        if re.fullmatch(r"\d+(%|px)?", item):
            continue
        return True
    return False


def _has_role_expand(attrlist: str) -> bool:
    return bool(re.search(r"(?:^|,)\s*role\s*=\s*[\"']?[^,\"']*\bexpand\b", attrlist))


def _antora_modules(root: Path, rel: str) -> set[str]:
    base = root / rel / "modules"
    return {p.name for p in base.iterdir() if p.is_dir()} if base.is_dir() else set()


def _xref_module(target: str) -> str | None:
    target = target.split("#", 1)[0]
    if "@" in target:
        target = target.split("@", 1)[1]
    parts = target.split(":")
    if len(parts) >= 3:
        return parts[-2] or None
    if len(parts) == 2:
        return parts[0] or None
    return None


def _text_files(root: Path, adapter: guidecfg.Adapter) -> list[Path]:
    found: set[Path] = set()
    for rel in (adapter.content_root, adapter.internal_root):
        base = root / rel
        if base.is_dir():
            found.update(p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES)
    return sorted(found)


def _check_rules(root: Path) -> list[Violation]:
    path = root / "guide-rules.yaml"
    if not path.is_file():
        return []
    out: list[Violation] = []
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        return [Violation("guide-rules.yaml", 0, "rule-config", f"invalid YAML: {exc}")]
    rules = data.get("rules") or [] if isinstance(data, dict) else []
    if not isinstance(rules, list):
        return [Violation("guide-rules.yaml", 0, "rule-config", "rules must be a list")]
    for i, rule in enumerate(rules):
        key = f"rules[{i}]"
        if not isinstance(rule, dict) or "glob" not in rule:
            out.append(Violation("guide-rules.yaml", 0, "rule-config", f"{key}: needs a glob"))
            continue
        unknown = set(rule) - {"glob", "require", "forbid", "require_order", "message"}
        if unknown:
            out.append(Violation("guide-rules.yaml", 0, "rule-config", f"{key}: unknown keys {sorted(unknown)}"))
        files = sorted(p for p in root.glob(rule["glob"]) if p.is_file())
        if not files:
            out.append(Violation("guide-rules.yaml", 0, "rule-require", f"{key}: glob {rule['glob']!r} matches no file"))
            continue
        for f in files:
            rel = _rel(f, root)
            text = f.read_text(errors="replace")
            lines = text.splitlines()
            for entry in rule.get("require") or []:
                pattern, message = _rule_entry(entry, rule)
                if not re.search(pattern, text, re.M):
                    out.append(Violation(rel, 1, "rule-require", message or f"missing required pattern {pattern!r}"))
            for entry in rule.get("forbid") or []:
                pattern, message = _rule_entry(entry, rule)
                rx = re.compile(pattern)
                for n, line in enumerate(lines, 1):
                    if rx.search(line):
                        out.append(Violation(rel, n, "rule-forbid", message or f"forbidden pattern {pattern!r}"))
            order = rule.get("require_order") or []
            prev = 0
            for entry in order:
                pattern, _ = _rule_entry(entry, rule)
                rx = re.compile(pattern)
                hit = next((n for n, line in enumerate(lines, 1) if rx.search(line)), None)
                if hit is None:
                    out.append(Violation(rel, 1, "rule-order", f"missing {pattern!r}"))
                    break
                if hit < prev:
                    out.append(Violation(rel, hit, "rule-order", f"{pattern!r} appears before an earlier step"))
                    break
                prev = hit
    return out


def _rule_entry(entry, rule: dict) -> tuple[str, str]:
    if isinstance(entry, dict):
        return str(entry.get("pattern", "")), str(entry.get("message") or rule.get("message") or "")
    return str(entry), str(rule.get("message") or "")


FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


def _md_fence_mask(lines: list[str]) -> list[bool]:
    """True for lines inside fenced code blocks (Markdown)."""
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


NAV_TOP_ITEM_RE = re.compile(r"^\*\s+(?:xref:[^\[]*\[(?P<link>[^\]]*)\]|(?P<text>.+?))\s*$")


def check_nav(root: Path, adapter: guidecfg.Adapter, warnings: list[str]) -> list[Violation]:
    """Antora navigation files (rule nav-format).

    A list title (`.Title`) after the first line needs a blank line before it: without
    one, Asciidoctor reads it as text of the list item above, which breaks that item's
    link (a violation). A list title that repeats the first top-level item under it shows
    the same name twice in the sidebar; that is only a warning, so guides written before
    this rule still pass after a toolkit refresh.
    """
    root = Path(root)
    out: list[Violation] = []
    files = sorted(root.glob(f"{adapter.content_root}/modules/*/nav.adoc")) + \
        sorted(root.glob(f"{adapter.internal_root}/modules/*/nav.adoc"))
    for f in files:
        rel = _rel(f, root)
        lines = f.read_text(errors="replace").splitlines()
        for n, line in enumerate(lines):
            if not BLOCK_TITLE_RE.match(line):
                continue
            title = line[1:].strip()
            if n > 0 and lines[n - 1].strip():
                out.append(Violation(rel, n + 1, "nav-format",
                                     f"list title {title!r} needs a blank line before it; "
                                     "without one it becomes text of the item above"))
            following = next((x for x in lines[n + 1:] if x.strip()), "")
            m = NAV_TOP_ITEM_RE.match(following)
            if m and (m.group("link") or m.group("text") or "").strip() == title:
                warnings.append(f"{rel}:{n + 1}: [nav-format] warning: list title {title!r} repeats the "
                                "item below it; drop the title and keep the item as the section entry")
    return out


def check_structure(root: Path, guide: guidecfg.Guide, adapter: guidecfg.Adapter) -> list[Violation]:
    """Every persona's entry page exists and every section title is in the navigation.

    An embedded guide's navigation is its front page (FR-008a).
    """
    root = Path(root)
    out: list[Violation] = []
    stems = {_rel(p, root).rsplit(".", 1)[0] for p in guidecfg.pages(root, adapter, "all")}
    for persona in guide.personas:
        start = persona.start.strip("/").rsplit(".", 1)[0] if persona.start.endswith((".adoc", ".md")) \
            else persona.start.strip("/")
        if not any(s == start or s.endswith("/" + start) for s in stems):
            out.append(Violation("guide.yaml", 0, "guide-structure",
                                 f"persona {persona.id!r}: entry page {persona.start!r} not found"))
    if guide.embedded is not None:
        nav_files = [guide.embedded.front_page] if guide.embedded.front_page.is_file() else []
    else:
        nav_files = list(root.glob(f"{adapter.content_root}/modules/*/nav.adoc")) + \
            [root / n for n in ("mkdocs.yml", "docs/SUMMARY.md", "docs/README.md") if (root / n).is_file()]

    def nav_text(path: Path) -> str:
        """A navigation file's text; an embedded front page narrows to its region
        (specs/006: section titles must be linked by guide-owned text, and author
        text must not satisfy the check by coincidence)."""
        text = path.read_text(errors="replace")
        try:
            return region.parse(text).content
        except region.RegionError:
            return text  # check_embedded reports the malformed markers

    nav = "\n".join(nav_text(f) for f in nav_files)
    for section in guide.sections:
        if section.title and section.title not in nav:
            out.append(Violation("guide.yaml", 0, "guide-structure",
                                 f"section {section.id!r}: title {section.title!r} not in the navigation"))
    return out


IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
ATTR_RE = re.compile(r'\b([\w-]+)\s*=\s*"([^"]*)"')
GOOGLE_FONTS = ("fonts.googleapis.com", "fonts.gstatic.com")   # the stock head-styles.hbs links
LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.I)
FOOTER_RE = re.compile(r'<footer\b[^>]*class="[^"]*\bfooter\b[^"]*"[^>]*>([\s\S]*?)</footer>', re.I)
STOCK_NOTICE = ("demo.redhat.com", "Demo Platform")
STOCK_NOTICE_MARKER = 'class="poweredBy"'          # the stock footer's link (contract rule footer-partial)
GENERATED_FOOTER_MARKER = 'class="guide-footer"'   # the footer rendered from branding.footer


def _stock_notice(footer: str, own_footer: bool) -> bool:
    """True when the content of a footer element is the stock Red Hat Demo Platform notice.

    The stock partial is recognized by its poweredBy link. Any other footer that names
    the Demo Platform counts too (for example the footer of a replaced UI bundle), except
    the one rendered from branding.footer and the author's own partials/footer-content.hbs
    in ui/supplemental/ (own_footer, passed only for a page whose header shows the branded
    logo, so the overlay demonstrably applied): both may mention the Demo Platform.
    """
    if STOCK_NOTICE_MARKER in footer:
        return True
    if own_footer or GENERATED_FOOTER_MARKER in footer:
        return False
    return any(notice in footer for notice in STOCK_NOTICE)


def _branding_problem(loc: str, msg: str) -> Violation:
    """A branding problem as a violation of the file it names (guide.yaml, site.yml,
    or the ui/supplemental/ entry)."""
    if loc == branding.OVERLAY or loc.startswith(branding.OVERLAY + ":"):
        rel = loc[len(branding.OVERLAY) + 1:]
        return Violation(f"{branding.OVERLAY}/{rel}" if rel else branding.OVERLAY, 0, "branding", msg)
    file, _, key = loc.partition(":")
    return Violation(file, 0, "branding", f"{key}: {msg}" if key else msg)


def check_branded_site(root: Path, guide: guidecfg.Guide) -> list[Violation]:
    """Built views of a branded guide that do not show the branding (FR-032).

    Every page with a header logo (img.navbar-logo-img) must show img/logo-guide.svg
    with the configured alt text (any alt text when ui/supplemental/ has its own
    helpers/navbar-logo-alt.js); a view where no page does (for example a replaced UI
    bundle that ignores the overlay) fails; unless footer is rhdp, no footer element may
    be the Red Hat Demo Platform notice (_stock_notice). Page content is not inspected,
    and pages under _exports/ (the print export) are skipped, as are views that were not
    built and the internal view while the internal part is disabled (its build/
    directory is then a leftover). An invalid branding block is reported as is, since
    the built views cannot be judged against it.
    """
    root = Path(root)
    if not isinstance(guide.branding, dict):
        return []
    raw, fmt = branding.load_block(root)
    problems, _ = branding.check(root, raw, fmt, branding.adapter_keys(root, fmt))
    if problems:
        return [_branding_problem(loc, msg) for loc, msg in problems]
    brand = branding.resolve(root, guide.branding)
    overlay = set(branding.overlay_files(root))
    own_alt = branding.ALT_HELPER in overlay
    own_footer = branding.FOOTER_PARTIAL in overlay
    views = ("site", "site-internal") if guide.internal_enabled else ("site",)
    out: list[Violation] = []
    for view in views:
        base = root / "build" / view
        pages = sorted(p for p in base.rglob("*.html") if "_exports" not in p.relative_to(base).parts) \
            if base.is_dir() else []
        if not pages:
            continue
        shown = 0
        for page in pages:
            rel = f"build/{view}/{page.relative_to(base).as_posix()}"
            text = page.read_text(errors="replace")
            branded = False
            for tag in IMG_TAG_RE.findall(text):
                attrs = dict(ATTR_RE.findall(tag))
                if "navbar-logo-img" not in attrs.get("class", "").split():
                    continue
                src, alt = attrs.get("src", ""), html.unescape(attrs.get("alt", ""))
                if src.endswith(branding.LOGO_FILE) and (own_alt or alt == brand.alt):
                    shown += 1
                    branded = True
                else:
                    out.append(Violation(rel, 0, "branding",
                                         f"header does not show the branded logo (found {src}, alt {alt!r})"))
                break
            if brand.footer != "rhdp":
                for footer in FOOTER_RE.findall(text):
                    if _stock_notice(footer, own_footer and branded):
                        out.append(Violation(rel, 0, "branding", "Red Hat Demo Platform notice still present"))
                        break
        if not shown:
            out.append(Violation(f"build/{view}", 0, "branding", "no page shows the branded logo"))
    return out


def _shows_logo(tag: str) -> bool:
    return "navbar-logo-img" in dict(ATTR_RE.findall(tag)).get("class", "").split()


def check_neutral_theme(root: Path, guide: guidecfg.Guide) -> list[Violation]:
    """Built views of a guide with `theme: neutral` that do not carry the theme (FR-026).

    Every page with a header logo (a UI page; Antora's start page redirect has none)
    must link css/theme-neutral.css and no Google Fonts host, and build/<view>/_/font/
    must hold the vendored fonts and OFL.txt. A view where no page has the header (a UI
    bundle that ignores the overlay) is reported by check_branded_site ("no page shows
    the branded logo"), not twice. Views, skipped pages, the internal view, and an invalid
    branding block (also reported there) follow check_branded_site. An author's ui/supplemental/css/theme-neutral.css counts, since
    the generated head-meta.hbs still links it.
    """
    root = Path(root)
    if not isinstance(guide.branding, dict) or guide.branding.get("theme") != "neutral":
        return []
    raw, fmt = branding.load_block(root)
    problems, _ = branding.check(root, raw, fmt, branding.adapter_keys(root, fmt))
    if problems:
        return []
    names = branding.font_files()
    views = ("site", "site-internal") if guide.internal_enabled else ("site",)
    out: list[Violation] = []
    for view in views:
        base = root / "build" / view
        pages = sorted(p for p in base.rglob("*.html") if "_exports" not in p.relative_to(base).parts) \
            if base.is_dir() else []
        if not pages:
            continue
        for page in pages:
            text = page.read_text(errors="replace")
            if not any(_shows_logo(tag) for tag in IMG_TAG_RE.findall(text)):
                continue
            links = [dict(ATTR_RE.findall(tag)).get("href", "") for tag in LINK_TAG_RE.findall(text)]
            rel = f"build/{view}/{page.relative_to(base).as_posix()}"
            if not any(href.endswith(branding.THEME_CSS) for href in links):
                out.append(Violation(rel, 0, "branding", "page does not load the neutral theme"))
            if any(host in href for href in links for host in GOOGLE_FONTS):
                out.append(Violation(rel, 0, "branding", "page still loads Google Fonts"))
        for name in names:
            if not (base / "_" / branding.FONT_DIR / name).is_file():
                out.append(Violation(f"build/{view}", 0, "branding", f"neutral theme font missing: {name}"))
    return out


def _relative_links(path: Path, root: Path, text: str) -> list[Violation]:
    """Broken relative links of a Markdown file outside fenced code blocks."""
    out = []
    lines = text.splitlines()
    fenced = _md_fence_mask(lines)
    for n, line in enumerate(lines, 1):
        if fenced[n - 1]:
            continue
        # inline links and href (MD_LINK_RE), plus the forms embed.py rewrites when it moves
        # text: reference definitions and src attributes (images)
        for raw in _link_targets(line):
            target = raw.split("#", 1)[0].split("?", 1)[0]
            if not target or SCHEME_RE.match(target) or target.startswith("/") or "{{" in target:
                continue
            if not (path.parent / target).resolve().exists():
                out.append(Violation(_rel(path, root), n, "broken-link", f"{target} does not exist"))
    return out


def _link_targets(line: str) -> list[str]:
    """Link targets of a Markdown line: inline links, href and src attributes, and a
    reference definition (footnotes and code spans excluded)."""
    targets = [m.group(1) or m.group(2) or "" for m in MD_LINK_RE.finditer(line)]
    targets += [m.group(1) for m in SRC_ATTR_RE.finditer(CODE_SPAN_RE.sub("", line))]
    ref = REFDEF_RE.match(line)
    if ref:
        targets.append(ref.group(1))
    return targets


def _absolute_links(front: Path, root: Path, text: str, web: str, ref: str) -> list[Violation]:
    """Broken absolute links of the front page into its own repository (FR-010).

    With `absolute_links: true` in the move plan the front page links the guide as
    `<web>/blob/<ref>/<host path>` (or `/tree/` for a directory), web and ref from the
    `self` baseline entry. Such a link is mapped to the host path and must exist in the
    host working tree; a link into the guide subdirectory must also name a guide page.
    URLs of other repositories, hosts, or refs are not checked.
    """
    top = guidecfg.host_toplevel(root)
    if top is None or not web:
        return []
    top = top.resolve()
    guide_root = Path(root).resolve()
    adapter = guidecfg.load_adapter(root, required=False)
    pages = {p.resolve() for p in guidecfg.pages(root, adapter, "all")} if adapter is not None else set()
    prefixes = tuple(f"{web.rstrip('/')}/{kind}/{ref}/" for kind in ("blob", "tree"))
    out = []
    lines = text.splitlines()
    fenced = _md_fence_mask(lines)
    for n, line in enumerate(lines, 1):
        if fenced[n - 1]:
            continue
        for raw in _link_targets(line):
            url = raw.split("#", 1)[0].split("?", 1)[0]
            prefix = next((p for p in prefixes if url.startswith(p)), None)
            if prefix is None:
                continue
            host_path = urllib.parse.unquote(url[len(prefix):]).strip("/")
            target = (top / host_path).resolve()
            if target != top and top not in target.parents:
                out.append(Violation(_rel(front, root), n, "broken-link",
                                     f"{url} points outside the repository"))
            elif not target.exists():
                out.append(Violation(_rel(front, root), n, "broken-link",
                                     f"{url}: {host_path} does not exist"))
            elif (target == guide_root or guide_root in target.parents) and target not in pages:
                out.append(Violation(_rel(front, root), n, "broken-link",
                                     f"{url}: {host_path} is not a guide page"))
    return out


def check_embedded(root: Path, guide: guidecfg.Guide,
                   baseline: guidecfg.Baseline | None = None) -> list[Violation]:
    """Front page ownership comment and absolute links, developer README links (embedded
    guides only). Absolute links are checked when the baseline's `self` entry has a web URL."""
    emb = guide.embedded
    if emb is None:
        return []
    out: list[Violation] = []
    front = emb.front_page
    if front.is_file():
        text = front.read_text(errors="replace")
        try:
            parsed = region.parse(text)
        except region.RegionError:
            # malformed markers are reported by the page rules (check_pages);
            # the ownership comment cannot be located without a valid region
            parsed = None
        if parsed is not None:
            # FR-011: the ownership comment is guide-written, so it sits inside the
            # region (first line of the file without markers, FR-002); a marked front
            # page states that the region is guide-owned and the rest is the author's
            expected = sources.OWNERSHIP_COMMENT_REGION if parsed.marked else sources.OWNERSHIP_COMMENT
            first = parsed.content.splitlines()[:1]
            if not first or first[0].strip() != expected:
                out.append(Violation(_rel(front, root), parsed.begin_line + 1, "front-page",
                                     "the first line of the guide-owned region (of the file without "
                                     "markers) must be the ownership comment: " + expected))
        src = baseline.source(guidecfg.SELF_ID) if baseline is not None else None
        if src is not None and src.web:
            # the same branch fallback as embed.py stage, which writes such links
            out.extend(_absolute_links(front, root, text, src.web, src.ref or "main"))
    dev = emb.developer_readme
    if dev is not None:
        if dev.is_file():
            out.extend(_relative_links(dev, root, dev.read_text(errors="replace")))
        else:
            out.append(Violation("guide.yaml", 0, "developer-readme",
                                 f"embedded.developer_readme {_rel(dev, root)} not found"))
    return out


def check_publish(root: Path, guide: guidecfg.Guide) -> list[Violation]:
    """The publish target of a guide with a publish block (specs/006, story 1).

    The target is the author's file: only the region between the markers is
    guide-owned. Two rules apply anyway (FR-008): the marker pair must be
    balanced and unique (region.parse, rules region-unbalanced and
    region-duplicate), and relative links anywhere in the file, author text
    included, must resolve. Author text is never checked for anything else.
    """
    if guide.publish is None:
        return []
    target = guide.publish.target
    rel = _rel(target, root)
    if not target.is_file():
        return [Violation(rel, 0, "publish-target", "publish target not found; create it with a "
                            f"{region.MARKER_BEGIN} / {region.MARKER_END} pair")]
    text = target.read_text(errors="replace")
    out: list[Violation] = []
    try:
        region.parse(text)
    except region.RegionError as err:
        out.append(Violation(rel, err.line, err.rule, str(err)))
    out.extend(_relative_links(target, root, text))
    return out


def check_stubs(root: Path, guide: guidecfg.Guide) -> list[Violation]:
    """Redirect stubs of an embedded guide (FR-023, FR-024): exactly one marker line (the
    first), and exactly one link, which resolves. No page rules apply to a stub."""
    if guide.embedded is None:
        return []
    out: list[Violation] = []
    for stub in guide.embedded.stubs:
        rel = _rel(stub, root)
        if not stub.is_file():
            out.append(Violation(rel, 0, "moved-stub", "stub not found (listed in guide.yaml embedded.stubs)"))
            continue
        lines = stub.read_text(errors="replace").splitlines()
        markers = [n for n, line in enumerate(lines, 1) if line.strip() == STUB_MARKER]
        if not lines or lines[0].strip() != STUB_MARKER or len(markers) != 1:
            out.append(Violation(rel, 1, "moved-stub", f"the first line must be the marker {STUB_MARKER}, once"))
        fenced = _md_fence_mask(lines)
        links = [(n, (m.group(1) or m.group(2) or "")) for n, line in enumerate(lines, 1) if not fenced[n - 1]
                 for m in MD_LINK_RE.finditer(line)]
        if len(links) != 1:
            out.append(Violation(rel, links[1][0] if len(links) > 1 else 1, "moved-stub",
                                 f"a stub has exactly one link (found {len(links)})"))
            continue
        n, target = links[0]
        path = target.split("#", 1)[0].split("?", 1)[0]
        if SCHEME_RE.match(path) or not path:
            continue
        if not (stub.parent / path).resolve().exists():
            out.append(Violation(rel, n, "moved-stub", f"{path} does not exist"))
    return out


def _md_link_rules(rel: str, page: Path, lines: list[str], fenced: list[bool],
                   internal: bool, internal_dir: Path, out: list[Violation]) -> None:
    """internal-link and broken-link over the whole text of a Markdown page.

    Used for a front page that carries the region markers: its other rules narrow to
    the region (FR-003), but the link rules read the entire file, author text
    included, at file line numbers (FR-008, the single exception).
    """
    for n, line in enumerate(lines, 1):
        if fenced[n - 1]:
            continue
        for m in MD_LINK_RE.finditer(line):
            target = (m.group(1) or m.group(2) or "").split("#", 1)[0].split("?", 1)[0]
            if not target or SCHEME_RE.match(target) or target.startswith("/") or "{{" in target:
                continue
            resolved = (page.parent / target).resolve()
            if not internal and (resolved == internal_dir or internal_dir in resolved.parents):
                out.append(Violation(rel, n, "internal-link", f"{target} links into the internal part"))
            elif not resolved.exists():
                out.append(Violation(rel, n, "broken-link", f"{target} does not exist"))


def check_pages(root: Path, guide: guidecfg.Guide, baseline: guidecfg.Baseline,
                strict: bool = False, structure: bool = False,
                warnings: list[str] | None = None) -> list[Violation]:
    """All content-check violations of a guide project.

    Warnings (problems that must not fail the check, such as a `self` citation without a
    fingerprint) are appended to warnings when a list is given.
    """
    root = Path(root)
    warnings = warnings if warnings is not None else []
    adapter = guidecfg.load_adapter(root)
    style = "line" if adapter.comment == "line" else "html"
    out: list[Violation] = []
    try:
        inputs = guidecfg.load_inputs(root)
    except guidecfg.ConfigError as err:
        out.extend(Violation("inputs.yaml", 0, "config", line) for line in err.lines())
        inputs = guidecfg.Inputs(root=root)

    cache = root / ".guide" / "cache"
    self_source = baseline.source(guidecfg.SELF_ID) if guide.embedded is not None else None
    typed = _typed_value_re(baseline)
    terms = [(t, re.compile(re.escape(t), re.I)) for t in guide.confidential_terms]
    patterns = [re.compile(p) for p in guide.confidential_patterns]
    diagrams = {p.stem for p in (root / "diagrams").glob("*.excalidraw")} if (root / "diagrams").is_dir() else set()
    internal_dir = (root / adapter.internal_root).resolve()
    internal_modules: set[str] = set()
    if adapter.format == "antora":
        internal_modules = (_antora_modules(root, adapter.internal_root)
                            - _antora_modules(root, adapter.content_root)) or {"internal"}

    front_res = guide.embedded.front_page.resolve() if guide.embedded is not None else None

    for page in guidecfg.pages(root, adapter, "all"):
        rel = _rel(page, root)
        text = page.read_text(errors="replace")
        # specs/006: a marked front page narrows every page rule to its region (FR-003);
        # only the link rules keep reading the whole file (FR-008). Violation lines are
        # offset to file lines; a malformed marker pair is reported and skips the page.
        offset = 0
        whole: list[str] | None = None
        if front_res is not None and page.resolve() == front_res:
            try:
                front_region = region.parse(text)
            except region.RegionError as err:
                out.append(Violation(rel, err.line, err.rule, str(err)))
                continue
            if front_region.marked:
                offset = front_region.begin_line
                whole = text.splitlines()
                text = front_region.content
        lines = text.splitlines()
        internal = guidecfg.is_internal(page, root, adapter)
        is_adoc = page.suffix in (".adoc", ".asciidoc")
        block = sources.find_block(text, style)
        span = _block_span(lines, block, style)
        mask = _verbatim_mask(lines) if is_adoc else [False] * len(lines)
        fenced = _md_fence_mask(lines) if not is_adoc else [False] * len(lines)

        for p in sources.check_text(text, style, rel):
            out.append(Violation(rel, p.line + offset, "source-block", p.message))
        for ref in (block.refs if block else []):
            if ref.kind == "input":
                if not internal:
                    out.append(Violation(rel, ref.line + offset, "input-on-shareable",
                                         f"{ref.raw}: input references are allowed only on internal pages"))
                elif inputs.get(ref.input_id) is None:
                    out.append(Violation(rel, ref.line + offset, "unknown-input",
                                         f"unknown input {ref.input_id!r} (not in inputs.yaml)"))
            elif ref.kind == "source" and ref.source_id == guidecfg.SELF_ID and self_source is not None:
                if guidecfg.is_guide_owned(root, ref.path):
                    out.append(Violation(rel, ref.line + offset, "self-citation",
                                         f"{ref.raw}: the guide must not verify itself against its own text "
                                         "(guide subdirectory, front page, developer README, or stub)"))
                    continue
                if ref.path not in self_source.fingerprints:
                    warnings.append(f"{rel}:{ref.line + offset}: [source-ref] warning: {ref.raw} has no fingerprint "
                                    "in baseline.yaml; run `uv run tools/guide/fetch.py rebaseline --to self=HEAD`")
                res = sources.resolve(ref, baseline, cache, inputs)
                if not res.ok:
                    out.append(Violation(rel, ref.line + offset, "source-ref", res.message))
                elif res.message.startswith("warning:"):
                    warnings.append(f"{rel}:{ref.line + offset}: [source-ref] {res.message}")
            elif ref.kind == "source" and cache.is_dir():
                res = sources.resolve(ref, baseline, cache, inputs)
                if not res.ok:
                    out.append(Violation(rel, ref.line, "source-ref", res.message))

        stub_re = STUB_LINE_RE if style == "line" else STUB_HTML_RE
        for n, line in enumerate(lines, 1):
            in_block = n in span
            if strict and stub_re.match(line.strip()):
                out.append(Violation(rel, n + offset, "stub", "unfinished stub page"))
            if typed and not in_block:
                for m in typed.finditer(REGION_RE.sub(r"\1\2", line)):
                    out.append(Violation(rel, n + offset, "typed-value",
                                         f"typed version or commit {m.group(0)!r}; use a baseline attribute"))
            if is_adoc and not mask[n - 1] and not in_block and _prose_line(line) and _sentence_problem(line):
                out.append(Violation(rel, n + offset, "sentence-per-line", "more than one sentence on this line"))
            if not internal:
                for term, rx in terms:
                    if rx.search(line):
                        out.append(Violation(rel, n + offset, "confidential",
                                             f"confidential term {term!r} on a shareable page"))
                for rx in patterns:
                    m = rx.search(line)
                    if m:
                        out.append(Violation(rel, n + offset, "confidential",
                                             f"confidential pattern match {m.group(0)!r} on a shareable page"))
                if is_adoc:
                    for m in XREF_RE.finditer(line):
                        if _xref_module(m.group(1)) in internal_modules:
                            out.append(Violation(rel, n + offset, "internal-link",
                                                 f"xref:{m.group(1)} links into the internal part"))
                elif whole is None:
                    for m in MD_LINK_RE.finditer(line):
                        target = (m.group(1) or m.group(2) or "").split("#", 1)[0].split("?", 1)[0]
                        if not target or SCHEME_RE.match(target) or target.startswith("/"):
                            continue
                        resolved = (page.parent / target).resolve()
                        if resolved == internal_dir or internal_dir in resolved.parents:
                            out.append(Violation(rel, n, "internal-link", f"{target} links into the internal part"))
            if whole is None and not is_adoc and not fenced[n - 1]:
                for m in MD_LINK_RE.finditer(line):
                    target = (m.group(1) or m.group(2) or "").split("#", 1)[0].split("?", 1)[0]
                    if not target or SCHEME_RE.match(target) or target.startswith("/") or "{{" in target:
                        continue
                    resolved = (page.parent / target).resolve()
                    if not internal and (resolved == internal_dir or internal_dir in resolved.parents):
                        continue  # reported as internal-link
                    if not resolved.exists():
                        out.append(Violation(rel, n, "broken-link", f"{target} does not exist"))
            if is_adoc and not mask[n - 1] and not line.lstrip().startswith("//"):
                for m in IMAGE_RE.finditer(line):
                    target, attrlist = m.group(1), m.group(2)
                    if _alt_comma_unquoted(attrlist):
                        out.append(Violation(rel, n + offset, "image-alt",
                                             f"alt text of {target} contains a comma; quote it: [\"...\"]"))
                    if adapter.format == "antora" and Path(target).stem in diagrams and not _has_role_expand(attrlist):
                        out.append(Violation(rel, n + offset, "diagram-expand",
                                             f"diagram {target} needs role=expand so it opens enlarged on click"))
        if whole is not None:
            # FR-008: the link rules of a marked front page read the whole file,
            # author text included, at file line numbers
            _md_link_rules(rel, page, whole, _md_fence_mask(whole), internal, internal_dir, out)

    text_files = _text_files(root, adapter)
    if guide.embedded is not None and guide.embedded.front_page.is_file():
        text_files.append(guide.embedded.front_page)
    for f in text_files:
        try:
            text = f.read_text()
        except UnicodeDecodeError:
            continue
        offset = 0
        if front_res is not None and f.resolve() == front_res:
            # specs/006: the dash rule reads the region of a marked front page only
            try:
                parsed = region.parse(text)
            except region.RegionError:
                parsed = None  # reported by the page rules
            if parsed is not None and parsed.marked:
                text, offset = parsed.content, parsed.begin_line
        for n, line in enumerate(text.splitlines(), 1):
            if DASH_RE.search(line):
                out.append(Violation(_rel(f, root), n + offset, "dash", "em dash or en dash character; rephrase"))

    out.extend(_check_rules(root))
    out.extend(check_embedded(root, guide, baseline))
    out.extend(check_publish(root, guide))
    out.extend(check_stubs(root, guide))
    if adapter.format == "antora":
        out.extend(check_nav(root, adapter, warnings))
    if adapter.format == "antora" and guide.branding is not None:
        out.extend(check_branded_site(root, guide))
        out.extend(check_neutral_theme(root, guide))
    if structure:
        out.extend(check_structure(root, guide, adapter))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Content checks for a guide project")
    parser.add_argument("--strict", action="store_true", help="also fail on stub pages (strict rigor)")
    parser.add_argument("--structure", action="store_true",
                        help="also check that persona entry pages and section titles resolve (end of a run)")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    strict = args.strict or os.environ.get("STRICT", "") == "1"
    structure = args.structure or os.environ.get("STRUCTURE", "") == "1"
    warnings: list[str] = []
    try:
        guide = guidecfg.load_guide(args.root)
        baseline = guidecfg.load_baseline(args.root)
        violations = check_pages(args.root, guide, baseline, strict, structure, warnings)
    except guidecfg.ConfigError as err:
        print(err)
        return 1
    for w in warnings:
        print(w, file=sys.stderr)
    for v in violations:
        print(v)
    if violations:
        print(f"check: {len(violations)} violation(s)")
        return 1
    print("check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
