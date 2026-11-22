#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""The guide-owned region of a Markdown file (specs/006-author-owned-front-page-region).

One region per file, delimited by two marker lines on their own lines:

  <!-- guide:region -->
  ... guide-owned content ...
  <!-- /guide:region -->

Everything outside the markers is author-owned: no guide command writes, verifies,
or reports it (the whole-file link check is the single exception, FR-008). Marker
text inside fenced code blocks is author text, never a delimiter (FR-005). A file
the guide owns without markers is one implicit region: the whole file (FR-002).
The markers mirror the generated-region pair of attrs.py
(<!-- guide:attr NAME -->VALUE<!-- /guide:attr -->).

No CLI: publish.py, check.py, embed.py, attrs.py, and fetch.py import this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MARKER_BEGIN = "<!-- guide:region -->"
MARKER_END = "<!-- /guide:region -->"

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
# generated regions (attrs.py) inside guide content hold baseline values that
# change between runs; comparisons empty them
ATTR_REGION_RE = re.compile(r"(<!--\s*guide:attr\s+[^\s>]+\s*-->).*?(<!--\s*/guide:attr\s*-->)", re.S)


class RegionError(ValueError):
    """Malformed region markers.

    `rule` is "region-unbalanced" (a begin without an end or the reverse) or
    "region-duplicate" (more than one marker pair); `line` is the 1-based line
    of the offending marker when there is one. The message names the problem;
    callers prefix the file path.
    """

    def __init__(self, message: str, rule: str, line: int = 0):
        super().__init__(message)
        self.rule = rule
        self.line = line


@dataclass
class Region:
    """The parsed view of a file (data-model.md).

    author_prefix, content, and author_suffix are byte-exact slices of the file:
    prefix runs to the end of the begin marker line, content is everything
    between the marker lines, suffix starts at the end marker line. Without
    markers the whole file is the content and both line numbers are 0.
    """

    author_prefix: str
    content: str
    author_suffix: str
    begin_line: int   # 1-based line of the begin marker; 0 without markers
    end_line: int     # 1-based line of the end marker; 0 without markers

    @property
    def marked(self) -> bool:
        """True when the file carries the marker pair."""
        return self.begin_line > 0


def fence_mask(lines: list[str]) -> list[bool]:
    """True for lines inside (or delimiting) fenced code blocks (``` or ~~~)."""
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


def marker_lines(text: str) -> list[tuple[str, int]]:
    """(kind, 1-based line) of every marker line outside fenced code blocks."""
    lines = text.splitlines()
    mask = fence_mask(lines)
    out: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        if mask[i]:
            continue
        stripped = line.strip()
        if stripped == MARKER_BEGIN:
            out.append(("begin", i + 1))
        elif stripped == MARKER_END:
            out.append(("end", i + 1))
    return out


def parse(text: str) -> Region:
    """The region view of text; raises RegionError on malformed markers.

    A file without markers parses to the whole file as content (an implicit
    guide-owned region, FR-002); a declared publish target rejects that view
    itself (the publish error, not a region error).
    """
    markers = marker_lines(text)
    if not markers:
        return Region(author_prefix="", content=text, author_suffix="", begin_line=0, end_line=0)
    begins = [line for kind, line in markers if kind == "begin"]
    ends = [line for kind, line in markers if kind == "end"]
    if len(begins) > 1 or len(ends) > 1:
        raise RegionError(f"found {len(begins)} begin and {len(ends)} end markers; "
                          "exactly one marker pair is allowed", "region-duplicate",
                          begins[1] if len(begins) > 1 else ends[1])
    if not begins or not ends:
        kind, line = markers[0]
        raise RegionError(f"{MARKER_BEGIN if kind == 'begin' else MARKER_END} at line {line} "
                          "has no matching counterpart", "region-unbalanced", line)
    begin, end = begins[0], ends[0]
    if begin > end:
        raise RegionError(f"{MARKER_END} at line {end} comes before {MARKER_BEGIN} at line {begin}",
                          "region-unbalanced", end)
    lines = text.splitlines(keepends=True)
    return Region(author_prefix="".join(lines[:begin - 1]), content="".join(lines[begin:end - 1]),
                  author_suffix="".join(lines[end:]), begin_line=begin, end_line=end)


def splice(text: str, new_content: str) -> str:
    """Replace the region content, leaving every byte of author text untouched.

    The only legal mutation of a file with markers (contracts/region-markers.md).
    A file without markers is one implicit region: the whole text is replaced.
    """
    region = parse(text)
    if not region.marked:
        return new_content
    lines = text.splitlines(keepends=True)
    return (region.author_prefix + lines[region.begin_line - 1] + new_content
            + lines[region.end_line - 1] + region.author_suffix)


def normalized(text: str) -> str:
    """The region content with generated guide:attr values emptied (the comparison
    key for hand-edit detection, research R5); the whole file without markers."""
    return ATTR_REGION_RE.sub(r"\1\2", parse(text).content)
