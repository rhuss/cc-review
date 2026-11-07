#!/usr/bin/env python3
"""Collect a read-only, bounded repository inbox snapshot using authenticated gh.

The snapshot is written to snapshot.json in a new private directory under
$TMPDIR (else /tmp), outside the invoking checkout. Standard output carries
only a one-line JSON summary naming that file, never the snapshot itself.
Needs network access to the GitHub API.

Contextual assessment uses commands/inbox.md; PR action eligibility is shared.
Requires Python 3.9+ and gh; reviewer state is read without creating any paths.
"""

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
from urllib.parse import urlsplit

from pr_actions import normalize_pr, assess_pr
from reviewer_activity import load_activity


TYPES = ("pr", "issue", "discussion")
DETAIL_COLLECTION_TIMEOUT_SECONDS = 120
REPO_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9_.-]+"
REASONS = {
    "pr": {"authored": "author", "assigned": "assignee", "mentioned": "mentions",
           "commented": "commenter", "reviewed": "reviewed-by", "review_requested": "review-requested",
           "team_review_requested": "team-review-requested-user"},
    "issue": {"authored": "author", "assigned": "assignee", "mentioned": "mentions", "commented": "commenter"},
    # Discussion search returns no matches for mentions: (and involves: covers only
    # author and commenter), so mentions are a known coverage limit.
    "discussion": {"authored": "author", "commented": "commenter"},
}
KNOWN_LIMITS = {
    "discussion": "Discussions where you were only @-mentioned are not discovered; "
                  "GitHub Discussion search does not support mentions.",
}
TYPENAMES = {"pr": "PullRequest", "issue": "Issue", "discussion": "Discussion"}
SNAPSHOT_PREFIX = "cc-review-inbox."
SNAPSHOT_FILE = "snapshot.json"
STALE_SNAPSHOT_SECONDS = 12 * 3600
NETWORK_FAILURE = re.compile(r"error connecting to|could not resolve host|no such host|dial tcp"
                             r"|connection refused|network is unreachable", re.I)
NETWORK_HINT = (" GitHub was unreachable. If this runs in a sandbox without network access,"
                " rerun the same command unchanged with network permission.")


class InboxError(Exception):
    """An actionable collection failure, safe to show without a traceback."""


def clean_text(value):
    """Keep readable text and line breaks while removing terminal/display controls."""
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    return "".join(c for c in value if c in "\n\t" or unicodedata.category(c) not in ("Cc", "Cf"))


def gh_failure(stderr, fallback):
    """Shortened gh error text, with a sandbox hint when the network was unreachable."""
    message = clean_text(stderr or "").strip()[:400] or fallback
    if NETWORK_FAILURE.search(message):
        message += NETWORK_HINT
    return message


def checkout_root():
    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                                text=True, timeout=5, check=False)
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return None
    root = result.stdout.strip()
    return os.path.realpath(root) if not result.returncode and root else None


def sweep_stale_snapshots(base, prefix):
    """Reclaim snapshot dirs orphaned by earlier runs that ended before their clean-up.

    A tour can span several turns, so clean-up is not always reached (an error
    mid-report, an abandoned tour, a fresh shell that lost the path).
    """
    cutoff = time.time() - STALE_SNAPSHOT_SECONDS
    try:
        names = os.listdir(base)
    except OSError:
        return
    for name in names:
        if not name.startswith(prefix):
            continue
        path = os.path.join(base, name)
        try:
            info = os.lstat(path)
            if stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and info.st_mtime < cutoff:
                shutil.rmtree(path)
        except OSError:
            continue


def snapshot_directory(prefix):
    """Create a private (0700) directory under $TMPDIR or /tmp, outside the invoking checkout."""
    base = os.path.realpath(os.environ.get("TMPDIR") or "/tmp")
    if not os.path.isdir(base):
        raise InboxError("Cannot resolve the temporary directory.")
    root = checkout_root()
    if root and (base == root or base.startswith(root.rstrip(os.sep) + os.sep)):
        raise InboxError("TMPDIR must be outside the invoking checkout.")
    sweep_stale_snapshots(base, prefix)
    try:
        return tempfile.mkdtemp(prefix=prefix, dir=base)
    except OSError as exc:
        raise InboxError("Cannot create a private snapshot directory: " + clean_text(str(exc))) from exc


