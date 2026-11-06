#!/usr/bin/env python3
"""
weekly_digest.py - Build weekly job digest from scrape_results.json,
send HTML email with Excel attachment.

Usage:
  python3 tools/weekly_digest.py --input /tmp/scrape_results.json
  python3 tools/weekly_digest.py --input /tmp/scrape_results.json --preview

Environment variables (or .env.email):
  DIGEST_EMAIL_FROM      sender Gmail
  DIGEST_EMAIL_TO        recipient (defaults to FROM)
  GMAIL_APP_PASSWORD     16-char Gmail App Password
"""

import argparse
import io
import json
import os
import smtplib
import sys
from datetime import date, datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ENV_FILE = REPO_ROOT / ".env.email"

# ── Category buckets (matched against title keywords) ────────────────────────
CATEGORIES = [
    ("🤖 AI / LLM Infrastructure",   ["ai infrastructure", "ml platform", "mlops", "llm", "genai", "ai platform", "agentic", "machine learning infra", "ai engineer"]),
    ("☸️  DevOps / Platform",          ["devops", "platform engineer", "cloud engineer", "cloud platform", "infrastructure engineer"]),
    ("🔒 SRE / Reliability",           ["sre", "site reliability", "reliability engineer"]),
    ("📦 Other",                        []),   # catch-all
]

# Dream + Tier1 companies for special highlight
DREAM_COMPANIES = {
    "zerodha", "harness", "devtron", "sarvam", "krutrim", "razorpay",
    "datadog", "grafana", "anthropic", "cred", "phonepe", "wise",
    "groww", "paytm", "setu", "m2p", "infracloud", "delhivery",
    "postman", "meesho", "cashfree", "cohere", "weights & biases", "wandb",
    "hugging face", "google", "amazon", "aws", "microsoft", "atlassian",
    "stripe", "together", "modal", "replicate"
}

# ── colours ───────────────────────────────────────────────────────────────────
C_DARK   = "#1e293b"
C_ACCENT = "#6366f1"   # indigo
C_DREAM  = "#f59e0b"   # amber — dream company highlight
C_BG     = "#f8fafc"
C_CARD   = "#ffffff"
C_BORDER = "#e2e8f0"
C_MUTED  = "#64748b"
C_GREEN  = "#16a34a"
C_TEXT   = "#1e293b"


def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def categorize(title: str) -> str:
    t = title.lower()
    for cat_name, keywords in CATEGORIES[:-1]:
        if any(k in t for k in keywords):
            return cat_name
    return CATEGORIES[-1][0]


def is_dream(company: str) -> bool:
    c = company.lower()
    return any(d in c for d in DREAM_COMPANIES)


def normalize_jobs(raw: list) -> list:
    jobs = []
    for item in raw:
        company = (item.get("company") or "").strip()
        title   = (item.get("title")   or "").strip()
        url     = item.get("url") or item.get("jobUrl") or ""
        if not company or not title or not url:
            continue
        jobs.append({
            "title":    title,
            "company":  company,
            "location": item.get("location") or "",
            "url":      url,
            "date":     item.get("date") or item.get("postedAt") or "",
            "portal":   item.get("_portal") or item.get("portal") or "",
            "skills":   item.get("skills") or [],
            "category": categorize(title),
            "dream":    is_dream(company),
        })
    # dedupe by url
    seen = set()
    deduped = []
    for j in jobs:
        if j["url"] not in seen:
            seen.add(j["url"])
            deduped.append(j)
    return deduped


