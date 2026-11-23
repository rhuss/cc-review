#!/usr/bin/env python3
"""Deterministic helpers for bulk issue assessment (issue --bulk).

Selection, skip rules, paging, run state, loop control, posting, re-checks,
fix branches and draft pull requests, and the report live here; the command
prompt (commands/issue-bulk.md) keeps only judgment and conversation.

Every subcommand prints one JSON line (report prints Markdown). Errors go to
standard error as "Error: <message>" with exit code 1; usage errors exit 2.
Untrusted issue text never reaches a shell, and no subcommand runs project code.
Requires Python 3.9+, gh and git.
"""

import argparse
import fnmatch
from contextlib import contextmanager, nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inbox import GitHub, InboxError, REPO_PATTERN, clean_text, gh_failure  # noqa: E402
import run_state  # noqa: E402
import assess_issue  # noqa: E402
import assessment  # noqa: E402
import ci  # noqa: E402


KIND = "issue"
CORE = Path(__file__).resolve().parents[1]
MAINTAINER_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")
ASSESSMENT_MARKER = assessment.HIDDEN_PREFIX
PAGE_SIZE = 20
SEARCH_CAP = 1000
SKIP_REASONS = ("already_assessed", "maintainer_replied", "maintainer_pr", "history_too_long")
SKIP_LABELS = {"already_assessed": "already assessed", "maintainer_replied": "maintainer replied",
               "maintainer_pr": "maintainer PR", "history_too_long": "history too long to verify"}

PR_FIELDS = """... on PullRequest {
      number url state merged headRefName authorAssociation author { login __typename }
      baseRepository { nameWithOwner } headRepository { nameWithOwner }
      reviews(last: 50) { totalCount pageInfo { hasPreviousPage } nodes { authorAssociation author { login __typename } } }
      comments(last: 50) { totalCount pageInfo { hasPreviousPage } nodes { authorAssociation author { login __typename } } }
    }"""
ISSUE_FIELDS = """__typename
  ... on Issue {
    number title url state createdAt authorAssociation author { login __typename }
    comments(last: 100) {
      totalCount pageInfo { hasPreviousPage }
      nodes { url body authorAssociation author { login __typename } }
    }
    timelineItems(itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT, DISCONNECTED_EVENT], last: 50) {
      totalCount pageInfo { hasPreviousPage }
      nodes {
        __typename
        ... on CrossReferencedEvent { source { __typename PR } }
        ... on ConnectedEvent { source { __typename PR } subject { __typename PR } }
        ... on DisconnectedEvent { source { __typename PR } subject { __typename PR } }
      }
    }
  }""".replace("PR }", PR_FIELDS + " }")
SEARCH_QUERY = """query BulkIssueSearch($q: String!, $after: String) {
  search(type: ISSUE, query: $q, first: %d, after: $after) {
    issueCount pageInfo { hasNextPage endCursor }
    nodes { %s }
  }
}""" % (PAGE_SIZE, ISSUE_FIELDS)
RECHECK_QUERY = """query BulkIssueRecheck($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { issue(number: $number) { %s } }
}""" % ISSUE_FIELDS


class BulkError(Exception):
    """An actionable failure, safe to show without a traceback."""


class UsageError(BulkError):
    """Invalid arguments (exit code 2)."""


# ---------------------------------------------------------------------------
# Selection: pure classification of one search node
# ---------------------------------------------------------------------------

def _login(actor):
    return actor.get("login") if isinstance(actor, dict) and isinstance(actor.get("login"), str) else None


def is_bot(actor):
    login = _login(actor) or ""
    return isinstance(actor, dict) and (actor.get("__typename") == "Bot" or login.lower().endswith("[bot]"))


def is_maintainer(record):
    """A record (comment, review, PR) whose author is an owner, member or collaborator, never a bot."""
    return (isinstance(record, dict) and record.get("authorAssociation") in MAINTAINER_ASSOCIATIONS
            and not is_bot(record.get("author")))


def _connection(value):
    return value if isinstance(value, dict) and isinstance(value.get("nodes"), list) else None


def _truncated(value):
    connection = _connection(value)
    if connection is None:
        return True
    page = connection.get("pageInfo")
    return not isinstance(page, dict) or page.get("hasPreviousPage") is not False


def _event_pr(event):
    """The pull request side of a timeline event, or None."""
    if event.get("__typename") == "CrossReferencedEvent":
        candidates = [event.get("source")]
    else:
        candidates = [event.get("source"), event.get("subject")]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("__typename") == "PullRequest":
            return candidate
    return None


def _pr_record(pr):
    activity = [n for key in ("reviews", "comments")
                for n in (_connection(pr.get(key)) or {}).get("nodes", [])]
    owned = is_maintainer(pr) or any(is_maintainer(n) for n in activity)
    state = pr.get("state")
    merged = pr.get("merged") is True or state == "MERGED"
    return {"number": pr.get("number"), "url": pr.get("url"), "state": state, "merged": merged,
            "author": _login(pr.get("author")), "maintainer_owned": owned,
            "open_non_maintainer": state == "OPEN" and not owned}


def _ignored_pr(pr, ignore):
    """True for this run's own fix PR, which never counts against the issue.

    ignore is {"pr_url", "branch", "user", "repository"}: the recorded PR URL when the run opened one, else the
    fix branch pushed to the repository itself by the run's user.
    """
    if not ignore:
        return False
    if ignore.get("pr_url"):
        return pr.get("url") == ignore["pr_url"]
    head = ((pr.get("headRepository") or {}).get("nameWithOwner") or "").lower()
    return (pr.get("headRefName") == ignore["branch"] and head == ignore["repository"].lower()
            and (_login(pr.get("author")) or "").lower() == ignore["user"])


def classify(node, repository, ignore=None):
    """Apply the skip rules to one issue node.

    Returns {"reason": None or a SKIP_REASONS entry, "pr": number or None,
    "linked_prs": [...]}; linked_prs holds pull requests on this repository that
    still reference the issue. ignore (see _ignored_pr) leaves out the run's own
    fix pull request (used by the re-checks before posting and before a fix).
    """
    issue_author = (_login(node.get("author")) or "").lower()
    comments = _connection(node.get("comments"))
    timeline = _connection(node.get("timelineItems"))
    comment_nodes = comments["nodes"] if comments else []
    # Only a maintainer's or a bot's marker counts: pasting the marker cannot suppress an assessment (FR-005).
    if any(ASSESSMENT_MARKER in (c.get("body") or "") and (is_maintainer(c) or is_bot(c.get("author")))
           for c in comment_nodes if isinstance(c, dict)):
        return {"reason": "already_assessed", "pr": None, "linked_prs": []}
    for c in comment_nodes:
        if is_maintainer(c) and (_login(c.get("author")) or "").lower() != issue_author:
            return {"reason": "maintainer_replied", "pr": None, "linked_prs": []}
    linked, sources = {}, {}
    for event in (timeline["nodes"] if timeline else []):
        if not isinstance(event, dict):
            continue
        pr = _event_pr(event)
        if pr is None or not isinstance(pr.get("number"), int):
            continue
        base = ((pr.get("baseRepository") or {}).get("nameWithOwner") or "")
        if base.lower() != repository.lower() or _ignored_pr(pr, ignore):
            continue
        # A cross-reference (closing keyword or mention) stays; a disconnect removes only a manual link.
        kinds = sources.setdefault(pr["number"], set())
        kind = event.get("__typename")
        if kind == "DisconnectedEvent":
            kinds.discard("connected")
        else:
            kinds.add("connected" if kind == "ConnectedEvent" else "cross_reference")
            linked[pr["number"]] = pr
    linked = {number: pr for number, pr in linked.items() if sources.get(number)}
    records = [_pr_record(linked[number]) for number in sorted(linked)]
    for record in records:
        if record["maintainer_owned"] and (record["state"] == "OPEN" or record["merged"]):
            return {"reason": "maintainer_pr", "pr": record["number"], "linked_prs": records}
    # Only open or merged PRs can cause a skip (FR-008), so only their history must be complete.
    deciding = [n for n in linked if linked[n].get("state") == "OPEN" or linked[n].get("merged") is True
                or linked[n].get("state") == "MERGED"]
    if (comments is None or _truncated(comments) or timeline is None or _truncated(timeline)
            or any(_truncated(linked[n].get(key)) for n in deciding for key in ("reviews", "comments"))):
        return {"reason": "history_too_long", "pr": None, "linked_prs": records}
    return {"reason": None, "pr": None, "linked_prs": records}


# ---------------------------------------------------------------------------
# Shared I/O helpers
# ---------------------------------------------------------------------------

def valid_repo(value):
    return (isinstance(value, str) and re.fullmatch(REPO_PATTERN, value) is not None
            and value.split("/")[1] not in (".", ".."))


def github():
    client = GitHub()
    client.host = "github.com"
    return client


def graphql(query, strings=None, ints=None):
    args = ["api", "--hostname", "github.com", "graphql", "-f", "query=" + query]
    for key, value in (strings or {}).items():
        if value is not None:
            args.extend(["-f", key + "=" + str(value)])
    for key, value in (ints or {}).items():
        args.extend(["-F", key + "=" + str(int(value))])
    try:
        response = github().call(args)
    except InboxError as exc:
        raise BulkError(str(exc)) from exc
    if not isinstance(response.get("data"), dict):
        raise BulkError("GitHub returned an invalid GraphQL response.")
    if response.get("errors"):
        errors = response["errors"] if isinstance(response["errors"], list) else [response["errors"]]
        detail = "; ".join(" ".join(clean_text(str((e or {}).get("message") if isinstance(e, dict) else e)).split())
                           for e in errors[:3])[:300]
        raise BulkError("GitHub returned a partial response (" + (detail or "no detail") + "); retry later.")
    return response["data"]


def write_json(path, value):
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    run_state.write_json(path, value)


def read_json(path, what):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError) as exc:
        raise BulkError("Cannot read " + what + " " + str(path) + ": " + str(exc)) from exc


# ---------------------------------------------------------------------------
# select
# ---------------------------------------------------------------------------

def search_string(repository, search):
    query = "repo:" + repository + " is:issue is:open sort:created-desc"
    return query + (" " + search if search else "")


def select(repository, limit, scan, search=None):
    query = search_string(repository, search)
    selected, skipped, seen = [], [], set()
    scanned, cursor = 0, None
    ceiling_reached = exhausted = False
    while True:
        data = graphql(SEARCH_QUERY, {"q": query, "after": cursor})
        result = data.get("search")
        if not isinstance(result, dict) or not isinstance(result.get("nodes"), list):
            raise BulkError("GitHub returned an invalid search response; retry later.")
        page = result.get("pageInfo") or {}
        has_next = page.get("hasNextPage") is True
        if has_next and not isinstance(page.get("endCursor"), str):
            raise BulkError("GitHub returned an incomplete search page; retry later.")
        # Only open issues of this repository are candidates, whatever the search matched (FR-004).
        prefix = ("https://github.com/" + repository + "/issues/").lower()
        nodes = []
        for n in result["nodes"]:
            if (isinstance(n, dict) and n.get("__typename") == "Issue" and n.get("state") == "OPEN"
                    and isinstance(n.get("number"), int) and n["number"] not in seen
                    and str(n.get("url") or "").lower() == prefix + str(n["number"])):
                seen.add(n["number"])
                nodes.append(n)
        done = False
        for index, node in enumerate(nodes):
            scanned += 1
            verdict = classify(node, repository)
            entry = {"number": node["number"], "url": node.get("url"),
                     "title": clean_text(str(node.get("title") or ""))}
            if verdict["reason"]:
                entry.update(reason=verdict["reason"], pr=verdict["pr"])
                skipped.append(entry)
            else:
                entry.update(author=_login(node.get("author")), created_at=node.get("createdAt"),
                             linked_prs=verdict["linked_prs"])
                selected.append(entry)
            if len(selected) >= limit:
                done = True
                break
            if scanned >= scan:
                capped = isinstance(result.get("issueCount"), int) and result["issueCount"] > SEARCH_CAP
                if index + 1 < len(nodes) or has_next or capped:
                    ceiling_reached = True
                else:
                    exhausted = True
                done = True
                break
        if done:
            break
        if not has_next:
            # GitHub search returns at most 1000 results; a capped search is not an exhausted queue.
            if isinstance(result.get("issueCount"), int) and result["issueCount"] > SEARCH_CAP:
                ceiling_reached = True
            else:
                exhausted = True
            break
        cursor = page["endCursor"]
    selected.sort(key=lambda c: c.get("created_at") or "", reverse=True)
    return {"repository": repository, "query": query, "scanned": scanned,
            "ceiling_reached": ceiling_reached, "exhausted": exhausted,
            "selected": selected, "skipped": skipped}


