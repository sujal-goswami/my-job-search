#!/usr/bin/env python3
"""fetch_ats.py - pull open roles from public applicant-tracking-system boards.

Most tech companies publish their own openings through an ATS that offers a
documented, public, key-free JSON endpoint. Reading those is stable, needs no
HTML parsing, and is the same in every country.

  python3 fetch_ats.py --out ats.json
  python3 fetch_ats.py --company Stripe --out stripe.json
  python3 fetch_ats.py --provider greenhouse --board stripe --out one-off.json
  python3 fetch_ats.py --list-providers

Companies come from companies[].ats in your config:

  {"name": "Stripe", "priority": true,
   "ats": {"provider": "greenhouse", "board": "stripe"}}

See reference/finding-your-board-slug.md for how to find a board slug.

Results are filtered by roles[].keywords and search.locations, then written as
canonical job records (shared/job-schema.md).

This never touches LinkedIn, Indeed or Glassdoor. Those sites forbid automated
collection, and nothing here works around that.

Every company is reported as ok / no-match / error. Exit codes:
  0  at least half the companies answered
  1  more than half errored - a dead run never looks like a quiet job market
  2  unusable config or arguments
"""

import argparse
import copy
import datetime
import html
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# --- jobdigest common core (generated - keep byte-identical across scripts) ---
# Agensi writes each script to a temp file and runs it in the buyer's session, so
# a script cannot import a sibling file from this pack. This block is therefore
# duplicated verbatim into every script by devtools/sync_common.py and its
# SHA-256 is asserted identical everywhere. Edit devtools/common_block.txt, then
# re-run the sync - never edit a copy in place.
#
# Config resolution, four layers, later wins:
#   DEFAULTS  <  ./jobdigest.config.json  <  JOBDIGEST_* env  <  CLI flags
# Environment variables are read one at a time by exact name, with os.getenv.
# The environment is never enumerated or iterated as a whole, so nothing
# outside ENV_MAP can be observed by this pack.

CONFIG_FILENAME = "jobdigest.config.json"
MAX_UPWARD_LEVELS = 5
SCHEMA_VERSION = 1

DEFAULTS = {
    "$schema_version": SCHEMA_VERSION,
    "profile": {
        "label": "My job search",
        "timezone": "UTC",
    },
    "search": {
        "locations": [],
        "max_age_days": 7,
    },
    "roles": [
        {
            "id": "engineering",
            "label": "Engineering",
            "keywords": ["engineer", "developer"],
        },
    ],
    "companies": [],
    "scoring": {
        "bands": {"strong": 75, "good": 60, "moderate": 45},
        "urgent_days": 7,
    },
    "email": {
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "smtp_user": "",
        "from": "",
        "to": [],
        "subject_template": "{brand} - {date} ({new_count} new)",
        "password_env": "JOBDIGEST_SMTP_PASSWORD",
    },
    "brand": {
        "name": "Weekly Job Digest",
        "accent": "#6366f1",
        "dark": "#1e293b",
        "priority_accent": "#f59e0b",
        "width_px": 620,
    },
    "excel": {
        "sheets": {
            "all": "All Jobs",
            "priority": "Priority Companies",
            "by_role": "By Role",
        },
    },
    "fetch": {
        "user_agent": "jobdigest/1.0 (+set-your-contact@example.com)",
        "request_delay_s": 1.0,
        "timeout_s": 15,
        "max_per_company": 10,
        "respect_robots": True,
    },
    "state": {
        "dir": ".jobdigest",
    },
}

ENV_MAP = (
    ("JOBDIGEST_TIMEZONE", ("profile", "timezone"), "str"),
    ("JOBDIGEST_LOCATIONS", ("search", "locations"), "list"),
    ("JOBDIGEST_MAX_AGE_DAYS", ("search", "max_age_days"), "int"),
    ("JOBDIGEST_SMTP_HOST", ("email", "smtp_host"), "str"),
    ("JOBDIGEST_SMTP_PORT", ("email", "smtp_port"), "int"),
    ("JOBDIGEST_SMTP_SECURITY", ("email", "smtp_security"), "str"),
    ("JOBDIGEST_SMTP_USER", ("email", "smtp_user"), "str"),
    ("JOBDIGEST_EMAIL_FROM", ("email", "from"), "str"),
    ("JOBDIGEST_EMAIL_TO", ("email", "to"), "list"),
    ("JOBDIGEST_PASSWORD_ENV", ("email", "password_env"), "str"),
    ("JOBDIGEST_BRAND_NAME", ("brand", "name"), "str"),
    ("JOBDIGEST_USER_AGENT", ("fetch", "user_agent"), "str"),
    ("JOBDIGEST_STATE_DIR", ("state", "dir"), "str"),
)

