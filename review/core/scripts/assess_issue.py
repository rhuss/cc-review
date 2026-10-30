#!/usr/bin/env python3
"""Collect one bounded, read-only GitHub issue snapshot for maintainer assessment."""

import argparse
from datetime import datetime, timezone
import json
import re
import subprocess
import sys

from inbox import GitHub, InboxError, REPO_PATTERN, clean_text


MAX_COMMENTS = 50
ISSUE_BODY_CHARS = 20000
COMMENT_BODY_CHARS = 4000
ISSUE_URL = r"https://github\.com/(" + REPO_PATTERN + r")/issues/([1-9][0-9]*)"
QUERY = """query AssessIssue($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issueOrPullRequest(number: $number) {
      __typename
      ... on Issue {
        number title url body state createdAt updatedAt author { login }
        comments(last: 50) {
          totalCount pageInfo { hasPreviousPage }
          nodes { body url createdAt updatedAt author { login } }
        }
      }
    }
  }
}"""


def valid_repo(value):
    return (isinstance(value, str) and re.fullmatch(REPO_PATTERN, value) is not None
            and value.split("/")[1] not in (".", ".."))


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue", help="positive issue number or https://github.com/owner/repo/issues/N")
    parser.add_argument("--repo", help="repository owner/name (otherwise use URL or current gh context)")
    args = parser.parse_args(argv)
    if args.repo is not None and not valid_repo(args.repo):
        parser.error("--repo must be owner/name")
    url = re.fullmatch(ISSUE_URL, args.issue)
    if url:
        repo, number = url.groups()
        if not valid_repo(repo):
            parser.error("issue URL must name a valid repository")
        if args.repo and args.repo.lower() != repo.lower():
            parser.error("issue URL and --repo select different repositories")
        args.repo = repo
    elif re.fullmatch(r"[1-9][0-9]*", args.issue):
        number = args.issue
    else:
        parser.error("select a positive issue number or canonical GitHub.com issue URL; PRs are unsupported")
    # GraphQL Int is a signed 32-bit integer. Validate without converting enormous input.
    if len(number) > 10 or int(number) > 2147483647:
        parser.error("issue number exceeds GitHub's supported range")
    args.number = int(number)
    return args


def local_context(repository):
    unavailable = {"matching": False, "root": None,
                   "reason": "No matching local origin; project guidance and code are unavailable."}
    try:
        origin = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True,
                                text=True, timeout=5, check=False)
        if origin.returncode:
            return unavailable
        match = re.fullmatch(r"(?:git@github\.com:|https://github\.com/)([^/]+/[^/]+?)(?:\.git)?/?",
                             origin.stdout.strip())
        if not match or match[1].lower() != repository.lower():
            return unavailable
        root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                              text=True, timeout=5, check=False)
        if not root.returncode and root.stdout.strip():
            return {"matching": True, "root": root.stdout.strip(),
                    "reason": "Local origin matches; local revision may differ from the default branch."}
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        pass
    return unavailable


def collect(args):
    github = GitHub()
    github.host = "github.com"
    repo_args = ["repo", "view"]
    if args.repo:
        repo_args.append("github.com/" + args.repo)
    repo_args.extend(["--json", "nameWithOwner,url"])
    metadata = github.call(repo_args)
    repository = metadata.get("nameWithOwner")
    if (not valid_repo(repository)
            or metadata.get("url") != "https://github.com/" + repository
            or (args.repo and args.repo.lower() != repository.lower())):
        raise InboxError("Could not resolve the selected GitHub.com repository; check --repo or issue URL.")
    project = local_context(repository)
    owner, name = repository.split("/")
    response = github.call(["api", "--hostname", "github.com", "graphql",
                            "-f", "query=" + QUERY, "-f", "owner=" + owner,
                            "-f", "name=" + name, "-F", "number=" + str(args.number)])
    data = response.get("data")
    remote_repo = data.get("repository") if isinstance(data, dict) else None
    value = remote_repo.get("issueOrPullRequest") if isinstance(remote_repo, dict) else None
    if isinstance(value, dict) and value.get("__typename") == "PullRequest":
        raise InboxError("This number identifies a pull request; use review or triage for PRs.")
    if not isinstance(value, dict) or value.get("__typename") != "Issue":
        raise InboxError("Issue not found or inaccessible; check repository, number, and gh authentication.")
    issue_url = "https://github.com/" + repository + "/issues/" + str(args.number)
    if (type(value.get("number")) is not int or value["number"] != args.number
            or value.get("url") != issue_url
            or value.get("state") not in ("OPEN", "CLOSED")
            or not all(isinstance(value.get(key), str)
                       for key in ("title", "body", "createdAt", "updatedAt"))):
        raise InboxError("GitHub returned invalid issue identity or content; retry collection.")

    warnings = []
    if response.get("errors"):
        warnings.append("Partial GitHub response; some issue context may be unavailable.")

    def text(value, limit, label):
        cleaned = clean_text(value)
        if len(cleaned) > limit:
            warnings.append(label + " was shortened to " + str(limit) + " characters.")
        return cleaned[:limit]

    def author(record):
        actor = record.get("author")
        if actor is None:
            return None
        if isinstance(actor, dict) and isinstance(actor.get("login"), str):
            return clean_text(actor["login"])
        warnings.append("An author identity was unavailable.")
        return None

    selected = {"number": args.number, "url": issue_url,
                "title": text(value["title"], 1000, "Issue title"),
                "body": text(value["body"], ISSUE_BODY_CHARS, "Issue body"),
                "state": value["state"], "author": author(value),
                "created_at": clean_text(value["createdAt"]),
                "updated_at": clean_text(value["updatedAt"])}
    conversation = value.get("comments")
    comments = []
    total = None
    if not isinstance(conversation, dict) or not isinstance(conversation.get("nodes"), list):
        warnings.append("Issue comments could not be read.")
    else:
        nodes = conversation["nodes"]
        total = conversation.get("totalCount")
        page = conversation.get("pageInfo")
        if (type(total) is not int or total < len(nodes)
                or not isinstance(page, dict) or type(page.get("hasPreviousPage")) is not bool):
            total = None
            warnings.append("Comment counts or pagination are incomplete.")
        elif page["hasPreviousPage"] or total > len(nodes):
            warnings.append("Earlier comments were omitted; only the latest 50 are collected.")
        if len(nodes) > MAX_COMMENTS:
            warnings.append("Returned comments exceeded the 50-comment limit.")
        for node in nodes[-MAX_COMMENTS:]:
            if (not isinstance(node, dict)
                    or not all(isinstance(node.get(key), str)
                               for key in ("body", "url", "createdAt", "updatedAt"))
                    or not re.fullmatch(re.escape(issue_url) + r"#issuecomment-[0-9]+", node["url"])):
                warnings.append("An invalid comment or source link was omitted.")
                continue
            comments.append({"body": text(node["body"], COMMENT_BODY_CHARS, "Comment body"),
                             "url": node["url"], "author": author(node),
                             "created_at": clean_text(node["createdAt"]),
                             "updated_at": clean_text(node["updatedAt"])})
    return {"schema_version": 1, "repository": repository,
            "repository_url": metadata["url"],
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "local_context": project, "issue": selected, "comments": comments,
            "comment_total": total, "conversation_complete": not warnings,
            "limits": {"max_comments": MAX_COMMENTS, "issue_body_chars": ISSUE_BODY_CHARS,
                       "comment_body_chars": COMMENT_BODY_CHARS},
            "warnings": warnings}


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        snapshot = collect(args)
    except InboxError as exc:
        print("issue: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(snapshot, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
