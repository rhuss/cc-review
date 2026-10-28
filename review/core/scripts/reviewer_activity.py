#!/usr/bin/env python3
"""Exact reviewer conversation fingerprints and identity scoped durable handling."""
from datetime import datetime, timezone
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import sys
from typing import Optional


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def validate_identity(host, repository, user, pr=None):
    parts = repository.split("/") if isinstance(repository, str) else []
    for index, value in enumerate([host, user] + parts):
        pattern = r"[A-Za-z0-9_.-]+" if index == 3 else r"[A-Za-z0-9][A-Za-z0-9_.-]*"
        if (not isinstance(value, str) or len(value) > 255
                or not re.fullmatch(pattern, value)
                or value in (".", "..")):
            raise ValueError("host, repository and user must be safe identity components")
    if len(parts) != 2:
        raise ValueError("repository must be owner/name")
    if pr is not None and (type(pr) is not int or pr < 1):
        raise ValueError("pr must be a positive integer")


def _identity(identity):
    if not isinstance(identity, dict):
        raise ValueError("identity must be an object")
    validate_identity(identity.get("host"), identity.get("repository"), identity.get("user"), identity.get("pr"))
    if type(identity.get("pr")) is not int or identity["pr"] < 1:
        raise ValueError("identity.pr is required")


def _activity(value):
    if not isinstance(value, dict):
        return False
    for key in ("thread_id", "root_comment_id", "head_oid"):
        if not isinstance(value.get(key), str) or not value[key] or len(value[key]) > 512:
            return False
    return all(isinstance(value.get(key), str) and re.fullmatch(r"[a-f0-9]{64}", value[key])
               for key in ("conversation_digest", "activity_key"))


def activity_marker(identity, activity, reply_body=""):
    _identity(identity)
    if not _activity(activity):
        raise ValueError("activity must contain exact thread/root/head and SHA-256 digests")
    if not isinstance(reply_body, str):
        raise ValueError("reply_body must be text")
    return "<!-- cc-review-activity:v1 " + _json({"identity": identity, "activity": activity,
                                                  "reply_digest": _hash(reply_body)}) + " -->"


def _marker_reply_body(body):
    for match in re.finditer(r"(?m)^<!-- cc-review-activity:v1 \{[^\n]{1,4096}\} -->$", body):
        prefix = body[:match.start()]
        if body[match.end():].strip():
            continue
        if prefix.endswith("\n\n"):
            return prefix[:-2]
        return prefix[:-1] if prefix.endswith("\n") else prefix
    return None


def matching_activity_reply(thread, identity, activity):
    """Return the exact database ID of our reply carrying this activity marker."""
    if not isinstance(thread, dict) or not isinstance(identity, dict) or not _activity(activity):
        return None
    comments = thread.get("comments")
    nodes = comments.get("nodes") if isinstance(comments, dict) else None
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if not isinstance(node, dict) or author(node) != identity.get("user"):
            continue
        body = node.get("body", "")
        marker = parse_activity_marker(body)
        content = _marker_reply_body(body) if isinstance(body, str) else None
        if (marker and marker.get("identity") == identity and marker.get("activity") == activity
                and content is not None and marker.get("reply_digest") == _hash(content)):
            return node.get("databaseId")
    return None


def parse_activity_marker(body: str) -> Optional[dict]:
    if not isinstance(body, str) or body.count("cc-review-activity:") != 1:
        return None
    # Track fenced examples, while allowing actual markers after a closed
    # code example in a real reply. Quoted and indented lines are not evidence.
    candidate, fence = None, None
    for line in body.splitlines():
        if re.match(r"^ {0,3}>", line):
            continue
        boundary = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if boundary:
            token, rest = boundary.groups()
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not rest.strip():
                fence = None
            continue
        if fence is None:
            match = re.fullmatch(r"<!-- cc-review-activity:v1 (\{[^\n]{1,4096}\}) -->", line)
            if match:
                candidate = match.group(1)
    if candidate is None:
        return None
    try:
        value = json.loads(candidate)
        _identity(value["identity"])
        if (set(value) not in ({"identity", "activity"}, {"identity", "activity", "reply_digest"})
                or not _activity(value["activity"])
                or ("reply_digest" in value and not re.fullmatch(r"[a-f0-9]{64}", value["reply_digest"]))):
            return None
        return value
    except (ValueError, KeyError, TypeError):
        return None


