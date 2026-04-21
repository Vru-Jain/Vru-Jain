"""
update_readme.py
Fetches live market data (Yahoo Finance) and recent GitHub commit activity,
then patches the two dynamic sections in README.md using HTML comment markers.

Markers expected in README.md:
    <!-- MARKET_DATA_START --> ... <!-- MARKET_DATA_END -->
    <!-- ACTIVITY_START -->    ... <!-- ACTIVITY_END -->

Required environment variable:
    GITHUB_TOKEN  — fine-grained PAT or the default GITHUB_TOKEN from Actions
"""

import os
import re
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── Optional yfinance import ──────────────────────────────────────────────────
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


# ── Configuration ─────────────────────────────────────────────────────────────
README_PATH = "README.md"
GITHUB_USER = "Vru-Jain"

# Indices to track: (display_name, yfinance_ticker)
INDICES = [
    ("S&P 500",  "^GSPC"),
    ("NASDAQ",   "^IXIC"),
    ("Nifty 50", "^NSEI"),
    ("Gold",     "GC=F"),
]

# Repos to pull recent commits from (leave empty to auto-discover)
WATCH_REPOS = []   # e.g. ["Vru-Jain/cgpo", "Vru-Jain/quant-tools"]


# ── Helpers ───────────────────────────────────────────────────────────────────
def arrow(change: float) -> str:
    """Return a directional indicator and sign string."""
    if change > 0:
        return f"▲ +{change:.2f}%"
    elif change < 0:
        return f"▼ {change:.2f}%"
    return f"→ {change:.2f}%"


def patch_section(content: str, marker: str, new_body: str) -> str:
    """Replace everything between HTML comment markers."""
    pattern = rf"().*?()"
    
    result, count = re.subn(
        pattern, 
        lambda m: f"{m.group(1)}\n{new_body}\n{m.group(2)}", 
        content, 
        flags=re.DOTALL
    )
    
    if count == 0:
        print(f"  Warning: marker {marker} not found in README - section skipped.")
    return result


def github_api(path: str, token: str):
    """Thin wrapper around the GitHub REST API."""
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
    except urllib.error.HTTPError as e:
        print(f"  GitHub API error {e.code} for {path}: {e.reason}")
        return None
    except Exception as e:
        print(f"  GitHub API request failed: {e}")
        return None


# ── Market data ───────────────────────────────────────────────────────────────
def build_market_block() -> str:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not YFINANCE_AVAILABLE:
        return (
            "| Index | Price | Change |\n"
            "|---|---|---|\n"
            "| — | — | `yfinance` not installed |\n\n"
            f"<sub>Last attempted: {now_utc}</sub>"
        )

    rows = []
    for name, ticker in INDICES:
        try:
            data = yf.Ticker(ticker)
            hist = data.history(period="2d")
            if len(hist) < 2:
                rows.append(f"| {name} | — | no data |")
                continue
            prev_close = hist["Close"].iloc[-2]
            last_close = hist["Close"].iloc[-1]
            pct = (last_close - prev_close) / prev_close * 100
            price_str = f"{last_close:,.2f}"
            rows.append(f"| {name} | `{price_str}` | {arrow(pct)} |")
        except Exception as e:
            print(f"  Failed to fetch {ticker}: {e}")
            rows.append(f"| {name} | — | fetch error |")

    table = "\n".join(
        ["| Index | Price | Change |", "|---|---|---|"] + rows
    )
    return f"{table}\n\n<sub>Last updated: {now_utc}</sub>"


# ── Recent activity ───────────────────────────────────────────────────────────
def build_activity_block(token: str) -> str:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Discover repos to watch if none configured
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
            sha     = commit.get("sha", "")[:7]
            message = commit.get("commit", {}).get("message", "").splitlines()[0]
            if len(message) > 72:
                message = message[:69] + "..."
            repo_short = repo.split("/")[-1]
            url = f"https://github.com/{repo}/commit/{commit.get('sha', '')}"
            events.append(
                f"- [`{sha}`]({url}) **{repo_short}** — {message}"
            )
        if len(events) >= 5:
            break

    if not events:
        return f"_No recent public commits found._\n\n<sub>Last updated: {now_utc}</sub>"

    body = "\n".join(events[:5])
    return f"{body}\n\n<sub>Last updated: {now_utc}</sub>"


# ── Main ──────────────────────────────────────────────────────────────────────
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
    content = patch_section(content, "ACTIVITY",    activity_block)

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print("README.md updated successfully.")


if __name__ == "__main__":
    main()