def save_snapshot(directory, snapshot):
    path = os.path.join(directory, SNAPSHOT_FILE)
    try:
        handle = os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8")
        with handle:
            json.dump(snapshot, handle, ensure_ascii=True, indent=2)
            handle.write("\n")
    except OSError as exc:
        raise InboxError("Cannot write the snapshot: " + clean_text(str(exc))) from exc
    return path


def run_collector(label, prefix, collect_snapshot, summarize):
    """Write the snapshot to a private file and print only a compact summary line.

    Keeping the snapshot off standard output means a harness that truncates
    command output can never cut it short; the agent reads the file instead.
    """
    try:
        directory = snapshot_directory(prefix)
    except InboxError as exc:
        print(label + ": " + str(exc), file=sys.stderr)
        return 1
    try:
        snapshot = collect_snapshot()
        path = save_snapshot(directory, snapshot)
    except BaseException as exc:
        shutil.rmtree(directory, ignore_errors=True)
        if not isinstance(exc, InboxError):
            raise
        print(label + ": " + str(exc), file=sys.stderr)
        return 1
    summary = {"snapshot_dir": directory, "snapshot": path}
    summary.update(summarize(snapshot))
    print(json.dumps(summary, ensure_ascii=True))
    return 0


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="GitHub repository in owner/name form (default: current repo)")
    parser.add_argument("--type", action="append", dest="type_filters", metavar="TYPES",
                        help="comma-separated pr,issue,discussion; repeat to combine (default: all)")
    parser.add_argument("--limit", type=int, default=10, help="items per type, 1..100 (default: 10)")
    parser.add_argument("--since", metavar="YYYY-MM-DD", help="updated-since date for all selected types")
    args = parser.parse_args(argv)
    if args.repo is not None and (not re.fullmatch(REPO_PATTERN, args.repo)
                      or args.repo.split("/")[1] in (".", "..")):
        parser.error("--repo must be owner/name")
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")
    if args.since is not None:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.since):
                raise ValueError
            date.fromisoformat(args.since)
        except ValueError:
            parser.error("--since must be a valid YYYY-MM-DD calendar date")
    selected = []
    for selection in args.type_filters or []:
        for kind in selection.split(","):
            kind = kind.strip()
            if kind not in TYPES:
                parser.error("--type accepts only pr, issue, discussion (no empty entries)")
            if kind not in selected:
                selected.append(kind)
    args.types = selected or list(TYPES)
    return args


class GitHub:
    def __init__(self):
        self.host = None

    def call(self, args, deadline=None):
        timeout = 30
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise InboxError("Detail collection deadline reached; remaining items have incomplete context.")
            timeout = min(timeout, remaining)
        try:
            result = subprocess.run(["gh", *args], capture_output=True, text=True,
                                    encoding="utf-8", errors="replace",
                                    timeout=timeout, check=False)
        except FileNotFoundError as exc:
            raise InboxError("gh is required; install GitHub CLI and run gh auth login.") from exc
        except subprocess.TimeoutExpired as exc:
            if deadline is not None and timeout < 30:
                message = "Detail collection deadline reached; this and remaining items may have incomplete context."
            else:
                message = "GitHub request timed out after " + format(timeout, "g") + " seconds; try again later."
            raise InboxError(message) from exc
        except OSError as exc:
            raise InboxError("Could not execute gh: " + clean_text(str(exc))) from exc
        try:
            value = json.loads(result.stdout, strict=False)
        except (ValueError, TypeError) as exc:
            raise InboxError(gh_failure(result.stderr, "gh returned invalid JSON; check authentication"
                                                       " and try again.")) from exc
        if not isinstance(value, dict):
            raise InboxError("gh returned an unexpected response; expected an object.")
        errors = value.get("errors") or []
        if not isinstance(errors, list) or any(not isinstance(error, dict) for error in errors):
            raise InboxError("GitHub returned an invalid error response.")
        # GraphQL can return useful data and errors together, with gh exiting 1.
        usable_data = isinstance(value.get("data"), dict) and any(
            v is not None for v in value["data"].values())
        if result.returncode and not (value.get("errors") and usable_data):
            raise InboxError(gh_failure(result.stderr, "GitHub request failed."))
        if value.get("errors") and not usable_data:
            errors = "; ".join(clean_text(str(e.get("message", "GraphQL error"))) for e in value["errors"])
            raise InboxError(errors[:400])
        return value

    def graphql(self, query, variables=None, deadline=None):
        args = ["api", "--hostname", self.host, "graphql", "-f", "query=" + query]
        for key, value in (variables or {}).items():
            args.extend(["-f", key + "=" + str(value)])
        response = self.call(args, deadline=deadline)
        if not isinstance(response.get("data"), dict):
            raise InboxError("GitHub returned an invalid GraphQL data response.")
        return response


