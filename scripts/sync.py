"""
sync.py — LeetCode Auto-Sync
=============================
Fetches your latest accepted submissions from LeetCode
and writes them to the repo in a clean folder structure.

Folder structure created:
  solutions/
    2026/
      July/
        Day-001_Two-Sum_Easy.py
        Day-002_Number-of-Islands_Medium.py
  README.md   (auto-regenerated with progress table)
  stats.json  (machine-readable progress data)

Requirements:
  pip install requests python-dateutil

Secrets needed in GitHub repo settings:
  LEETCODE_SESSION  — your LeetCode session cookie
  LEETCODE_CSRF     — your LeetCode CSRF token
  (See SETUP.md for how to get these)
"""

import os
import json
import time
import requests
from datetime import datetime, timezone
from dateutil import parser as dateparser
from pathlib import Path

# ─── CONFIG ────────────────────────────────────────────────────
LEETCODE_SESSION = os.environ.get("LEETCODE_SESSION", "")
LEETCODE_CSRF    = os.environ.get("LEETCODE_CSRF",    "")

SOLUTIONS_DIR = Path("solutions")
STATS_FILE    = Path("stats.json")
README_FILE   = Path("README.md")

# How many recent submissions to check each run
SUBMISSION_LIMIT = 50

# Map LeetCode language slugs to file extensions
LANG_EXTENSION = {
    "python3":    ".py",
    "python":     ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "java":       ".java",
    "cpp":        ".cpp",
    "c":          ".c",
    "golang":     ".go",
    "rust":       ".rs",
    "kotlin":     ".kt",
    "swift":      ".swift",
    "scala":      ".scala",
    "ruby":       ".rb",
}

LANG_COMMENT = {
    ".py":   "# ",
    ".js":   "// ",
    ".ts":   "// ",
    ".java": "// ",
    ".cpp":  "// ",
    ".c":    "// ",
    ".go":   "// ",
    ".rs":   "// ",
    ".kt":   "// ",
    ".rb":   "# ",
}

DIFFICULTY_EMOJI = {"Easy": "🟢", "Medium": "🟡", "Hard": "🔴"}

# ─── LEETCODE API ───────────────────────────────────────────────
GRAPHQL_URL = "https://leetcode.com/graphql"

HEADERS = {
    "Content-Type":  "application/json",
    "Referer":       "https://leetcode.com",
    "User-Agent":    "Mozilla/5.0 (compatible; leetcode-sync-bot/1.0)",
    "Cookie":        f"LEETCODE_SESSION={LEETCODE_SESSION}; csrftoken={LEETCODE_CSRF}",
    "x-csrftoken":   LEETCODE_CSRF,
}

SUBMISSIONS_QUERY = """
query recentAcSubmissions($limit: Int!) {
  recentAcSubmissionList(limit: $limit) {
    id
    title
    titleSlug
    timestamp
    lang
    statusDisplay
  }
}
"""

SUBMISSION_DETAIL_QUERY = """
query submissionDetails($submissionId: Int!) {
  submissionDetails(submissionId: $submissionId) {
    code
    timestamp
    lang {
      name
      verboseName
    }
    question {
      questionId
      title
      titleSlug
      difficulty
      topicTags {
        name
        slug
      }
    }
  }
}
"""