def build_excel(jobs: list, today: str) -> bytes:
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None

    wb = openpyxl.Workbook()

    # ── Sheet 1: All Jobs ─────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "All Jobs"

    headers = ["#", "Category", "Company", "Role", "Location", "Posted", "Portal", "Apply URL", "Skills"]
    header_fill  = PatternFill("solid", fgColor="1e293b")
    dream_fill   = PatternFill("solid", fgColor="FEF3C7")
    alt_fill     = PatternFill("solid", fgColor="F8FAFC")
    header_font  = Font(bold=True, color="FFFFFF", size=11)
    dream_font   = Font(bold=True, color="92400E")
    link_font    = Font(color="4F46E5", underline="single")
    border_side  = Side(style="thin", color="E2E8F0")
    thin_border  = Border(bottom=Border(bottom=border_side).bottom)

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.row_dimensions[1].height = 28
    col_widths = [4, 22, 22, 42, 20, 12, 16, 55, 50]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # sort: dream companies first, then by category
    sorted_jobs = sorted(jobs, key=lambda j: (0 if j["dream"] else 1, j["category"], j["company"]))

    for i, job in enumerate(sorted_jobs, 1):
        row = i + 1
        fill = dream_fill if job["dream"] else (alt_fill if i % 2 == 0 else None)
        font = dream_font if job["dream"] else None

        values = [
            i,
            job["category"].split(" ", 1)[-1].strip(),
            job["company"],
            job["title"],
            job["location"],
            job["date"],
            job["portal"],
            job["url"],
            ", ".join(job["skills"][:8]) if job["skills"] else "",
        ]
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.alignment = Alignment(vertical="center", wrap_text=(col in (4, 9)))
            if fill:
                cell.fill = fill
            if font and col in (2, 3, 4):
                cell.font = font
            if col == 8 and val:  # URL column — make it a hyperlink
                cell.hyperlink = val
                cell.font = link_font
                cell.value = "Apply →"
        ws.row_dimensions[row].height = 18

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

    # ── Sheet 2: Dream Companies ──────────────────────────────────────────────
    ws2 = wb.create_sheet("Dream Companies ⭐")
    dream_jobs = [j for j in sorted_jobs if j["dream"]]

    for col, h in enumerate(headers, 1):
        cell = ws2.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for i, w in enumerate(col_widths, 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    ws2.row_dimensions[1].height = 28

    for i, job in enumerate(dream_jobs, 1):
        row = i + 1
        values = [i, job["category"].split(" ", 1)[-1].strip(), job["company"],
                  job["title"], job["location"], job["date"], job["portal"], job["url"],
                  ", ".join(job["skills"][:8]) if job["skills"] else ""]
        for col, val in enumerate(values, 1):
            cell = ws2.cell(row=row, column=col, value=val)
            cell.fill = dream_fill
            cell.font = dream_font if col in (2,3,4) else None
            cell.alignment = Alignment(vertical="center", wrap_text=(col in (4,9)))
            if col == 8 and val:
                cell.hyperlink = val
                cell.font = link_font
                cell.value = "Apply →"
        ws2.row_dimensions[row].height = 18

    ws2.freeze_panes = "A2"

    # ── Sheet 3: By Category ──────────────────────────────────────────────────
    ws3 = wb.create_sheet("By Category")
    row_idx = 1
    for cat_name, _ in CATEGORIES:
        cat_jobs = [j for j in sorted_jobs if j["category"] == cat_name]
        if not cat_jobs:
            continue
        # category header
        cell = ws3.cell(row=row_idx, column=1, value=f"{cat_name}  ({len(cat_jobs)} roles)")
        cell.font = Font(bold=True, color="FFFFFF", size=12)
        cell.fill = PatternFill("solid", fgColor="1e293b")
        cell.alignment = Alignment(vertical="center")
        ws3.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=8)
        ws3.row_dimensions[row_idx].height = 24
        row_idx += 1
        for job in cat_jobs:
            for col, val in enumerate([
                "⭐" if job["dream"] else "", job["company"], job["title"],
                job["location"], job["date"], job["portal"], job["url"], ""
            ], 1):
                cell = ws3.cell(row=row_idx, column=col, value=val)
                cell.alignment = Alignment(vertical="center")
                if col == 7 and val:
                    cell.hyperlink = val
                    cell.font = link_font
                    cell.value = "Apply →"
            ws3.row_dimensions[row_idx].height = 16
            row_idx += 1
        row_idx += 1  # blank row between categories

    for i, w in enumerate([4, 22, 42, 20, 12, 16, 14, 4], 1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_html(jobs: list, today: str) -> str:
    by_category = {}
    for j in jobs:
        by_category.setdefault(j["category"], []).append(j)

    dream_count = sum(1 for j in jobs if j["dream"])
    total = len(jobs)

    def job_row(j):
        dream_badge = '<span style="background:#f59e0b;color:#fff;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:700;margin-right:6px">⭐ DREAM</span>' if j["dream"] else ""
        skills_html = ""
        if j["skills"]:
            tags = "".join(f'<span style="background:#e0e7ff;color:#3730a3;padding:1px 6px;border-radius:3px;font-size:10px;margin:1px 2px 1px 0;display:inline-block">{s}</span>' for s in j["skills"][:6])
            skills_html = f'<div style="margin-top:4px">{tags}</div>'
        date_str = f'<span style="color:{C_MUTED};font-size:11px">{j["date"]}</span>' if j["date"] else ""
        border_color = C_DREAM if j["dream"] else C_BORDER
        return f"""
<tr><td style="padding:0 0 8px 0">
<table width="100%" cellpadding="0" cellspacing="0" style="background:{C_CARD};border:1px solid {C_BORDER};border-left:4px solid {border_color};border-radius:5px">
<tr><td style="padding:12px 16px">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div>
      {dream_badge}<strong style="font-size:14px;color:{C_TEXT}">{j['title']}</strong>
      <span style="color:{C_MUTED};font-size:13px"> · {j['company']}</span>
    </div>
    <a href="{j['url']}" style="display:inline-block;padding:4px 14px;background:{C_ACCENT};color:#fff;text-decoration:none;border-radius:4px;font-size:12px;font-weight:600;white-space:nowrap;margin-left:12px">Apply →</a>
  </div>
  <div style="margin-top:3px;color:{C_MUTED};font-size:12px">{j['location'] or 'India'} &nbsp;·&nbsp; {date_str} &nbsp;·&nbsp; {j['portal']}</div>
  {skills_html}
</td></tr></table>
</td></tr>"""

    sections = ""
    for cat_name, _ in CATEGORIES:
        cat_jobs = by_category.get(cat_name, [])
        if not cat_jobs:
            continue
        # dream companies first within category
        cat_jobs = sorted(cat_jobs, key=lambda j: (0 if j["dream"] else 1, j["company"]))
        rows = "".join(job_row(j) for j in cat_jobs)
        sections += f"""
<tr><td style="background:{C_CARD};padding:0 28px">
  <h2 style="margin:20px 0 10px;font-size:14px;font-weight:700;color:{C_DARK};text-transform:uppercase;letter-spacing:.06em;border-bottom:2px solid {C_BORDER};padding-bottom:6px">{cat_name} &nbsp;<span style="font-weight:400;color:{C_MUTED}">({len(cat_jobs)})</span></h2>
  <table width="100%" cellpadding="0" cellspacing="0">{rows}</table>
</td></tr>"""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weekly Job Digest — {today}</title></head>
<body style="margin:0;padding:0;background:{C_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:20px 12px">
<table width="620" cellpadding="0" cellspacing="0" style="max-width:620px;width:100%">

<tr><td style="background:{C_DARK};border-radius:8px 8px 0 0;padding:24px 28px">
  <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700">Weekly Job Digest</h1>
  <p style="margin:6px 0 0;color:#94a3b8;font-size:13px">{today} &nbsp;·&nbsp; <strong style="color:#fff">{total} new openings</strong> &nbsp;·&nbsp; {dream_count} from dream companies &nbsp;·&nbsp; Excel attached</p>
</td></tr>

<tr><td style="background:#eff6ff;padding:12px 28px;border-left:4px solid {C_ACCENT}">
  <p style="margin:0;color:#1e40af;font-size:13px">
    📋 <strong>Review this email</strong> → open personal laptop → run <code>/rank</code> on interesting ones → run <code>/apply</code> → submit
  </p>
</td></tr>

{sections}

<tr><td style="background:{C_DARK};border-radius:0 0 8px 8px;padding:16px 28px">
  <p style="margin:0;color:#64748b;font-size:11px">
    Weekly Job Digest · {today} · ai-job-search pipeline<br>
    Sources: LinkedIn (GitHub Actions) + freehire.me aggregator + 53 target company career pages<br>
    Excel spreadsheet attached with full data, hyperlinks, and category tabs
  </p>
</td></tr>

</table></td></tr></table></body></html>"""


def send(html: str, excel_bytes: bytes, subject: str, from_addr: str, to_addr: str,
         app_password: str, today: str, preview: bool = False):
    if preview:
        print(html[:3000])
        print(f"\n[Excel: {len(excel_bytes) if excel_bytes else 0} bytes]")
        return

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(html, "html"))
    msg.attach(alt)

    if excel_bytes:
        part = MIMEBase("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        part.set_payload(excel_bytes)
        encoders.encode_base64(part)
        fname = f"job_digest_{today}.xlsx"
        part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
        msg.attach(part)

    print(f"Sending to {to_addr}...")
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(from_addr, app_password)
        smtp.sendmail(from_addr, to_addr, msg.as_string())
    print(f"Sent! {len(jobs) if 'jobs' in dir() else '?'} jobs, Excel {'attached' if excel_bytes else 'skipped (openpyxl missing)'}.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to scrape_results.json")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--to", type=str)
    args = parser.parse_args()

    load_env()
    from_addr = os.environ.get("DIGEST_EMAIL_FROM", "")
    to_addr   = args.to or os.environ.get("DIGEST_EMAIL_TO", from_addr)
    app_pw    = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not args.preview and (not from_addr or not app_pw):
        print("Error: DIGEST_EMAIL_FROM and GMAIL_APP_PASSWORD must be set in .env.email")
        sys.exit(1)

    with open(args.input) as f:
        raw = json.load(f)

    global jobs
    jobs = normalize_jobs(raw)
    print(f"Jobs loaded: {len(jobs)} (from {len(raw)} raw)")

    today = date.today().strftime("%Y-%m-%d")
    html  = build_html(jobs, today)
    xlsx  = build_excel(jobs, today)

    if xlsx is None:
        print("Warning: openpyxl not installed — Excel skipped. Install with: pip install openpyxl")

    subject = f"Weekly Job Digest — {today} ({len(jobs)} openings)"
    send(html, xlsx, subject, from_addr, to_addr, app_pw, today, preview=args.preview)


if __name__ == "__main__":
    main()