def author(value):
    actor = value.get("author") if isinstance(value, dict) else None
    return actor.get("login") if isinstance(actor, dict) else actor


def validate_comment(comment):
    if not isinstance(comment, dict):
        raise ValueError("thread comments must be objects")
    actor = comment.get("author")
    if actor is not None and not isinstance(actor, (str, dict)):
        raise ValueError("comment author must be an actor object, login or null")
    if isinstance(actor, dict) and actor.get("login") is not None and not isinstance(actor["login"], str):
        raise ValueError("comment author login must be a string or null")
    for name in ("originalCommit", "commit", "pullRequestReview", "review"):
        nested = comment.get(name)
        if nested is not None and not isinstance(nested, dict):
            raise ValueError("comment " + name + " must be an object or null")
    review = comment.get("pullRequestReview") or comment.get("review")
    if review:
        validate_comment(review)


def validate_thread(thread):
    if not isinstance(thread, dict):
        raise ValueError("thread must be an object")
    if "coverage" in thread and not isinstance(thread["coverage"], dict):
        raise ValueError("thread coverage must be an object")
    for name in ("comments", "rootComment"):
        connection = thread.get(name)
        if connection is None:
            continue
        if not isinstance(connection, dict):
            raise ValueError("thread " + name + " must be a connection object or null")
        if connection.get("pageInfo") is not None and not isinstance(connection["pageInfo"], dict):
            raise ValueError("thread comment pageInfo must be an object or null")
        nodes = connection.get("nodes")
        if nodes is not None and not isinstance(nodes, list):
            raise ValueError("thread comment nodes must be an array or null")
        for node in nodes or []:
            if node is not None:
                validate_comment(node)
    if thread.get("root") is not None:
        validate_comment(thread["root"])


def root_comment(thread):
    root = thread.get("root") or thread.get("rootComment")
    if isinstance(root, dict) and "nodes" in root:
        root = next(iter(root.get("nodes") or []), None)
    if isinstance(root, dict):
        return root
    comments = thread.get("comments")
    nodes = comments.get("nodes") if isinstance(comments, dict) else comments
    if isinstance(nodes, list) and nodes:
        return nodes[0]
    return None


def _without_fenced_code(body):
    lines, fence = [], None
    for line in body.splitlines():
        boundary = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if boundary:
            token, rest = boundary.groups()
            if fence is None:
                fence = token[0], len(token)
            elif token[0] == fence[0] and len(token) >= fence[1] and not rest.strip():
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return "\n".join(lines)


def owned_root(root, user):
    if not isinstance(root, dict) or author(root) != user or not isinstance(root.get("body"), str):
        return False
    body = _without_fenced_code(root["body"])
    source = re.search(r"(?m)^_Source: [A-Za-z0-9][A-Za-z0-9 ._-]*_\s*$", body)
    review = root.get("pullRequestReview") or root.get("review") or {}
    marked_review = (author(review) == user and re.search(r"(?m)^<!-- cc-review:run-id:[^\s<>]{1,256} -->$",
                                                         _without_fenced_code(review.get("body") or "")))
    return bool(source or marked_review)


def conversation_complete(thread):
    coverage = thread.get("coverage", {})
    if not isinstance(coverage, dict) or coverage.get("complete") is False:
        return False
    comments = thread.get("comments")
    if not isinstance(comments, dict) or not isinstance(comments.get("nodes"), list):
        return False
    page = comments.get("pageInfo")
    return (isinstance(page, dict) and page.get("hasNextPage") is False
            and page.get("hasPreviousPage") is False
            and type(comments.get("totalCount")) is int
            and comments["totalCount"] == len(comments["nodes"]))


