#!/usr/bin/env python3
"""Daily Slack digest: COST Jira column counts + open PRs for the koku team."""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "https://redhat.atlassian.net").rstrip("/")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in {"1", "true", "yes"}
FORCE_RUN = os.environ.get("FORCE_RUN", "").lower() in {"1", "true", "yes"}

TIMEZONE = ZoneInfo("Europe/Lisbon")
POST_HOUR = 7

JIRA_PROJECT = "COST"
# Cost Management Dev Board — counts must use this board, not project-wide status.
JIRA_BOARD_ID = "1189"
# Board column label → Jira status name (from board column config)
JIRA_COLUMNS = (
    ("In Progress", "In Progress"),
    ("QA Review", "Review"),
    ("Release to Prod Pending", "Release Pending"),
)

GITHUB_OWNER = "project-koku"
GITHUB_REPO = "koku"

# Populated from secrets DIGEST_JIRA_ACCOUNT_IDS / DIGEST_GITHUB_LOGINS at runtime.
JIRA_TEAM_ACCOUNT_IDS: tuple[str, ...] = ()
TEAM_LOGINS: set[str] = set()


def parse_csv_env(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def load_team_config() -> None:
    """Load team identity lists from env (repo secrets), not hardcoded in source."""
    global JIRA_TEAM_ACCOUNT_IDS, TEAM_LOGINS
    JIRA_TEAM_ACCOUNT_IDS = tuple(parse_csv_env("DIGEST_JIRA_ACCOUNT_IDS"))
    TEAM_LOGINS = {login.lower() for login in parse_csv_env("DIGEST_GITHUB_LOGINS")}


def jira_swimlane_jql() -> str:
    if not JIRA_TEAM_ACCOUNT_IDS:
        raise RuntimeError("DIGEST_JIRA_ACCOUNT_IDS is empty")
    assignees = ", ".join(JIRA_TEAM_ACCOUNT_IDS)
    return f"assignee in ({assignees}) " "AND (component not in (UI, Docs) OR component is EMPTY)"


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def lisbon_now() -> datetime:
    return datetime.now(tz=TIMEZONE)


def should_run() -> bool:
    if FORCE_RUN:
        return True
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return True
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        return lisbon_now().hour == POST_HOUR
    return True


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    parse_json: bool = True,
) -> dict | list:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if headers:
        for key, value in headers.items():
            req.add_header(key, value)
    # Avoid leaking Slack webhook secrets into Actions logs on HTTP errors.
    log_url = "hooks.slack.com/services/***" if "hooks.slack.com" in url else url
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            if not parse_json:
                return {}
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {log_url} failed ({exc.code}): {detail}") from exc


def jira_headers() -> dict[str, str]:
    token = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def jira_count_on_board(status: str) -> int:
    """Count Backend and QE swimlane issues on the Dev Board for a status."""
    # Board WIP uses issueCountExclSubs — mirror that here.
    jql = f'status = "{status}" AND issuetype != Sub-task AND {jira_swimlane_jql()}'
    params = urllib.parse.urlencode(
        {
            "jql": jql,
            "maxResults": 1,
            "fields": "summary",
        }
    )
    url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{JIRA_BOARD_ID}/issue?{params}"
    data = request_json(url, headers=jira_headers())
    if isinstance(data, dict) and isinstance(data.get("total"), int):
        return data["total"]
    raise RuntimeError(f"Unexpected board issue response for status={status!r}: {data!r}")


def fetch_jira_columns() -> list[tuple[str, str, int]]:
    rows = []
    for label, status in JIRA_COLUMNS:
        rows.append((label, status, jira_count_on_board(status)))
    return rows


def gh_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def fetch_open_pulls() -> list[dict]:
    pulls: list[dict] = []
    page = 1
    while page <= 10:
        url = (
            f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls" f"?state=open&per_page=100&page={page}"
        )
        batch = request_json(url, headers=gh_headers())
        if not isinstance(batch, list) or not batch:
            break
        pulls.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return pulls


