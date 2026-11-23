#!/usr/bin/env python3
"""Kind-agnostic, resumable run state for cc-review bulk commands.

A run lives in <root>/<run-id>/state.json. The root is always a per-user state
directory keyed by repository, never inside a checkout:
${XDG_STATE_HOME:-~/.local/state}/cc-review/<kind>-bulk/<owner>__<name>/.

Every write replaces its file atomically (temp file, fsync, os.replace, fsync of
the directory), so an interrupted session never leaves a half-written state.
Item fields are owned by the calling command; this module never assumes what an
item is.

One session at a time works on a run: <run>/lock records the active session and
its last activity, and another session is refused until the lock is older than
LOCK_TTL seconds.

Usage:
  run_state.py root --kind K --repo R
  run_state.py find-unfinished --kind K --repo R [<run-id> | --latest]
  run_state.py abandon <run-dir>
  run_state.py show <run-dir>
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
import re
import sys
import tempfile


SCHEMA_VERSION = 1
STATUSES = ("running", "finished", "abandoned")
KIND_PATTERN = r"[a-z][a-z0-9]*"
REPO_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9_.-]+"
STATE_FILE = "state.json"
SESSION_LOCK = "lock"
LOCK_TTL = 30 * 60
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class StateError(Exception):
    """An actionable run state failure, safe to show without a traceback."""


def run_id_pattern(kind):
    return r"[0-9]{8}-[0-9]{6}-" + re.escape(kind) + r"(-[0-9]+)?"


def _check_kind(kind):
    if not isinstance(kind, str) or not re.fullmatch(KIND_PATTERN, kind):
        raise StateError("kind must be lowercase letters and digits.")


def _check_repo(repository):
    if (not isinstance(repository, str) or not re.fullmatch(REPO_PATTERN, repository)
            or repository.split("/")[1] in (".", "..")):
        raise StateError("repository must be owner/name.")


def now_iso(now=None):
    return (now or datetime.now(timezone.utc)).strftime(TIME_FORMAT)


def root(kind, repository):
    """State root for a kind and repository (per user, keyed by repository)."""
    _check_kind(kind)
    _check_repo(repository)
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "cc-review", kind + "-bulk", repository.replace("/", "__"))


def _fsync_directory(directory):
    try:
        handle = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


def atomic_write(path, text):
    """Write text to path atomically and durably: temp file, fsync, rename, fsync of the directory."""
    directory = os.path.dirname(os.path.abspath(path))
    handle, temp = tempfile.mkstemp(prefix=".write.", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
    _fsync_directory(directory)


def write_json(path, value):
    """Atomic JSON write, shared with callers that keep files next to the state."""
    atomic_write(path, json.dumps(value, ensure_ascii=True, indent=2) + "\n")


@contextmanager
def locked(run_dir):
    """Exclusive lock on a run for the duration of one helper call (no-op when the run does not exist)."""
    if not os.path.isdir(run_dir):
        yield
        return
    path = os.path.join(run_dir, ".lock")
    try:
        handle = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        raise StateError("Cannot open the run lock " + path + ": " + str(exc)) from exc
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX)
        except OSError as exc:
            raise StateError("Cannot lock the run " + run_dir + ": " + str(exc)) from exc
        yield
    finally:
        os.close(handle)


def claim_session(run_dir, session, now=None):
    """Record session as the run's active session, or refuse while another session was active recently.

    Call inside locked(run_dir). A lock older than LOCK_TTL seconds is taken over.
    """
    moment = now or datetime.now(timezone.utc)
    path = os.path.join(run_dir, SESSION_LOCK)
    try:
        with open(path, encoding="utf-8") as stream:
            current = json.load(stream)
    except FileNotFoundError:
        current = None
    except (OSError, ValueError):
        current = None  # an unreadable lock protects nothing; it is replaced
    if isinstance(current, dict) and current.get("session") not in (None, session):
        try:
            seen = datetime.strptime(str(current.get("updated_at")), TIME_FORMAT).replace(tzinfo=timezone.utc)
        except ValueError:
            seen = None
        if seen is not None and (moment - seen).total_seconds() < LOCK_TTL:
            minutes = max(0, int((moment - seen).total_seconds() // 60))
            free = now_iso(seen + timedelta(seconds=LOCK_TTL))
            raise StateError("Run " + os.path.basename(run_dir) + " is in use by another session (last active "
                             + now_iso(seen) + ", " + str(minutes) + " minutes ago). Finish that session, or "
                             "resume again after " + free + ", when this session may take the run over.")
    write_json(path, {"session": session, "updated_at": now_iso(moment)})


def init(state_root, kind, repository, user, options, extra, items=None, now=None):
    """Create a new running run; return its directory."""
    _check_kind(kind)
    _check_repo(repository)
    os.makedirs(state_root, mode=0o700, exist_ok=True)
    moment = now or datetime.now(timezone.utc)
    stem = moment.strftime("%Y%m%d-%H%M%S") + "-" + kind
    run_id, suffix = stem, 1
    while True:
        run_dir = os.path.join(state_root, run_id)
        try:
            os.mkdir(run_dir, 0o700)
            break
        except FileExistsError:
            suffix += 1
            run_id = stem + "-" + str(suffix)
    stamp = now_iso(moment)
    state = {"schema_version": SCHEMA_VERSION, "kind": kind, "run_id": run_id, "status": "running",
             "repository": repository, "user": user, "options": options or {},
             "created_at": stamp, "updated_at": stamp, "extra": extra or {},
             "items": {str(key): value for key, value in (items or {}).items()}}
    write_json(os.path.join(run_dir, STATE_FILE), state)
    return run_dir


def load(run_dir):
    path = os.path.join(run_dir, STATE_FILE)
    try:
        with open(path, encoding="utf-8") as stream:
            state = json.load(stream)
    except (OSError, ValueError) as exc:
        raise StateError("Cannot read run state " + path + ": " + str(exc)) from exc
    if (not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION
            or state.get("status") not in STATUSES or not isinstance(state.get("items"), dict)):
        raise StateError("Run state " + path + " is not a supported run.")
    return state


def update(run_dir, fn):
    """Apply fn to a loaded state and write it back atomically; return the new state.

    fn may mutate the state in place or return a replacement. An exception in fn
    leaves state.json untouched.
    """
    state = load(run_dir)
    result = fn(state)
    if result is not None:
        state = result
    state["updated_at"] = now_iso()
    write_json(os.path.join(run_dir, STATE_FILE), state)
    return state


def set_item(run_dir, item_id, **fields):
    def change(state):
        current = state["items"].get(str(item_id))
        if current is None:
            raise StateError("Run has no item " + str(item_id) + ".")
        current.update(fields)
    return update(run_dir, change)["items"][str(item_id)]


def set_status(run_dir, status):
    if status not in STATUSES:
        raise StateError("status must be one of " + ", ".join(STATUSES) + ".")

    def change(state):
        state["status"] = status
    return update(run_dir, change)


def _run_order(run):
    """Newest first: creation time, then the run id stem, then its numeric suffix (no suffix counts as 1)."""
    match = re.fullmatch(r"(.*?)(?:-([0-9]+))?", run["run_id"].split("-", 2)[-1])
    suffix = int(match.group(2)) if match and match.group(2) else 1
    return run["created_at"], run["run_id"][:15], suffix


def find_unfinished(state_root, kind, unreadable=None):
    """Running runs of the kind under the root, newest first.

    Runs whose state cannot be read are appended to unreadable (as {"run_dir", "reason"}) when a list is given,
    so a damaged run is reported rather than silently dropped.
    """
    runs = []
    try:
        names = os.listdir(state_root)
    except OSError:
        return runs
    for name in names:
        if not re.fullmatch(run_id_pattern(kind), name):
            continue
        run_dir = os.path.join(state_root, name)
        try:
            state = load(run_dir)
        except StateError as exc:
            if unreadable is not None:
                unreadable.append({"run_dir": run_dir, "reason": str(exc)})
            continue
        if state.get("kind") == kind and state.get("status") == "running":
            runs.append({"run_id": state["run_id"], "run_dir": run_dir,
                         "created_at": state.get("created_at", "")})
    runs.sort(key=_run_order, reverse=True)
    return runs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("root", help="print the state root")
    p.add_argument("--kind", required=True)
    p.add_argument("--repo", required=True)
    p = sub.add_parser("find-unfinished", help="list unfinished runs, newest first")
    p.add_argument("--kind", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("run_id", nargs="?")
    p.add_argument("--latest", action="store_true", help="select the newest unfinished run")
    p = sub.add_parser("abandon", help="mark a run abandoned")
    p.add_argument("run_dir")
    p = sub.add_parser("show", help="print state.json")
    p.add_argument("run_dir")
    args = parser.parse_args(argv)
    try:
        if args.command == "root":
            print(json.dumps({"root": root(args.kind, args.repo)}))
        elif args.command == "find-unfinished":
            state_root = root(args.kind, args.repo)
            unreadable = []
            runs = find_unfinished(state_root, args.kind, unreadable)
            if args.run_id or args.latest:
                chosen = [run for run in runs if run["run_id"] == args.run_id] if args.run_id else runs[:1]
                if not chosen:
                    label = " '" + args.run_id + "'" if args.run_id else ""
                    damaged = ("; unreadable runs: " + ", ".join(os.path.basename(u["run_dir"]) for u in unreadable)
                               if unreadable else "")
                    raise StateError("no unfinished " + args.kind + " run" + label + "; unfinished runs: "
                                     + (", ".join(run["run_id"] for run in runs) or "none") + damaged)
                print(json.dumps(chosen[0]))
            else:
                print(json.dumps({"root": state_root, "runs": runs, "unreadable": unreadable}))
        elif args.command == "abandon":
            with locked(args.run_dir):
                state = set_status(args.run_dir, "abandoned")
            print(json.dumps({"run_id": state["run_id"], "status": state["status"]}))
        else:
            print(json.dumps(load(args.run_dir), indent=2))
    except StateError as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