def fingerprint(thread: dict, head_oid: str, user: str, identity: Optional[dict] = None) -> Optional[dict]:
    if not isinstance(thread, dict) or not isinstance(head_oid, str) or not head_oid:
        return None
    root = root_comment(thread)
    if (not owned_root(root, user) or not isinstance(thread.get("id"), str) or not thread["id"]
            or not isinstance(root.get("id"), str) or not root["id"]
            or not conversation_complete(thread)):
        return None
    nodes = thread["comments"]["nodes"]
    comments = {root["id"]: root}
    marker_groups = {}
    for node in nodes:
        if (not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]
                or not isinstance(node.get("body"), str) or "author" not in node
                or not isinstance(node.get("updatedAt"), str)):
            return None
        parsed = parse_activity_marker(node["body"])
        content = _marker_reply_body(node["body"])
        if (parsed and content is not None and parsed.get("reply_digest") == _hash(content)
                and author(node) == user and parsed["identity"]["user"] == user
                and (identity is None or parsed["identity"] == identity)):
            a = parsed["activity"]
            if a["thread_id"] == thread["id"] and a["root_comment_id"] == root["id"]:
                marker_groups.setdefault(_json(a), {"activity": a, "ids": set()})["ids"].add(node["id"])
        comments.setdefault(node["id"], node)
    if not isinstance(root.get("updatedAt"), str):
        return None

    def result_for(excluded):
        included = [node for node in comments.values() if node["id"] not in excluded]
        digest = _hash([{ "id": node["id"], "author": author(node), "body": _hash(node["body"]),
                         "updated_at": node["updatedAt"]} for node in sorted(included, key=lambda n: n["id"])])
        result = {"thread_id": thread["id"], "root_comment_id": root["id"],
                  "head_oid": head_oid, "conversation_digest": digest}
        result["activity_key"] = _hash([user, result])
        return result

    # A marker is omitted from the conversation only when its *entire* embedded
    # activity is exactly the fingerprint of the conversation without that
    # marker. A newer or malformed marker remains ordinary conversation data.
    for marker in marker_groups.values():
        candidate = result_for(marker["ids"])
        if marker["activity"] == candidate:
            return candidate
    return result_for(set())


def check_activity(identity: dict, expected: dict, current_pr: dict, thread: dict) -> dict:
    _identity(identity)
    if not _activity(expected):
        raise ValueError("expected must be an exact Activity")
    result = {"allowed": False, "complete": True, "reason": None, "activity": None, "warnings": []}
    reason = None
    if current_pr.get("state") != "OPEN":
        reason = "PR is closed or open state is unavailable"
    elif not current_pr.get("author") or current_pr["author"] == identity["user"]:
        reason = "reviewer role requires another author's PR"
    elif current_pr.get("head_oid") != expected["head_oid"]:
        reason = "PR head moved; reassessment required"
    elif not isinstance(thread, dict) or thread.get("id") != expected["thread_id"]:
        reason = "exact thread is missing or replaced"
    elif thread.get("isResolved") is not False:
        reason = "thread is already resolved or resolution state is unavailable"
    else:
        activity = fingerprint(thread, current_pr["head_oid"], identity["user"], identity)
        result["activity"] = activity
        if activity is None:
            reason = "thread ownership/provenance or complete conversation is unavailable"
            result["complete"] = False
        elif activity != expected:
            reason = "root or conversation changed; reassessment required"
    result.update(allowed=reason is None, reason=reason)
    return result


def _path(host, repository, user):
    validate_identity(host, repository, user)
    override = os.environ.get("CC_REVIEW_REVIEWER_STATE_FILE")
    if override:
        return Path(override)
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return base / "cc-review/reviewer-activity" / host / repository / (user + ".json")