PROBLEM_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    title
    difficulty
    topicTags {
      name
    }
  }
}
"""


def graphql(query: str, variables: dict) -> dict:
    """Make a GraphQL request to LeetCode."""
    try:
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"  [ERROR] GraphQL request failed: {e}")
        return {}


def get_recent_accepted(limit: int = 50) -> list:
    """Fetch recent accepted submissions."""
    print(f"Fetching last {limit} accepted submissions...")
    data = graphql(SUBMISSIONS_QUERY, {"limit": limit})
    subs = data.get("data", {}).get("recentAcSubmissionList", [])
    print(f"  Found {len(subs)} accepted submissions")
    return subs


def get_submission_code(submission_id: str) -> dict:
    """Fetch the actual code + problem details for a submission."""
    data = graphql(SUBMISSION_DETAIL_QUERY, {"submissionId": int(submission_id)})
    return data.get("data", {}).get("submissionDetails", {})


def get_problem_info(title_slug: str) -> dict:
    """Fetch problem metadata (difficulty, tags)."""
    data = graphql(PROBLEM_QUERY, {"titleSlug": title_slug})
    return data.get("data", {}).get("question", {})


def slugify(title: str) -> str:
    """Convert problem title to filename-safe string."""
    return title.replace(" ", "-").replace("/", "-").replace(":", "").replace("'", "")


def load_stats() -> dict:
    """Load existing stats from stats.json."""
    if STATS_FILE.exists():
        with open(STATS_FILE) as f:
            return json.load(f)
    return {
        "total_solved":   0,
        "easy":           0,
        "medium":         0,
        "hard":           0,
        "synced_ids":     [],
        "problems":       [],
        "last_synced":    None,
        "streak_days":    0,
        "start_date":     datetime.now(timezone.utc).date().isoformat(),
    }


def save_stats(stats: dict):
    """Save stats to stats.json."""
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)


def get_day_number(stats: dict, submission_date: datetime) -> int:
    """Calculate which day number this is since we started tracking."""
    start = datetime.fromisoformat(stats["start_date"])
    delta = submission_date.date() - start.date()
    return max(1, delta.days + 1)


def write_solution(
    submission: dict,
    detail: dict,
    problem: dict,
    stats: dict,
) -> bool:
    """
    Write a solution file to the correct folder.
    Returns True if a new file was written.
    """
    sub_id     = submission["id"]
    title      = submission["title"]
    lang_slug  = submission["lang"]
    timestamp  = int(submission["timestamp"])

    ext         = LANG_EXTENSION.get(lang_slug, ".txt")
    code        = detail.get("code", "# Code not available")
    difficulty  = problem.get("difficulty", "Unknown")
    tags        = [t["name"] for t in problem.get("topicTags", [])]
    q_id        = problem.get("questionId", "???")

    sub_date    = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    year        = sub_date.strftime("%Y")
    month       = sub_date.strftime("%B")       # e.g. "July"
    day_num     = get_day_number(stats, sub_date)
    date_str    = sub_date.strftime("%Y-%m-%d")
    time_str    = sub_date.strftime("%H:%M UTC")

    safe_title  = slugify(title)
    filename    = f"Day-{day_num:03d}_{safe_title}_{difficulty}{ext}"

    folder = SOLUTIONS_DIR / year / month
    folder.mkdir(parents=True, exist_ok=True)
    filepath = folder / filename

    # Never overwrite an existing solution
    if filepath.exists():
        print(f"  [SKIP] Already exists: {filepath}")
        return False

    # Build the file header comment
    cmt = LANG_COMMENT.get(ext, "# ")
    diff_emoji = DIFFICULTY_EMOJI.get(difficulty, "⚪")

    header = f"""{cmt}{'=' * 60}
{cmt} LeetCode #{q_id} — {title}
{cmt} Difficulty : {diff_emoji} {difficulty}
{cmt} Language   : {lang_slug}
{cmt} Tags       : {', '.join(tags) if tags else 'N/A'}
{cmt} Solved on  : {date_str} at {time_str}
{cmt} Day #      : {day_num}
{cmt} Submission : https://leetcode.com/submissions/detail/{sub_id}/
{cmt} Problem    : https://leetcode.com/problems/{submission['titleSlug']}/
{cmt}{'=' * 60}

"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(header + code + "\n")

    print(f"  [NEW] {filepath}")
    return True


