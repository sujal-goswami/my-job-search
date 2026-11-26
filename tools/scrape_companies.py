#!/usr/bin/env python3
"""
scrape_companies.py - Scrape target company career pages for DevOps/Platform/AI roles.
Outputs JSON to stdout (list of job objects).

Companies with a public ATS board (Greenhouse/Lever/Ashby) live in
tools/ats_companies.json and are fetched by tools/fetch_ats.py instead - that
returns real postings with locations and dates. This scraper is only the
fallback for career pages without a public board, so it is deliberately
strict: a link counts as a job only if its text names an engineering role and
its URL looks like a posting (or lives on a known ATS host).
"""
import json
import sys
import time
import urllib.request
import urllib.error
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse

COMPANIES = [
    ("Zerodha",      "https://zerodha.com/careers/",                       ["devops","platform","infrastructure","kubernetes","sre"]),
    ("Devtron",      "https://devtron.ai/careers/",                        ["devops","platform","kubernetes","infrastructure"]),
    ("Razorpay",     "https://razorpay.com/jobs/",                         ["devops","platform","sre","infrastructure","kubernetes"]),
    ("InfraCloud",   "https://www.infracloud.io/careers/",                 ["kubernetes","devops","platform","cloud"]),
    ("Delhivery",    "https://www.delhivery.com/careers/",                 ["devops","platform","sre","infrastructure"]),
    ("Cashfree",     "https://www.cashfree.com/company/careers/",          ["devops","platform","infrastructure","engineer"]),
    ("Juspay",       "https://juspay.in/careers",                          ["devops","platform","infrastructure","sre"]),
    ("BrowserStack", "https://www.browserstack.com/careers",               ["devops","platform","infrastructure","sre"]),
    ("Sprinklr",     "https://www.sprinklr.com/careers/",                  ["devops","platform","infrastructure","cloud"]),
    ("Freshworks",   "https://www.freshworks.com/company/careers/",        ["devops","sre","platform","infrastructure"]),
    ("Postman",      "https://www.postman.com/company/careers/",           ["devops","sre","platform","infrastructure"]),
    ("Swiggy",       "https://careers.swiggy.com/",                        ["devops","platform","sre","infrastructure"]),
    ("Cars24",       "https://www.cars24.com/careers/",                    ["devops","platform","infrastructure","engineer"]),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# Link text must name an engineering role, not just a topic ("Kubernetes",
# "AI Platform" product pages, blog posts).
ROLE_RE = re.compile(r"\b(engineer|engineering|sre|devops|devsecops|developer|architect|sde)\b", re.I)
# Posting-shaped URL paths, or ATS hosts that only serve postings.
JOB_PATH_RE = re.compile(r"/(jobs?|careers?|positions?|openings?|roles?|vacanc(y|ies)|apply)(/|\?|#|$|-)", re.I)
ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "smartrecruiters.com",
             "keka.com", "darwinbox.in", "zohorecruit", "freshteam.com", "myworkdayjobs.com")
BLOCKED_HOSTS = ("linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com", "youtube.com")


def looks_like_job(text, href, base_url):
    if not ROLE_RE.search(text):
        return False
    parsed = urlparse(href)
    host = parsed.netloc.lower()
    if parsed.scheme not in ("http", "https") or any(b in host for b in BLOCKED_HOSTS):
        return False
    if any(a in host for a in ATS_HOSTS):
        return True
    # A link back to the careers page itself (or an anchor on it) is navigation.
    if href.split("#")[0].rstrip("/") == base_url.split("#")[0].rstrip("/"):
        return False
    return bool(JOB_PATH_RE.search(parsed.path + ("?" + parsed.query if parsed.query else "")))


class JobLinkExtractor(HTMLParser):
    def __init__(self, base_url, terms):
        super().__init__()
        self.base_url = base_url
        self.terms = terms
        self.jobs = []
        self._href = None
        self._text = []
        self._in_a = False

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href", "")
            self._text = []
            self._in_a = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            text = " ".join(" ".join(self._text).split())
            href = self._href or ""
            if text and href and any(t in text.lower() for t in self.terms):
                if not href.startswith("http"):
                    href = urljoin(self.base_url, href)
                if 8 < len(text) < 120 and looks_like_job(text, href, self.base_url):
                    self.jobs.append({"title": text, "url": href})
            self._in_a = False
            self._href = None
            self._text = []

    def handle_data(self, data):
        if self._in_a:
            self._text.append(data.strip())


def main():
    all_jobs = []
    for company, url, terms in COMPANIES:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            parser = JobLinkExtractor(url, terms)
            parser.feed(html)
            seen = set()
            count = 0
            for job in parser.jobs:
                if job["url"] not in seen and count < 10:
                    seen.add(job["url"])
                    all_jobs.append({
                        "title":   job["title"],
                        "company": company,
                        "location": "India",
                        "url":     job["url"],
                        "date":    "",
                        "_portal": "company-careers",
                    })
                    count += 1
            print(f"  {company}: {count} jobs", file=sys.stderr)
        except Exception as e:
            print(f"  {company}: skipped ({e})", file=sys.stderr)
        time.sleep(0.5)

    print(json.dumps(all_jobs, indent=2))


if __name__ == "__main__":
    main()