def load_activity(host: str, repository: str, user: str) -> tuple:
    path = _path(host, repository, user)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(value, dict) or value.get("schema_version") != 1
                or any(value.get(k) != v for k, v in (("host", host), ("repository", repository), ("user", user)))
                or not isinstance(value.get("records"), dict)):
            raise ValueError("schema or identity does not match")
        for key, record in value["records"].items():
            if (not re.fullmatch(r"[1-9][0-9]*/[^/]+", key) or not _activity(record)
                    or key.split("/", 1)[1] != record["thread_id"]
                    or not isinstance(record.get("outcome"), dict)
                    or record["outcome"].get("completed") is not True
                    or record["outcome"].get("status") not in ("confirmed-fixed", "still-present", "accepted-explanation")):
                raise ValueError("invalid thread record")
        return value["records"], []
    except FileNotFoundError:
        return {}, []
    except (OSError, ValueError, TypeError) as exc:
        return {}, ["Cannot read reviewer activity cache " + str(path) + ": " + str(exc)]


def record_activity(host: str, repository: str, user: str, pr: int, thread: dict, outcome: dict) -> None:
    validate_identity(host, repository, user, pr)
    if not _activity(thread):
        raise ValueError("record requires an exact Activity")
    if "/" in thread["thread_id"]:
        raise ValueError("thread_id cannot contain '/'")
    if not isinstance(outcome, dict) or outcome.get("status") not in (
            "confirmed-fixed", "still-present", "accepted-explanation", "deferred", "unclear"):
        raise ValueError("outcome has an invalid status")
    if outcome.get("completed") is not True or outcome["status"] in ("deferred", "unclear"):
        return
    path = _path(host, repository, user)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        records, warnings = load_activity(host, repository, user)
        if warnings:
            raise OSError("; ".join(warnings))
        record = dict(thread, outcome={"status": outcome["status"], "completed": True},
                      completed_at=datetime.now(timezone.utc).isoformat(),
                      reply_id=outcome.get("reply_id"), resolved=outcome.get("resolved", False))
        records[str(pr) + "/" + thread["thread_id"]] = record
        value = dict(schema_version=1, host=host, repository=repository, user=user, records=records)
        descriptor, temporary = tempfile.mkstemp(prefix=".activity-", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(_json(value) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("load", "fingerprint", "check", "record"))
    args = parser.parse_args(argv)
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise ValueError("stdin must be one JSON object")
        identity = value.get("identity")
        _identity(identity)
        host, repo, user, pr = [identity[k] for k in ("host", "repository", "user", "pr")]
        if args.operation == "load":
            records, warnings = load_activity(host, repo, user)
            result = dict(records=records, complete=not warnings, warnings=warnings)
        elif args.operation in ("fingerprint", "check"):
            if not isinstance(value.get("thread"), dict):
                raise ValueError("thread must be an object with exact root/conversation evidence")
            validate_thread(value["thread"])
            if args.operation == "fingerprint":
                if not isinstance(value.get("head_oid"), str):
                    raise ValueError("head_oid must be a string")
                current = fingerprint(value["thread"], value["head_oid"], user, identity)
                result = dict(activity=current, complete=current is not None, warnings=[],
                              reason=None if current else "Exact owned root, head or complete conversation is unavailable")
            else:
                if not isinstance(value.get("current_pr"), dict):
                    raise ValueError("current_pr must be an object")
                result = check_activity(identity, value.get("expected"), value["current_pr"], value["thread"])
        else:
            outcome = value.get("outcome")
            if not isinstance(outcome, dict) or type(outcome.get("completed")) is not bool:
                raise ValueError("outcome must have status and boolean completed")
            reply_id, resolved = value.get("reply_id"), value.get("resolved")
            if (reply_id is not None and (type(reply_id) is not int or reply_id < 1)) or type(resolved) is not bool:
                raise ValueError("reply_id must be null/positive integer and resolved must be boolean")
            outcome = dict(outcome, reply_id=reply_id, resolved=resolved)
            record_activity(host, repo, user, pr, value.get("activity"), outcome)
            recorded = outcome["completed"] and outcome["status"] not in ("unclear", "deferred")
            result = dict(recorded=recorded, complete=True, warnings=[],
                          reason=None if recorded else "Pending question or decision was not recorded")
        json.dump(result, sys.stdout, ensure_ascii=True)
        sys.stdout.write("\n")
        return 0
    except (ValueError, KeyError, TypeError) as exc:
        print("reviewer-activity: " + str(exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print("reviewer-activity: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