def cmd_select(args):
    if not valid_repo(args.repo):
        raise UsageError("--repo must be owner/name.")
    if not 1 <= args.limit <= 100 or not 1 <= args.scan <= 1000 or args.scan < args.limit:
        raise UsageError("--limit must be 1 to 100 and --scan 1 to 1000, not below --limit.")
    if args.search:
        check_search(args.search)
    selection = select(args.repo, args.limit, args.scan, args.search)
    selection["options"] = {"search": args.search, "limit": args.limit, "scan": args.scan, "repo": args.repo}
    write_json(args.out, selection)
    return {"scanned": selection["scanned"], "selected": len(selection["selected"]),
            "skipped": len(selection["skipped"]), "ceiling_reached": selection["ceiling_reached"],
            "exhausted": selection["exhausted"]}


# ---------------------------------------------------------------------------
# Run lifecycle: resolve-repo, start, collect
# ---------------------------------------------------------------------------

PUSH_PERMISSIONS = ("ADMIN", "MAINTAIN", "WRITE")
NEW_POST = {"comment": "pending", "comment_url": None, "label": "pending", "reason": None}


def repo_view(repository, fields):
    args = ["repo", "view"] + (["github.com/" + repository] if repository else []) + ["--json", fields]
    metadata = github().call(args)
    name = metadata.get("nameWithOwner")
    if (not valid_repo(name) or metadata.get("url") != "https://github.com/" + name
            or (repository and repository.lower() != name.lower())):
        raise BulkError("Could not resolve the GitHub.com repository; check --repo and gh authentication.")
    return metadata


def cmd_resolve_repo(args):
    if args.repo is not None and not valid_repo(args.repo):
        raise UsageError("--repo must be owner/name.")
    return {"repository": repo_view(args.repo, "nameWithOwner,url")["nameWithOwner"]}


def new_item(candidate):
    return {"number": candidate["number"], "url": candidate["url"], "title": candidate.get("title", ""),
            "linked_prs": candidate.get("linked_prs", []), "phase": "selected", "failure": None,
            "kind": None, "recommendation": None, "label": None, "fix_eligible": False,
            "fix_ineligible_reason": None, "rendered_sha256": None, "decision": None,
            "post": dict(NEW_POST), "fix": None, "attempt_session": {}}


def cmd_start(args):
    selection = read_json(args.selection, "selection")
    if not isinstance(selection, dict) or not isinstance(selection.get("selected"), list):
        raise BulkError("The selection file is not a selection; run select again.")
    if not selection["selected"]:
        raise BulkError("Nothing was selected, so no run is created; print report --selection instead.")
    repository = selection.get("repository")
    if not valid_repo(repository):
        raise BulkError("The selection names no valid repository; run select again.")
    options = selection.get("options") or {}
    metadata = repo_view(repository, "nameWithOwner,url,defaultBranchRef,viewerPermission")
    repository = metadata["nameWithOwner"]
    user = _login(github().call(["api", "user"]))
    if not user:
        raise BulkError("Could not read the authenticated GitHub login; run gh auth login.")
    default = (metadata.get("defaultBranchRef") or {}).get("name")
    project = assess_issue.local_context(repository)
    checkout = os.path.realpath(project["root"]) if project.get("matching") and project.get("root") else None
    permission = metadata.get("viewerPermission")
    reason = None
    if not checkout:
        reason = ("No verified local checkout of " + repository + "; run issue --bulk from a clone of it "
                  "to enable fixes.")
    elif permission not in PUSH_PERMISSIONS:
        reason = ("You cannot push to " + repository + " (permission " + str(permission or "unknown")
                  + "), so fixes cannot open pull requests from it.")
    elif not isinstance(default, str) or not default:
        reason = "The default branch of " + repository + " is unknown."
    order = [c["number"] for c in selection["selected"]]
    items = {str(c["number"]): new_item(c) for c in selection["selected"]}
    extra = {"fixes_available": reason is None, "fixes_unavailable_reason": reason,
             "default_branch": default, "checkout_root": checkout, "handoff_prs": [], "order": order}
    run_dir = run_state.init(run_state.root(KIND, repository), KIND, repository, user, options, extra, items)
    write_json(os.path.join(run_dir, "selection.json"), selection)
    return {"run_id": os.path.basename(run_dir), "run_dir": run_dir, "selected": len(order),
            "fixes_available": reason is None, "fixes_unavailable_reason": reason}


def load_run(run_dir):
    run_dir = os.path.abspath(run_dir)
    state = run_state.load(run_dir)
    if state.get("kind") != KIND:
        raise BulkError(run_dir + " is not an issue run.")
    return run_dir, state


def item_key(state, number):
    key = str(number)
    if not re.fullmatch(r"[1-9][0-9]{0,9}", key) or key not in state["items"]:
        raise BulkError("Issue #" + key + " is not part of this run.")
    return key


def item_dir(run_dir, key):
    path = os.path.join(run_dir, "items", key)
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def cmd_collect(args):
    run_dir, state = load_run(args.run)
    key = item_key(state, args.number)
    item = state["items"][key]
    if item["phase"] not in ("selected", "collected"):
        raise BulkError("Issue #" + key + " is already " + item["phase"] + "; it is not collected again.")
    try:
        snapshot = assess_issue.collect_issue(state["repository"], int(key))
    except (InboxError, BulkError) as exc:
        reason = "collection failed: " + str(exc)
        run_state.set_item(run_dir, key, phase="assessment_failed", failure=reason)
        return {"number": int(key), "ok": False, "reason": reason}
    snapshot["linked_prs"] = item.get("linked_prs", [])
    write_json(os.path.join(item_dir(run_dir, key), "snapshot.json"), snapshot)
    run_state.set_item(run_dir, key, phase="collected", failure=None)
    return {"number": int(key), "ok": True, "warnings": len(snapshot.get("warnings", []))}


# ---------------------------------------------------------------------------
# render-item
# ---------------------------------------------------------------------------

BOUND = {"files": 3, "lines": 100, "test_lines": 300}
ESTIMATE_FIELDS = ("confirmed", "files", "lines", "test_lines", "note")


def load_labels(state):
    """Recommendation labels: the project's CI mapping when configured, else the bundled defaults."""
    checkout = (state.get("extra") or {}).get("checkout_root")
    project = os.path.join(checkout, ".cc-review", "ci.yml") if checkout else None
    path = project if project and os.path.isfile(project) else str(CORE.parent / "config" / "ci.yml")
    try:
        return ci.load_config(path)["labels"]
    except ci.CIError as exc:
        raise BulkError("Cannot read labels from " + path + ": " + str(exc)) from exc


def check_estimate(value):
    if not isinstance(value, dict):
        raise BulkError("assessment.json needs fix_estimate {confirmed, files, lines, test_lines, note}.")
    if set(value) != set(ESTIMATE_FIELDS):
        raise BulkError("fix_estimate must have exactly confirmed, files, lines, test_lines and note.")
    if type(value["confirmed"]) is not bool:
        raise BulkError("fix_estimate.confirmed must be true or false.")
    for key in ("files", "lines", "test_lines"):
        if type(value[key]) is not int or value[key] < 0:
            raise BulkError("fix_estimate." + key + " must be a non-negative integer.")
    if not isinstance(value["note"], str) or len(value["note"]) > 300:
        raise BulkError("fix_estimate.note must be text of at most 300 characters.")
    return value


