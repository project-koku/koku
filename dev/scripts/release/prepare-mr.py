#!/usr/bin/env python3
"""
prepare-mr.py — Prepare app-interface branch for koku release MR.

Usage:
    prepare-mr.py deploy --target-sha <sha>
    prepare-mr.py migration --target-sha <sha> --type <pg|trino> [--command <cmd>] [--invocation <num>]

Creates the branch and commit locally. Does NOT push (that requires human approval).
Prints branch name, diff summary, push command, and MR URL.

Env:
    APP_INTERFACE_DIR           — path to app-interface clone
                                  (default: ~/development/app-interface)
    APP_INTERFACE_FORK_REMOTE   — git remote name for your fork (optional;
                                  auto-detected from remotes if unset)
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

APP_INTERFACE = Path(os.environ.get("APP_INTERFACE_DIR", Path.home() / "development" / "app-interface")).expanduser()
DEPLOY_FILE = APP_INTERFACE / "data/services/insights/hccm/deploy-clowder.yml"
FORK_REMOTE_ENV = os.environ.get("APP_INTERFACE_FORK_REMOTE", "").strip()

_GIT_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)
_BRANCH_RE = re.compile(r"^hccm-prod(-migrations)?-[0-9a-f]{7}$", re.IGNORECASE)
_COMMIT_MSG_RE = re.compile(r"^hccm: promote [0-9a-f]{7}( migrations)? to prod$", re.IGNORECASE)


def _exit_on_git_failure(label: str, result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode == 0:
        return
    print(f"ERROR running: {label}", file=sys.stderr)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    sys.exit(1)


def validate_target_sha(sha: str) -> str:
    if not _SHA_RE.fullmatch(sha):
        print("ERROR: --target-sha must be a git commit SHA (7-40 hex chars)", file=sys.stderr)
        sys.exit(1)
    return sha.lower()


def _validate_git_remote_name(remote: str) -> str:
    if not _GIT_NAME_RE.fullmatch(remote):
        print(f"ERROR: invalid git remote name: {remote!r}", file=sys.stderr)
        sys.exit(1)
    return remote


def _validate_branch_name(branch: str) -> str:
    if not _BRANCH_RE.fullmatch(branch):
        print(f"ERROR: invalid branch name: {branch!r}", file=sys.stderr)
        sys.exit(1)
    return branch


def _validate_commit_message(message: str) -> str:
    if not _COMMIT_MSG_RE.fullmatch(message):
        print(f"ERROR: invalid commit message: {message!r}", file=sys.stderr)
        sys.exit(1)
    return message


def git_list_remotes() -> str:
    result = subprocess.run(
        ["git", "remote"],
        shell=False,
        cwd=APP_INTERFACE,
        capture_output=True,
        text=True,
        check=False,
    )
    _exit_on_git_failure("git remote", result)
    return result.stdout.strip()


def git_remote_url(remote: str) -> str:
    remote = _validate_git_remote_name(remote)
    result = subprocess.run(
        ["git", "remote", "get-url", remote],
        shell=False,
        cwd=APP_INTERFACE,
        capture_output=True,
        text=True,
        check=False,
    )
    _exit_on_git_failure(f"git remote get-url {remote}", result)
    return result.stdout.strip()


def git_switch_new_branch(branch: str, base: str = "origin/master") -> None:
    branch = _validate_branch_name(branch)
    if base != "origin/master":
        print(f"ERROR: unsupported base branch: {base!r}", file=sys.stderr)
        sys.exit(1)
    result = subprocess.run(
        ["git", "switch", "--no-track", "-c", branch, base],
        shell=False,
        cwd=APP_INTERFACE,
        capture_output=True,
        text=True,
        check=False,
    )
    _exit_on_git_failure(f"git switch -c {branch}", result)


def git_add_deploy_file() -> None:
    result = subprocess.run(
        ["git", "add", str(DEPLOY_FILE)],
        shell=False,
        cwd=APP_INTERFACE,
        capture_output=True,
        text=True,
        check=False,
    )
    _exit_on_git_failure(f"git add {DEPLOY_FILE}", result)


def git_commit(message: str) -> None:
    message = _validate_commit_message(message)
    result = subprocess.run(
        ["git", "commit", "-m", message],
        shell=False,
        cwd=APP_INTERFACE,
        capture_output=True,
        text=True,
        check=False,
    )
    _exit_on_git_failure("git commit", result)


def require_app_interface():
    if not (APP_INTERFACE / ".git").is_dir():
        print(f"ERROR: app-interface not found at: {APP_INTERFACE}", file=sys.stderr)
        print("Set APP_INTERFACE_DIR to your local clone.", file=sys.stderr)
        sys.exit(1)
    if not DEPLOY_FILE.is_file():
        print(f"ERROR: deploy file not found: {DEPLOY_FILE}", file=sys.stderr)
        sys.exit(1)


def resolve_fork_remote() -> str:
    if FORK_REMOTE_ENV:
        _validate_git_remote_name(FORK_REMOTE_ENV)
        git_remote_url(FORK_REMOTE_ENV)
        return FORK_REMOTE_ENV

    remotes = git_list_remotes()
    for name in remotes.split():
        url = git_remote_url(name)
        match = re.search(r"gitlab\.cee\.redhat\.com[:/]([^/]+)/app-interface", url)
        if match and match.group(1) != "service":
            return name

    print("ERROR: Could not find an app-interface fork remote.", file=sys.stderr)
    print("Add your fork and set APP_INTERFACE_FORK_REMOTE, e.g.:", file=sys.stderr)
    print(
        f"  git -C {APP_INTERFACE} remote add my-fork " "git@gitlab.cee.redhat.com:<user>/app-interface.git",
        file=sys.stderr,
    )
    print("  export APP_INTERFACE_FORK_REMOTE=my-fork", file=sys.stderr)
    sys.exit(1)


def fork_mr_new_base_url(remote: str) -> str:
    url = git_remote_url(remote)
    match = re.search(r"gitlab\.cee\.redhat\.com[:/]([^/]+)/app-interface", url)
    if not match:
        print(f"ERROR: Could not parse fork URL: {url}", file=sys.stderr)
        sys.exit(1)
    user = match.group(1)
    return f"https://gitlab.cee.redhat.com/{user}/app-interface/-/merge_requests/new"


def read_deploy():
    return DEPLOY_FILE.read_text()


def write_deploy(content, original):
    if original.endswith("\n") and not content.endswith("\n"):
        content += "\n"
    elif not original.endswith("\n") and content.endswith("\n"):
        content = content.rstrip("\n")
    DEPLOY_FILE.write_text(content)


def get_prod_ref(content):
    in_prod = False
    for line in content.splitlines():
        if "hccm-prod.yml" in line:
            in_prod = True
            continue
        if in_prod and line.strip().startswith("ref:") and "$ref" not in line:
            return line.split("ref:")[1].strip()
    raise ValueError("Could not find prod ref in deploy-clowder.yml")


def get_field(content, field, section_marker="hccm-prod.yml"):
    in_section = False
    for line in content.splitlines():
        if section_marker in line:
            in_section = True
        if in_section and f"{field}:" in line and not line.strip().startswith("#"):
            return line.split(f"{field}:")[1].strip().strip('"')
    return None


def set_field(content, field, new_value, section_marker="hccm-prod.yml"):
    lines = content.splitlines()
    in_section = False
    updated = False
    for i, line in enumerate(lines):
        if section_marker in line:
            in_section = True
        if in_section and f"{field}:" in line and not line.strip().startswith("#"):
            indent = len(line) - len(line.lstrip())
            lines[i] = " " * indent + f"{field}: {new_value}"
            updated = True
            break
    if not updated:
        raise ValueError(f"Could not find field {field} in prod section")
    return "\n".join(lines)


def set_prod_ref(content, new_sha):
    in_prod = False
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if "hccm-prod.yml" in line:
            in_prod = True
        if in_prod and line.strip().startswith("ref:") and "$ref" not in line:
            indent = len(line) - len(line.lstrip())
            lines[i] = " " * indent + f"ref: {new_sha}"
            break
    return "\n".join(lines)


def git_switch_branch(branch, base="origin/master"):
    print("Fetching latest origin/master (requires VPN)...")
    result = subprocess.run(
        ["git", "fetch", "origin"],
        shell=False,
        cwd=APP_INTERFACE,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print("", file=sys.stderr)
        print("ERROR: git fetch origin failed.", file=sys.stderr)
        print(
            "Make sure you are connected to the Red Hat VPN before running this script.",
            file=sys.stderr,
        )
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    print("Fetch OK.")
    git_switch_new_branch(branch, base)


def print_section(title):
    print(f"\n{'═' * 50}")
    print(f"  {title}")
    print(f"{'═' * 50}")


def cmd_deploy(args):
    sha = args.target_sha
    short = sha[:7]
    branch = f"hccm-prod-{short}"
    commit_msg = f"hccm: promote {short} to prod"
    fork_remote = resolve_fork_remote()
    mr_base = fork_mr_new_base_url(fork_remote)

    print_section(f"PREPARE DEPLOY MR — {short}")

    content = read_deploy()
    old_ref = get_prod_ref(content)

    print(f"\nApp-interface   : {APP_INTERFACE}")
    print(f"Fork remote     : {fork_remote}")
    print(f"Current prod ref: {old_ref}")
    print(f"New ref         : {sha}")
    print(f"Branch          : {branch}")
    print(f"Commit message  : {commit_msg}")

    print("\n── Change preview ──")
    print(f"  - ref: {old_ref}")
    print(f"  + ref: {sha}")

    if args.dry_run:
        print("\n[dry-run] No changes applied.")
        return

    git_switch_branch(branch)
    content = read_deploy()
    new_content = set_prod_ref(content, sha)
    write_deploy(new_content, content)
    git_add_deploy_file()
    git_commit(commit_msg)

    mr_url = f"{mr_base}?merge_request[source_branch]={branch}" f"&merge_request[title]=hccm:+promote+{short}+to+prod"

    print_section("READY TO PUSH")
    print("\nRun this to push:")
    print(f"  git -C {APP_INTERFACE} push {fork_remote} {branch}")
    print("\nThen open MR at:")
    print(f"  {mr_url}")
    print("\nPost in #crc-cost-mgmt-sre: " "'Review needed for hccm prod deploy @crc-cost-mgmt-dev'")


def cmd_migration(args):
    sha = args.target_sha
    short = sha[:7]
    mtype = args.type
    branch = f"hccm-prod-migrations-{short}"
    commit_msg = f"hccm: promote {short} migrations to prod"
    invocation = args.invocation or "01"
    fork_remote = resolve_fork_remote()
    mr_base = fork_mr_new_base_url(fork_remote)

    print_section(f"PREPARE MIGRATION MR — {mtype.upper()} — {short}")

    content = read_deploy()
    new_inv = None

    if mtype == "pg":
        current_tag = get_field(content, "DBM_IMAGE_TAG")
        current_inv = get_field(content, "DBM_INVOCATION")
        if current_tag == short:
            new_inv = f'"{int(current_inv or 0) + 1:02d}"'
        else:
            new_inv = f'"{invocation}"'

        print(f"\nApp-interface   : {APP_INTERFACE}")
        print(f"Fork remote     : {fork_remote}")
        print(f"DBM_IMAGE_TAG : {current_tag} → {short}")
        print(f"DBM_INVOCATION: {current_inv} → {new_inv}")

    elif mtype == "trino":
        if not args.command:
            print("ERROR: --command is required for Trino migrations", file=sys.stderr)
            print(
                "  Example: --command 'python koku/manage.py migrate_trino_tables ...'",
                file=sys.stderr,
            )
            sys.exit(1)

        current_tag = get_field(content, "MGMT_IMAGE_TAG")
        current_inv = get_field(content, "MGMT_INVOCATION")
        if current_tag == short:
            new_inv = f'"{int(current_inv or 0) + 1:02d}"'
        else:
            new_inv = f'"{invocation}"'

        print(f"\nApp-interface   : {APP_INTERFACE}")
        print(f"Fork remote     : {fork_remote}")
        print(f"MGMT_IMAGE_TAG : {current_tag} → {short}")
        print(f"MGMT_INVOCATION: {current_inv} → {new_inv}")
        print(f"MGMT_COMMAND   : {args.command}")
    else:
        print(f"Unknown migration type: {mtype}", file=sys.stderr)
        sys.exit(1)

    print(f"\nBranch         : {branch}")
    print(f"Commit message : {commit_msg}")

    if args.dry_run:
        print("\n[dry-run] No changes applied.")
        return

    git_switch_branch(branch)
    content = read_deploy()
    if mtype == "pg":
        new_content = set_field(content, "DBM_IMAGE_TAG", short)
        new_content = set_field(new_content, "DBM_INVOCATION", new_inv)
    else:
        new_content = set_field(content, "MGMT_IMAGE_TAG", short)
        new_content = set_field(new_content, "MGMT_INVOCATION", new_inv)
        new_content = set_field(new_content, "MGMT_COMMAND", args.command)
    write_deploy(new_content, content)
    git_add_deploy_file()
    git_commit(commit_msg)

    mr_url = (
        f"{mr_base}?merge_request[source_branch]={branch}"
        f"&merge_request[title]=hccm:+promote+{short}+migrations+to+prod"
    )

    print_section("READY TO PUSH")
    print("\nRun this to push:")
    print(f"  git -C {APP_INTERFACE} push {fork_remote} {branch}")
    print("\nThen open MR at:")
    print(f"  {mr_url}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["deploy", "migration"])
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--type", choices=["pg", "trino"])
    parser.add_argument("--command", default="")
    parser.add_argument("--invocation", default="")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without applying them",
    )

    args = parser.parse_args()
    require_app_interface()
    args.target_sha = validate_target_sha(args.target_sha)

    if args.command == "deploy":
        cmd_deploy(args)
    elif args.command == "migration":
        if not args.type:
            print(
                "ERROR: --type pg|trino is required for migration command",
                file=sys.stderr,
            )
            sys.exit(1)
        cmd_migration(args)


if __name__ == "__main__":
    main()