def search_query(kind, repository, login, since):
    """Separate search matches preserve provenance, including manual reviews."""
    reasons = REASONS[kind]
    declarations = ", ".join("$q_" + reason + ": String!" for reason in reasons)
    search_type = "DISCUSSION" if kind == "discussion" else "ISSUE"
    count_field = "discussionCount" if kind == "discussion" else "issueCount"
    fields = "id number title url updatedAt author { login } "
    fields += "closed" if kind == "discussion" else "state"
    if kind == "pr":
        fields += " isDraft"
    selections, variables = [], {}
    for reason, qualifier in reasons.items():
        parts = ["repo:" + repository]
        if kind != "discussion":
            parts += ["is:" + kind, "is:open"]
        parts.append(qualifier + ":" + login)
        if since:
            parts.append("updated:>=" + since)
        parts.append("sort:updated-desc")
        variables["q_" + reason] = " ".join(parts)
        selections.append(reason + ": search(query: $q_" + reason + ", type: " + search_type
                          + ", first: 100) { " + count_field + " pageInfo { hasNextPage } "
                          + "nodes { __typename ... on " + TYPENAMES[kind] + " { " + fields + " } } }")
    return "query InboxSearch_" + kind + "(" + declarations + ") { " + " ".join(selections) + " }", variables


def discover(kind, repository, login, since, limit, github):
    source = {"type": kind, "status": "unavailable", "discovered": 0,
              "selected": 0, "queries": [], "warnings": []}
    query, variables = search_query(kind, repository, login, since)
    try:
        response = github.graphql(query, variables)
    except InboxError as exc:
        source["warnings"].append(str(exc))
        return source, []
    data = response.get("data") or {}
    for error in response.get("errors") or []:
        source["warnings"].append("Partial search: " + clean_text(str(error.get("message", "GraphQL error"))))
    candidates, succeeded = {}, 0
    count_field = "discussionCount" if kind == "discussion" else "issueCount"
    for reason in REASONS[kind]:
        connection = data.get(reason)
        if not isinstance(connection, dict) or not isinstance(connection.get("nodes"), list):
            source["warnings"].append("Could not read " + reason + " matches.")
            continue
        nodes = connection["nodes"]
        total = connection.get(count_field)
        page = connection.get("pageInfo")
        if (not isinstance(total, int) or isinstance(total, bool) or total < 0
                or not isinstance(page, dict) or not isinstance(page.get("hasNextPage"), bool)):
            source["warnings"].append(reason + ": invalid search counts or pagination; matches were not trusted.")
            continue
        succeeded += 1
        incomplete = page["hasNextPage"] or total > len(nodes)
        source["queries"].append({"reason": reason, "total": total, "incomplete": incomplete})
        if incomplete:
            source["warnings"].append(reason + ": discovery limited to 100 matches; additional matches may be omitted.")
        for node in nodes:
            if not isinstance(node, dict) or node.get("__typename") != TYPENAMES[kind]:
                source["warnings"].append(reason + ": a missing or unexpected item type was omitted.")
                continue
            if (not isinstance(node.get("id"), str) or not node["id"]
                    or not isinstance(node.get("number"), int) or isinstance(node["number"], bool)
                    or node["number"] < 1 or not isinstance(node.get("title"), str)
                    or not isinstance(node.get("url"), str) or not isinstance(node.get("updatedAt"), str)
                    or (node.get("author") is not None and not isinstance(node["author"], dict))):
                source["warnings"].append(reason + ": invalid item metadata was omitted.")
                continue
            if kind != "discussion" and node.get("state") != "OPEN":
                continue
            entry = candidates.get(node["id"])
            if entry is None:
                entry = {"id": node["id"], "type": kind, "number": node["number"],
                         "title": clean_text(node.get("title") or "Untitled"), "url": node.get("url", ""),
                         "author": (node.get("author") or {}).get("login"),
                         "state": node.get("state") or ("CLOSED" if node.get("closed") else "OPEN"),
                         "is_draft": bool(node.get("isDraft")), "updated_at": node.get("updatedAt") or "",
                         "reasons": [], "detail": None, "context_complete": False,
                         "warnings": ["Conversation details have not been collected."]}
                candidates[node["id"]] = entry
            if reason not in entry["reasons"]:
                entry["reasons"].append(reason)
    if not succeeded:
        return source, []
    entries = sorted(candidates.values(), key=lambda e: (e["updated_at"], e["number"]), reverse=True)
    source["discovered"] = len(entries)
    if len(entries) > limit:
        source["warnings"].append("Showing " + str(limit) + " of " + str(len(entries))
                                  + " discovered items; remaining items are omitted (maximum --limit: 100 per type).")
    entries = entries[:limit]
    source["selected"] = len(entries)
    source["status"] = "partial" if source["warnings"] else "ok"
    return source, entries


