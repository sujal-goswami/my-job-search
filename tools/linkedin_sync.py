#!/usr/bin/env python3
"""
linkedin_sync.py - Download latest scrape artifact from GitHub Actions
and feed new jobs into seen_jobs.json via scrape_state.py.

Usage:
  python3 tools/linkedin_sync.py                  # download latest artifact
  python3 tools/linkedin_sync.py --run-id <id>    # specific run
  python3 tools/linkedin_sync.py --file <path>    # skip download, use local file
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ARTIFACT_NAME = "scrape-results"
WORKFLOW_FILE = "scrape.yml"

# Auto-detect the GitHub repo from git remote, fallback to env var
def _detect_gh_repo():
    env_repo = os.environ.get("GH_REPO", "")
    if env_repo:
        return env_repo
    result = subprocess.run(
        "git remote get-url origin", shell=True, capture_output=True, text=True,
        cwd=REPO_ROOT
    )
    url = result.stdout.strip()
    # https://github.com/owner/repo.git  or  git@github.com:owner/repo.git
    if "github.com" in url:
        url = url.replace("git@github.com:", "https://github.com/")
        url = url.removesuffix(".git")
        return "/".join(url.split("/")[-2:])
    return ""

GH_REPO = _detect_gh_repo()
GH_REPO_FLAG = f"--repo {GH_REPO}" if GH_REPO else ""


def run(cmd, check=True, capture=True):
    result = subprocess.run(
        cmd, shell=True, capture_output=capture, text=True
    )
    if check and result.returncode != 0:
        print(f"Error running: {cmd}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result


def get_latest_run_id():
    result = run(
        f'gh run list {GH_REPO_FLAG} --workflow={WORKFLOW_FILE} --limit=5 --json databaseId,status,conclusion,createdAt'
    )
    runs = json.loads(result.stdout)
    completed = [r for r in runs if r["status"] == "completed" and r["conclusion"] == "success"]
    if not completed:
        print("No successful scrape runs found. Run: gh workflow run scrape.yml")
        sys.exit(1)
    return completed[0]["databaseId"]


def download_artifact(run_id, dest_dir):
    print(f"Downloading artifact from run {run_id}...")
    run(f'gh run download {run_id} {GH_REPO_FLAG} --name {ARTIFACT_NAME} --dir "{dest_dir}"')
    artifact_path = Path(dest_dir) / "scrape_results.json"
    if not artifact_path.exists():
        print(f"Artifact not found at {artifact_path}")
        sys.exit(1)
    return artifact_path


def normalize_results(raw_results):
    """Normalize LinkedIn and freehire results into the full schema scrape_state.py store expects."""
    from datetime import date as _date
    today = _date.today().isoformat()

    normalized = []
    for item in raw_results:
        portal = item.get("_portal", "linkedin-search")

        url = item.get("url") or item.get("jobUrl") or ""
        if not url:
            continue
        title = (item.get("title") or "").strip()
        company = (item.get("company") or "").strip()
        if not title or not company:
            continue

        posted_date = item.get("date") or item.get("postedAt") or None

        normalized.append({
            "title": title,
            "company": company,
            "location": item.get("location") or "",
            "url": url,
            "posted_date": posted_date,
            "first_seen": today,
            "deadline": None,
            "fit": "medium",        # /rank will score properly
            "status": "new",
            "portal": portal,
            "source": "cli",
            "work_mode": item.get("workplaceType") or item.get("work_mode") or None,
            "skills": item.get("skills") or [],
        })

    return normalized


def main():
    parser = argparse.ArgumentParser(description="Sync LinkedIn scrape results into seen_jobs.json")
    parser.add_argument("--run-id", type=int, help="Specific GitHub Actions run ID")
    parser.add_argument("--file", type=str, help="Use a local scrape_results.json instead of downloading")
    args = parser.parse_args()

    if args.file:
        results_path = Path(args.file)
        if not results_path.exists():
            print(f"File not found: {args.file}")
            sys.exit(1)
        print(f"Using local file: {results_path}")
    else:
        run_id = args.run_id or get_latest_run_id()
        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = download_artifact(run_id, tmpdir)
            # copy out of tempdir so we can use it after context exits
            import shutil
            local_copy = Path("/tmp/scrape_results_latest.json")
            shutil.copy(results_path, local_copy)
            results_path = local_copy

    with open(results_path) as f:
        raw_results = json.load(f)

    print(f"Raw results: {len(raw_results)}")

    normalized = normalize_results(raw_results)
    print(f"Normalized: {len(normalized)}")

    if not normalized:
        print("No results to store.")
        return

    tmp_normalized = Path("/tmp/linkedin_sync_normalized.json")
    with open(tmp_normalized, "w") as f:
        json.dump(normalized, f, indent=2)

    # first run candidates check to see what's new
    result = run(
        f'python3 {REPO_ROOT}/tools/scrape_state.py candidates --results "{tmp_normalized}"',
        check=False
    )
    print(result.stdout)

    # store all results
    result = run(
        f'python3 {REPO_ROOT}/tools/scrape_state.py store --results "{tmp_normalized}"',
        check=False
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)

    print("\nDone. Run /rank to score new jobs, then /apply for shortlisted ones.")


if __name__ == "__main__":
    main()
