#!/usr/bin/env python3
"""
digest_email.py - Send a job search digest email with ranked shortlist,
drafted applications, and urgent deadlines.

Usage:
  python3 tools/digest_email.py                        # send digest
  python3 tools/digest_email.py --preview              # print HTML to stdout, no send
  python3 tools/digest_email.py --to other@gmail.com   # override recipient

Config (set in .env.email or environment variables):
  DIGEST_EMAIL_FROM      sender Gmail address
  DIGEST_EMAIL_TO        recipient address (defaults to FROM)
  GMAIL_APP_PASSWORD     Gmail App Password (16-char, no spaces)
"""

import argparse
import json
import os
import smtplib
import sys
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SEEN_JOBS = REPO_ROOT / "job_scraper" / "seen_jobs.json"
TRACKER_CSV = REPO_ROOT / "job_search_tracker.csv"
ENV_FILE = REPO_ROOT / ".env.email"

# ── colour palette ────────────────────────────────────────────────────────────
C_URGENT  = "#dc2626"   # red
C_STRONG  = "#16a34a"   # green
C_GOOD    = "#2563eb"   # blue
C_MODERATE= "#d97706"   # amber
C_MUTED   = "#6b7280"   # grey
C_BG      = "#f9fafb"
C_CARD    = "#ffffff"
C_BORDER  = "#e5e7eb"


def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_seen_jobs():
    if not SEEN_JOBS.exists():
        return {}
    with open(SEEN_JOBS) as f:
        data = json.load(f)
    return data.get("seen", data)