MAX_FIELD_LEN = 300
SAFE_SCHEMES = ("http", "https")

# Python 3.10 is the floor. Say so in one sentence rather than letting an older
# interpreter fail somewhere deep with a message about something unrelated.
MIN_PYTHON = (3, 10)
if sys.version_info < MIN_PYTHON:
    sys.stderr.write(
        "This pack needs Python %d.%d or newer; this is %d.%d. "
        "Run it with a newer interpreter (try `python3.10` or later).\n"
        % (MIN_PYTHON + sys.version_info[:2])
    )
    sys.exit(2)


class ConfigError(Exception):
    """Config exists but is unusable. Callers print the message and exit 2."""


def eprint(*parts):
    """Print to stderr, so stdout stays usable as a pipe of pure JSON."""
    print(*parts, file=sys.stderr)


def _deep_merge(base, overlay):
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def find_config(start=None):
    """Nearest jobdigest.config.json at or above `start`, or None."""
    here = pathlib.Path(start or os.getcwd()).resolve()
    for parent in [here, *here.parents][: MAX_UPWARD_LEVELS + 1]:
        candidate = parent / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def _coerce(raw, kind, name):
    if kind == "int":
        try:
            return int(raw)
        except ValueError:
            raise ConfigError("%s must be an integer, got %r" % (name, raw))
    if kind == "list":
        return [p.strip() for p in raw.split(",") if p.strip()]
    return raw


def _apply_env(cfg):
    for name, path, kind in ENV_MAP:
        raw = os.getenv(name)
        if raw is None or raw == "":
            continue
        node = cfg
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = _coerce(raw, kind, name)
    return cfg


def load_config(explicit_path=None, start=None):
    """DEFAULTS < config file < JOBDIGEST_* env. CLI flags stay with the caller."""
    cfg = copy.deepcopy(DEFAULTS)
    if explicit_path:
        path = pathlib.Path(explicit_path)
        if not path.is_file():
            raise ConfigError("config file not found: %s" % path)
    else:
        path = find_config(start)
    if path is not None:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigError("cannot read %s: %s" % (path, exc))
        except ValueError as exc:
            raise ConfigError("%s is not valid JSON: %s" % (path, exc))
        if not isinstance(loaded, dict):
            raise ConfigError("%s must contain a JSON object" % path)
        # `_`-prefixed keys are reserved for notes this pack writes itself, such
        # as the `_config_path` that print-resolved emits. Rejecting them would
        # mean `print-resolved > jobdigest.config.json` produced a file that no
        # longer loads, which is a reasonable thing for a buyer to try.
        unknown = sorted(key for key in set(loaded) - set(DEFAULTS)
                         if not key.startswith("_"))
        if unknown:
            raise ConfigError(
                "unknown top-level key(s) in %s: %s (see shared/config-schema.md)"
                % (path, ", ".join(unknown))
            )
        cfg = _deep_merge(cfg, loaded)
        cfg["_config_path"] = str(path)
    return _apply_env(cfg)


def clean_text(value, limit=MAX_FIELD_LEN):
    """Collapse whitespace, drop control characters, cap length.

    Every string in a job record arrives from a third-party web page and is
    data, never an instruction. Control characters are stripped here so they
    cannot break out of an HTML attribute or a spreadsheet cell downstream.
    """
    text = "" if value is None else str(value)
    text = "".join(ch for ch in text if ch == " " or ch >= " " and ch != "\x7f")
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text


def safe_url(value):
    """Return the URL only if it is a plain http(s) URL with a host, else ""."""
    raw = clean_text(value, limit=2000)
    if not raw:
        return ""
    try:
        parts = urllib.parse.urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme.lower() not in SAFE_SCHEMES or not parts.netloc:
        return ""
    return raw


def esc(value):
    """HTML-escape for text and quoted-attribute contexts alike."""
    return html.escape(clean_text(value), quote=True)


