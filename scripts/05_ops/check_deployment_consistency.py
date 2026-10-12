#!/usr/bin/env python3
"""Read-only audit of Git scripts, the remote checkout, and deployed copies.

This command never fetches, copies files, or restarts services. Network access is
limited to ``git ls-remote`` and one SSH invocation running a read-only collector.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import stat
import subprocess
import sys


SCOPES = ("scripts/", ".agents/")
DEFAULT_REPO = Path(__file__).resolve().parents[2]


def run(command, *, cwd=None, input=None):
    try:
        result = subprocess.run(
            command, cwd=cwd, input=input, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=60,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{shlex.join(map(str, command))}: timed out after 60 seconds") from error
    if result.returncode:
        error = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"{shlex.join(map(str, command))}: {error or 'command failed'}")
    return result.stdout


def git(repo, *arguments):
    return run(["git", "-C", str(repo), *arguments])


def fingerprint(path):
    """Hash Git-style symlink contents; do not follow a deployed symlink."""
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            data = os.fsencode(os.readlink(path))
            kind, executable = "symlink", False
        elif stat.S_ISREG(mode):
            data = path.read_bytes()
            kind, executable = "file", bool(mode & 0o111)
        else:
            return {"status": "error", "error": "not a regular file or symlink"}
        return {
            "status": "ok", "sha256": hashlib.sha256(data).hexdigest(),
            "executable": executable, "kind": kind,
        }
    except FileNotFoundError:
        return {"status": "missing"}
    except OSError as error:
        return {"status": "error", "error": str(error)}


def split_paths(output):
    return [os.fsdecode(value) for value in output.split(b"\0") if value]


def dirty_paths(output):
    """Parse porcelain -z, including both names in a tracked rename."""
    tokens = split_paths(output)
    paths = []
    index = 0
    while index < len(tokens):
        record = tokens[index]
        paths.append(record[3:])
        if "R" in record[:2] or "C" in record[:2]:
            index += 1
            if index < len(tokens):
                paths.append(tokens[index])
        index += 1
    return sorted(set(paths))


def relative_path(value, label):
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError(f"{label} must be a nonempty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) == ".":
        raise ValueError(f"{label} must stay inside its root: {value!r}")
    return str(path)


def read_manifest(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    for group in ("runtime_copies", "local_copies"):
        entries = manifest.get(group, [])
        if not isinstance(entries, list):
            raise ValueError(f"manifest {group} must be a list")
        for entry in entries:
            for key in ("source", "target"):
                entry[key] = relative_path(entry.get(key), f"{group}.{key}")
    exclusions = manifest.get("excluded_remote_files", [])
    if not isinstance(exclusions, list):
        raise ValueError("manifest excluded_remote_files must be a list")
    for entry in exclusions:
        entry["path"] = relative_path(entry.get("path"), "excluded_remote_files.path")
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            raise ValueError("each excluded_remote_files entry needs a reason")
    return manifest


# All variable data is embedded below as a Python string containing JSON. Neither
# repository paths nor manifest targets are interpolated into the remote shell.
REMOTE_COLLECTOR = r'''
import hashlib, json, os, pathlib, stat, subprocess
payload = json.loads(__PAYLOAD_JSON__)
repo = pathlib.Path(payload["repo"])
home = pathlib.Path(payload["home"])
def git(*args):
    result = subprocess.run(["git", "-C", str(repo), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout
def paths(data):
    return [os.fsdecode(x) for x in data.split(b"\0") if x]
def snapshot(path):
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            data, kind, executable = os.fsencode(os.readlink(path)), "symlink", False
        elif stat.S_ISREG(mode):
            data, kind, executable = path.read_bytes(), "file", bool(mode & 0o111)
        else:
            return {"status": "error", "error": "not a regular file or symlink"}
        return {"status": "ok", "sha256": hashlib.sha256(data).hexdigest(),
                "executable": executable, "kind": kind}
    except FileNotFoundError:
        return {"status": "missing"}
    except OSError as error:
        return {"status": "error", "error": str(error)}
tracked = paths(git("ls-files", "-z", "--", "scripts/", ".agents/", *payload["paths"]))
requested = sorted(set(tracked) | set(payload["paths"]))
dirty = git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--",
            "scripts/", ".agents/", *payload["paths"]).decode("utf-8", "surrogateescape")
result = {
    "head": git("rev-parse", "--verify", "HEAD").decode().strip(),
    "tracked_paths": tracked, "dirty_porcelain": dirty,
    "files": {path: snapshot(repo / path) for path in requested},
    "runtime_files": {path: snapshot(home / path) for path in payload["runtime_paths"]},
}
print(json.dumps(result, ensure_ascii=True))
'''


def collect_remote(args, paths, runtime_paths):
    payload = json.dumps({
        "repo": args.remote_repo, "home": args.remote_home,
        "paths": sorted(paths), "runtime_paths": sorted(set(runtime_paths)),
    }, ensure_ascii=True)
    script = REMOTE_COLLECTOR.replace("__PAYLOAD_JSON__", repr(payload))
    output = run([
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        "--", args.host, "python3", "-",
    ], input=script.encode("utf-8"))
    return json.loads(output)


def compare(checks, category, source, target, expected, actual, *, check_mode=True):
    entry = {"category": category, "source": source, "target": target}
    entry.update(expected=expected, actual=actual)
    if expected.get("status") != "ok" or actual.get("status") != "ok":
        entry["status"] = "missing" if "missing" in (
            expected.get("status"), actual.get("status")
        ) else "error"
        entry["detail"] = "source or target is unavailable"
    else:
        fields = ["sha256", "kind"] + (["executable"] if check_mode else [])
        different = [field for field in fields if expected.get(field) != actual.get(field)]
        entry["status"] = "mismatch" if different else "ok"
        if different:
            entry["detail"] = "different " + ", ".join(different)
    checks.append(entry)


def check_deployment(args):
    repo = Path(args.repo).resolve()
    manifest_path = Path(args.manifest) if args.manifest else repo / "scripts/deployment_manifest.json"
    manifest = read_manifest(manifest_path)
    checks = []
    head = git(repo, "rev-parse", "--verify", "HEAD").decode().strip()
    origin_head = git(repo, "rev-parse", "--verify", f"{args.origin_ref}^{{commit}}").decode().strip()
    refs = {"local_head": head, "origin_ref": args.origin_ref, "origin_ref_head": origin_head}

    def reference(source, target, expected, actual):
        checks.append({
            "category": "git_ref", "source": source, "target": target,
            "status": "ok" if expected == actual else "mismatch",
            "expected": expected, "actual": actual,
        })

    reference("local HEAD", args.origin_ref, head, origin_head)
    if args.skip_origin_network:
        refs["origin_network"] = "skipped"
        checks.append({"category": "git_ref", "source": "local HEAD", "target": "origin network",
                       "status": "skipped", "detail": "--skip-origin-network"})
    else:
        try:
            branch = args.origin_ref.removeprefix("origin/")
            remote_ref = f"refs/heads/{branch}"
            output = git(repo, "ls-remote", "--exit-code", "origin", remote_ref).decode().splitlines()
            matches = [line.split()[0] for line in output if line.split()[1] == remote_ref]
            if len(matches) != 1:
                raise RuntimeError(f"origin did not return exactly one {remote_ref}")
            refs["origin_actual_head"] = matches[0]
            reference("local HEAD", f"origin:{remote_ref}", head, matches[0])
        except RuntimeError as error:
            checks.append({"category": "git_ref", "source": "local HEAD", "target": "origin network",
                           "status": "error", "detail": str(error)})

    manifest_sources = sorted({entry["source"] for group in ("runtime_copies", "local_copies")
                               for entry in manifest.get(group, [])})
    audit_paths = [*SCOPES, *manifest_sources]
    local_paths = set(split_paths(git(repo, "ls-files", "-z", "--", *audit_paths)))
    origin_files = {}
    for record in git(repo, "ls-tree", "-rz", "--full-tree", origin_head, "--", *audit_paths).split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, _ = metadata.decode().split()
        path = os.fsdecode(raw_path)
        if kind != "blob":
            origin_files[path] = {"status": "error", "error": f"unsupported Git object {kind}"}
            continue
        content = git(repo, "show", f"{origin_head}:{path}")
        origin_files[path] = {
            "status": "ok", "sha256": hashlib.sha256(content).hexdigest(),
            "executable": mode == "100755", "kind": "symlink" if mode == "120000" else "file",
        }
    all_paths = local_paths | origin_files.keys()
    local_files = {path: fingerprint(repo / path) for path in all_paths}
    missing = {"status": "missing"}
    for path in sorted(all_paths):
        # Presence in the index is checked too, so an untracked replacement
        # cannot conceal a staged deletion from the origin inventory.
        actual = local_files[path] if path in local_paths else missing
        compare(checks, "repo_origin", f"{args.origin_ref}:{path}", str(repo / path),
                origin_files.get(path, missing), actual)

    local_dirty = dirty_paths(git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all",
                                  "--", *audit_paths))
    for path in local_dirty:
        checks.append({"category": "local_worktree", "source": f"HEAD:{path}",
                       "target": str(repo / path), "status": "dirty", "detail": "local worktree change"})

    remote = None
    try:
        remote = collect_remote(args, all_paths, [entry["target"] for entry in manifest.get("runtime_copies", [])])
        refs["remote_head"] = remote["head"]
        reference("local HEAD", f"{args.host}:{args.remote_repo} HEAD", head, remote["head"])
        remote_paths = set(remote["tracked_paths"])
        for path in sorted(all_paths | remote_paths):
            compare(checks, "repo_remote", str(repo / path),
                    f"{args.host}:{PurePosixPath(args.remote_repo) / path}",
                    local_files.get(path, missing) if path in local_paths else missing,
                    remote["files"].get(path, missing) if path in remote_paths else missing)
        remote_dirty = dirty_paths(remote["dirty_porcelain"].encode("utf-8", "surrogateescape"))
        for path in remote_dirty:
            checks.append({"category": "remote_worktree", "source": f"remote HEAD:{path}",
                           "target": f"{args.host}:{PurePosixPath(args.remote_repo) / path}",
                           "status": "dirty", "detail": "remote worktree change"})
    except (RuntimeError, ValueError, KeyError) as error:
        checks.append({"category": "remote_access", "source": str(repo), "target": args.host,
                       "status": "error", "detail": str(error)})
        remote = None
        remote_dirty = []

    for entry in manifest.get("runtime_copies", []):
        source, target = entry["source"], entry["target"]
        actual = remote["runtime_files"].get(target, missing) if remote else {
            "status": "error", "error": "remote collection unavailable",
        }
        compare(checks, "runtime_copy", str(repo / source),
                f"{args.host}:{PurePosixPath(args.remote_home) / target}",
                fingerprint(repo / source), actual)
    for entry in manifest.get("local_copies", []):
        compare(checks, "local_copy", str(repo / entry["source"]), str(repo / entry["target"]),
                fingerprint(repo / entry["source"]), fingerprint(repo / entry["target"]),
                check_mode=entry.get("check_mode", False))
    for entry in manifest.get("excluded_remote_files", []):
        checks.append({"category": "remote_exclusion", "source": str(manifest_path),
                       "target": f"{args.host}:{PurePosixPath(args.remote_home) / entry['path']}",
                       "status": "excluded", "detail": entry["reason"]})

    counts = dict(Counter(entry["status"] for entry in checks))
    failures = [entry for entry in checks if entry["status"] not in {"ok", "skipped", "excluded"}]
    return {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": not failures, "failure_count": len(failures),
        "repo": str(repo), "host": args.host, "manifest": str(manifest_path),
        "refs": refs, "counts": counts, "local_dirty_paths": local_dirty,
        "remote_dirty_paths": remote_dirty, "checks": checks,
    }


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo", default=str(DEFAULT_REPO), help="local Git checkout")
    result.add_argument("--host", default="admin@100.115.178.96")
    result.add_argument("--remote-repo", default="/home/admin/dgx-spark-deploy")
    result.add_argument("--remote-home", default="/home/admin")
    result.add_argument("--origin-ref", default="origin/main")
    result.add_argument("--manifest", help="defaults to <repo>/scripts/deployment_manifest.json")
    result.add_argument("--output", type=Path, help="write the complete JSON report locally")
    result.add_argument("--skip-origin-network", action="store_true",
                        help="offline fixtures only: skip the live git ls-remote check")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        report = check_deployment(args)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        report = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
                  "ok": False, "failure_count": 1, "counts": {"error": 1},
                  "checks": [{"category": "audit", "source": str(args.repo), "target": args.host,
                              "status": "error", "detail": str(error)}]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    counts = ", ".join(f"{status}={count}" for status, count in sorted(report["counts"].items()))
    print(f"Deployment consistency: {'PASS' if report['ok'] else 'FAIL'} ({counts})")
    for entry in report["checks"]:
        if entry["status"] not in {"ok", "skipped", "excluded"}:
            print(f"[{entry['status']}] {entry['source']} -> {entry['target']}: "
                  f"{entry.get('detail', 'different Git revisions')}")
    if args.skip_origin_network:
        print("Live origin verification was skipped (--skip-origin-network).")
    if args.output:
        print(f"JSON report: {args.output}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