def load_tracker():
    rows = []
    if not TRACKER_CSV.exists():
        return rows
    import csv
    with open(TRACKER_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def days_until(deadline_str):
    try:
        d = datetime.strptime(deadline_str, "%Y-%m-%d").date()
        return (d - date.today()).days
    except Exception:
        return None


def verdict_color(verdict):
    v = (verdict or "").lower()
    if "strong" in v:   return C_STRONG
    if "good" in v:     return C_GOOD
    if "moderate" in v: return C_MODERATE
    return C_MUTED


def badge(text, color):
    return f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;background:{color};color:#fff;font-size:11px;font-weight:600">{text}</span>'


def build_html(jobs_data, tracker_rows):
    today = date.today().strftime("%Y-%m-%d")

    # split into sections
    urgent, strong, good, moderate, drafted_rows = [], [], [], [], []

    for key, job in jobs_data.items():
        status = job.get("status", "")
        if status not in ("ranked", "applied", "drafted"):
            continue

        deadline = job.get("deadline")
        days = days_until(deadline) if deadline else None
        is_urgent = deadline and days is not None and days <= 7

        score = job.get("rank_score", 0)
        verdict = job.get("rank_verdict", "")

        entry = {
            "key": key,
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "url": job.get("url", "#"),
            "location": job.get("location", ""),
            "score": score,
            "verdict": verdict,
            "deadline": deadline,
            "days": days,
            "strengths": job.get("strengths", []),
            "gaps": job.get("gaps", []),
            "status": status,
        }

        if is_urgent:
            urgent.append(entry)
        elif score >= 75:
            strong.append(entry)
        elif score >= 60:
            good.append(entry)
        elif score >= 45:
            moderate.append(entry)

    # drafted tracker rows
    for row in tracker_rows:
        if row.get("status") == "drafted":
            drafted_rows.append(row)

    def sort_key(e):
        return (-e["score"], e.get("days") or 9999)

    urgent.sort(key=sort_key)
    strong.sort(key=sort_key)
    good.sort(key=sort_key)
    moderate.sort(key=sort_key)

    total_active = len(urgent) + len(strong) + len(good)

    # ── HTML ──────────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job Search Digest — {today}</title>
</head>
<body style="margin:0;padding:0;background:{C_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 16px">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

<!-- header -->
<tr><td style="background:#1e293b;border-radius:8px 8px 0 0;padding:28px 32px">
  <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700">Job Search Digest</h1>
  <p style="margin:6px 0 0;color:#94a3b8;font-size:14px">{today} &nbsp;·&nbsp; {total_active} active matches &nbsp;·&nbsp; {len(drafted_rows)} ready to submit</p>
</td></tr>
"""

    def job_card(e):
        color = C_URGENT if e.get("days") is not None and e["days"] <= 7 else verdict_color(e["verdict"])
        deadline_html = ""
        if e["deadline"]:
            d = e["days"]
            if d is not None and d < 0:
                deadline_html = f'<span style="color:{C_URGENT};font-weight:600">Deadline passed</span>'
            elif d is not None and d <= 7:
                deadline_html = f'<span style="color:{C_URGENT};font-weight:600">🔥 {e["deadline"]} ({d}d left)</span>'
            else:
                deadline_html = f'<span style="color:{C_MUTED}">Deadline: {e["deadline"]}</span>'

        strengths_html = ""
        if e["strengths"]:
            items = "".join(f'<li style="margin:2px 0">{s}</li>' for s in e["strengths"][:2])
            strengths_html = f'<ul style="margin:6px 0 0 0;padding-left:18px;color:#374151;font-size:13px">{items}</ul>'

        return f"""
<tr><td style="padding:0 0 12px 0">
<table width="100%" cellpadding="0" cellspacing="0" style="background:{C_CARD};border:1px solid {C_BORDER};border-left:4px solid {color};border-radius:6px">
<tr><td style="padding:16px 20px">
  <table width="100%" cellpadding="0" cellspacing="0"><tr>
    <td><span style="font-size:15px;font-weight:600;color:#111827">{e['title']}</span>
      <span style="color:{C_MUTED};font-size:13px"> · {e['company']}</span></td>
    <td align="right">{badge(e['verdict'] or str(e['score']), color)}</td>
  </tr></table>
  <p style="margin:4px 0 0;color:{C_MUTED};font-size:12px">{e['location'] or ''} &nbsp; {deadline_html}</p>
  {strengths_html}
  <p style="margin:10px 0 0">
    <a href="{e['url']}" style="display:inline-block;padding:6px 16px;background:{color};color:#fff;text-decoration:none;border-radius:4px;font-size:13px;font-weight:600">Apply →</a>
    &nbsp;<span style="color:{C_MUTED};font-size:12px">Score: {e['score']}/100</span>
  </p>
</td></tr></table>
</td></tr>"""

    def section(title, icon, entries, color):
        if not entries:
            return ""
        cards = "".join(job_card(e) for e in entries)
        return f"""
<tr><td style="background:{C_CARD};border-radius:0;padding:0 32px">
  <h2 style="margin:24px 0 12px;font-size:15px;font-weight:700;color:{color};text-transform:uppercase;letter-spacing:.05em">{icon} {title}</h2>
  <table width="100%" cellpadding="0" cellspacing="0">{cards}</table>
</td></tr>"""

    html += section("Urgent — Apply Now", "🔥", urgent, C_URGENT)
    html += section("Strong Fit", "✅", strong, C_STRONG)
    html += section("Good Fit", "👍", good, C_GOOD)
    if moderate:
        html += section("Moderate Fit", "📋", moderate, C_MODERATE)

    # drafted section
    if drafted_rows:
        rows_html = "".join(f"""
<tr style="border-bottom:1px solid {C_BORDER}">
  <td style="padding:10px 0;font-size:13px;font-weight:600;color:#111827">{r.get('company','')}</td>
  <td style="padding:10px 8px;font-size:13px;color:#374151">{r.get('role','')}</td>
  <td style="padding:10px 0;font-size:12px;color:{C_MUTED}">{r.get('deadline','—') or '—'}</td>
  <td style="padding:10px 0" align="right">
    <a href="{r.get('url','#')}" style="color:{C_STRONG};font-size:12px;font-weight:600">Submit →</a>
  </td>
</tr>""" for r in drafted_rows)

        html += f"""
<tr><td style="background:{C_CARD};padding:0 32px">
  <h2 style="margin:24px 0 12px;font-size:15px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:.05em">📎 Documents Ready — Submit These</h2>
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr style="border-bottom:2px solid {C_BORDER}">
      <th style="padding:8px 0;font-size:12px;color:{C_MUTED};text-align:left">Company</th>
      <th style="padding:8px 8px;font-size:12px;color:{C_MUTED};text-align:left">Role</th>
      <th style="padding:8px 0;font-size:12px;color:{C_MUTED};text-align:left">Deadline</th>
      <th style="padding:8px 0;font-size:12px;color:{C_MUTED};text-align:right">Action</th>
    </tr>
    {rows_html}
  </table>
  <p style="font-size:12px;color:{C_MUTED};margin:12px 0">CV and cover letter PDFs are in <code>cv/</code> and <code>cover_letters/</code> in your repo.</p>
</td></tr>"""

    # footer
    html += f"""
<tr><td style="background:#1e293b;border-radius:0 0 8px 8px;padding:20px 32px">
  <p style="margin:0;color:#94a3b8;font-size:12px">
    Generated by ai-job-search · {today}<br>
    Run <code style="color:#e2e8f0">python3 tools/digest_email.py --preview</code> to preview without sending.
  </p>
</td></tr>

</table>
</td></tr></table>
</body></html>"""

    return html


def send_email(html, subject, from_addr, to_addr, app_password, preview=False):
    if preview:
        print(html)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(html, "html"))

    print(f"Sending to {to_addr}...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(from_addr, app_password)
        smtp.sendmail(from_addr, to_addr, msg.as_string())
    print("Sent.")


def main():
    parser = argparse.ArgumentParser(description="Send job search digest email")
    parser.add_argument("--preview", action="store_true", help="Print HTML to stdout, don't send")
    parser.add_argument("--to", type=str, help="Override recipient email")
    args = parser.parse_args()

    load_env()

    from_addr = os.environ.get("DIGEST_EMAIL_FROM", "")
    to_addr = args.to or os.environ.get("DIGEST_EMAIL_TO", from_addr)
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not args.preview:
        if not from_addr:
            print("Error: DIGEST_EMAIL_FROM not set. Add to .env.email or export it.")
            sys.exit(1)
        if not app_password:
            print("Error: GMAIL_APP_PASSWORD not set. Add to .env.email or export it.")
            sys.exit(1)

    jobs_data = load_seen_jobs()
    tracker_rows = load_tracker()

    if not jobs_data:
        print("No jobs in seen_jobs.json. Run /scrape first.")
        sys.exit(1)

    html = build_html(jobs_data, tracker_rows)
    today = date.today().strftime("%Y-%m-%d")
    subject = f"Job Search Digest — {today}"

    send_email(html, subject, from_addr, to_addr, app_password, preview=args.preview)


if __name__ == "__main__":
    main()
