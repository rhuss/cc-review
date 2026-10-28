#!/usr/bin/env python3
"""Pure independent review/triage assessment shared by inbox and bulk commands."""
import argparse
import copy
import json
import re
import sys

import reviewer_activity as activity


def _connection(value, list_complete=False):
    if isinstance(value, list):
        if any(not isinstance(n, dict) for n in value):
            raise ValueError("PR activity arrays must contain objects")
        return value, list_complete and all(isinstance(n, dict) for n in value)
    if not isinstance(value, dict) or not isinstance(value.get("nodes"), list):
        return [], False
    nodes, page = value["nodes"], value.get("pageInfo") or {}
    if not isinstance(page, dict):
        raise ValueError("PR connection pageInfo must be an object or null")
    complete = (page.get("hasNextPage") is False and not page.get("hasPreviousPage")
                and type(value.get("totalCount")) is int and value["totalCount"] == len(nodes)
                and all(isinstance(n, dict) for n in nodes))
    return [n for n in nodes if isinstance(n, dict)], complete


def normalize_pr(value: dict, source: str, repository: str, user: str) -> dict:
    if source not in ("canonical", "inbox", "bulk") or not isinstance(value, dict):
        raise ValueError("source must be canonical, inbox or bulk and each PR must be an object")
    activity.validate_identity(value.get("host", "github.com"), repository, user)
    raw = value.get("detail") if source == "inbox" else value
    raw = raw if isinstance(raw, dict) else {}
    number = raw.get("number", value.get("number"))
    if type(number) is not int or number < 1:
        raise ValueError("each PR requires a positive integer number")
    reasons = value.get("reasons") or []
    if not isinstance(reasons, list) or any(not isinstance(r, str) for r in reasons):
        raise ValueError("PR reasons must be an array of strings")
    reviews, reviews_complete = _connection(raw.get("reviews"), list_complete=source == "bulk")
    threads, threads_complete = _connection(raw.get("reviewThreads", raw.get("threads")))
    coverage = raw.get("coverage") or {}
    if not isinstance(coverage, dict):
        raise ValueError("PR coverage must be an object")
    if any(type(coverage[k]) is not bool for k in ("reviews", "threads") if k in coverage):
        raise ValueError("PR coverage flags must be boolean")
    if source == "canonical":
        reviews, reviews_complete = _connection(raw.get("reviews"), list_complete=coverage.get("reviews") is True)
        threads, threads_complete = _connection(raw.get("threads"), list_complete=coverage.get("threads") is True)
    for review in reviews:
        activity.validate_comment(review)
    for thread in threads:
        activity.validate_thread(thread)
    requested, _ = _connection(raw.get("reviewRequests"))
    if any((r.get("requestedReviewer") or {}).get("login") == user for r in requested):
        reasons = list(dict.fromkeys(reasons + ["review_requested"]))
    author = activity.author(raw) or (activity.author(value) if source == "inbox" else None)
    head = raw.get("head_oid", raw.get("headRefOid"))
    draft = raw.get("is_draft", raw.get("isDraft", value.get("is_draft", False)))
    if author is not None and not isinstance(author, str):
        raise ValueError("PR author must be a login string or null")
    if head is not None and not isinstance(head, str):
        raise ValueError("PR head must be a string or null")
    if draft is not None and type(draft) is not bool:
        raise ValueError("PR draft status must be boolean or null")
    seed = copy.deepcopy(value.get("seed") or {})
    if source != "canonical":
        head_repo = raw.get("headRepository") or {}
        head_owner = raw.get("headRepositoryOwner") or head_repo.get("owner") or {}
        owner = head_owner.get("login") if isinstance(head_owner, dict) else None
        name = head_repo.get("name")
        url = None
        if owner and name:
            activity.validate_identity(value.get("host", "github.com"), owner + "/" + name, user)
            host = value.get("host", "github.com")
            url = ("git@" + host + ":" if value.get("origin_protocol") == "ssh" else "https://" + host + "/") + owner + "/" + name + ".git"
        seed = dict(number=number, title=raw.get("title") or value.get("title") or "", author=author,
                    head_ref=raw.get("headRefName"), base_ref=raw.get("baseRefName"), head_repo_url=url,
                    is_cross_repo=raw.get("isCrossRepository", False), authored_by_user=author == user)
    return dict(host=value.get("host", "github.com"), repository=repository, user=user, number=number,
                title=raw.get("title") or value.get("title") or "", author=author,
                state=raw.get("state", value.get("state", "OPEN" if source == "bulk" else None)),
                is_draft=draft,
                head_oid=head,
                updated_at=raw.get("updated_at", raw.get("updatedAt", value.get("updated_at", ""))),
                reasons=sorted(set(reasons)), reviews=copy.deepcopy(reviews), threads=copy.deepcopy(threads),
                coverage=dict(reviews=coverage.get("reviews", reviews_complete),
                              threads=coverage.get("threads", threads_complete)),
                contribution=copy.deepcopy(raw.get("contribution") or {}), seed=seed,
                scope=copy.deepcopy(value.get("scope") or {}), handled_complete=value.get("handled_complete", True))


