"""
update_readme.py
Fetches live market data and recent GitHub commit activity,
then safely patches dynamic sections using string splitting.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

README_PATH = "README.md"
GITHUB_USER = "Vru-Jain"
INDICES = [
    ("S&P 500",  "^GSPC"),
    ("NASDAQ",   "^IXIC"),
    ("Nifty 50", "^NSEI"),
    ("Gold",     "GC=F"),
]
WATCH_REPOS = []

def arrow(change: float) -> str:
    if change > 0:
        return f"^+{change:.2f}%"
    if change < 0:
        return f"v{change:.2f}%"
    return f"-> {change:.2f}%"

def patch_section(content: str, marker: str, new_body: str) -> str:
    """Replace content between markers using safe string splitting."""
    start_tag = f"<!-- START {marker} -->"
    end_tag = f"<!-- END {marker} -->"
    
    if start_tag in content and end_tag in content:
        before = content.split(start_tag, 1)[0]
        after = content.split(end_tag, 1)[1]
        return f"{before}{start_tag}\n{new_body}\n{end_tag}{after}"
    
    print(f"  Warning: marker {marker} not found in README.")
    return content

def github_api(path: str, token: str):
    url = f"https://api.github.com{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  GitHub API error for {path}: {e}")
        return None

def build_market_block() -> str:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not YFINANCE_AVAILABLE:
        return f"| Index | Price | Change |\n|---|---|---|\n| N/A | N/A | `yfinance` missing |\n\n<sub>Last updated: {now_utc}</sub>"

    rows = []
    for name, ticker in INDICES:
        try:
            data = yf.Ticker(ticker)
            hist = data.history(period="5d")
            if len(hist) < 2:
                rows.append(f"| {name} | N/A | no data |")
                continue
            prev_close = hist["Close"].iloc[-2]
            last_close = hist["Close"].iloc[-1]
            pct = (last_close - prev_close) / prev_close * 100
            rows.append(f"| {name} | `{last_close:,.2f}` | {arrow(pct)} |")
        except Exception as e:
            rows.append(f"| {name} | N/A | fetch error |")

    table = "\n".join(["| Index | Price | Change |", "|---|---|---|"] + rows)
    return f"{table}\n\n<sub>Last updated: {now_utc}</sub>"

def build_activity_block(token: str) -> str:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    repos = list(WATCH_REPOS)
    if not repos:
        data = github_api(f"/users/{GITHUB_USER}/repos?sort=pushed&per_page=6", token)
        if data:
            repos = [r["full_name"] for r in data if not r.get("fork", False)]

    if not repos:
        return f"_Could not retrieve repository list._\n\n<sub>Last updated: {now_utc}</sub>"

    events = []
    for repo in repos[:5]:
        commits = github_api(f"/repos/{repo}/commits?per_page=2", token)
        if not commits:
            continue
        for commit in commits:
            sha = commit.get("sha", "")[:7]
            message = commit.get("commit", {}).get("message", "").splitlines()[0]
            if len(message) > 72:
                message = message[:69] + "..."
            repo_short = repo.split("/")[-1]
            url = f"https://github.com/{repo}/commit/{commit.get('sha', '')}"
            events.append(f"- [`{sha}`]({url}) **{repo_short}** : {message}")
        if len(events) >= 5:
            break

    if not events:
        return f"_No recent public commits found._\n\n<sub>Last updated: {now_utc}</sub>"

    body = "\n".join(events[:5])
    return f"{body}\n\n<sub>Last updated: {now_utc}</sub>"

def main():
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("Error: GITHUB_TOKEN environment variable is not set.")
        sys.exit(1)

    if not os.path.exists(README_PATH):
        print(f"Error: {README_PATH} not found in working directory.")
        sys.exit(1)

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    print("Fetching market data...")
    market_block = build_market_block()

    print("Fetching recent activity...")
    activity_block = build_activity_block(token)

    content = patch_section(content, "MARKET_DATA", market_block)
    content = patch_section(content, "ACTIVITY", activity_block)

    if len(content.encode('utf-8')) > 1000000:
        print("CRITICAL: Python string expanded beyond 1MB. Aborting disk write to prevent git failure.")
        sys.exit(1)

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print("README.md updated successfully.")

if __name__ == "__main__":
    main()