def detail_query(kind):
    actor = "author { login __typename }"
    comment = "id databaseId body url createdAt updatedAt " + actor
    page = "totalCount pageInfo { hasNextPage hasPreviousPage }"
    common = "id number title url updatedAt body " + actor
    comments = "comments(last: 20) { " + page + " nodes { " + comment + " } }"
    if kind == "pr":
        fields = (common + " state isDraft headRefOid reviewDecision " + comments
                  + " assignees(first: 100) { " + page + " nodes { login } }"
                  + " reviewRequests(first: 100) { " + page
                  + " nodes { requestedReviewer { __typename ... on User { login } ... on Team { name slug } } } }"
                  + " reviews(last: 20) { " + page + " nodes { body url submittedAt " + actor
                  + " state commit { oid committedDate } } }"
                  + " reviewThreads(last: 20) { " + page
                  + " nodes { id isResolved isOutdated path line"
                  + " rootComment: comments(first: 1) { nodes { " + comment
                  + " originalCommit { oid } pullRequestReview { body author { login } commit { oid } } } }"
                  + " comments(last: 10) { " + page
                  + " nodes { " + comment + " originalCommit { oid }"
                  + " pullRequestReview { body author { login } commit { oid } } } } } }"
                  + " commits(last: 20) { " + page
                  + " nodes { commit { oid committedDate url messageHeadline statusCheckRollup { state } } } }")
    elif kind == "discussion":
        fields = (common + " closed isAnswered category { isAnswerable } answer { " + comment + " }"
                  + " comments(last: 20) { " + page + " nodes { " + comment
                  + " replies(last: 10) { " + page + " nodes { " + comment + " } } } }")
    else:
        fields = common + " state " + comments + " assignees(first: 100) { " + page + " nodes { login } }"
    return ("query InboxDetail_" + kind + "($id: ID!) { node(id: $id) { __typename ... on "
            + TYPENAMES[kind] + " { " + fields + " } } }")