def _action(eligible=False, role=None, reason="No supported action", evidence=None,
            uncertain=False, complete=True, exclusion=None):
    return dict(eligible=eligible, role=role, reason=reason, evidence=evidence or [],
                uncertain=uncertain, complete=complete, exclusion=exclusion)


def _marker(review):
    # Preserve bulk review's existing marker/author policy, including markers
    # in review bodies. Reviewer-thread provenance uses the stricter helper.
    body = activity._without_fenced_code(review.get("body") or "")
    return ("<!-- cc-review:run-id:" in body
            and not re.search(r"(?m)^<!-- cc-review-incomplete:v1 -->$", body))


def _incomplete(review):
    body = activity._without_fenced_code(review.get("body") or "")
    return ("<!-- cc-review:run-id:" in body
            and bool(re.search(r"(?m)^<!-- cc-review-incomplete:v1 -->$", body)))


def assess_pr(evidence: dict, handled: dict, review_mode: str = "default",
              include_review_drafts: bool = False, force_full: bool = False) -> dict:
    if review_mode not in ("default", "all-open", "search"):
        raise ValueError("review_mode must be default, all-open or search")
    user, author = evidence.get("user"), evidence.get("author")
    head = evidence.get("head_oid")
    coverage = evidence.get("coverage") or {}
    reasons = evidence.get("reasons") or []
    result = {k: evidence.get(k) for k in ("host", "repository", "number", "user")}
    review = _action(role="reviewer", exclusion="not-requested")
    triage = _action(role="author" if author == user else "reviewer", exclusion="no-open-threads")
    result.update(review=review, triage=triage)
    if not author:
        for action in (review, triage):
            action.update(complete=False, reason="PR author identity is unavailable", exclusion="incomplete-evidence")
        return result
    if evidence.get("state") != "OPEN":
        for action in (review, triage):
            action.update(reason="PR is closed or its state is unavailable", exclusion="closed",
                          complete=evidence.get("state") in ("CLOSED", "MERGED"))
        return result
    scope_exclusion = (evidence.get("scope") or {}).get("exclusion")
    if scope_exclusion:
        for action in (review, triage):
            action.update(reason="Excluded by effective scope: " + str(scope_exclusion), exclusion=scope_exclusion)
        return result

    reviews = evidence.get("reviews") or []
    attempts = [(r.get("submittedAt") or "", i, r) for i, r in enumerate(reviews)
                if activity.author(r) == user and (_marker(r) or _incomplete(r))]
    pending_incomplete = bool(attempts and _incomplete(sorted(attempts, key=lambda r: (r[0], r[1]))[-1][2]))
    at_head = [r for r in reviews if _marker(r) and (r.get("commit") or {}).get("oid") == head
               and (activity.author(r) != author or activity.author(r) == user)]
    older = [r for r in reviews if _marker(r) and activity.author(r) == user and author != user
             and (r.get("commit") or {}).get("oid") and (r.get("commit") or {}).get("oid") != head]
    requested = any(r in reasons for r in ("review_requested", "team_review_requested"))
    if evidence.get("is_draft") and not include_review_drafts:
        review.update(reason="Draft excluded from ordinary bulk review; triage is assessed separately", exclusion="draft")
    elif not head or not coverage.get("reviews", False):
        review.update(reason="Head or review history is incomplete", complete=False, exclusion="incomplete-evidence")
    elif requested:
        review.update(eligible=True, reason="Outstanding personal or team review request", exclusion=None,
                      evidence=[{"kind": "review-request", "reasons": reasons}])
    elif pending_incomplete:
        review.update(eligible=True, reason="Latest personal cc-review attempt was incomplete", exclusion=None,
                      evidence=[{"kind": "incomplete-review"}])
    elif force_full and (at_head or older or review_mode in ("all-open", "search")):
        review.update(eligible=True, reason="Explicit full review of a PR in review scope", exclusion=None,
                      evidence=[{"kind": "full-override"}])
    elif at_head:
        review.update(reason="cc-review already reviewed this head", exclusion="reviewed-at-head",
                      evidence=[{"kind": "reviewed-at-head", "head_oid": head}])
    elif older:
        unchanged = evidence.get("contribution") or {}
        if unchanged.get("reliable") is True and unchanged.get("unchanged") is True:
            review.update(reason="Reliable evidence establishes unchanged author contribution",
                          exclusion="unchanged-contribution", evidence=[{"kind": "unchanged-contribution"}])
        else:
            review.update(eligible=True, reason="Possible follow-up review: head changed; contribution equivalence unknown",
                          exclusion=None, uncertain=True,
                          evidence=[{"kind": "changed-head", "head_oid": head,
                                     "reviewed_heads": [(r.get("commit") or {}).get("oid") for r in older]}])
    elif review_mode in ("all-open", "search"):
        review.update(eligible=True, reason="Open PR in explicit review scope", exclusion=None,
                      evidence=[{"kind": "scope", "mode": review_mode}])
    else:
        review.update(reason="No outstanding request or earlier personal cc-review marker")

    threads = evidence.get("threads") or []
    incomplete = not coverage.get("threads", False) or evidence.get("handled_complete") is False
    if author == user:
        open_threads = [t for t in threads if t.get("isResolved") is False]
        if open_threads:
            triage.update(eligible=True, reason=("Unresolved feedback on your PR"
                          + ("; thread coverage is incomplete" if incomplete else "")), exclusion=None,
                          complete=not incomplete,
                          evidence=[{"kind": "author-feedback", "count": len(open_threads)}])
        elif incomplete:
            triage.update(complete=False, reason="Review thread coverage is incomplete", exclusion="incomplete-evidence")
        else:
            triage.update(reason="No unresolved feedback on your PR")
    else:
        qualifying = []
        for thread in threads:
            if thread.get("isResolved") is True:
                continue
            root = activity.root_comment(thread)
            if not root:
                incomplete = True
                continue
            if not activity.owned_root(root, user):
                continue
            current = activity.fingerprint(thread, head, user)
            if thread.get("isResolved") is not False or current is None:
                incomplete = True
                continue
            previous = handled.get(str(evidence["number"]) + "/" + thread["id"])
            if any(not activity.author(n) for n in thread["comments"]["nodes"]):
                incomplete = True
            if previous and all(previous.get(k) == v for k, v in current.items()):
                outcome = previous.get("outcome") or {}
                if outcome.get("completed") is True and outcome.get("status") in ("confirmed-fixed", "still-present", "accepted-explanation"):
                    continue
            root_review = root.get("pullRequestReview") or root.get("review") or {}
            original = (root.get("originalCommit") or root_review.get("commit") or {}).get("oid")
            external_reply = any(n.get("id") != root["id"] and activity.author(n) and activity.author(n) != user
                                 and not activity.author(n).endswith("[bot]")
                                 and (not isinstance(n.get("author"), dict) or n["author"].get("__typename") != "Bot")
                                 for n in thread["comments"]["nodes"])
            if previous or external_reply or (original and original != head):
                qualifying.append({"kind": "reviewer-activity", "activity": current,
                                   "external_reply": external_reply, "changed_head": original != head})
            elif not original:
                incomplete = True
        if qualifying:
            triage.update(eligible=True, reason="Verify new replies or code on your unresolved cc-review findings",
                          exclusion=None, evidence=qualifying, complete=not incomplete)
        elif incomplete:
            triage.update(reason="Owned reviewer activity cannot be fully assessed from incomplete evidence",
                          complete=False, exclusion="incomplete-evidence")
        else:
            triage.update(reason="No fresh owned unresolved cc-review activity", exclusion="no-reviewer-activity")
    return result


