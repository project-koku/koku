#!/usr/bin/env python3
"""Session start hook: load .env and check git branch freshness."""
import json
import os
import subprocess


def load_dotenv(path):
    """Parse .env file and return dict of key=value pairs."""
    env = {}
    if not os.path.isfile(path):
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:]
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            env[key] = value
    return env


def git_branch_status():
    """Check if current branch is ahead/behind remote."""
    try:
        subprocess.run(["git", "fetch", "--quiet"], capture_output=True, timeout=10)
        result = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        parts = result.stdout.strip().split()
        if len(parts) == 2:
            ahead, behind = int(parts[0]), int(parts[1])
            if behind > 0:
                return f"⚠ Branch is {behind} commits behind remote"
            if ahead > 0:
                return f"{ahead} commits ahead of remote"
        return None
    except Exception:
        return None


def migration_status():
    """Count pending migrations."""
    try:
        result = subprocess.run(
            ["python", "koku/manage.py", "showmigrations", "--list"],
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "DJANGO_READ_DOT_ENV_FILE": "True"},
        )
        if result.returncode != 0:
            return None
        pending = sum(1 for line in result.stdout.splitlines() if "[ ]" in line)
        if pending > 0:
            return f"{pending} pending migrations"
        return None
    except Exception:
        return None


def main():
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    messages = []

    dotenv_path = os.path.join(project_dir, ".env")
    env_vars = load_dotenv(dotenv_path)
    if env_vars and env_file:
        with open(env_file, "a") as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
        messages.append(f"Loaded {len(env_vars)} vars from .env")
    elif not os.path.isfile(dotenv_path):
        messages.append("No .env file found — copy .env.example if needed")

    branch_msg = git_branch_status()
    if branch_msg:
        messages.append(branch_msg)

    context = " | ".join(messages) if messages else "koku session ready"

    output = {"hookSpecificOutput": {"additionalContext": context}}
    print(json.dumps(output))


if __name__ == "__main__":
    main()
