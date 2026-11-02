#!/usr/bin/env python3
"""Prepare and revalidate one approved reviewer notification per PR.

prepare reads a reviewer plan. check reads {plan, current_pr, threads, comments};
comments must come from a complete collection. Neither operation publishes.
"""
import argparse
import copy
import json
import re
import sys

import reviewer_activity as activity


PREFIX = "<!-- cc-review-triage-summary:v1 "


def verified(item):
    outcome = item.get("outcome") or {}
    return outcome.get("completed") is True and (
        outcome.get("status") == "confirmed-fixed" or
        (outcome.get("status") == "accepted-explanation" and outcome.get("approved") is True))


def summary_key(identity, keys, body):
    activity._identity(identity)
    if (not isinstance(body, str) or not body.strip() or PREFIX in body
            or not isinstance(keys, list) or not keys or len(set(keys)) != len(keys)
            or any(not isinstance(k, str) or not re.fullmatch(r"[a-f0-9]{64}", k) for k in keys)):
        raise ValueError("summary needs a body and unique exact activity keys")
    return activity._hash(dict(identity=identity, activity_keys=sorted(keys), body=body))


def prepare(plan):
    plan = copy.deepcopy(plan)
    if plan.get("triage_role") != "reviewer":
        raise ValueError("summary requires trusted reviewer role")
    identity = plan["activity_identity"]
    activity._identity(identity)
    candidates = [i for i in plan["cc_review_threads"]
                  if verified(i) and i.get("viewer_can_resolve") is not True]
    plan["resolution_summary"] = None
    if not candidates:
        return plan
    head = plan["expected_head"]
    lines = [f"Verified reviewer findings at `{head}`.", "",
             "Please resolve the following threads:", ""]
    keys = []
    for item in candidates:
        a = item["activity"]
        if not activity._activity(a) or a["head_oid"] != head or a["thread_id"] != item["thread_id"]:
            raise ValueError("summary requires exact verified activities at the prepared head")
        cid = item["comment_id"]
        if type(cid) is not int or cid < 1:
            raise ValueError("summary requires exact root comment database IDs")
        url = f'https://{identity["host"]}/{identity["repository"]}/pull/{identity["pr"]}#discussion_r{cid}'
        label = "fix confirmed" if item["outcome"]["status"] == "confirmed-fixed" else "explanation accepted"
        lines.append(f"- [Thread {cid}]({url}): {label}.")
        keys.append(a["activity_key"])
        item.update(resolve=False, body="")
    body = "\n".join(lines)
    plan["resolution_summary"] = dict(body=body, activity_keys=sorted(keys),
                                      summary_key=summary_key(identity, keys, body))
    return plan


def check(plan, current_pr, threads, comments, published_comment_id=None):
    summary = plan["resolution_summary"]
    identity = plan["activity_identity"]
    if plan.get("triage_role") != "reviewer" or not isinstance(summary, dict):
        raise ValueError("approved reviewer summary is missing")
    keys, body = summary["activity_keys"], summary["body"]
    key = summary_key(identity, keys, body)
    if key != summary.get("summary_key"):
        raise ValueError("summary changed; refresh approval")
    marker = PREFIX + key + " -->"
    signed = body + "\n\n" + marker
    if len(signed) > 65536:
        raise ValueError("summary exceeds the PR comment size limit")
    items = [i for i in plan["cc_review_threads"] if i["activity"]["activity_key"] in keys]
    if len(items) != len(keys) or len({i["activity"]["activity_key"] for i in items}) != len(keys):
        raise ValueError("summary coverage does not match the prepared activities")
    if published_comment_id is not None and (type(published_comment_id) is not int or published_comment_id < 1):
        raise ValueError("recorded summary comment ID must be a positive integer")
    found = published_comment_id
    for comment in comments:
        if activity.author(comment) != identity["user"]:
            continue
        text = comment.get("body", "")
        if marker in text:
            if text != signed or type(comment.get("databaseId")) is not int or comment["databaseId"] < 1:
                raise ValueError("published summary conflicts with approval; inspect it before retrying")
            found = comment["databaseId"]
    for item in items:
        if not verified(item) or item.get("resolve") is not False or item.get("body") != "":
            raise ValueError("summary cannot replace unverified or separately approved actions")
        matches = [t for t in threads if t.get("id") == item["thread_id"]]
        if len(matches) != 1:
            raise ValueError("summary thread is missing or ambiguous")
        t = copy.deepcopy(matches[0])
        root = activity.root_comment(t)
        if not root or root.get("databaseId") != item["comment_id"]:
            raise ValueError("summary root comment was replaced")
        # A notification already published can be recorded after an author resolves it.
        if found and t.get("isResolved") is True:
            t["isResolved"] = False
        result = activity.check_activity(identity, item["activity"], current_pr, t)
        if not result["allowed"] or not result["complete"]:
            raise ValueError(result["reason"])
    return dict(body=signed, summary_key=key, comment_id=found, items=items)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "check"))
    args = parser.parse_args()
    try:
        value = json.load(sys.stdin)
        result = prepare(value) if args.operation == "prepare" else check(
            value["plan"], value["current_pr"], value["threads"], value["comments"], value.get("published_comment_id"))
        json.dump(result, sys.stdout)
        print()
        return 0
    except (ValueError, KeyError, TypeError) as exc:
        print("reviewer-summary: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