def select_prs(evidence: list, handled: dict, action: str, limit: int,
               review_mode: str = "default", include_review_drafts: bool = False,
               force_full: bool = False) -> dict:
    if action not in ("review", "triage"):
        raise ValueError("action must be review or triage")
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    selected, excluded, warnings = [], [], []
    for value in sorted(evidence, key=lambda e: (e.get("updated_at") or "", e["number"])):
        assessment = assess_pr(value, handled, review_mode, include_review_drafts, force_full)
        decision = assessment[action]
        if not decision["complete"]:
            warnings.append("PR #" + str(value["number"]) + ": " + decision["reason"])
        if decision["eligible"] and len(selected) < limit:
            seed = dict(value.get("seed") or {}, number=value["number"], title=value.get("title") or "",
                        author=value.get("author"), triage_role=decision["role"] if action == "triage" else None,
                        assessment=assessment)
            selected.append(seed)
        else:
            excluded.append(dict(number=value["number"], title=value.get("title") or "",
                                 reason="over-limit" if decision["eligible"] else decision["exclusion"],
                                 assessment=assessment))
    return dict(selected=selected, excluded=excluded, warnings=warnings)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("assess", "select"))
    parser.add_argument("--source", required=True, choices=("inbox", "bulk", "canonical"))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--review-mode", required=True, choices=("default", "all-open", "search"))
    parser.add_argument("--include-review-drafts", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--action", choices=("review", "triage"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    try:
        activity.validate_identity(args.host, args.repo, args.user)
        if args.operation == "select" and (not args.action or args.limit is None or args.limit < 1):
            raise ValueError("select requires --action and a positive --limit")
        values = json.load(sys.stdin)
        if not isinstance(values, list):
            raise ValueError("stdin must be one JSON array of PR records")
        records, warnings = activity.load_activity(args.host, args.repo, args.user)
        evidence = []
        for value in values:
            normalized = normalize_pr(value, args.source, args.repo, args.user)
            normalized.update(host=args.host, handled_complete=not warnings)
            evidence.append(normalized)
        if args.operation == "select":
            result = select_prs(evidence, records, args.action, args.limit, args.review_mode, args.include_review_drafts, args.full)
            result["warnings"] = warnings + result["warnings"]
        else:
            assessments = [assess_pr(value, records, args.review_mode, args.include_review_drafts, args.full) for value in evidence]
            result = dict(assessments=assessments, warnings=warnings + [
                "PR #" + str(a["number"]) + ": " + a[k]["reason"] for a in assessments
                for k in ("review", "triage") if not a[k]["complete"]])
        json.dump(result, sys.stdout, ensure_ascii=True)
        sys.stdout.write("\n")
        return 0
    except (ValueError, TypeError, KeyError) as exc:
        print("pr-actions: " + str(exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print("pr-actions: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