def normalize_detail(value):
    warnings = []

    def visit(current, path):
        connection_name = path.rsplit(".", 1)[-1]
        if connection_name in ("comments", "replies", "reviews", "commits", "reviewThreads", "reviewRequests", "assignees"):
            if (not isinstance(current, dict) or not isinstance(current.get("nodes"), list)
                    or not isinstance(current.get("totalCount"), int)
                    or not isinstance(current.get("pageInfo"), dict)):
                warnings.append(path + ": activity or its coverage metadata is unavailable.")
        if isinstance(current, dict):
            if "nodes" in current and not isinstance(current["nodes"], list):
                warnings.append(path + ": activity is unavailable.")
            elif isinstance(current.get("nodes"), list) and connection_name != "rootComment":
                page = current.get("pageInfo")
                if not isinstance(page, dict):
                    page = {}
                    warnings.append(path + ": pagination is unavailable.")
                total = current.get("totalCount", len(current["nodes"]))
                if (page.get("hasNextPage") or page.get("hasPreviousPage")
                        or (isinstance(total, int) and total > len(current["nodes"]))):
                    warnings.append(path + ": activity is truncated; earlier or later entries were not inspected.")
            return {key: visit(val, path + "." + key) for key, val in current.items()}
        if isinstance(current, list):
            if path.endswith(".nodes") and any(val is None for val in current):
                warnings.append(path + ": some activity is unavailable.")
            return [visit(val, path + "[" + str(i) + "]") for i, val in enumerate(current)]
        if isinstance(current, str):
            text = clean_text(current)
            if path.rsplit(".", 1)[-1] in ("body", "messageHeadline", "title", "path"):
                cap = 2000 if path == "detail.body" else 1000
                if len(text) > cap:
                    warnings.append(path + ": text truncated to " + str(cap) + " characters.")
                    return text[:cap]
            return text
        return current

    return visit(value, "detail"), warnings


def attach_assessment(entry, raw, context):
    value = dict(entry, detail=raw, host=context["host"])
    evidence = normalize_pr(value, "inbox", context["repository"], context["user"])
    evidence["handled_complete"] = context["handled_complete"]
    entry["assessment"] = assess_pr(evidence, context["handled"])


def hydrate(entry, github, deadline=None, action_context=None):
    try:
        response = github.graphql(detail_query(entry["type"]), {"id": entry["id"]}, deadline=deadline)
        node = (response.get("data") or {}).get("node")
        if (not isinstance(node, dict) or node.get("__typename") != TYPENAMES[entry["type"]]
                or node.get("id") != entry["id"]):
            raise InboxError("Conversation is unavailable or the item type changed.")
        if entry["type"] == "pr" and action_context:
            # Fingerprints must use original bodies and exact identities,
            # before display sanitization or the 1000-character body cap.
            attach_assessment(entry, node, action_context)
        detail, warnings = normalize_detail(node)
        required = {"body": str, "comments": dict}
        if entry["type"] == "pr":
            required.update(headRefOid=str, reviews=dict, reviewThreads=dict, commits=dict, reviewRequests=dict)
        if entry["type"] == "discussion":
            required.update(closed=bool, category=dict)
            # GitHub returns isAnswered: null for categories that cannot be answered.
            category = node.get("category")
            if not isinstance(category, dict) or category.get("isAnswerable") is not False:
                required["isAnswered"] = bool
        warnings.extend("detail." + name + ": required context is unavailable."
                        for name, expected in required.items() if not isinstance(node.get(name), expected))
        warnings.extend("Partial detail: " + clean_text(str(error.get("message", "GraphQL error")))
                        for error in response.get("errors") or [])
        entry.update(detail=detail, warnings=warnings, context_complete=not warnings)
    except InboxError as exc:
        entry.update(detail=None, context_complete=False, warnings=["Could not read conversation: " + str(exc)])
        if entry["type"] == "pr" and action_context:
            attach_assessment(entry, None, action_context)
    if entry.get("assessment"):
        for action in ("review", "triage"):
            if not entry["assessment"][action]["complete"]:
                entry["warnings"].append(action + ": " + entry["assessment"][action]["reason"])
                entry["context_complete"] = False


