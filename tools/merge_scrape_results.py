#!/usr/bin/env python3
"""
merge_scrape_results.py - Merge and deduplicate all scrape result files.

Usage:
  python3 tools/merge_scrape_results.py <file1:portal1> <file2:portal2> ... --out <output.json>

Each argument is  <path>:<portal_name>  separated by a colon.
"""
import json
import sys

def main():
    args = sys.argv[1:]
    out_path = None
    if "--out" in args:
        idx = args.index("--out")
        out_path = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    all_results = []
    for arg in args:
        if ":" not in arg:
            print(f"Warning: skipping {arg} (no colon separator)", file=sys.stderr)
            continue
        path, portal = arg.rsplit(":", 1)
        try:
            with open(path) as f:
                data = json.load(f)
            items = data if isinstance(data, list) else data.get("results", [])
            for item in items:
                if not item.get("_portal"):
                    item["_portal"] = portal
            all_results.extend(items)
        except Exception as e:
            print(f"Warning: {path}: {e}", file=sys.stderr)

    seen_urls, seen_combos = set(), set()
    deduped = []
    for item in all_results:
        url     = (item.get("url") or item.get("jobUrl") or "").strip()
        company = (item.get("company") or "").strip().lower()
        title   = (item.get("title")   or "").strip().lower()
        if not url or not title or not company:
            continue
        combo = f"{company}||{title}"
        if url in seen_urls or combo in seen_combos:
            continue
        seen_urls.add(url)
        seen_combos.add(combo)
        deduped.append(item)

    print(f"Total: {len(all_results)}, after dedup: {len(deduped)}", file=sys.stderr)
    result = json.dumps(deduped, indent=2)

    if out_path:
        with open(out_path, "w") as f:
            f.write(result)
        print(f"Written to {out_path}", file=sys.stderr)
    else:
        print(result)


if __name__ == "__main__":
    main()