def pull_needs_review(number: int) -> tuple[bool, list[str]]:
    base = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls/{number}"
    pr = request_json(base, headers=gh_headers())
    reviews = request_json(f"{base}/reviews", headers=gh_headers())
    if not isinstance(pr, dict) or not isinstance(reviews, list):
        raise RuntimeError(f"Unexpected GitHub response shape for PR #{number}")

    if pr.get("draft"):
        return False, []

    requested = [u["login"] for u in (pr.get("requested_reviewers") or [])]
    latest: dict[str, str] = {}
    for review in reviews:
        user = (review.get("user") or {}).get("login")
        state = review.get("state")
        if not user or state == "COMMENTED":
            continue
        latest[user] = state

    has_approval = "APPROVED" in latest.values()
    has_changes_requested = "CHANGES_REQUESTED" in latest.values()
    # REST list/detail often omits a useful review_decision; derive needs from reviews.
    # Keep CHANGES_REQUESTED visible even if another reviewer already approved.
    needs = has_changes_requested or bool(requested) or not has_approval
    return needs, requested


def fetch_team_pulls() -> tuple[list[dict], list[dict]]:
    open_team = []
    for pr in fetch_open_pulls():
        login = ((pr.get("user") or {}).get("login") or "").lower()
        if login not in TEAM_LOGINS:
            continue
        needs, requested = pull_needs_review(pr["number"])
        item = {
            "number": pr["number"],
            "title": pr["title"],
            "url": pr["html_url"],
            "author": pr["user"]["login"],
            "draft": bool(pr.get("draft")),
            "needs_review": needs and not pr.get("draft"),
            "requested_reviewers": requested,
        }
        open_team.append(item)
    open_team.sort(key=lambda p: p["number"])
    needs_review = [p for p in open_team if p["needs_review"]]
    return open_team, needs_review


def build_message(
    jira_rows: list[tuple[str, str, int]],
    open_prs: list[dict],
    needs_review: list[dict],
) -> str:
    date_label = lisbon_now().strftime("%a, %d %b %Y")  # English via C locale in Actions
    jira_lines = "\n".join(f"• *{label}*: {count}" for label, _status, count in jira_rows)

    if needs_review:
        review_lines = "\n".join(
            (
                f"• <{pr['url']}|#{pr['number']}> — {pr['title']} (@{pr['author']})"
                + (
                    f" — waiting on {', '.join('@' + r for r in pr['requested_reviewers'])}"
                    if pr["requested_reviewers"]
                    else ""
                )
            )
            for pr in needs_review
        )
    else:
        review_lines = "_No PRs waiting for review._"

    return "\n".join(
        [
            f"*koku daily digest* · {date_label}",
            "",
            f"*Jira* (`{JIRA_PROJECT}` · Backend and QE)",
            jira_lines,
            "",
            f"*GitHub* (`{GITHUB_OWNER}/{GITHUB_REPO}`)",
            f"Open team PRs: *{len(open_prs)}*",
            f"Needs review: *{len(needs_review)}*",
            review_lines,
        ]
    )


def post_slack(text: str) -> None:
    # Incoming Webhooks return plain-text "ok", not JSON.
    request_json(
        SLACK_WEBHOOK_URL,
        method="POST",
        body={"text": text},
        parse_json=False,
    )


def main() -> None:
    if not should_run():
        print(f"Skipping: Lisbon hour is {lisbon_now().hour}, want {POST_HOUR}")
        return

    missing = [
        name
        for name, value in (
            ("JIRA_EMAIL", JIRA_EMAIL),
            ("JIRA_API_TOKEN", JIRA_API_TOKEN),
            ("DIGEST_JIRA_ACCOUNT_IDS", os.environ.get("DIGEST_JIRA_ACCOUNT_IDS", "")),
            ("DIGEST_GITHUB_LOGINS", os.environ.get("DIGEST_GITHUB_LOGINS", "")),
            ("SLACK_WEBHOOK_URL", SLACK_WEBHOOK_URL if not DRY_RUN else "ok"),
        )
        if not value
    ]
    if missing:
        die(f"Missing required env: {', '.join(missing)}")

    load_team_config()

    print("Fetching Jira column counts…")
    jira_rows = fetch_jira_columns()
    for label, status, count in jira_rows:
        print(f"  {label} ({status}): {count}")

    print("Fetching team pull requests…")
    open_prs, needs_review = fetch_team_pulls()
    print(f"  open={len(open_prs)} needs_review={len(needs_review)}")

    message = build_message(jira_rows, open_prs, needs_review)
    if DRY_RUN:
        print("\n--- DRY RUN ---\n")
        print(message)
        return

    print("Posting to Slack…")
    post_slack(message)
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - surface failure clearly in Actions logs
        die(str(exc))