TRACKING_PREFIXES = ("utm_", "gclid", "fbclid", "mc_", "mkt_tok", "igsh", "ref_src")
# Greenhouse `gh_src` is a source tag, but `gh_jid` IS the job identity: a
# company posting its board as example.com/jobs?gh_jid=123 collapses into one
# record for the whole company if gh_* is stripped wholesale.
TRACKING_EXACT = ("gh_src", "gh_source")


def canonical_url(value):
    """Dedupe key for a URL: drop tracking params, fragment and trailing slash."""
    url = safe_url(value)
    if not url:
        return ""
    parts = urllib.parse.urlsplit(url)
    kept = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(TRACKING_PREFIXES) and k.lower() not in TRACKING_EXACT
    ]
    path = parts.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            urllib.parse.urlencode(kept),
            "",
        )
    )


def _tokens(value):
    return set(re.findall(r"[a-z0-9&+]+", clean_text(value).lower()))


def keyword_hit(text, keyword):
    """Whole-word keyword match, so "sre" never fires inside "pressure"."""
    pattern = r"\b" + r"\W+".join(re.escape(p) for p in keyword.lower().split())
    return re.search(pattern, clean_text(text).lower()) is not None


def role_of(title, cfg):
    """First configured role whose keywords match, else ("other", "Other")."""
    for role in cfg.get("roles") or []:
        for keyword in role.get("keywords") or []:
            if keyword_hit(title, keyword):
                return role.get("id") or "other", role.get("label") or "Other"
    return "other", "Other"


def company_entry(company, cfg):
    """Configured company whose name or alias token-set is inside `company`.

    Token containment, not substring: substring matching flagged "wise" inside
    "Bitwise" and "cred" inside "Credit Suisse" as priority companies.
    """
    have = _tokens(company)
    if not have:
        return None
    best = None
    for entry in cfg.get("companies") or []:
        names = [entry.get("name") or ""] + list(entry.get("aliases") or [])
        for name in names:
            want = _tokens(name)
            if want and want <= have:
                if best is None or len(want) > best[0]:
                    best = (len(want), entry)
    return best[1] if best else None


def is_priority(company, cfg):
    """True when `company` resolves to a configured company marked priority."""
    entry = company_entry(company, cfg)
    return bool(entry and entry.get("priority"))


def normalize_job(item, cfg):
    """One source record -> the canonical job record in shared/job-schema.md.

    Returns None when company, title or a usable http(s) URL is missing - a
    record without all three cannot be deduped or applied to.
    """
    if not isinstance(item, dict):
        return None
    company = clean_text(item.get("company") or item.get("companyName"))
    title = clean_text(item.get("title") or item.get("jobTitle"))
    url = safe_url(item.get("url") or item.get("jobUrl") or item.get("applyUrl"))
    if not company or not title or not url:
        return None
    role_id, role_label = role_of(title, cfg)
    job = {
        "title": title,
        "company": company,
        "location": clean_text(item.get("location") or item.get("city")),
        "url": url,
        "date": clean_text(item.get("date") or item.get("postedAt") or item.get("posted_date"), 32),
        "work_mode": clean_text(item.get("work_mode") or item.get("workMode"), 32),
        "skills": [clean_text(s, 48) for s in (item.get("skills") or []) if clean_text(s, 48)][:12],
        "_portal": clean_text(item.get("_portal") or item.get("portal") or item.get("source"), 64),
        "role_id": role_id,
        "role_label": role_label,
        "priority": is_priority(company, cfg),
        "key": canonical_url(url),
    }
    # Scoring fields nothing in this pack produces. They survive normalization
    # so a ranked file from your own scoring step - or another tool - can still
    # be rendered by `send_digest.py --mode pipeline`, which needs them.
    score = item.get("rank_score")
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        job["rank_score"] = score
    deadline = clean_text(item.get("deadline"), 32)
    if deadline:
        job["deadline"] = deadline
    for field in ("strengths", "gaps"):
        values = [clean_text(v, 160) for v in (item.get(field) or []) if clean_text(v, 160)]
        if values:
            job[field] = values[:6]
    return job


def normalize_jobs(raw, cfg):
    """Normalize a whole file - a bare list or a {\"results\": [...]} object.

    Unusable records are dropped and repeats of a canonical URL are folded
    into the first occurrence, so the result is already deduplicated.
    """
    records = raw if isinstance(raw, list) else (raw or {}).get("results") or []
    out, seen = [], set()
    for item in records:
        job = normalize_job(item, cfg)
        if job is None or job["key"] in seen:
            continue
        seen.add(job["key"])
        out.append(job)
    return out