def _texts(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for inner in value.values():
            yield from _texts(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _texts(inner)


def fix_eligibility(state, item, recommendation, estimate):
    """(eligible, reason) per FR-013, FR-017 and FR-021."""
    extra = state.get("extra") or {}
    open_prs = [p for p in item.get("linked_prs", []) if p.get("open_non_maintainer")]
    if recommendation != "pursue":
        return False, "The recommendation is not Pursue."
    if not estimate["confirmed"]:
        return False, "The problem is not confirmed in the code, or the change is not clearly bounded."
    if any(estimate[key] > BOUND[key] for key in BOUND):
        return False, ("The estimated change exceeds the small bound ({files} files, {lines} lines, {test_lines} "
                       "test lines; at most 3, 100 and 300).").format(**estimate)
    if open_prs:
        return False, "A linked PR under review (" + ", ".join("#" + str(p["number"]) for p in open_prs) + ")."
    if not extra.get("fixes_available"):
        return False, "Fixes are unavailable: " + str(extra.get("fixes_unavailable_reason") or "unknown reason")
    return True, None


def write_text(path, text):
    run_state.atomic_write(path, text)


def sha256_file(path):
    try:
        with open(path, "rb") as stream:
            return hashlib.sha256(stream.read()).hexdigest()
    except OSError:
        return None


def cmd_render_item(args):
    run_dir, state = load_run(args.run)
    key = item_key(state, args.number)
    item = state["items"][key]
    if item["phase"] not in ("collected", "assessed"):
        raise BulkError("Issue #" + key + " is " + item["phase"] + "; only a collected or assessed issue is rendered.")
    directory = item_dir(run_dir, key)
    data = read_json(os.path.join(directory, "assessment.json"), "assessment")
    if not isinstance(data, dict) or not isinstance(data.get("body"), str):
        raise BulkError("assessment.json needs a body text, an assessment object and a fix_estimate.")
    labels = load_labels(state)
    try:
        assessment.validate(data.get("assessment"), labels)
    except assessment.AssessmentError as exc:
        raise BulkError(str(exc)) from exc
    a = data["assessment"]
    if "fix_estimate" not in data:
        raise BulkError("assessment.json needs fix_estimate {confirmed, files, lines, test_lines, note}.")
    estimate = check_estimate(data["fix_estimate"])
    if a["kind"] == "bug" and estimate["confirmed"] and a["check"]["result"] != "confirmed":
        raise BulkError("fix_estimate.confirmed is true for a bug, so assessment.check.result must be confirmed.")
    text = "\n".join([data["body"], *_texts(a)])
    open_prs = [p for p in item.get("linked_prs", []) if p.get("open_non_maintainer")]
    missing = [p["url"] for p in open_prs if p.get("url") and p["url"] not in text]
    if missing:
        raise BulkError("The reply or assessment must name each open linked pull request with its link: "
                        + ", ".join(missing) + ".")
    body, fixed, _ = assessment.repair(data["body"], a)
    rendered = assessment.render(body, fixed, labels, run_id=state["run_id"])
    path = os.path.join(directory, "rendered.md")
    write_text(path, rendered)
    recommendation = a["recommendation"]
    eligible, reason = fix_eligibility(state, item, recommendation, estimate)
    run_state.set_item(run_dir, key, phase="assessed", failure=None, kind=a["kind"],
                       recommendation=recommendation, label=labels[recommendation], fix_eligible=eligible,
                       fix_ineligible_reason=reason, rendered_sha256=sha256_file(path), decision=None,
                       fix_estimate=estimate)
    return {"number": int(key), "recommendation": recommendation, "label": labels[recommendation],
            "fix_eligible": eligible, "fix_ineligible_reason": reason,
            "linked_open_prs": [p["number"] for p in open_prs]}


# ---------------------------------------------------------------------------
# Loop control: next, fail, decide
# ---------------------------------------------------------------------------

PHASES = ("collect", "assess", "decide", "post", "fix")
OPEN_POST = ("pending", "failed")


def attempted(item, kind, session):
    return session is not None and (item.get("attempt_session") or {}).get(kind) == session


def fix_open(item):
    fix = item.get("fix") or {}
    return not fix.get("pr_url") and not fix.get("abandoned")


def needs(run_dir, item, phase, session, extra=None):
    key = str(item["number"])
    if phase == "collect":
        return item["phase"] == "selected"
    if phase == "assess":
        return item["phase"] == "collected" or (
            item["phase"] == "assessed" and not os.path.isfile(os.path.join(run_dir, "items", key, "rendered.md")))
    if phase == "decide":
        return item["phase"] == "assessed" and item.get("decision") is None
    if phase == "post":
        post = item.get("post") or {}
        return (item["phase"] == "decided" and (post.get("comment") in OPEN_POST or post.get("label") in OPEN_POST)
                and not attempted(item, "post", session))
    decision = item.get("decision") or {}
    if decision.get("action") != "fix":
        return False
    fix = item.get("fix") or {}
    if fix.get("tainted") or (extra or {}).get("git_tainted"):
        return False
    if fix.get("abandoned") or fix.get("pr_url"):
        # A finished fix still needs fix-cleanup when its worktree or branch was created and not removed.
        return fix_owned(fix) and not fix.get("cleaned") and not attempted(item, "fix", session)
    return fix_open(item) and not attempted(item, "fix", session)


def ordered(state):
    order = (state.get("extra") or {}).get("order") or sorted(int(k) for k in state["items"])
    return [state["items"][str(n)] for n in order if str(n) in state["items"]]


def cmd_next(args):
    run_dir, state = load_run(args.run)
    for item in ordered(state):
        if needs(run_dir, item, args.phase, args.session, state.get("extra")):
            result = {"number": item["number"]}
            if args.phase == "assess":
                # A worker finished before an interruption: render its stored assessment instead of reassessing.
                result["stored"] = os.path.isfile(os.path.join(run_dir, "items", str(item["number"]),
                                                               "assessment.json"))
            return result
    return {"number": None}


# ---------------------------------------------------------------------------
# item, guard-begin, guard-end
# ---------------------------------------------------------------------------

def cmd_item(args):
    """One item's decision-relevant fields, so the approval pass never loads the whole run state."""
    run_dir, state = load_run(args.run)
    item = state["items"][item_key(state, args.number)]
    return {key: item.get(key) for key in ("number", "title", "url", "phase", "recommendation", "label",
                                           "fix_eligible", "fix_ineligible_reason", "linked_prs", "decision",
                                           "post", "failure")}


GUARD_SKIP = ("state.json", ".lock", run_state.SESSION_LOCK)


def run_digest(run_dir, key):
    """Canonical digest of what an assessment worker for item key must not change: state.json (without
    updated_at) and every other file of the run, except the item's own directory, the locks and fix worktrees."""
    state = run_state.load(run_dir)
    state.pop("updated_at", None)
    files = {}
    own = os.path.join("items", key)
    for directory, subdirs, names in os.walk(run_dir):
        relative = os.path.relpath(directory, run_dir)
        if relative in (own, "worktrees") or relative.startswith(own + os.sep) or \
                relative.startswith("worktrees" + os.sep):
            subdirs[:] = []
            continue
        subdirs.sort()
        for name in sorted(names):
            path = os.path.normpath(os.path.join(relative, name))
            if path not in GUARD_SKIP:
                files[path] = _file_digest(os.path.join(directory, name))
    canonical = json.dumps({"state": state, "files": files}, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def cmd_guard_begin(args):
    """Digest before an assessment worker runs; the caller keeps it in its own context, out of a worker's reach."""
    run_dir, state = load_run(args.run)
    key = item_key(state, args.number)
    return {"number": int(key), "digest": run_digest(run_dir, key)}


def cmd_guard_end(args):
    """After the worker: anything it changed outside its own item directory stops the run."""
    run_dir, state = load_run(args.run)
    key = item_key(state, args.number)
    if not re.fullmatch(r"[0-9a-f]{64}", args.digest or ""):
        raise UsageError("guard-end needs --digest, the value guard-begin printed.")
    if run_digest(run_dir, key) == args.digest:
        return {"number": int(key), "unchanged": True}
    reason = ("The run state changed while the assessment worker for #" + key + " ran (state.json or files of "
              "other items); the run is stopped. Inspect " + run_dir + ", then start a new run.")
    run_state.update(run_dir, lambda st: st["extra"].update(halted=reason))
    raise BulkError(reason)


def cmd_fail(args):
    run_dir, state = load_run(args.run)
    key = item_key(state, args.number)
    if state["items"][key]["phase"] not in ("selected", "collected", "assessed"):
        raise BulkError("Issue #" + key + " is already " + state["items"][key]["phase"] + ".")
    reason = " ".join(clean_text(args.reason).split())[:500] or "assessment failed"
    run_state.set_item(run_dir, key, phase="assessment_failed", failure=reason, decision=None)
    return {"number": int(key), "phase": "assessment_failed"}


def post_final(post):
    return post.get("comment") not in OPEN_POST and post.get("label") not in OPEN_POST


def settled_phase(item):
    """Phase once posting is final: done unless a chosen fix is still open.

    With an open fix the phase is "posted" when the comment was published, else "fix_pending" (the reply was
    skipped or withheld), so the phase never claims a comment that does not exist.
    """
    decision = item.get("decision") or {}
    if decision.get("action") == "fix" and fix_open(item):
        return "posted" if (item.get("post") or {}).get("comment") == "posted" else "fix_pending"
    return "done"


def cmd_decide(args):
    run_dir, state = load_run(args.run)
    key = item_key(state, args.number)
    item = state["items"][key]
    if item["phase"] != "assessed" or item.get("decision") is not None:
        raise BulkError("Issue #" + key + " is " + item["phase"] + "; only an assessed, undecided issue is decided.")
    path = os.path.join(run_dir, "items", key, "rendered.md")
    if not item.get("rendered_sha256") or sha256_file(path) != item["rendered_sha256"]:
        raise BulkError("rendered.md of #" + key + " does not match its recorded rendering; run render-item again "
                        "and show the new text before deciding.")
    if args.action == "fix" and not item.get("fix_eligible"):
        raise BulkError("Issue #" + key + " is not fix-eligible: " + str(item.get("fix_ineligible_reason")))
    if args.action == "review" and not any(p.get("open_non_maintainer") for p in item.get("linked_prs", [])):
        raise BulkError("Issue #" + key + " has no open non-maintainer linked pull request to review.")
    decision = {"post": args.post, "action": args.action, "rendered_sha256": item["rendered_sha256"]}
    fields = {"decision": decision, "phase": "decided"}
    if args.post == "skip":
        fields["post"] = {"comment": "skipped", "comment_url": None, "label": "none", "reason": None}
        if args.action != "fix":
            fields["phase"] = "done"
    run_state.set_item(run_dir, key, **fields)
    return {"number": int(key), "decision": decision}


# ---------------------------------------------------------------------------
# post
# ---------------------------------------------------------------------------

def gh_run(args):
    """Run gh for a write or a status check; return (exit code, stdout, stderr), never raising on failure."""
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=60, check=False)
    except FileNotFoundError as exc:
        raise BulkError("gh is required; install GitHub CLI and run gh auth login.") from exc
    except subprocess.TimeoutExpired:
        return 124, "", "GitHub request timed out after 60 seconds."
    except OSError as exc:
        return 126, "", "Could not execute gh: " + str(exc)
    return result.returncode, result.stdout, result.stderr


def not_found(code, stdout, stderr):
    if code == 0:
        return False
    if "HTTP 404" in stderr:
        return True
    try:
        return str(json.loads(stdout).get("status")) == "404"
    except (ValueError, AttributeError):
        return False


def recheck(state, key):
    owner, name = state["repository"].split("/")
    data = graphql(RECHECK_QUERY, {"owner": owner, "name": name}, {"number": int(key)})
    node = (data.get("repository") or {}).get("issue")
    if not isinstance(node, dict) or node.get("number") != int(key):
        raise BulkError("Issue #" + key + " could not be read again.")
    return node


def recheck_verdict(state, key, node):
    """("posted", url) when this run's comment exists, ("withheld", reason), or (None, None) to post."""
    marker = assessment.RUN_MARKER.format(state["run_id"])
    user = str(state.get("user") or "").lower()
    for comment in (_connection(node.get("comments")) or {}).get("nodes", []):
        if (isinstance(comment, dict) and marker in (comment.get("body") or "")
                and (_login(comment.get("author")) or "").lower() == user):
            return "posted", comment.get("url")
    if node.get("state") != "OPEN":
        return "withheld", "The issue was closed after selection."
    verdict = classify(node, state["repository"], ignore=own_pr(state, key))
    if verdict["reason"]:
        return "withheld", "The issue no longer qualifies: " + SKIP_DETAILS[verdict["reason"]](verdict) + "."
    return None, None


SKIP_DETAILS = {"already_assessed": lambda v: "it now has a cc-review assessment from another run",
                "maintainer_replied": lambda v: "a maintainer replied after selection",
                "maintainer_pr": lambda v: "a maintainer PR now references it (#" + str(v["pr"]) + ")",
                "history_too_long": lambda v: "its history is now too long to verify"}


def own_pr(state, key):
    """How to recognize this run's own fix PR for the item, or None when the run pushed none."""
    fix = state["items"][key].get("fix") or {}
    if not ((fix.get("steps") or {}).get("pushed") or fix.get("pr_url")):
        return None
    return {"pr_url": fix.get("pr_url"), "branch": fix_branch(key), "repository": state["repository"],
            "user": str(state.get("user") or "").lower()}


def without_own_comment(state, node):
    """The node without this run's own posted comment, which never counts against the issue."""
    marker = assessment.RUN_MARKER.format(state["run_id"])
    user = str(state.get("user") or "").lower()
    comments = _connection(node.get("comments"))
    if comments is None:
        return node
    kept = [c for c in comments["nodes"] if not (isinstance(c, dict) and marker in (c.get("body") or "")
                                                 and (_login(c.get("author")) or "").lower() == user)]
    return dict(node, comments=dict(comments, nodes=kept))


def post_label(state, key, label, directory):
    repository = state["repository"]
    code, out, err = gh_run(["api", "--hostname", "github.com", "repos/" + repository + "/labels/" + quote(label, safe="")])
    if not_found(code, out, err):
        return "missing", "The label " + label + " does not exist in " + repository + "; it was not created."
    if code:
        return "failed", "Label check failed: " + gh_failure(err, "GitHub request failed.")
    request = os.path.join(directory, "label-request.json")
    write_json(request, {"labels": [label]})
    code, out, err = gh_run(["api", "--hostname", "github.com", "repos/" + repository + "/issues/" + key + "/labels",
                             "--method", "POST", "--input", request])
    if code:
        return "failed", "Adding the label failed: " + gh_failure(err, "GitHub request failed.")
    return "applied", None


def cmd_post(args):
    run_dir, state = load_run(args.run)
    key = item_key(state, args.number)
    item = state["items"][key]
    decision = item.get("decision") or {}
    post = dict(item.get("post") or {})
    if decision.get("post") == "post" and post_final(post):
        # Already settled (for example on resume): report the recorded result, never post again.
        return {"number": int(key), "comment": post.get("comment"), "label": post.get("label"),
                "reason": post.get("reason"), "comment_url": post.get("comment_url")}
    if item["phase"] != "decided" or decision.get("post") != "post":
        raise BulkError("Issue #" + key + " has no approved reply waiting to be posted.")
    directory = item_dir(run_dir, key)
    attempts = dict(item.get("attempt_session") or {})
    if args.session:
        attempts["post"] = args.session
        run_state.set_item(run_dir, key, attempt_session=attempts)
    approved = None
    if post.get("comment") in OPEN_POST:
        # Read once: the bytes that are hashed are the bytes that are posted.
        try:
            with open(os.path.join(directory, "rendered.md"), "rb") as stream:
                approved = stream.read()
        except OSError:
            approved = None
        if approved is None or hashlib.sha256(approved).hexdigest() != decision.get("rendered_sha256"):
            raise BulkError("rendered.md of #" + key + " is not the text that was approved; render, show and "
                            "decide again before posting.")
    fields = {}
    if post.get("comment") in OPEN_POST:
        try:
            outcome, detail = recheck_verdict(state, key, recheck(state, key))
        except (BulkError, InboxError) as exc:
            outcome, detail = "failed", "Re-check before posting failed: " + str(exc)
        if outcome == "posted":
            post.update(comment="posted", comment_url=detail, reason=None)
        elif outcome in ("withheld", "failed"):
            post.update(comment=outcome, reason=detail)
            if outcome == "withheld":
                post["label"] = "none"
                current = item.get("fix") or {}
                pushed = (current.get("steps") or {}).get("pushed")
                if decision.get("action") == "fix" and fix_open(item) and not pushed:
                    # A pushed branch keeps its pending PR: the draft PR is the maintainer's checkpoint.
                    fields["fix"] = dict(current, abandoned="Reply withheld: " + detail, pr_url=None, pending=None)
        else:
            request = os.path.join(directory, "comment-request.json")
            write_json(request, {"body": approved.decode("utf-8")})
            code, out, err = gh_run(["api", "--hostname", "github.com",
                                     "repos/" + state["repository"] + "/issues/" + key + "/comments",
                                     "--method", "POST", "--input", request])
            url = None
            if not code:
                try:
                    url = json.loads(out).get("html_url")
                except (ValueError, AttributeError):
                    url = None
            if code:
                post.update(comment="failed", reason="Posting the comment failed: "
                            + gh_failure(err, "GitHub request failed."))
            else:
                post.update(comment="posted", comment_url=url, reason=None)
    if post.get("comment") == "posted" and post.get("label") in OPEN_POST:
        post["label"], post["reason"] = post_label(state, key, item["label"], directory)
    fields["post"] = post
    merged = dict(item, **fields)
    fields["phase"] = settled_phase(merged) if post_final(post) else "decided"
    run_state.set_item(run_dir, key, **fields)
    return {"number": int(key), "comment": post["comment"], "label": post["label"], "reason": post.get("reason"),
            "comment_url": post.get("comment_url")}


# ---------------------------------------------------------------------------
# Fixes: fix-prepare, fix-measure, fix-publish, fix-cleanup
#
# No step runs project code: every git call disables fsmonitor and, where a
# hook could start, gets an empty private core.hooksPath; commits and pushes
# also pass --no-verify, and nothing but git and gh is executed. Git calls in a
# fix worktree name its git directory explicitly, so a worker that rewrites the
# worktree's .git file cannot point git at a configuration it wrote. The
# branch, worktree path and PR title are derived from the issue number, never
# read back from state a worker could have written.
# ---------------------------------------------------------------------------

STEPS = ("prepared", "worker_done", "measured", "committed", "pushed", "pr_opened")
# No fsmonitor and no hooks for any helper git call, including reads such as status (post-index-change).
GIT_SAFETY = ("-c", "core.fsmonitor=false", "-c", "core.hooksPath=" + os.devnull)


@contextmanager
def no_hooks():
    directory = tempfile.mkdtemp(prefix="cc-review-nohooks.")
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def git(cwd, *args, hooks=None, binary=False, timeout=300, git_dir=None):
    command = ["git", *GIT_SAFETY] + (["-c", "core.hooksPath=" + hooks] if hooks else [])
    if git_dir:
        command += ["--git-dir=" + git_dir, "--work-tree=" + cwd]
    command += ["-C", cwd, *args]
    # No credential prompts, and reads such as status never refresh (write) the maintainer's index.
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        return subprocess.run(command, capture_output=True, text=not binary, timeout=timeout, check=False,
                              stdin=subprocess.DEVNULL, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BulkError("git " + args[0] + " failed: " + str(exc)) from exc


def git_out(cwd, *args, hooks=None, git_dir=None):
    result = git(cwd, *args, hooks=hooks, git_dir=git_dir)
    if result.returncode:
        raise BulkError("git " + " ".join(args[:2]) + " failed: " + clean_text(result.stderr).strip()[:300])
    return result.stdout.strip()


def fix_branch(key):
    return "cc-review/fix-issue-" + key


def fix_worktree(run_dir, key):
    return os.path.join(run_dir, "worktrees", key)


def fix_owned(fix):
    """True once the run may have created the fix branch or worktree (so cleanup may remove them)."""
    steps = fix.get("steps") or {}
    return bool(steps.get("prepared") or fix.get("creating"))


def worktree_gitdir(fix):
    """The fix worktree's git directory, verified to be a worktree entry of the recorded common directory."""
    common = os.path.realpath(str(fix.get("common_dir") or ""))
    admin = os.path.realpath(str(fix.get("gitdir") or ""))
    if not fix.get("common_dir") or not fix.get("gitdir") or \
            os.path.dirname(admin) != os.path.join(common, "worktrees"):
        raise BulkError("The fix worktree's git directory is not recorded correctly; the fix cannot continue.")
    return admin


def _file_digest(path):
    try:
        if os.path.islink(path):
            return "link:" + os.readlink(path)
        if os.path.isdir(path):
            return "dir"
        with open(path, "rb") as stream:
            return hashlib.sha256(stream.read()).hexdigest()
    except FileNotFoundError:
        return None
    except OSError as exc:
        return "error:" + type(exc).__name__


def global_git_configs():
    home = os.path.expanduser("~")
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    if os.environ.get("GIT_CONFIG_GLOBAL"):
        return [os.environ["GIT_CONFIG_GLOBAL"]]
    return [os.path.join(home, ".gitconfig"), os.path.join(xdg, "git", "config")]


def run_git_baseline(checkout):
    """Run-level git files of the maintainer's checkout, recorded at the first fix-prepare (before any fix
    worker ran): its .git entry, its own git directory when it is a linked worktree, the common directory's
    configuration, attributes and excludes, and the global configuration."""
    admin = os.path.realpath(git_out(checkout, "rev-parse", "--absolute-git-dir"))
    common = os.path.realpath(os.path.join(checkout, git_out(checkout, "rev-parse", "--git-common-dir")))
    paths = [os.path.join(checkout, ".git")]
    paths += [os.path.join(common, name) for name in ("config", "config.worktree", os.path.join("info", "attributes"),
                                                      os.path.join("info", "exclude"))]
    if admin != common:
        paths += [os.path.join(admin, name) for name in ("commondir", "gitdir", "config.worktree")]
    return {path: _file_digest(path) for path in paths + global_git_configs()}


def run_guard(run_dir, state):
    """The reason no git command may run in this run any more, or None. Checked without running git.

    Once any recorded git file of the checkout changed, every later fix step of the run refuses git, so a
    configuration planted by one fix worker can never run during another fix, a cleanup or abandon-run.
    """
    extra = state.get("extra") or {}
    if extra.get("git_tainted"):
        return extra["git_tainted"]
    baseline = extra.get("git_baseline") or {}
    changed = sorted(path for path in baseline if _file_digest(path) != baseline[path])
    if not changed:
        return None
    reason = ("Git configuration or metadata of the checkout changed during the fix pass (" + ", ".join(changed)
              + "); no further git command is run for this run. Inspect these files before using git in this "
              "checkout.")
    run_state.update(run_dir, lambda st: st["extra"].update(git_tainted=reason))
    return reason


def taint(run_dir, key, fix, reason):
    """Abandon a fix because git files changed: no git command runs for it again (cleanup is manual)."""
    fix["tainted"] = True
    if not fix.get("pr_url"):
        abandon(run_dir, key, fix, reason)
    else:
        run_state.set_item(run_dir, key, fix=fix)
    return reason


def git_metadata(fix, worktree):
    """Digests of git files that could make a later git call run code, read without running git.

    Covers the repository and worktree configuration, attributes and excludes, the worktree's own
    git directory, its .git file, and the user's global git configuration.
    """
    common = os.path.realpath(str(fix.get("common_dir") or ""))
    admin = os.path.realpath(str(fix.get("gitdir") or ""))
    paths = [os.path.join(common, name) for name in ("config", "config.worktree", "commondir",
                                                     os.path.join("info", "attributes"),
                                                     os.path.join("info", "exclude"))]
    paths += [os.path.join(admin, name) for name in ("HEAD", "commondir", "gitdir", "config.worktree")]
    paths += [os.path.join(worktree, ".git")] + global_git_configs()
    return {path: _file_digest(path) for path in paths}


def state_digest(state, key):
    """sha256 of the run state without the run's updated_at and this item's fix snapshot."""
    copy = json.loads(json.dumps(state))
    copy.pop("updated_at", None)
    fix = copy["items"][key].get("fix")
    if isinstance(fix, dict):
        fix.pop("snapshot", None)
    return hashlib.sha256(json.dumps(copy, sort_keys=True).encode()).hexdigest()


def _status_paths(checkout, raw):
    """Each listed path with its status code and content digest, so edits to already dirty files show."""
    paths = {}
    entries, index = raw.split(b"\0"), 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) > 3:
            name = os.fsdecode(entry[3:])
            paths[name] = os.fsdecode(entry[:2]) + " " + str(_file_digest(os.path.join(checkout, name)))
            if entry[:1] in (b"R", b"C") or entry[1:2] in (b"R", b"C"):
                index += 1  # a rename or copy is followed by its original path
    return paths


def describe_changes(now, recorded, skip=()):
    """Short neutral description of what changed between two snapshots, naming up to five changed paths."""
    parts = []
    for name in sorted(now):
        if name in skip or name in ("status_paths", "git_metadata") or now[name] == recorded.get(name):
            continue
        label = name.replace("_sha256", "")
        if name == "status_sha256":
            old, new = recorded.get("status_paths") or {}, now.get("status_paths") or {}
            changed = sorted(path for path in set(old) | set(new) if old.get(path) != new.get(path))
            if changed:
                label += ": " + ", ".join(changed[:5]) + (" and " + str(len(changed) - 5) + " more"
                                                           if len(changed) > 5 else "")
        parts.append(label)
    return "; ".join(parts)


CHANGED_DURING_FIX = ("The checkout changed during the fix ({}). A change by you or by the fix worker stops the "
                      "fix, so nothing was published; avoid editing the checkout while fixes run.")


def checkout_snapshot(checkout, key, state, fix, worktree):
    """What a fix worker must never change: the maintainer's HEAD, index, working tree (status and the content
    of dirty files), branches, git configuration and metadata, and the run state."""
    def digest(*args):
        result = git(checkout, *args, binary=True)
        if result.returncode:
            raise BulkError("git " + args[0] + " failed in the checkout.")
        return result.stdout
    # Fix branches this run creates come and go with their fixes; every other local branch must stay.
    own = {"refs/heads/" + fix_branch(k) for k, i in state["items"].items() if i.get("fix")} | \
          {"refs/heads/" + fix_branch(key)}
    head = git(checkout, "rev-parse", "--verify", "--quiet", "HEAD")
    refs = git_out(checkout, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads")
    refs = "\n".join(line for line in refs.splitlines() if line.split(" ")[0] not in own)
    metadata = json.dumps(git_metadata(fix, worktree), sort_keys=True).encode()
    status = _status_paths(checkout, digest("status", "--porcelain", "-z", "--untracked-files=all"))
    return {"head": head.stdout.strip() if not head.returncode else None,
            "index_sha256": hashlib.sha256(digest("ls-files", "--stage", "-z")).hexdigest(),
            "status_sha256": hashlib.sha256(json.dumps(status, sort_keys=True).encode()).hexdigest(),
            "status_paths": status,
            "branches_sha256": hashlib.sha256(refs.encode()).hexdigest(),
            "git_sha256": hashlib.sha256(metadata).hexdigest(),
            "state_sha256": state_digest(state, key)}


def metadata_changed(fix, worktree):
    """Names of git files changed since prepare, checked without running git (empty when unchanged)."""
    recorded = (fix.get("snapshot") or {}).get("git_metadata") or {}
    now = git_metadata(fix, worktree)
    return sorted(path for path in set(now) | set(recorded) if now.get(path) != recorded.get(path))


def new_fix(branch, key):
    return {"branch": branch, "worktree": "worktrees/" + key, "base": None, "snapshot": None,
            "steps": dict.fromkeys(STEPS, False), "size": None, "tree": None, "commit": None,
            "summary": None, "pr_url": None, "pending": None, "abandoned": None}


def fix_context(args, need_prepared=True):
    run_dir, state = load_run(args.run)
    key = item_key(state, args.number)
    item = state["items"][key]
    if (item.get("decision") or {}).get("action") != "fix":
        raise BulkError("Issue #" + key + " has no fix chosen.")
    extra = state.get("extra") or {}
    if not extra.get("fixes_available") or not extra.get("checkout_root") or not extra.get("default_branch"):
        raise BulkError("Fixes are unavailable in this run: " + str(extra.get("fixes_unavailable_reason")))
    fix = item.get("fix") or {}
    if need_prepared and not (fix.get("steps") or {}).get("prepared") and not fix.get("abandoned"):
        raise BulkError("The fix for #" + key + " was not prepared; run fix-prepare first.")
    return run_dir, state, key, item, extra, dict(fix)


def abandon(run_dir, key, fix, reason):
    fix["abandoned"] = reason
    fix["pending"] = None
    run_state.set_item(run_dir, key, fix=fix)
    return reason


def record_attempt(run_dir, key, item, session):
    if session:
        run_state.set_item(run_dir, key, attempt_session=dict(item.get("attempt_session") or {}, fix=session))


def fail_step(run_dir, key, step, exc):
    """A fix step raised: record it so the fix ends as abandoned (or a pending PR), never silently open."""
    state = run_state.load(run_dir)
    fix = dict(state["items"][key].get("fix") or new_fix(fix_branch(key), key))
    reason = step + " failed: " + " ".join(clean_text(str(exc)).split())[:300]
    if fix.get("abandoned") or fix.get("pr_url"):
        raise BulkError(reason) from exc
    if (fix.get("steps") or {}).get("pushed"):
        fix.update(pending="pr", pr_error=reason)
        run_state.set_item(run_dir, key, fix=fix)
    else:
        abandon(run_dir, key, fix, reason)
    return fix


def fix_recheck(state, key):
    """Why a new fix must not start (closed, no longer qualifying, or a contributor PR appeared), or None."""
    node = without_own_comment(state, recheck(state, key))
    if node.get("state") != "OPEN":
        return "The issue was closed after selection; the fix was not started."
    verdict = classify(node, state["repository"], ignore=own_pr(state, key))
    if verdict["reason"]:
        return ("The issue no longer qualifies: " + SKIP_DETAILS[verdict["reason"]](verdict)
                + "; the fix was not started.")
    contributors = [p["number"] for p in verdict["linked_prs"] if p.get("open_non_maintainer")]
    if contributors:
        return ("A contributor pull request now references the issue (" + ", ".join("#" + str(n) for n in contributors)
                + "); the fix was not started, so it does not duplicate that work.")
    return None


def prepare_result(key, worktree, worker_needed):
    return {"number": int(key), "worktree": worktree, "branch": fix_branch(key), "worker_needed": worker_needed}


def cmd_fix_prepare(args):
    run_dir, state, key, item, extra, fix = fix_context(args, need_prepared=False)
    record_attempt(run_dir, key, item, args.session)
    tainted = run_guard(run_dir, state)
    if tainted and not fix.get("abandoned"):
        return {"number": int(key), "abandoned": taint(run_dir, key, fix or new_fix(fix_branch(key), key), tainted)}
    try:
        return _fix_prepare(run_dir, state, key, extra, fix)
    except (BulkError, OSError) as exc:
        fix = fail_step(run_dir, key, "Preparing the fix", exc)
        return {"number": int(key), "abandoned": fix.get("abandoned")} if fix.get("abandoned") else \
            prepare_result(key, fix_worktree(run_dir, key), False)


def _fix_prepare(run_dir, state, key, extra, fix):
    if fix.get("abandoned"):
        return {"number": int(key), "abandoned": fix["abandoned"]}
    branch, worktree = fix_branch(key), fix_worktree(run_dir, key)
    steps = fix.get("steps") or {}
    result_file = os.path.join(run_dir, "items", key, "fix.json")
    if fix.get("pr_url") or steps.get("pushed") or steps.get("measured"):
        # The worker phase is over: measure, publish and cleanup continue from the recorded steps.
        return prepare_result(key, worktree, False)
    gitfile = os.path.join(worktree, ".git")
    if steps.get("prepared"):
        # Checked first and without git, whether or not the worktree still looks intact.
        changed = metadata_changed(fix, worktree)
        if changed:
            reason = taint(run_dir, key, fix, "Git configuration or metadata changed while the fix was in "
                           "progress (" + ", ".join(changed) + "); no git command was run. Inspect these "
                           "files before using git in this checkout.")
            return {"number": int(key), "abandoned": reason}
        if not os.path.isfile(gitfile):
            reason = abandon(run_dir, key, fix, "The fix worktree " + worktree + " disappeared before the fix "
                             "was measured.")
            return {"number": int(key), "abandoned": reason}
        # A resumed run dispatches a new worker. Other items' state legitimately changed since the first
        # snapshot, so only the run-state digest is refreshed; the checkout must still match.
        state = run_state.load(run_dir)
        now = checkout_snapshot(extra["checkout_root"], key, state, fix, worktree)
        old = fix.get("snapshot") or {}
        changed = describe_changes(now, old, skip=("state_sha256",))
        if changed:
            reason = abandon(run_dir, key, fix, CHANGED_DURING_FIX.format(changed))
            return {"number": int(key), "abandoned": reason}
        fix["snapshot"] = dict(old, state_sha256=now["state_sha256"])
        run_state.set_item(run_dir, key, fix=fix)
        return prepare_result(key, worktree, not os.path.isfile(result_file))
    checkout, default = extra["checkout_root"], extra["default_branch"]
    # Interrupted after git created the worktree but before it was recorded: both are this run's own. Without
    # the worktree, an existing branch is never assumed to be ours; the conflict checks below decide.
    own_worktree = fix.get("branch") == branch and fix.get("creating") and os.path.isfile(gitfile)
    fix = dict(new_fix(branch, key), **fix) if own_worktree else new_fix(branch, key)
    if not own_worktree:
        # The issue may have changed since the assessment: re-classify it before any git work.
        reason = fix_recheck(state, key)
        if reason:
            return {"number": int(key), "abandoned": abandon(run_dir, key, fix, reason)}
    if not extra.get("git_baseline"):
        # The first fix of the run, before any fix worker ran: record the git files every later step checks.
        baseline = run_git_baseline(checkout)
        run_state.update(run_dir, lambda st: st["extra"].update(git_baseline=baseline))
    with no_hooks() as hooks:
        fetched = git(checkout, "fetch", "--quiet", "origin", default, hooks=hooks)
        if fetched.returncode:
            reason = "Fetching origin/" + default + " failed: " + clean_text(fetched.stderr).strip()[:300]
            return {"number": int(key), "abandoned": abandon(run_dir, key, fix, reason)}
        local = not git(checkout, "rev-parse", "--verify", "--quiet", "refs/heads/" + branch).returncode
        if own_worktree:
            add = None
        else:
            remote = git(checkout, "ls-remote", "--heads", "origin", "refs/heads/" + branch, hooks=hooks)
            if remote.returncode:
                reason = "Checking origin for " + branch + " failed: " + clean_text(remote.stderr).strip()[:300]
                return {"number": int(key), "abandoned": abandon(run_dir, key, fix, reason)}
            if local or remote.stdout.strip():
                where = "locally" if local else "on origin"
                reason = ("Branch conflict: " + branch + " already exists " + where
                          + " and is not recorded by this run; it was left untouched.")
                return {"number": int(key), "abandoned": abandon(run_dir, key, fix, reason)}
            add = ["worktree", "add", "--no-track", "-b", branch, worktree, "origin/" + default]
        # Record ownership before git creates anything, so an interruption never orphans the branch. The branch
        # is created with --no-track, so no fix ever writes the repository configuration the snapshot guards.
        fix["creating"] = True
        run_state.set_item(run_dir, key, fix=fix)
        if add:
            os.makedirs(os.path.dirname(worktree), mode=0o700, exist_ok=True)
            added = git(checkout, *add, hooks=hooks)
            if added.returncode:
                # Keep the claim only for a branch this call created (absent before, present now); never claim a
                # branch someone else created meanwhile, so cleanup cannot delete it.
                exists = not git(checkout, "rev-parse", "--verify", "--quiet", "refs/heads/" + branch).returncode
                if local or not exists:
                    fix.pop("creating", None)
                reason = "Creating the fix worktree failed: " + clean_text(added.stderr).strip()[:300]
                return {"number": int(key), "abandoned": abandon(run_dir, key, fix, reason)}
    # The worker has not run yet, so the worktree's git directory is still the one git created.
    fix["gitdir"] = os.path.realpath(git_out(worktree, "rev-parse", "--absolute-git-dir"))
    fix["common_dir"] = os.path.realpath(os.path.join(worktree, git_out(worktree, "rev-parse", "--git-common-dir")))
    admin = worktree_gitdir(fix)
    fix["base"] = fix.get("base") or git_out(worktree, "rev-parse", "HEAD", git_dir=admin)
    fix["steps"] = dict(fix.get("steps") or {}, prepared=True)
    fix.pop("creating", None)
    state = run_state.load(run_dir)
    state["items"][key]["fix"] = fix
    snapshot = checkout_snapshot(checkout, key, state, fix, worktree)
    fix["snapshot"] = dict(snapshot, git_metadata=git_metadata(fix, worktree))
    run_state.set_item(run_dir, key, fix=fix)
    return prepare_result(key, worktree, not os.path.isfile(result_file))


TEST_DIRS = ("test", "tests", "spec", "__tests__")
TEST_NAMES = ("*_test.*", "test_*.*", "*.test.*", "*.spec.*")


def is_test_path(path):
    parts = path.split("/")
    return (any(part in TEST_DIRS for part in parts[:-1])
            or any(fnmatch.fnmatchcase(parts[-1], pattern) for pattern in TEST_NAMES))


def measure_size(worktree, admin, base, hooks):
    added = git(worktree, "add", "-A", hooks=hooks, git_dir=admin)
    if added.returncode:
        raise BulkError("Staging the fix failed: " + clean_text(added.stderr).strip()[:300])
    diff = git(worktree, "diff", "--cached", "--numstat", "--no-renames", "--no-ext-diff", "--no-textconv",
               "-z", base, hooks=hooks, git_dir=admin)
    if diff.returncode:
        raise BulkError("Measuring the fix failed: " + clean_text(diff.stderr).strip()[:300])
    size = {"files": 0, "lines": 0, "test_lines": 0}
    changed, binary = 0, []
    for entry in diff.stdout.split("\0"):
        if not entry.strip():
            continue
        plus, minus, path = entry.split("\t", 2)
        changed += 1
        if plus == "-" or minus == "-":
            binary.append(path)
        elif is_test_path(path):
            size["test_lines"] += int(plus) + int(minus)
        else:
            size["files"] += 1
            size["lines"] += int(plus) + int(minus)
    return size, changed, binary


def read_fix_result(path):
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return None
    if (not isinstance(data, dict) or data.get("status") not in ("done", "gave_up")
            or not isinstance(data.get("summary", ""), str) or not isinstance(data.get("reason", ""), str)):
        return None
    return data


def cmd_fix_measure(args):
    run_dir, state, key, item, extra, fix = fix_context(args)
    tainted = run_guard(run_dir, state)
    if tainted and not fix.get("abandoned") and not fix["steps"].get("measured"):
        return {"number": int(key), "within_bound": False, "size": None, "reason": taint(run_dir, key, fix, tainted)}
    try:
        return _fix_measure(run_dir, state, key, extra, fix)
    except (BulkError, OSError) as exc:
        fix = fail_step(run_dir, key, "Measuring the fix", exc)
        return {"number": int(key), "within_bound": False, "size": fix.get("size"), "reason": fix.get("abandoned")}


def _fix_measure(run_dir, state, key, extra, fix):
    size = fix.get("size")
    if fix.get("abandoned"):
        return {"number": int(key), "within_bound": False, "size": size, "reason": fix["abandoned"]}
    if fix["steps"].get("measured"):
        return {"number": int(key), "within_bound": True, "size": size, "reason": None}
    worktree = fix_worktree(run_dir, key)
    # Checked first and without git: a planted configuration would run with the next git command.
    changed = metadata_changed(fix, worktree)
    if changed:
        reason = taint(run_dir, key, fix, "Git configuration or metadata changed during the fix ("
                       + ", ".join(changed) + "); no git command was run. Inspect these files before using git "
                       "in this checkout.")
        return {"number": int(key), "within_bound": False, "size": None, "reason": reason}
    result = read_fix_result(os.path.join(run_dir, "items", key, "fix.json"))
    if result is None:
        reason = abandon(run_dir, key, fix, "The fix worker wrote no valid fix.json.")
        return {"number": int(key), "within_bound": False, "size": None, "reason": reason}
    summary = " ".join(clean_text(result.get("summary") or "").split())
    if result["status"] == "gave_up":
        fix["steps"] = dict(fix["steps"], worker_done=True)
        fix["summary"] = summary
        why = " ".join(clean_text(result.get("reason") or "no reason given").split())[:300]
        reason = abandon(run_dir, key, fix, "The fix worker gave up: " + why)
        return {"number": int(key), "within_bound": False, "size": None, "reason": reason}
    now = checkout_snapshot(extra["checkout_root"], key, state, fix, worktree)
    changed = describe_changes(now, fix.get("snapshot") or {})
    if changed:
        reason = abandon(run_dir, key, fix, CHANGED_DURING_FIX.format(changed))
        return {"number": int(key), "within_bound": False, "size": None, "reason": reason}
    fix["steps"] = dict(fix["steps"], worker_done=True)
    fix["summary"] = summary
    admin = worktree_gitdir(fix)
    if git_out(worktree, "rev-parse", "HEAD", git_dir=admin) != fix.get("base"):
        # The worker may only edit files: a commit or a moved branch ref is never published.
        reason = abandon(run_dir, key, fix, "The fix branch no longer points at its base commit; the fix worker "
                         "must not commit or move branches.")
        return {"number": int(key), "within_bound": False, "size": None, "reason": reason}
    with no_hooks() as hooks:
        size, changed_files, binary = measure_size(worktree, admin, fix["base"], hooks)
        fix["size"] = size
        if not changed_files:
            reason = abandon(run_dir, key, fix, "The fix worker produced no change.")
            return {"number": int(key), "within_bound": False, "size": size, "reason": reason}
        if binary:
            reason = abandon(run_dir, key, fix, "Binary change: the fix changes " + ", ".join(sorted(binary)[:5])
                             + "; a fix with a binary file is never published.")
            return {"number": int(key), "within_bound": False, "size": size, "reason": reason}
        if any(size[name] > BOUND[name] for name in BOUND):
            reason = abandon(run_dir, key, fix, ("The change exceeds the small bound ({files} non-test files, "
                                                 "{lines} lines, {test_lines} test lines; at most 3, 100 and "
                                                 "300).").format(**size))
            return {"number": int(key), "within_bound": False, "size": size, "reason": reason}
        fix["tree"] = git_out(worktree, "write-tree", hooks=hooks, git_dir=admin)
    fix["steps"] = dict(fix["steps"], measured=True)
    run_state.set_item(run_dir, key, fix=fix)
    return {"number": int(key), "within_bound": True, "size": size, "reason": None}


SUMMARY_LIMIT = 1500
TITLE_LIMIT = 72
CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b(?=\s*:?\s*(?:#[0-9]|[\w.-]+/[\w.-]+#[0-9]"
                     r"|https?://github\.com/[\w.-]+/[\w.-]+/issues/[0-9]))", re.I)
TESTS_NOTE = "Tests were not run locally; the repository's checks on this pull request run them."
COMMIT_TYPES = {"bug": "fix", "feature": "feat"}
def sanitize_summary(text):
    # The summary is 1 to 3 sentences of model text: no code-span exception, so no escaping trick (unbalanced or
    # backslash-escaped backticks) can carry a closing keyword, a mention or HTML into the PR body.
    text = " ".join(clean_text(text or "").split())
    text = CLOSING.sub("see", text)
    text = text.replace("@", "&#64;").replace("<", "&lt;").replace(">", "&gt;")
    if len(text) > SUMMARY_LIMIT:
        text = text[:SUMMARY_LIMIT - 3].rstrip() + "..."
    return text


def commit_subject(item, key):
    # Plain text (a commit message closes issues when it reaches the default branch): no code-span exception.
    title = CLOSING.sub("see", " ".join(clean_text(item.get("title") or "").split()))
    title = title[:TITLE_LIMIT].rstrip() or "issue " + key
    return COMMIT_TYPES.get(item.get("kind"), "chore") + ": " + title + " (#" + key + ")"


def pr_body(fix, key):
    summary = sanitize_summary(fix.get("summary") or "")
    parts = ([summary] if summary else []) + ["Fixes #" + key, TESTS_NOTE]
    return "\n\n".join(parts) + "\n"


def open_pr_for(repository, branch):
    """URL of an open PR for the branch, None when there is none; raises on a failed lookup."""
    code, out, err = gh_run(["pr", "list", "--repo", repository, "--head", branch, "--state", "open",
                             "--json", "url"])
    if code:
        raise BulkError("Looking up open pull requests failed: " + gh_failure(err, "GitHub request failed."))
    try:
        listed = json.loads(out or "[]")
    except ValueError as exc:
        raise BulkError("gh pr list returned invalid JSON.") from exc
    urls = [entry.get("url") for entry in listed if isinstance(entry, dict) and isinstance(entry.get("url"), str)]
    return urls[0] if urls else None


GITHUB_URL = re.compile(r"(?:git@github\.com:|ssh://git@github\.com/|https://github\.com/)([^/]+/[^/]+?)(?:\.git)?/?")


def github_url_of(url, repository):
    match = GITHUB_URL.fullmatch(url)
    return bool(match) and match[1].lower() == repository.lower()


def publish_result(key, fix):
    return {"number": int(key), "pr_url": fix.get("pr_url"), "pending": fix.get("pending"),
            "abandoned": fix.get("abandoned")}


def cmd_fix_publish(args):
    run_dir, state, key, item, extra, fix = fix_context(args)
    if fix.get("abandoned") or (fix.get("steps") or {}).get("pr_opened"):
        return publish_result(key, fix)
    if not fix["steps"].get("measured"):
        raise BulkError("The fix for #" + key + " was not measured; run fix-measure first.")
    record_attempt(run_dir, key, item, args.session)
    tainted = run_guard(run_dir, state)
    if tainted:
        taint(run_dir, key, fix, tainted)
        return publish_result(key, fix)
    try:
        return _fix_publish(run_dir, state, key, item, extra, fix)
    except (BulkError, OSError) as exc:
        return publish_result(key, fail_step(run_dir, key, "Publishing the fix", exc))


def _fix_publish(run_dir, state, key, item, extra, fix):
    branch, worktree = fix_branch(key), fix_worktree(run_dir, key)
    subject = commit_subject(item, key)
    with no_hooks() as hooks:
        if not fix["steps"].get("committed"):
            changed = metadata_changed(fix, worktree)
            if changed:
                taint(run_dir, key, fix, "Git configuration or metadata of the fix worktree changed after measuring ("
                      + ", ".join(changed) + "); nothing was committed and no git command was run.")
                return publish_result(key, fix)
            admin = worktree_gitdir(fix)
            head = git_out(worktree, "rev-parse", "HEAD", git_dir=admin)
            adopt = False
            if head != fix.get("base"):
                # Only the helper's own commit, made just before an interruption, is adopted: one parent (the
                # base), the measured tree and the helper's message. Anything else is never published.
                parents = git_out(worktree, "rev-list", "--parents", "-n", "1", "HEAD", git_dir=admin).split()
                adopt = (parents[1:] == [fix.get("base")]
                         and git_out(worktree, "rev-parse", "HEAD^{tree}", git_dir=admin) == fix.get("tree")
                         and git_out(worktree, "log", "-1", "--format=%B", git_dir=admin).strip() == subject)
                if not adopt:
                    abandon(run_dir, key, fix, "The fix branch moved after measuring; nothing was published.")
                    return publish_result(key, fix)
            if adopt:
                fix.update(commit=head, subject=subject)
            else:
                if git(worktree, "write-tree", hooks=hooks, git_dir=admin).stdout.strip() != fix.get("tree"):
                    abandon(run_dir, key, fix, "The worktree changed after measuring; nothing was committed.")
                    return publish_result(key, fix)
                committed = git(worktree, "commit", "--no-verify", "--quiet", "-m", subject, hooks=hooks,
                                git_dir=admin)
                if committed.returncode:
                    abandon(run_dir, key, fix, "Commit failed: "
                            + clean_text(committed.stderr or committed.stdout).strip()[:300])
                    return publish_result(key, fix)
                fix.update(commit=git_out(worktree, "rev-parse", "HEAD", git_dir=admin), subject=subject)
            fix["steps"] = dict(fix["steps"], committed=True)
            run_state.set_item(run_dir, key, fix=fix)
        if not fix["steps"].get("pushed"):
            # The recorded commit is pushed, never whatever the branch points at now. A push that failed or timed
            # out may still have reached origin: compare the remote branch with the commit before giving up.
            checkout = extra["checkout_root"]
            # The checkout was verified by its fetch URL; a push URL elsewhere would publish the branch there.
            fetch_url = git_out(checkout, "remote", "get-url", "origin")
            wrong = [url for url in git_out(checkout, "remote", "get-url", "--push", "--all", "origin").splitlines()
                     if url.strip() and url.strip() != fetch_url and not github_url_of(url.strip(), state["repository"])]
            if wrong:
                abandon(run_dir, key, fix, "origin pushes to " + wrong[0] + ", not to " + state["repository"]
                        + "; nothing was pushed. Correct the push URL, then choose the fix again.")
                return publish_result(key, fix)
            try:
                pushed = git(checkout, "push", "--no-verify", "--quiet", "origin",
                             fix["commit"] + ":refs/heads/" + branch, hooks=hooks)
                failure = clean_text(pushed.stderr).strip()[:300] if pushed.returncode else None
            except BulkError as exc:
                failure = str(exc)[:300]
            if failure is not None:
                remote = git(checkout, "ls-remote", "--heads", "origin", "refs/heads/" + branch, hooks=hooks)
                if remote.returncode or remote.stdout.split()[:1] != [fix["commit"]]:
                    # Not confirmed on origin: the fix stays open with a pending push; resume pushes the recorded
                    # commit again (idempotent when the earlier push did arrive).
                    fix["pending"] = "push"
                    fix["pr_error"] = ("Push not confirmed: " if remote.returncode else "Push failed: ") + failure
                    run_state.set_item(run_dir, key, fix=fix)
                    return publish_result(key, fix)
            fix["steps"] = dict(fix["steps"], pushed=True)
            fix["pending"] = "pr"
            run_state.set_item(run_dir, key, fix=fix)
    body = os.path.join(item_dir(run_dir, key), "pr-body.md")
    write_text(body, pr_body(fix, key))
    repository = state["repository"]
    try:
        url = open_pr_for(repository, branch)
        if url is None:
            code, out, err = gh_run(["pr", "create", "--repo", repository, "--draft",
                                     "--base", extra["default_branch"], "--head", branch,
                                     "--title", subject, "--body-file", body])
            lines = [line.strip() for line in out.splitlines() if line.strip()]
            if code or not lines or not lines[-1].startswith("https://github.com/" + repository + "/pull/"):
                raise BulkError("Opening the draft pull request failed: " + gh_failure(err, "no PR URL returned."))
            url = lines[-1]
    except BulkError as exc:
        fix["pending"] = "pr"
        fix["pr_error"] = str(exc)
        run_state.set_item(run_dir, key, fix=fix)
        return publish_result(key, fix)
    fix.update(pr_url=url, pending=None, pr_error=None)
    fix["steps"] = dict(fix["steps"], pr_opened=True)
    run_state.set_item(run_dir, key, fix=fix)
    return publish_result(key, fix)


def remove_fix_checkout(run_dir, key, checkout):
    """Remove the fix worktree and the local fix branch; the pushed branch stays on origin."""
    worktree, branch = fix_worktree(run_dir, key), fix_branch(key)
    with no_hooks() as hooks:
        if os.path.exists(worktree):
            removed = git(checkout, "worktree", "remove", "--force", worktree, hooks=hooks)
            if removed.returncode:
                raise BulkError("Removing the fix worktree failed: " + clean_text(removed.stderr).strip()[:300])
        git(checkout, "worktree", "prune", hooks=hooks)
        if not git(checkout, "rev-parse", "--verify", "--quiet", "refs/heads/" + branch).returncode:
            deleted = git(checkout, "branch", "-D", branch, hooks=hooks)
            if deleted.returncode:
                raise BulkError("Deleting the local fix branch failed: " + clean_text(deleted.stderr).strip()[:300])


def cmd_fix_cleanup(args):
    run_dir, state, key, item, extra, fix = fix_context(args, need_prepared=False)
    record_attempt(run_dir, key, item, args.session)
    tainted = run_guard(run_dir, state)
    if tainted and fix_owned(fix) and not fix.get("cleaned"):
        fix["tainted"] = True
        run_state.set_item(run_dir, key, fix=fix)
    if fix.get("tainted"):
        return {"number": int(key), "cleaned": False,
                "reason": "Git configuration or metadata changed during the fix; no git command is run. Inspect "
                          "the checkout, then remove " + fix_worktree(run_dir, key) + " and the branch "
                          + fix_branch(key) + " yourself."}
    if fix_owned(fix) and not fix.get("cleaned"):
        # A pushed branch needs neither the worktree nor the local branch to get its pull request opened.
        remove_fix_checkout(run_dir, key, extra["checkout_root"])
    fix["cleaned"] = True
    fields = {"fix": fix}
    if post_final(item.get("post") or {}):
        fields["phase"] = settled_phase(dict(item, fix=fix))
    run_state.set_item(run_dir, key, **fields)
    return {"number": int(key), "cleaned": True}


def cmd_abandon_run(args):
    """Mark a run abandoned after removing its fix worktrees and local fix branches."""
    run_dir, state = load_run(args.run)
    checkout = (state.get("extra") or {}).get("checkout_root")
    if checkout and run_guard(run_dir, state):
        checkout = None  # git files changed: run no git; the leftovers are listed for manual cleanup
    cleaned, failed, pushed = [], [], []
    for item in ordered(state):
        key, fix = str(item["number"]), dict(item.get("fix") or {})
        if fix_owned(fix) and not fix.get("cleaned"):
            # A worktree already removed by an earlier, partial cleanup is expected to be gone.
            if ((fix.get("snapshot") or {}).get("git_metadata") and os.path.isdir(fix_worktree(run_dir, key))
                    and metadata_changed(fix, fix_worktree(run_dir, key))):
                fix["tainted"] = True
                run_state.set_item(run_dir, key, fix=fix)
                checkout = None  # a worker changed git files: run no git for any item
            if fix.get("tainted") or not checkout:
                failed.append({"number": item["number"], "reason": "git metadata changed; inspect it by hand"})
            else:
                try:
                    remove_fix_checkout(run_dir, key, checkout)
                    fix["cleaned"] = True
                    run_state.set_item(run_dir, key, fix=fix)
                    cleaned.append(item["number"])
                except BulkError as exc:
                    failed.append({"number": item["number"], "reason": str(exc)})
        if (fix.get("steps") or {}).get("pushed") and not fix.get("pr_url"):
            pushed.append(fix_branch(key))
    run_state.set_status(run_dir, "abandoned")
    return {"run_id": state["run_id"], "status": "abandoned", "cleaned": cleaned, "cleanup_failed": failed,
            "pushed_without_pr": pushed}


# ---------------------------------------------------------------------------
# record-handoff and report
# ---------------------------------------------------------------------------

def _issue_link(entry):
    return "[#" + str(entry["number"]) + "](" + str(entry.get("url") or "") + ")"


def coverage(selection):
    options = selection.get("options") or {}
    counts = {}
    for entry in selection.get("skipped", []):
        counts[entry["reason"]] = counts.get(entry["reason"], 0) + 1
    by_reason = ", ".join(SKIP_LABELS[r] + " " + str(counts[r]) for r in SKIP_REASONS if r in counts)
    lines = ["### Coverage", "",
             "- Search: `" + str(selection.get("query", "")).replace("`", "'") + "`",
             "- Scanned: " + str(selection.get("scanned", 0)) + " candidates",
             "- Selected: " + str(len(selection.get("selected", []))),
             "- Skipped: " + str(len(selection.get("skipped", []))) + (" (" + by_reason + ")" if by_reason else "")]
    if selection.get("ceiling_reached"):
        lines.append("- The scan ceiling of " + str(options.get("scan", "?")) + " candidates was reached before the "
                     "batch was full, so this is not a verified empty queue; raise --scan to look further.")
    if selection.get("skipped"):
        lines += ["", "Skipped issues:", ""]
        for entry in selection["skipped"]:
            reason = SKIP_LABELS.get(entry["reason"], entry["reason"])
            if entry["reason"] == "maintainer_pr" and entry.get("pr"):
                reason += " #" + str(entry["pr"])
            lines.append("- " + _issue_link(entry) + " " + assessment._flat(entry.get("title", "")) + ": " + reason)
    return lines


def reviewable_prs(state):
    """Open non-maintainer linked PRs of items whose follow-up is "review", in selection order."""
    numbers = []
    for item in ordered(state):
        if (item.get("decision") or {}).get("action") == "review":
            for pr in item.get("linked_prs", []):
                if pr.get("open_non_maintainer") and pr["number"] not in numbers:
                    numbers.append(pr["number"])
    return numbers


def cmd_record_handoff(args):
    if args.prs is not None and not re.fullmatch(r"[1-9][0-9]{0,9}(,[1-9][0-9]{0,9})*", args.prs):
        raise UsageError("record-handoff takes a comma-separated list of pull request numbers, like 12,15.")
    run_dir, state = load_run(args.run)
    allowed = reviewable_prs(state)
    if args.prs is None:
        # Default: every open non-maintainer linked PR of the issues whose follow-up is "review".
        wanted = list(allowed)
    else:
        wanted = []
        for number in (int(n) for n in args.prs.split(",")):
            if number not in wanted:
                wanted.append(number)
        unknown = [n for n in wanted if n not in allowed]
        if unknown:
            raise BulkError("Only open non-maintainer linked PRs of issues with the review follow-up can be handed "
                            "to review; not: " + ", ".join("#" + str(n) for n in unknown) + ".")
    # The state was recorded at selection: a PR closed or merged since then is never handed to review.
    still_open = [n for n in wanted if pr_is_open(state["repository"], n)]
    closed = [n for n in wanted if n not in still_open]
    run_state.update(run_dir, lambda st: st["extra"].update(handoff_prs=still_open))
    return dict(handoff_result(state, still_open), closed=closed)


def pr_is_open(repository, number):
    try:
        pr = github().call(["api", "--hostname", "github.com", "repos/" + repository + "/pulls/" + str(number)])
    except InboxError as exc:
        raise BulkError("Reading pull request #" + str(number) + " failed: " + str(exc)) from exc
    return isinstance(pr, dict) and pr.get("state") == "open"


def handoff_result(state, numbers):
    """review --bulk selects in the invoking checkout, so the command must run in a checkout of the repository."""
    return {"handoff_prs": numbers, "repository": state["repository"],
            "command": "review --bulk --prs " + ",".join(str(n) for n in numbers) if numbers else None}


def item_outcome(item, handoff):
    if item["phase"] == "assessment_failed":
        return "Assessment failed: " + str(item.get("failure") or "unknown reason")
    if item["phase"] in ("selected", "collected"):
        return "Not assessed yet"
    if item.get("decision") is None:
        return "Waiting for a decision"
    post, decision = item.get("post") or {}, item["decision"]
    label = "`" + str(item.get("label")) + "`"
    comment = post.get("comment")
    if comment == "posted":
        text = "Posted"
        if post.get("label") == "applied":
            text += " with label " + label
        elif post.get("label") == "missing":
            text += "; label " + label + " missing (not created)"
        elif post.get("label") == "failed":
            text += "; label failed: " + str(post.get("reason"))
        else:
            text += "; label pending"
    elif comment == "failed":
        text = "Post failed: " + str(post.get("reason"))
    elif comment == "withheld":
        text = "Withheld: " + str(post.get("reason"))
    elif comment == "skipped":
        text = "Skipped by maintainer"
    else:
        text = "Post pending"
    parts = [text]
    action = decision.get("action")
    fix = item.get("fix") or {}
    if action == "fix":
        if fix.get("pr_url"):
            parts.append("draft PR " + fix["pr_url"])
        elif fix.get("pending") == "pr":
            parts.append("PR pending (branch " + str(fix.get("branch")) + " pushed, PR not opened)")
        elif fix.get("pending") == "push":
            parts.append("push pending (" + str(fix.get("pr_error") or "not pushed yet") + ")")
        elif fix.get("abandoned"):
            parts.append("fix abandoned: " + str(fix["abandoned"]))
        else:
            parts.append("fix not run yet")
    elif action == "review":
        numbers = [p["number"] for p in item.get("linked_prs", []) if p.get("open_non_maintainer")]
        handed = [n for n in numbers if n in handoff]
        listed = ", ".join("#" + str(n) for n in (handed or numbers))
        parts.append(("linked PRs handed to review: " if handed else "review of linked PRs chosen: ") + listed)
    return "; ".join(parts)


def run_report(run_dir, state):
    selection = read_json(os.path.join(run_dir, "selection.json"), "selection")
    handoff = (state.get("extra") or {}).get("handoff_prs") or []
    items = ordered(state)
    stopped = bool((state.get("extra") or {}).get("git_tainted"))
    # A tainted fix is never resumed (no git runs for it), so it does not keep the run open.
    pending = [item for item in items if (item.get("fix") or {}).get("pending") == "pr" and not stopped
               and not (item.get("fix") or {}).get("tainted")]
    retry = [item for item in items if (item.get("decision") or {}).get("post") == "post"
             and not post_final(item.get("post") or {})]
    # A chosen fix that is neither finished nor abandoned, or whose worktree was never removed, keeps the run open.
    fixes = [item for item in items if item not in pending and (item.get("decision") or {}).get("action") == "fix"
             and not stopped and (fix_open(item) or (fix_owned(item.get("fix") or {}) and not (item.get("fix") or {}).get("cleaned")
                                     and not (item.get("fix") or {}).get("tainted")))]
    undecided = [item for item in items if item["phase"] in ("selected", "collected")
                 or (item["phase"] == "assessed" and item.get("decision") is None)]
    status = "running" if pending or retry or fixes or undecided else "finished"
    lines = ["## Bulk issue run " + state["run_id"], "",
             "Repository: " + state["repository"] + ". Status: " + status + ".", "",
             "| Issue | Title | Recommendation | Outcome |", "|---|---|---|---|"]
    for item in ordered(state):
        recommendation = assessment.RECOMMENDATIONS.get(item.get("recommendation"), "") if item.get("recommendation") else ""
        lines.append("| " + _issue_link(item) + " | " + assessment._cell(item.get("title", "")) + " | "
                     + recommendation + " | " + assessment._cell(item_outcome(item, handoff)) + " |")
    extra = state.get("extra") or {}
    if extra.get("git_tainted"):
        lines += ["", "Fixes stopped: " + assessment._flat(extra["git_tainted"])]
    if not extra.get("fixes_available") and extra.get("fixes_unavailable_reason"):
        lines += ["", "Fixes were not offered: " + assessment._flat(extra["fixes_unavailable_reason"])]
    if handoff:
        lines += ["", "Handed to bulk review (run it in a checkout of " + state["repository"] + "): "
                  "`review --bulk --prs " + ",".join(str(n) for n in handoff) + "`"]
    lines += [""] + coverage(selection)
    if status == "running":
        waiting = []
        for label, group in (("pull requests for", pending), ("posts for", retry), ("fixes for", fixes),
                             ("assessments or decisions for", undecided)):
            if group:
                waiting.append(label + " " + ", ".join("#" + str(i["number"]) for i in group))
        lines += ["", "Still pending: " + "; ".join(waiting) + ". The run stays open; retry from a checkout of "
                  + state["repository"] + " with `issue --resume " + state["run_id"] + "`"]
    else:
        run_state.set_status(run_dir, "finished")
    return "\n".join(lines) + "\n"


def selection_report(selection):
    selected, skipped = selection.get("selected", []), selection.get("skipped", [])
    query = str(selection.get("query", "")).replace("`", "'")
    if not selection.get("scanned"):
        head = "No issues matched `" + query + "`."
    elif not selected:
        head = "All " + str(len(skipped)) + " candidates were skipped."
        if not selection.get("ceiling_reached"):
            head += " No open issue matching this search still needs a first answer."
    else:
        head = "Selected " + str(len(selected)) + " issues: " + ", ".join(_issue_link(c) for c in selected) + "."
    return "\n".join(["## Bulk issue selection", "", head, ""] + coverage(selection)) + "\n"


def cmd_report(args):
    if args.selection:
        return selection_report(read_json(args.selection, "selection"))
    if not args.run:
        raise UsageError("report needs a run directory or --selection FILE.")
    run_dir, state = load_run(args.run)
    return run_report(run_dir, state)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

FORBIDDEN_QUALIFIERS = (re.compile(r"(?:^|[\s(])-?(?:repo|org|user|state|sort):", re.I),
                        re.compile(r"(?:^|[\s(])-?(?:is|type):(?:pr|closed|merged|open|issue)(?![\w-])", re.I))


def check_search(search):
    spaced, joined = re.sub(r"[\"']", " ", search), re.sub(r"[\"']", "", search)
    if any(pattern.search(flat) for pattern in FORBIDDEN_QUALIFIERS for flat in (spaced, joined)):
        raise UsageError("--search must not contain repo:, org:, user:, is:pr, type:pr, is:closed, is:merged, "
                         "is:open, state:, is:issue or sort:; the repository comes from --repo, and state, "
                         "type and order are fixed.")


RUN_ID = re.compile(run_state.run_id_pattern(KIND))
VALUE_FLAGS = ("--search", "--limit", "--scan", "--repo")
TARGET = re.compile(r"[0-9]+|https?://\S+")


def parse_raw(raw):
    """Tokenize the user's issue arguments without any service call."""
    found = {"bulk": False, "resume": False, "resume_id": None, "unattended": False,
             "targets": [], "values": {}}
    index = 0
    while index < len(raw):
        token = raw[index]
        name, eq, inline = token.partition("=") if token.startswith("--") else (token, "", "")
        if name in ("--bulk", "--unattended") and not eq:
            found[name[2:]] = True
        elif name == "--resume":
            found["resume"] = True
            if eq:
                found["resume_id"] = inline
            elif index + 1 < len(raw) and not raw[index + 1].startswith("--"):
                index += 1
                if TARGET.fullmatch(raw[index]):
                    found["targets"].append(raw[index])
                else:
                    found["resume_id"] = raw[index]
        elif name in VALUE_FLAGS:
            if name in found["values"]:
                raise UsageError(name + " is given twice.")
            if eq:
                value = inline
            elif index + 1 < len(raw) and not raw[index + 1].startswith("--"):
                index += 1
                value = raw[index]
            else:
                raise UsageError(name + " needs a value.")
            found["values"][name] = value
        elif token.startswith("-"):
            raise UsageError("unknown option " + token + " for issue --bulk; allowed: --bulk, --resume [<run-id>], "
                             "--search Q, --limit N, --scan S, --repo owner/name.")
        else:
            found["targets"].append(token)
        index += 1
    return found


def _bounded(flag, value, low, high):
    if not re.fullmatch(r"[0-9]{1,5}", value) or not low <= int(value) <= high:
        raise UsageError(flag + " must be a number from " + str(low) + " to " + str(high) + ".")
    return int(value)


def validate(raw):
    """Apply the FR-002 table to the raw arguments; return the normalized options."""
    found = parse_raw(raw)
    values = found["values"]
    if not found["bulk"] and not found["resume"]:
        for flag in ("--search", "--limit", "--scan"):
            if flag in values:
                raise UsageError(flag + " works only with --bulk; add --bulk to assess a batch of issues.")
        raise UsageError("give --bulk to start a batch or --resume [<run-id>] to continue one.")
    if found["targets"]:
        raise UsageError("a bulk run selects its own issues; remove the issue number or URL "
                         "(" + found["targets"][0] + "), or drop --bulk/--resume to assess one issue.")
    if found["unattended"]:
        raise UsageError("bulk issue assessment is interactive only; --unattended works with a single issue.")
    if found["resume"]:
        for flag in VALUE_FLAGS:
            if flag in values:
                raise UsageError("a resumed run keeps its recorded options; remove " + flag + ".")
        resume_id = found["resume_id"]
        if resume_id is not None and not RUN_ID.fullmatch(resume_id):
            raise UsageError("--resume takes an issue run id like 20261123-091446-issue.")
        return {"mode": "resume", "search": None, "limit": None, "scan": None, "repo": None,
                "resume_id": resume_id}
    repo = values.get("--repo")
    if repo is not None and not valid_repo(repo):
        raise UsageError("--repo must be owner/name.")
    limit = _bounded("--limit", values["--limit"], 1, 100) if "--limit" in values else 10
    if "--scan" in values:
        scan = _bounded("--scan", values["--scan"], 1, 1000)
        if scan < limit:
            raise UsageError("--scan must be 1 to 1000 and not below --limit (" + str(limit) + ").")
    else:
        scan = max(100, limit)
    search = values.get("--search")
    if search is not None:
        search = " ".join(clean_text(search).split())
        if not search:
            raise UsageError("--search needs a query, for example 'label:bug crash'.")
        check_search(search)
    return {"mode": "new", "search": search, "limit": limit, "scan": scan, "repo": repo, "resume_id": None}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate raw issue --bulk/--resume arguments (all following arguments)")
    p = sub.add_parser("select", help="select open issues by search and skip rules")
    p.add_argument("--repo", required=True)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--scan", type=int, default=100)
    p.add_argument("--search")
    p.add_argument("--out", required=True)
    p = sub.add_parser("resolve-repo", help="resolve the target repository (gh context or --repo)")
    p.add_argument("--repo")
    p = sub.add_parser("start", help="create the run from a non-empty selection")
    p.add_argument("--selection", required=True)
    for name, text in (("collect", "collect one selected issue into items/<n>/snapshot.json"),
                       ("render-item", "validate assessment.json and render items/<n>/rendered.md"),
                       ("item", "print one item's decision fields"),
                       ("guard-begin", "digest of the run before an assessment worker runs"),
                       ("guard-end", "verify the run digest after an assessment worker; stops the run on change")):
        p = sub.add_parser(name, help=text)
        p.add_argument("run")
        p.add_argument("number")
        p.add_argument("--session")
        if name == "guard-end":
            p.add_argument("--digest", required=True)
    p = sub.add_parser("next", help="first item in selection order that needs the phase")
    p.add_argument("run")
    p.add_argument("phase", choices=PHASES)
    p.add_argument("--session")
    p = sub.add_parser("fail", help="mark an issue's assessment as failed")
    p.add_argument("run")
    p.add_argument("number")
    p.add_argument("--reason", required=True)
    p = sub.add_parser("decide", help="record the maintainer's decision for one issue")
    p.add_argument("run")
    p.add_argument("number")
    p.add_argument("--post", required=True, choices=("post", "skip"))
    p.add_argument("--action", choices=("fix", "leave", "review"))
    p.add_argument("--session")
    p = sub.add_parser("post", help="re-check, then post the approved comment and its label")
    p.add_argument("run")
    p.add_argument("number")
    p.add_argument("--session")
    for name, text in (("fix-prepare", "create the fix worktree and branch from the default branch tip"),
                       ("fix-measure", "check containment and measure the fix against the small bound"),
                       ("fix-publish", "commit without hooks, push, and open the draft pull request"),
                       ("fix-cleanup", "remove the fix worktree and local branch (keeps the pushed branch)")):
        p = sub.add_parser(name, help=text)
        p.add_argument("run")
        p.add_argument("number")
        p.add_argument("--session")
    p = sub.add_parser("record-handoff", help="record the linked PRs handed to review --bulk "
                                              "(default: all open non-maintainer PRs of review follow-ups)")
    p.add_argument("run")
    p.add_argument("prs", nargs="?")
    p = sub.add_parser("abandon-run", help="remove a run's fix worktrees and local fix branches, then abandon it")
    p.add_argument("run")
    p = sub.add_parser("report", help="print the Markdown report (finishes the run unless a PR is pending)")
    p.add_argument("run", nargs="?")
    p.add_argument("--selection")
    return parser


COMMANDS = {"select": cmd_select, "resolve-repo": cmd_resolve_repo, "start": cmd_start, "collect": cmd_collect, "render-item": cmd_render_item, "next": cmd_next, "fail": cmd_fail,
            "decide": cmd_decide, "post": cmd_post, "report": cmd_report,
            "fix-prepare": cmd_fix_prepare, "fix-measure": cmd_fix_measure,
            "fix-publish": cmd_fix_publish, "fix-cleanup": cmd_fix_cleanup,
            "record-handoff": cmd_record_handoff, "abandon-run": cmd_abandon_run, "item": cmd_item,
            "guard-begin": cmd_guard_begin, "guard-end": cmd_guard_end}
# Commands that still work on a run stopped by guard-end: inspection and abandonment.
HALT_EXEMPT = ("report", "abandon-run", "item")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["validate"]:
            # The raw user arguments start with "--"; argparse would claim them as its own options.
            result = validate(argv[1:])
        else:
            args = build_parser().parse_args(argv)
            run_dir = getattr(args, "run", None)
            # One helper call at a time per run: two sessions can never both post or publish the same item.
            with run_state.locked(run_dir) if run_dir else nullcontext():
                if run_dir and os.path.isdir(run_dir):
                    if getattr(args, "session", None):
                        # The active session holds the run; another session is refused until the lock expires.
                        run_state.claim_session(run_dir, args.session)
                    halted = (run_state.load(run_dir).get("extra") or {}).get("halted")
                    if halted and args.command not in HALT_EXEMPT:
                        raise BulkError(halted)
                result = COMMANDS[args.command](args)
    except UsageError as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 2
    except (BulkError, run_state.StateError, InboxError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 1
    if isinstance(result, str):
        sys.stdout.write(result)
    elif result is not None:
        print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