def generate_readme(stats: dict):
    """Regenerate the README with current progress."""
    total   = stats["total_solved"]
    easy    = stats["easy"]
    medium  = stats["medium"]
    hard    = stats["hard"]
    last    = stats.get("last_synced", "Never")
    problems = stats.get("problems", [])

    # Progress bars
    def bar(n, total_for_diff, width=20):
        if total_for_diff == 0:
            return "░" * width
        filled = round(n / total_for_diff * width)
        return "█" * filled + "░" * (width - filled)

    # Group problems by month for the table
    by_month: dict = {}
    for p in problems:
        key = p.get("month_year", "Unknown")
        by_month.setdefault(key, []).append(p)

    # Build monthly tables
    monthly_section = ""
    for month_year, probs in sorted(by_month.items(), reverse=True):
        monthly_section += f"\n### {month_year}\n\n"
        monthly_section += "| Day | # | Problem | Difficulty | Tags | Language |\n"
        monthly_section += "|-----|---|---------|------------|------|----------|\n"
        for p in sorted(probs, key=lambda x: x.get("day", 0)):
            diff   = p.get("difficulty", "?")
            emoji  = DIFFICULTY_EMOJI.get(diff, "⚪")
            tags   = ", ".join(p.get("tags", [])[:3])  # max 3 tags
            link   = f"[{p['title']}](https://leetcode.com/problems/{p['slug']}/)"
            monthly_section += (
                f"| {p.get('day','?'):03d} "
                f"| {p.get('q_id','?')} "
                f"| {link} "
                f"| {emoji} {diff} "
                f"| {tags} "
                f"| {p.get('lang','?')} |\n"
            )

    readme = f"""# 🧠 LeetCode Solutions — Sushree S Swain

> Auto-synced by GitHub Actions every 6 hours. No manual updates needed.

## Progress

| Metric | Count |
|--------|-------|
| Total solved | **{total}** |
| 🟢 Easy | {easy} |
| 🟡 Medium | {medium} |
| 🔴 Hard | {hard} |
| Last synced | {last} |

## Difficulty breakdown

```
Easy    {bar(easy,   max(total,1))}  {easy}
Medium  {bar(medium, max(total,1))}  {medium}
Hard    {bar(hard,   max(total,1))}  {hard}
```

## Solutions
{monthly_section}

---

## How this works

Every 6 hours a GitHub Action:
1. Hits the LeetCode API with a session cookie stored as a GitHub Secret
2. Pulls any new accepted submissions since the last run
3. Writes each solution as a file named `Day-NNN_Problem-Title_Difficulty.py`
4. Auto-commits and pushes — zero manual effort

**Setup:** See [SETUP.md](SETUP.md)

---

*Auto-generated by [leetcode-sync](scripts/sync.py) — last updated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*
"""

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(readme)
    print("  [README] Regenerated README.md")


# ─── MAIN ───────────────────────────────────────────────────────
def main():
    if not LEETCODE_SESSION or not LEETCODE_CSRF:
        print("[ERROR] LEETCODE_SESSION or LEETCODE_CSRF not set.")
        print("        Add them as GitHub Secrets. See SETUP.md.")
        raise SystemExit(1)

    print("=" * 50)
    print("LeetCode Sync — starting")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 50)

    stats    = load_stats()
    synced   = set(stats.get("synced_ids", []))
    new_count = 0

    submissions = get_recent_accepted(SUBMISSION_LIMIT)

    for sub in submissions:
        sub_id = sub["id"]

        if sub_id in synced:
            print(f"  [SKIP] Already synced: {sub['title']} (#{sub_id})")
            continue

        print(f"\nProcessing: {sub['title']} ({sub['lang']})")

        # Get full code
        detail = get_submission_code(sub_id)
        if not detail:
            print(f"  [WARN] Could not fetch detail for submission {sub_id}")
            continue

        # Get problem metadata
        problem = get_problem_info(sub["titleSlug"])
        if not problem:
            # Fall back to basic info
            problem = {"questionId": "?", "difficulty": "Unknown", "topicTags": []}

        # Write the file
        written = write_solution(sub, detail, problem, stats)

        # Update stats
        synced.add(sub_id)
        stats["synced_ids"] = list(synced)

        if written:
            new_count += 1
            diff = problem.get("difficulty", "Unknown")
            timestamp = int(sub["timestamp"])
            sub_date  = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            day_num   = get_day_number(stats, sub_date)

            stats["total_solved"] = stats.get("total_solved", 0) + 1
            stats["easy"]   = stats.get("easy",   0) + (1 if diff == "Easy"   else 0)
            stats["medium"] = stats.get("medium", 0) + (1 if diff == "Medium" else 0)
            stats["hard"]   = stats.get("hard",   0) + (1 if diff == "Hard"   else 0)

            stats.setdefault("problems", []).append({
                "title":      sub["title"],
                "slug":       sub["titleSlug"],
                "q_id":       problem.get("questionId", "?"),
                "difficulty": diff,
                "lang":       sub["lang"],
                "tags":       [t["name"] for t in problem.get("topicTags", [])],
                "date":       sub_date.date().isoformat(),
                "day":        day_num,
                "month_year": sub_date.strftime("%B %Y"),
            })

        # Be polite to LeetCode's API
        time.sleep(1.5)

    stats["last_synced"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    save_stats(stats)
    generate_readme(stats)

    print("\n" + "=" * 50)
    print(f"Done. {new_count} new solution(s) added.")
    print(f"Total solved: {stats['total_solved']}")
    print("=" * 50)


if __name__ == "__main__":
    main()