def read_json(path):
    """Parse a JSON file, raising ConfigError with the path on any failure."""
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError("cannot read %s: %s" % (path, exc))
    except ValueError as exc:
        raise ConfigError("%s is not valid JSON: %s" % (path, exc))


def write_json(path, payload):
    """Atomic write: a crashed run never leaves a half-written state file."""
    target = pathlib.Path(path)
    body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    try:
        if str(target.parent) not in ("", "."):
            target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, target)
    except OSError as exc:
        # Writing through a temp file means a special file such as /dev/null
        # cannot be a target. Say so instead of unwinding a stack trace.
        raise ConfigError("cannot write %s: %s" % (target, exc))
# --- end jobdigest common core ------------------------------------------------

PROVIDERS = {
    "greenhouse": {
        "url": "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=false",
        "docs": "Board slug is the path in boards.greenhouse.io/<slug>",
    },
    "lever": {
        "url": "https://api.lever.co/v0/postings/{board}?mode=json",
        "docs": "Board slug is the path in jobs.lever.co/<slug>",
    },
    "ashby": {
        "url": "https://api.ashbyhq.com/posting-api/job-board/{board}",
        "docs": "Board slug is the path in jobs.ashbyhq.com/<slug>",
    },
    "workable": {
        "url": "https://apply.workable.com/api/v1/widget/accounts/{board}?details=true",
        "docs": "Board slug is the subdomain in <slug>.workable.com",
    },
    "smartrecruiters": {
        "url": "https://api.smartrecruiters.com/v1/companies/{board}/postings?limit=100",
        "docs": "Board slug is the path in jobs.smartrecruiters.com/<slug>",
    },
}