def collect(args, github, now=None):
    now = now or datetime.now(timezone.utc)
    repo_args = ["repo", "view"]
    if args.repo:
        repo_args.append(args.repo)
    repo_args.extend(["--json", "nameWithOwner,url,hasDiscussionsEnabled"])
    try:
        repo = github.call(repo_args)
    except InboxError as exc:
        raise InboxError("Cannot resolve repository; use --repo owner/name and check access. " + str(exc)) from exc
    repository = repo.get("nameWithOwner")
    repo_url = repo.get("url")
    if not isinstance(repository, str) or not re.fullmatch(REPO_PATTERN, repository) or not isinstance(repo_url, str):
        raise InboxError("Repository metadata is incomplete; check access or use --repo owner/name.")
    try:
        parsed = urlsplit(repo_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError
    except ValueError as exc:
        raise InboxError("Repository URL is invalid; check repository access.") from exc
    github.host = parsed.hostname
    try:
        identity = github.graphql("query InboxIdentity { viewer { login } }")
        viewer = identity["data"].get("viewer")
        login = viewer.get("login") if isinstance(viewer, dict) else None
        if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", login):
            raise InboxError("authenticated username is unavailable")
    except InboxError as exc:
        raise InboxError("Cannot identify the authenticated user; run gh auth login --hostname "
                         + github.host + ". " + str(exc)) from exc
    discussion_since = args.since or (now.date() - timedelta(days=90)).isoformat()
    handled, state_warnings = load_activity(github.host, repository, login) if "pr" in args.types else ({}, [])
    action_context = dict(host=github.host, repository=repository, user=login,
                          handled=handled, handled_complete=not state_warnings)
    snapshot = {
        "schema_version": 1, "repository": repository, "repository_url": repo["url"],
        "host": github.host, "user": login, "collected_at": now.isoformat(),
        "scope": {"types": args.types, "limit_per_type": args.limit, "since": args.since,
                  "discussion_since": discussion_since, "pr_issue_state": "open",
                  "discovery_limit_per_reason": 100,
                  "pr_actions": {"review_mode": "default", "include_review_drafts": False,
                                 "include_triage_drafts": True, "bulk_default_limit": 10,
                                 "selection": "eligibility within collected candidates; bulk orders oldest updates first"},
                  "detail_collection_timeout_seconds": DETAIL_COLLECTION_TIMEOUT_SECONDS,
                  "known_limits": [KNOWN_LIMITS[kind] for kind in args.types if kind in KNOWN_LIMITS],
                  "detail_bounds": {"activity": 20, "replies": 10, "body_characters": 2000,
                                    "activity_body_characters": 1000, "people": 100}},
        "sources": [], "items": [], "warnings": state_warnings,
    }
    detail_deadline = None
    for kind in args.types:
        if kind == "discussion" and repo.get("hasDiscussionsEnabled") is False:
            source = {"type": kind, "status": "unavailable", "discovered": 0, "selected": 0,
                      "queries": [], "warnings": ["Discussions are disabled for this repository."]}
            entries = []
        else:
            since = discussion_since if kind == "discussion" else args.since
            source, entries = discover(kind, repository, login, since, args.limit, github)
        for entry in entries:
            if detail_deadline is None:
                detail_deadline = time.monotonic() + DETAIL_COLLECTION_TIMEOUT_SECONDS
            hydrate(entry, github, deadline=detail_deadline, action_context=action_context)
            snapshot["warnings"].extend(kind + " #" + str(entry["number"]) + ": " + warning
                                        for warning in entry["warnings"])
        snapshot["sources"].append(source)
        snapshot["items"].extend(entries)
        snapshot["warnings"].extend(kind + ": " + warning for warning in source["warnings"])
    if not any(source["status"] != "unavailable" for source in snapshot["sources"]):
        raise InboxError("No selected item type could be read. " + "; ".join(snapshot["warnings"]))
    return snapshot


def summarize(snapshot):
    return {"repository": snapshot["repository"], "user": snapshot["user"],
            "sources": {source["type"]: {"status": source["status"], "selected": source["selected"]}
                        for source in snapshot["sources"]},
            "items": len(snapshot["items"]), "warnings": len(snapshot["warnings"])}


def main(argv=None):
    args = parse_args(argv)
    return run_collector("inbox", SNAPSHOT_PREFIX, lambda: collect(args, GitHub()), summarize)


if __name__ == "__main__":
    sys.exit(main())
