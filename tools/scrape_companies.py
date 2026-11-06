#!/usr/bin/env python3
"""
scrape_companies.py - Scrape target company career pages for DevOps/Platform/AI roles.
Outputs JSON to stdout (list of job objects).
"""
import json
import sys
import time
import urllib.request
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin

COMPANIES = [
    ("Zerodha",      "https://zerodha.com/careers/",                       ["devops","platform","infrastructure","kubernetes","sre"]),
    ("Harness",      "https://www.harness.io/company/careers",             ["devops","platform","sre","infrastructure","kubernetes"]),
    ("Devtron",      "https://devtron.ai/careers/",                        ["devops","platform","kubernetes","infrastructure"]),
    ("Sarvam AI",    "https://www.sarvam.ai/careers",                      ["devops","mlops","platform","ai","infrastructure"]),
    ("Razorpay",     "https://razorpay.com/jobs/",                         ["devops","platform","sre","infrastructure","kubernetes"]),
    ("CRED",         "https://cred.club/careers/",                         ["devops","platform","infrastructure","sre"]),
    ("PhonePe",      "https://www.phonepe.com/en-in/careers/",             ["devops","platform","sre","infrastructure"]),
    ("Groww",        "https://careers.groww.in/",                          ["devops","platform","sre","infrastructure"]),
    ("Paytm",        "https://careers.paytm.com/",                        ["devops","platform","infrastructure","sre"]),
    ("InfraCloud",   "https://www.infracloud.io/careers/",                 ["kubernetes","devops","platform","cloud"]),
    ("Delhivery",    "https://www.delhivery.com/careers/",                 ["devops","platform","sre","infrastructure"]),
    ("Cashfree",     "https://www.cashfree.com/company/careers/",          ["devops","platform","infrastructure","engineer"]),
    ("Juspay",       "https://juspay.in/careers",                          ["devops","platform","infrastructure","sre"]),
    ("BrowserStack", "https://www.browserstack.com/careers",               ["devops","platform","infrastructure","sre"]),
    ("Sprinklr",     "https://www.sprinklr.com/careers/",                  ["devops","platform","infrastructure","cloud"]),
    ("Freshworks",   "https://www.freshworks.com/company/careers/",        ["devops","sre","platform","infrastructure"]),
    ("Meesho",       "https://meesho.io/careers",                          ["devops","sre","platform","infrastructure"]),
    ("Postman",      "https://www.postman.com/company/careers/",           ["devops","sre","platform","infrastructure"]),
    ("Datadog",      "https://careers.datadoghq.com/",                     ["devops","sre","platform","infrastructure","india"]),
    ("Anthropic",    "https://www.anthropic.com/careers",                  ["devops","platform","infrastructure","ml","ai"]),
    ("Cohere",       "https://cohere.com/careers",                         ["devops","mlops","platform","infrastructure","ai"]),
    ("Swiggy",       "https://careers.swiggy.com/",                        ["devops","platform","sre","infrastructure"]),
    ("Cars24",       "https://www.cars24.com/careers/",                    ["devops","platform","infrastructure","engineer"]),
    ("OfBusiness",   "https://www.ofbusiness.in/careers",                  ["devops","platform","infrastructure","engineer"]),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


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
            text = " ".join(self._text).strip()
            href = self._href or ""
            if text and href and any(t in text.lower() for t in self.terms):
                if not href.startswith("http"):
                    href = urljoin(self.base_url, href)
                if 8 < len(text) < 120:
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