def iso_date(value):
    """Best-effort ISO date from the several shapes ATS vendors use."""
    if value in (None, "", 0):
        return ""
    if isinstance(value, (int, float)):
        seconds = value / 1000.0 if value > 10_000_000_000 else float(value)
        try:
            return datetime.datetime.fromtimestamp(
                seconds, datetime.timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    text = clean_text(value, 40)
    match = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else ""


def _location(*parts):
    bits = []
    for part in parts:
        text = clean_text(part, 80)
        if text and text.lower() not in (b.lower() for b in bits):
            bits.append(text)
    return ", ".join(bits)


def parse_greenhouse(payload, board):
    for job in (payload or {}).get("jobs") or []:
        yield {
            "title": job.get("title"),
            "url": job.get("absolute_url"),
            "location": (job.get("location") or {}).get("name"),
            "date": iso_date(job.get("updated_at") or job.get("first_published")),
        }


def parse_lever(payload, board):
    for job in payload or []:
        categories = job.get("categories") or {}
        yield {
            "title": job.get("text"),
            "url": job.get("hostedUrl") or job.get("applyUrl"),
            "location": _location(categories.get("location"), categories.get("team")),
            "date": iso_date(job.get("createdAt")),
        }


def parse_ashby(payload, board):
    for job in (payload or {}).get("jobs") or []:
        yield {
            "title": job.get("title"),
            "url": job.get("jobUrl") or job.get("applyUrl"),
            "location": job.get("location"),
            "date": iso_date(job.get("publishedAt") or job.get("updatedAt")),
        }


def parse_workable(payload, board):
    for job in (payload or {}).get("jobs") or []:
        location = job.get("location") or {}
        url = job.get("url") or job.get("application_url")
        if not url and job.get("shortcode"):
            url = "https://apply.workable.com/%s/j/%s/" % (board, job["shortcode"])
        yield {
            "title": job.get("title"),
            "url": url,
            "location": _location(location.get("city"), location.get("region"),
                                  location.get("country")),
            "date": iso_date(job.get("published_on") or job.get("created_at")),
        }


def parse_smartrecruiters(payload, board):
    for job in (payload or {}).get("content") or []:
        location = job.get("location") or {}
        identifier = job.get("id") or job.get("uuid") or ""
        # `ref` is the API URL for the posting, which is no use to a human
        # clicking "Apply", so the public job-board URL is built from the id
        # where there is one and `ref` is only the last resort.
        url = job.get("applyUrl")
        if not url and identifier:
            url = "https://jobs.smartrecruiters.com/%s/%s" % (
                urllib.parse.quote(board), urllib.parse.quote(str(identifier)))
        url = url or job.get("ref")
        yield {
            "title": job.get("name"),
            "url": url,
            "location": _location(location.get("city"), location.get("region"),
                                  location.get("country")),
            "date": iso_date(job.get("releasedDate") or job.get("createdOn")),
        }


PARSERS = {
    "greenhouse": parse_greenhouse,
    "lever": parse_lever,
    "ashby": parse_ashby,
    "workable": parse_workable,
    "smartrecruiters": parse_smartrecruiters,
}


def fetch_json(url, user_agent, timeout):
    """GET one documented public endpoint. No cookies, no redirects off http(s)."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError("HTTP %s" % response.status)
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read(8_000_000).decode(charset, errors="replace")
    return json.loads(body)


def matches_role(title, cfg):
    # No roles configured means no opinion about titles, so keep everything.
    # Reading "no roles" as "nothing matches" would make an unfinished config
    # fetch every board successfully and still return zero postings.
    if not (cfg.get("roles") or []):
        return True, "Other"
    role_id, label = role_of(title, cfg)
    if role_id != "other":
        return True, label
    return False, label


def matches_location(location, cfg):
    wanted = [clean_text(w).lower() for w in (cfg.get("search") or {}).get("locations") or []]
    if not wanted:
        return True
    text = clean_text(location).lower()
    if not text:
        # A board that publishes no location should not be silently dropped;
        # the digest shows it with an empty location and you decide.
        return True
    return any(w in text for w in wanted)


def fetch_company(entry, cfg, delay):
    """Returns (records, status, detail). Never raises."""
    name = clean_text(entry.get("name"))
    ats = entry.get("ats") or {}
    provider = clean_text(ats.get("provider")).lower()
    board = clean_text(ats.get("board"), 120)

    if provider not in PROVIDERS:
        return [], "error", "unknown provider %r (try: %s)" % (
            provider, ", ".join(sorted(PROVIDERS)))
    if not board:
        return [], "error", "ats.board is empty"

    fetch_cfg = cfg["fetch"]
    url = PROVIDERS[provider]["url"].format(board=urllib.parse.quote(board, safe=""))
    eprint("  %-24s %s %s" % (name, provider, urllib.parse.urlsplit(url).netloc))
    try:
        payload = fetch_json(url, fetch_cfg["user_agent"], float(fetch_cfg["timeout_s"]))
    except urllib.error.HTTPError as exc:
        hint = " - is the board slug right?" if exc.code in (403, 404) else ""
        return [], "error", "HTTP %d%s" % (exc.code, hint)
    except urllib.error.URLError as exc:
        return [], "error", "unreachable: %s" % exc.reason
    except (TimeoutError, OSError) as exc:
        return [], "error", "%s: %s" % (type(exc).__name__, exc)
    except ValueError:
        return [], "error", "the board answered with something that is not JSON"
    finally:
        time.sleep(delay)

    raw, kept, rejected_role, rejected_location = [], [], 0, 0
    try:
        raw = list(PARSERS[provider](payload, board))
    except (AttributeError, TypeError) as exc:
        return [], "error", "unexpected payload shape: %s" % exc

    limit = int(fetch_cfg["max_per_company"])
    examined, capped = 0, False
    for item in raw:
        examined += 1
        role_ok, _ = matches_role(item.get("title"), cfg)
        if not role_ok:
            rejected_role += 1
            continue
        if not matches_location(item.get("location"), cfg):
            rejected_location += 1
            continue
        job = normalize_job(dict(item, company=name, _portal=provider), cfg)
        if job is None:
            continue
        kept.append(job)
        if len(kept) >= limit:
            capped = True
            break

    detail = "%d of %d posting(s) matched" % (len(kept), len(raw))
    if rejected_role or rejected_location:
        detail += " (%d off-role, %d off-location)" % (rejected_role, rejected_location)
    # Without this the line reads "5 of 145 matched (72 off-role)", which looks
    # like 140 postings were rejected when 68 were never looked at. A pack that
    # sells itself on accounting for every discarded record has to account for
    # the ones it stopped short of too.
    if capped:
        detail += ", stopped at the fetch.max_per_company cap of %d after %d of %d" % (
            limit, examined, len(raw))
    if not raw:
        return [], "no-match", "the board is reachable but published 0 postings"
    if not kept:
        return [], "no-match", detail
    return kept, "ok", detail


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="fetch_ats.py",
        description="Fetch open roles from public ATS job-board APIs.",
    )
    parser.add_argument("--config", help="path to jobdigest.config.json")
    parser.add_argument("--out", metavar="PATH", help="write here instead of stdout")
    parser.add_argument("--company", action="append", metavar="NAME",
                        help="only this company (repeatable)")
    parser.add_argument("--provider", choices=sorted(PROVIDERS),
                        help="one-off fetch, with --board; ignores the config's companies")
    parser.add_argument("--board", help="board slug for a one-off --provider fetch")
    parser.add_argument("--list-providers", action="store_true",
                        help="show supported providers and how to find a board slug")
    parser.add_argument("--no-filter", action="store_true",
                        help="keep every posting, ignoring roles[] and search.locations")
    args = parser.parse_args(argv)

    if args.list_providers:
        for provider in sorted(PROVIDERS):
            print("%-16s %s" % (provider, PROVIDERS[provider]["docs"]))
            print("%-16s %s" % ("", PROVIDERS[provider]["url"]))
        return 0

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        eprint("config error: %s" % exc)
        return 2

    # jobdigest_config.py's `validate` rejects this too, but a hand-edited config
    # never goes through validate and the request would still go out. The check
    # belongs where the socket is opened, not only where the file is checked.
    if "Mozilla" in str(cfg["fetch"].get("user_agent") or ""):
        eprint("refusing to run: fetch.user_agent impersonates a browser.")
        eprint("Use an honest identifier carrying a contact address, e.g.")
        eprint("  jobdigest/1.0 (+you@example.com)")
        return 2

    if args.no_filter:
        cfg["roles"] = [{"id": "all", "label": "All", "keywords": [""]}]
        cfg["search"]["locations"] = []

    if args.provider or args.board:
        if not (args.provider and args.board):
            eprint("--provider and --board must be given together")
            return 2
        targets = [{"name": args.board, "ats": {"provider": args.provider, "board": args.board}}]
    else:
        targets = [c for c in cfg.get("companies") or [] if c.get("ats")]
        if args.company:
            wanted = {clean_text(n).lower() for n in args.company}
            targets = [c for c in targets if clean_text(c.get("name")).lower() in wanted]
            missing = wanted - {clean_text(c.get("name")).lower() for c in targets}
            for name in sorted(missing):
                eprint("not in config, or has no ats block: %s" % name)

    if not targets:
        eprint("No companies with an ats block to fetch.")
        eprint("Add one:  python3 jobdigest_config.py add-company \"Stripe\" "
               "--ats greenhouse:stripe")
        eprint("Or list the providers:  python3 fetch_ats.py --list-providers")
        return 2

    delay = float(cfg["fetch"]["request_delay_s"])
    eprint("fetching %d board(s), %.1fs between requests, as %r"
           % (len(targets), delay, cfg["fetch"]["user_agent"]))

    jobs, report = [], []
    for entry in targets:
        records, status, detail = fetch_company(entry, cfg, delay)
        jobs.extend(records)
        report.append({"company": clean_text(entry.get("name")),
                       "provider": clean_text((entry.get("ats") or {}).get("provider")),
                       "status": status, "detail": detail, "count": len(records)})

    seen, unique = set(), []
    for job in jobs:
        if job["key"] in seen:
            continue
        seen.add(job["key"])
        unique.append(job)

    errors = sum(1 for r in report if r["status"] == "error")
    eprint("")
    eprint("fetch report:")
    for row in report:
        eprint("  %-24s %-9s %s" % (row["company"], row["status"], row["detail"]))
    eprint("total: %d job(s) from %d board(s); %d errored"
           % (len(unique), len(targets), errors))

    payload = {"_fetch_report": report,
               "generated": datetime.date.today().isoformat(),
               "results": unique}
    if args.out:
        write_json(args.out, payload)
        eprint("wrote %s" % args.out)
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    if errors * 2 > len(targets):
        eprint("")
        eprint("more than half the boards errored - treating this run as failed so a")
        eprint("scheduled job does not quietly report an empty week")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
