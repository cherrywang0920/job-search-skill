#!/usr/bin/env python3
"""Daily job / internship finder. Pure stdlib, no pip installs needed.

Everything personal (roles, countries, seasons, work authorization, sources) lives
in ../config.json, which the onboarding flow writes. See config.example.json.

Sources (all unauthenticated, all deduplicated across runs):
  1. SimplifyJobs listings.json feeds (structured: date_posted, terms, locations,
     category, sponsorship). Mostly US and Canada.
  2. Company watchlist (companies.json) via public Greenhouse / Lever / Ashby /
     Workday job-board APIs.
  3. Discovery sweep: every Greenhouse/Lever/Ashby board that shows up in the
     Simplify feeds but is not on the watchlist.
  4. LinkedIn public jobs-guest endpoints. Personal use only; volume is kept low.
  5. apmlist.com status diff (optional, product-management searches only).

State:
  state/seen_jobs.json  - every posting ever surfaced, keyed by company_title
  state/applied.json    - [{"company":..., "role":...}] rows from the user's
                          application tracker, written by the agent before a run

Usage:
  python3 job_search.py run [--days N] [--li-pages 2] [--max-detail 30]
  python3 job_search.py config                      # print the effective filters
  python3 job_search.py check --title "..." [--location "..."]
  python3 job_search.py detail <linkedin id|url>
  python3 job_search.py key --company "X" --title "Y"

`run` prints a JSON document of NEW candidates (not seen before, not already
applied) for the agent to fit-assess, and records everything into seen_jobs.json.

The LinkedIn card parser and the canonical dedup key were adapted from
MadsLorentzen/ai-job-search (MIT).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
SEEN_FILE = STATE_DIR / "seen_jobs.json"
APPLIED_FILE = STATE_DIR / "applied.json"
APMLIST_STATE = STATE_DIR / "apmlist.json"
DISCOVERED_FILE = STATE_DIR / "discovered_boards.json"
CONFIG_FILE = ROOT / "config.json"
CONFIG_EXAMPLE = ROOT / "config.example.json"
COMPANIES_FILE = ROOT / "companies.json"
COMPANIES_EXAMPLE = ROOT / "companies.example.json"
APMLIST_URL = "https://apmlist.com/"

LI_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LI_DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


# ---- helpers ---------------------------------------------------------------
def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def fetch(url: str, headers: dict | None = None, retries: int = 5) -> str:
    """GET with exponential backoff on 429/5xx. Returns '' on 404."""
    delay = 1.0
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ""
            if e.code == 429 or e.code >= 500:
                if attempt == retries:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 10)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 10)
    return ""


def li_headers() -> dict:
    return {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
    }


def decode_entities(t: str) -> str:
    t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&quot;", '"').replace("&#39;", "'").replace("&apos;", "'")
          .replace("&nbsp;", " "))
    t = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))) if int(m.group(1)) <= 0x10FFFF else "", t)
    t = re.sub(r"&#[xX]([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), t)
    return t


def strip_tags(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()


def clean(h: str) -> str:
    return decode_entities(strip_tags(h))


def word_re(items: list[str]) -> re.Pattern | None:
    """Keyword list -> one case-insensitive regex with word boundaries on both sides.
    Entries are regex fragments, so `product manag\\w*` matches manager/management."""
    items = [i for i in (items or []) if i and i.strip()]
    if not items:
        return None
    return re.compile(r"\b(?:" + "|".join(items) + r")\b", re.I)


# ---- config ----------------------------------------------------------------
class Config:
    """Compiled view of config.json. Every filter the script applies comes from here."""

    def __init__(self, raw: dict):
        self.raw = raw
        self.name = raw.get("name") or "the user"
        self.job_types = [j.lower() for j in raw.get("job_types") or ["internship"]]

        roles = raw.get("roles") or {}
        self.include_re = word_re(roles.get("title_include"))
        self.exclude_re = word_re(roles.get("title_exclude"))
        self.discover_include_re = word_re(roles.get("discover_title_include")) or self.include_re
        self.discover_exclude_re = word_re(roles.get("discover_title_exclude"))
        self.li_queries = roles.get("linkedin_queries") or []
        self.ats_terms = roles.get("ats_search_terms") or self.li_queries[:2]
        self.simplify_categories = set(roles.get("simplify_categories") or [])

        locs = raw.get("locations") or {}
        self.countries = locs.get("countries") or []
        self.cities = [c.lower() for c in locs.get("cities") or []]
        self.remote_ok = locs.get("remote", True)
        self.li_locations = locs.get("linkedin_locations") or self.countries
        self.wide_window = {k: int(v) for k, v in (locs.get("wide_window_days") or {}).items()}
        for country, extra in (locs.get("extra_city_markers") or {}).items():
            COUNTRIES.setdefault(country, {"aliases": [country.lower()], "codes": [], "cities": []})
            COUNTRIES[country]["cities"] = COUNTRIES[country].get("cities", []) + [e.lower() for e in extra]

        self.auth = raw.get("work_authorization") or {}
        self.sponsor_countries = [c for c, v in self.auth.items() if str(v).lower().startswith("needs")]

        self.window_days = int(raw.get("window_days") or 2)
        src = raw.get("sources") or {}
        self.simplify_feeds = src.get("simplify_feeds") or []
        self.use_linkedin = src.get("linkedin", True)
        self.linkedin_experience = src.get("linkedin_experience_levels") or []
        self.use_ats = src.get("ats_watchlist", True)
        self.use_discover = src.get("discover_boards", True)
        self.use_apmlist = src.get("apmlist", False)
        self.ambassador = bool(raw.get("ambassador_programs", False))

        self._build_job_type_res()
        self._build_term_res(raw.get("terms") or [], raw.get("term_hints") or [])
        self._build_visa_res()

    # Title must look like the right *kind* of job. Full-time searches skip this test.
    def _build_job_type_res(self):
        jt = self.job_types
        if "full-time" in jt or "full time" in jt:
            self.jobtype_re = self.ats_jobtype_re = None
            return
        loose, strict = [], []
        if "internship" in jt or "co-op" in jt:
            loose += [r"intern", r"internship", r"co-?op", r"summer", r"work term", r"placement"]
            strict += [r"intern", r"internship", r"co-?op", r"apprentice\w*", r"work term", r"placement"]
        if "new-grad" in jt or "new grad" in jt or "entry-level" in jt:
            ng = [r"new grad\w*", r"graduate", r"entry[- ]level", r"early[- ]career", r"university grad\w*",
                  r"junior", r"associate", r"rotational", r"class of \d{4}", r"campus"]
            loose += ng
            strict += ng
        years = sorted({y for t in (self.raw.get("terms") or []) for y in re.findall(r"20\d\d", t)})
        loose += years
        self.jobtype_re = word_re(loose)
        self.ats_jobtype_re = word_re(strict)

    def _build_term_res(self, terms: list[str], hints: list[str]):
        self.terms = [t.strip() for t in terms if t.strip()]
        self.terms_lower = {t.lower() for t in self.terms}
        months = {"summer": ["may", "june"], "winter": ["jan", "january"], "fall": ["sep", "sept", "september"],
                  "autumn": ["sep", "sept", "september"], "spring": ["jan", "january", "april"]}
        parts, years = [], set()
        for t in self.terms:
            m = re.match(r"(\w+)\s+(20\d\d)", t, re.I)
            if not m:
                parts.append(re.escape(t))
                continue
            season, year = m.group(1).lower(), m.group(2)
            years.add(int(year))
            parts += [rf"{season}\s*{year}", rf"{year}\s*{season}"]
            parts += [rf"{mo}\.?\s*{year}" for mo in months.get(season, [])]
        parts += [re.escape(h) for h in hints if h.strip()]
        self.term_re = re.compile("(" + "|".join(parts) + ")", re.I) if parts else None
        if years:
            past = min(years) - 1
            self.stale_re = re.compile(rf"((summer|fall|autumn|winter|spring)\s*{past}|{past}\s*start)", re.I)
        else:
            self.stale_re = None

    def _build_visa_res(self):
        aliases = []
        for c in self.sponsor_countries:
            aliases += [re.escape(a) for a in COUNTRIES.get(c, {}).get("aliases", [c.lower()])]
            if c == "United States":
                aliases += [r"u\.?s\.?"]
        where = "(?:the )?(?:" + "|".join(aliases) + ")" if aliases else "(?:the )?(?:country)"
        self.visa_block_re = re.compile(
            r"(will not (?:be able to )?sponsor|not able to sponsor|unable to sponsor|"
            r"do(?:es)? not (?:offer |provide )?(?:visa )?sponsor|no visa sponsorship|"
            r"without (?:the need for )?(?:visa )?sponsorship|not (?:provide|offer) (?:visa )?sponsorship|"
            r"sponsorship is not (?:available|offered|provided)|"
            r"not require sponsorship (?:now or )?(?:in the future)?|"
            rf"must be (?:legally )?authorized to work in {where}|"
            rf"authorized to work in {where} without|"
            r"(?:citizen(?:ship)?|permanent resident)s? (?:is |are )?(?:required|only)|"
            r"must be a (?:u\.?s\.? )?citizen|security clearance|right to work in)", re.I)
        self.visa_ok_re = re.compile(
            r"(j-?1|cpt/opt|opt/cpt|visa sponsorship (?:is )?(?:available|provided|offered)|"
            r"(?:we|will) sponsor|offers? sponsorship|sponsor(?:ship for)? (?:eligible )?(?:international )?"
            r"(?:students|candidates|interns)|f-?1 students? are (?:welcome|eligible)|"
            r"international (?:students|applicants) (?:are )?(?:welcome|eligible|encouraged))", re.I)

    def window_for(self, country: str) -> int:
        return max(self.window_days, self.wide_window.get(country, 0))


CFG: Config  # set in main()


def load_config() -> Config:
    raw = load_json(CONFIG_FILE, None)
    if raw is None:
        log("No config.json found. Run the onboarding flow first (see references/onboarding.md), "
            "or copy config.example.json to config.json.")
        sys.exit(2)
    return Config(raw)


# ---- location classification -----------------------------------------------
US_STATES = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC"
).split()
CA_PROVS = "BC ON QC AB MB SK NS NB NL PE YT NT NU".split()

# aliases: country names (matched as whole words, case-insensitive)
# codes:   state/province codes after a comma ("Austin, TX"), case-sensitive
# cities:  major cities, used only when no country name or code is present
COUNTRIES: dict[str, dict] = {
    "United States": {"aliases": ["united states", "usa", "u.s.a.", "u.s."], "codes": US_STATES,
                      "cities": ["new york", "nyc", "san francisco", "seattle", "los angeles", "boston", "chicago",
                                 "austin", "bay area", "silicon valley", "palo alto", "mountain view", "menlo park",
                                 "san jose", "sunnyvale", "atlanta", "denver", "washington dc", "miami",
                                 "philadelphia", "pittsburgh", "dallas", "houston", "san diego", "portland",
                                 "salt lake city", "raleigh", "minneapolis", "detroit", "phoenix", "nashville"]},
    "Canada": {"aliases": ["canada"], "codes": CA_PROVS,
               "cities": ["vancouver", "toronto", "montreal", "montréal", "ottawa", "calgary", "waterloo",
                          "kitchener", "edmonton", "victoria", "burnaby", "mississauga", "markham", "halifax",
                          "winnipeg", "quebec city", "québec"]},
    "United Kingdom": {"aliases": ["united kingdom", "uk", "england", "scotland", "wales", "great britain",
                                   "northern ireland"],
                       "cities": ["london", "manchester", "edinburgh", "cambridge", "oxford", "bristol",
                                  "birmingham", "glasgow", "leeds", "belfast"]},
    "Ireland": {"aliases": ["ireland"], "cities": ["dublin", "cork", "galway"]},
    "Germany": {"aliases": ["germany", "deutschland"],
                "cities": ["berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln", "stuttgart"]},
    "France": {"aliases": ["france"], "cities": ["paris", "lyon", "toulouse"]},
    "Netherlands": {"aliases": ["netherlands", "holland"],
                    "cities": ["amsterdam", "rotterdam", "utrecht", "eindhoven", "the hague"]},
    "Spain": {"aliases": ["spain", "españa"], "cities": ["madrid", "barcelona", "valencia"]},
    "Portugal": {"aliases": ["portugal"], "cities": ["lisbon", "porto"]},
    "Italy": {"aliases": ["italy"], "cities": ["milan", "rome", "turin"]},
    "Switzerland": {"aliases": ["switzerland"], "cities": ["zurich", "zürich", "geneva", "lausanne", "basel"]},
    "Sweden": {"aliases": ["sweden"], "cities": ["stockholm", "gothenburg", "malmö"]},
    "Denmark": {"aliases": ["denmark"], "cities": ["copenhagen", "aarhus"]},
    "Norway": {"aliases": ["norway"], "cities": ["oslo"]},
    "Finland": {"aliases": ["finland"], "cities": ["helsinki"]},
    "Poland": {"aliases": ["poland"], "cities": ["warsaw", "krakow", "kraków", "wroclaw", "wrocław"]},
    "Belgium": {"aliases": ["belgium"], "cities": ["brussels", "antwerp"]},
    "Austria": {"aliases": ["austria"], "cities": ["vienna"]},
    "Czech Republic": {"aliases": ["czech republic", "czechia"], "cities": ["prague", "brno"]},
    "Singapore": {"aliases": ["singapore"]},
    "India": {"aliases": ["india"], "cities": ["bangalore", "bengaluru", "hyderabad", "mumbai", "delhi", "new delhi",
                                               "pune", "chennai", "gurgaon", "gurugram", "noida", "kolkata"]},
    "Australia": {"aliases": ["australia"], "codes": ["NSW", "VIC", "QLD", "TAS", "ACT"],
                  "cities": ["sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra"]},
    "New Zealand": {"aliases": ["new zealand"], "cities": ["auckland", "wellington"]},
    "Japan": {"aliases": ["japan"], "cities": ["tokyo", "osaka", "kyoto"]},
    "South Korea": {"aliases": ["south korea", "korea"], "cities": ["seoul"]},
    "China": {"aliases": ["china"], "cities": ["shanghai", "beijing", "shenzhen", "hangzhou", "guangzhou"]},
    "Hong Kong": {"aliases": ["hong kong"]},
    "Taiwan": {"aliases": ["taiwan"], "cities": ["taipei", "hsinchu"]},
    "Israel": {"aliases": ["israel"], "cities": ["tel aviv", "jerusalem", "haifa"]},
    "United Arab Emirates": {"aliases": ["united arab emirates", "uae"], "cities": ["dubai", "abu dhabi"]},
    "Brazil": {"aliases": ["brazil", "brasil"], "cities": ["são paulo", "sao paulo", "rio de janeiro"]},
    "Mexico": {"aliases": ["mexico", "méxico"], "cities": ["mexico city", "guadalajara", "monterrey"]},
}
for _c in ("Philippines", "Pakistan", "Nigeria", "Kenya", "Egypt", "South Africa", "Vietnam", "Indonesia",
           "Thailand", "Malaysia", "Turkey", "Argentina", "Colombia", "Chile", "Peru", "Ecuador", "Uruguay",
           "Costa Rica", "Guatemala", "Romania", "Hungary", "Serbia", "Ukraine", "Greece", "Saudi Arabia",
           "Qatar", "EMEA", "APAC", "LATAM"):
    COUNTRIES.setdefault(_c, {"aliases": [_c.lower()]})


def _segment_country(seg: str) -> str | None:
    low = seg.lower()
    for country, m in COUNTRIES.items():
        if any(re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", low) for a in m.get("aliases", [])):
            return country
    if re.search(r"\bUS\b", seg):
        return "United States"
    for country, m in COUNTRIES.items():
        codes = m.get("codes")
        if codes and re.search(r",\s*(" + "|".join(codes) + r")\b", seg):
            return country
    for country, m in COUNTRIES.items():
        if any(re.search(r"(?<!\w)" + re.escape(c) + r"(?!\w)", low) for c in m.get("cities", [])):
            return country
    return None


def location_ok(loc: str) -> tuple[bool, str]:
    """(keep?, country). Country is a COUNTRIES key, 'remote', or 'unknown'.
    A multi-city string is kept when any of its cities is in a target country; when several
    match ("Remote in USA; Remote in Canada"), the one needing no sponsorship wins, then the
    one with the widest date window."""
    if not loc or not loc.strip():
        return True, "unknown"
    segs = [s for s in re.split(r";|\||\s+or\s+", loc) if s.strip()]
    found, hits = [], []
    for s in segs:
        c = _segment_country(s)
        if not c:
            continue
        if c in CFG.countries and (not CFG.cities or any(city in s.lower() for city in CFG.cities)
                                   or "remote" in s.lower()):
            hits.append(c)
        found.append(c)
    if hits:
        return True, min(hits, key=lambda c: (c in CFG.sponsor_countries, -CFG.wide_window.get(c, 0)))
    if found:
        return False, found[0]
    if "remote" in loc.lower():
        return bool(CFG.remote_ok), "remote"
    return True, "unknown"


def visa_check(country: str, text: str, simplify_field: str | None = None) -> tuple[str, str | None]:
    """('n/a'|'blocked'|'sponsors'|'unknown', evidence quote). Only checked where the user
    said they need sponsorship (or where the country could not be determined)."""
    if not CFG.sponsor_countries:
        return "n/a", None
    if country not in CFG.sponsor_countries and country not in ("remote", "unknown"):
        return "n/a", None
    if country == "United States" or country in ("remote", "unknown"):
        if simplify_field in ("Does Not Offer Sponsorship", "U.S. Citizenship is Required"):
            return "blocked", simplify_field
        if simplify_field == "Offers Sponsorship":
            return "sponsors", simplify_field
    t = text or ""
    for verdict, rx in (("blocked", CFG.visa_block_re), ("sponsors", CFG.visa_ok_re)):
        m = rx.search(t)
        if m:
            i = max(0, m.start() - 60)
            return verdict, "..." + t[i:m.end() + 60].strip().replace("\n", " ") + "..."
    return "unknown", None


# ---- canonical dedup key (from ai-job-search tools/job_key.py) -------------
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    if not text:
        return ""
    d = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return _NON_SLUG.sub("-", d.lower()).strip("-")


def _cap(slug: str, limit: int) -> str:
    if len(slug) <= limit:
        return slug
    return f"{slug[:limit].rstrip('-')}-{hashlib.sha1(slug.encode()).hexdigest()[:6]}"


def make_key(company: str, title: str, url: str = "") -> str:
    c = _cap(slugify(company), 40) or "unknown-company"
    t = _cap(slugify(title), 60)
    if not t:
        m = re.search(r"(\d{6,})", url or "")
        t = m.group(1) if m else "untitled-" + hashlib.sha1((title + url).encode()).hexdigest()[:6]
    return f"{c}_{t}"


# ---- cross-source identity -------------------------------------------------
_CORP_SUFFIX = re.compile(
    r"\b(inc|corp|corporation|ltd|limited|llc|plc|co|company|companies|group|holdings|"
    r"bank|financial|technologies|technology|labs|software|solutions|canada|usa|us|gmbh|ag|sa)\b", re.I)


def norm_company(name: str) -> str:
    """'TD Bank' and 'TD' must collapse: the same posting is listed by the ATS under
    the legal name and by LinkedIn under the brand."""
    n = _CORP_SUFFIX.sub(" ", slugify(name).replace("-", " "))
    return re.sub(r"\s+", " ", n).strip() or slugify(name)


_TITLE_NOISE = re.compile(
    r"\b(intern|internship|co op|coop|student|program|programme|the|a|an|of|for|and|"
    r"winter|summer|spring|fall|20\d\d|months?|\d)\b", re.I)


def title_tokens(title: str) -> set:
    t = slugify(title).replace("-", " ")
    return {w for w in _TITLE_NOISE.sub(" ", t).split() if len(w) > 2}


def same_role(a: dict, b: dict) -> bool:
    """Same employer and a strong token overlap in the meaningful part of the title."""
    if norm_company(a["company"]) != norm_company(b["company"]):
        return False
    ta, tb = title_tokens(a["title"]), title_tokens(b["title"])
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= 0.8


# ---- title filters ---------------------------------------------------------
AMBASSADOR_RE = re.compile(
    r"\b(campus|student|university|college)\s+(ambassador|representative|rep|partner|"
    r"advocate|lead|evangelist|innovator|influencer)\b|"
    r"\bambassador (program|programme)\b|\bcampus (crew|club lead)\b", re.I)
# Ambassador postings that are really unpaid sales/MLM or pure promo gigs.
AMBASSADOR_EXCLUDE_RE = re.compile(
    r"\b(commission[- ]only|mlm|multi-level|door[- ]to[- ]door|canvass|"
    r"nightlife|promoter|brand rep for|bartend|admissions|enrollment|tour guide)\b", re.I)
# A university hiring its own "University Ambassador" is an admissions job, not a brand program.
UNIVERSITY_EMPLOYER_RE = re.compile(
    r"\b(university|college|school of|institute of technology|seminary|academy)\b", re.I)
LI_AMBASSADOR_QUERIES = ["campus ambassador", "student ambassador", "campus representative",
                         "university ambassador", "student partner program"]


def role_ok(title: str) -> bool:
    return (CFG.include_re is None or bool(CFG.include_re.search(title))) and not (
        CFG.exclude_re and CFG.exclude_re.search(title))


def ambassador_ok(title: str) -> bool:
    return CFG.ambassador and bool(AMBASSADOR_RE.search(title)) and not AMBASSADOR_EXCLUDE_RE.search(title)


def classify(title: str, ats: bool = False) -> str | None:
    """'job' | 'ambassador' | None (not a match)."""
    if ambassador_ok(title):
        return "ambassador"
    jt = CFG.ats_jobtype_re if ats else CFG.jobtype_re
    if (jt is None or jt.search(title)) and role_ok(title):
        return "job"
    return None


def terms_in(text: str) -> list[str]:
    return sorted({m.group(0).strip() for m in CFG.term_re.finditer(text)}) if CFG.term_re else []


# ---- source 1: Simplify ----------------------------------------------------
_SIMPLIFY_CACHE: list | None = None


def simplify_feed() -> list:
    """All configured Simplify listings, fetched once per run (also used by board discovery)."""
    global _SIMPLIFY_CACHE
    if _SIMPLIFY_CACHE is None:
        rows = []
        for url in CFG.simplify_feeds:
            rows += json.loads(fetch(url))
        _SIMPLIFY_CACHE = rows
    return _SIMPLIFY_CACHE


def simplify_candidates(days: int) -> list[dict]:
    if not CFG.simplify_feeds:
        return []
    log(f"[simplify] fetching {len(CFG.simplify_feeds)} feed(s) ...")
    try:
        data = simplify_feed()
    except Exception as e:
        log(f"[simplify] FAILED: {e}")
        return []
    now = time.time()
    out = []
    for x in data:
        if not x.get("active") or not x.get("is_visible", True):
            continue
        title = x.get("title", "")
        kind = "job"
        if ambassador_ok(title):
            kind = "ambassador"
        elif x.get("category") in CFG.simplify_categories:
            # The feed already fixes the job type and category; only drop clear non-fits.
            if CFG.exclude_re and CFG.exclude_re.search(title):
                continue
        elif not role_ok(title) or CFG.include_re is None:
            continue
        terms = [t for t in (x.get("terms") or [])]
        # Internship feeds carry terms; new-grad feeds carry none. "N/A" means unstated.
        if kind == "job" and CFG.terms and terms:
            if not any(t.lower() in CFG.terms_lower for t in terms):
                continue
        loc_str = "; ".join(x.get("locations") or [])
        ok, country = location_ok(loc_str)
        if not ok:
            continue
        # Ambassador rows and wide-window countries get the longer window.
        win = max(days, 21) if kind == "ambassador" else max(days, CFG.wide_window.get(country, 0))
        if x.get("date_posted", 0) < now - win * 86400:
            continue
        visa, evidence = visa_check(country, "", x.get("sponsorship"))
        out.append({
            "source": "simplify", "company": x.get("company_name", ""), "title": title,
            "location": loc_str, "country": country, "terms": [t for t in terms if t != "N/A"],
            "posted": date.fromtimestamp(x["date_posted"]).isoformat(), "url": x.get("url", ""),
            "sponsorship": x.get("sponsorship"), "kind": kind, "visa": visa, "visa_evidence": evidence,
            "degrees": x.get("degrees"), "description": None,
        })
    log(f"[simplify] {len(out)} matching active rows posted in the window")
    return out


# ---- source 2: LinkedIn ----------------------------------------------------
def li_parse_cards(html: str) -> list[dict]:
    cards = []
    for chunk in html.split('data-entity-urn="urn:li:jobPosting:')[1:]:
        m = re.match(r"(\d+)", chunk)
        if not m:
            continue
        jid = m.group(1)
        link = re.search(r'class="base-card__full-link[^"]*"[^>]*href="([^"]+)"', chunk, re.I)
        url = decode_entities(link.group(1)).split("?")[0] if link else f"https://www.linkedin.com/jobs/view/{jid}"
        h3 = re.search(r'class="base-search-card__title"[^>]*>([\s\S]*?)</h3>', chunk, re.I)
        title = clean(h3.group(1)) if h3 else None
        if not title:
            sr = re.search(r'class="sr-only"[^>]*>([\s\S]*?)</span>', chunk, re.I)
            title = clean(sr.group(1)) if sr else None
        if not title:
            continue
        sub = re.search(r'class="base-search-card__subtitle"[^>]*>([\s\S]*?)</h4>', chunk, re.I)
        company = clean(sub.group(1)) if sub else ""
        loc = re.search(r'class="job-search-card__location"[^>]*>([\s\S]*?)</span>', chunk, re.I)
        dt = re.search(r'class="job-search-card__listdate[^"]*"[^>]*datetime="([^"]+)"', chunk, re.I)
        cards.append({
            "id": jid, "title": title, "company": company,
            "location": clean(loc.group(1)) if loc else "",
            "date": dt.group(1) if dt else None, "url": url,
        })
    return cards


def li_search(query: str, location: str, days: int, page: int, experience: list[str] | None = None) -> list[dict]:
    params = {"keywords": query, "location": location, "start": str((page - 1) * 10)}
    if days and days > 0:  # 0 = no recency filter (ambassador programs)
        params["f_TPR"] = f"r{days * 86400}"
    if experience:  # LinkedIn experience levels: 1 internship, 2 entry level, 3 associate, 4 mid-senior
        params["f_E"] = ",".join(experience)
    return li_parse_cards(fetch(f"{LI_SEARCH}?{urllib.parse.urlencode(params)}", li_headers()))


def li_detail(jid: str) -> dict:
    html = fetch(f"{LI_DETAIL}/{jid}", li_headers())
    if not html:
        return {"id": jid, "found": False}
    desc_html = None
    for cls in ("show-more-less-html__markup", "description__text"):
        m = re.search(r'<div[^>]*class="[^"]*' + cls + r'[^"]*"[^>]*>([\s\S]*?)</div>\s*(?:</div>|<div)', html, re.I)
        if m:
            desc_html = m.group(1)
            break
    desc = None
    if desc_html:
        desc = decode_entities(strip_tags(re.sub(r"<\s*br\s*/?>|</(p|li|ul|ol|div|h\d)>", "\n", desc_html, flags=re.I)))
    crit = {}
    for m in re.finditer(r'class="description__job-criteria-subheader"[^>]*>([\s\S]*?)</h3>[\s\S]*?class="description__job-criteria-text[^"]*"[^>]*>([\s\S]*?)</span>', html, re.I):
        crit[clean(m.group(1)).lower()] = clean(m.group(2))
    desc_start = re.search(r'class="(?:show-more-less-html__markup|description__text)', html)
    top = html[: desc_start.start()] if desc_start else html
    is_active = not re.search(r"closed-job__flavor|no longer accepting applications", top, re.I)
    loc = re.search(r'class="topcard__flavor topcard__flavor--bullet"[^>]*>([\s\S]*?)</span>', html, re.I)
    return {
        "id": jid, "found": True, "isActive": is_active,
        "location": clean(loc.group(1)) if loc else None,
        "seniority": crit.get("seniority level"), "employmentType": crit.get("employment type"),
        "description": desc,
    }


def normalize_li_id(s: str) -> str | None:
    m = re.search(r"urn:li:jobPosting:(\d+)", s) or re.search(r"-(\d{6,})(?:[/?]|$)", s) or re.search(r"/(\d{6,})(?:[/?]|$)", s) or re.match(r"^(\d{6,})$", s)
    return m.group(1) if m else None


def linkedin_candidates(days: int, pages: int) -> list[dict]:
    """Each LinkedIn location uses its own window (wide_window_days), and ambassador
    queries use no window at all, since those programs accept late applications."""
    if not CFG.use_linkedin or not CFG.li_queries:
        return []
    pool: dict[str, dict] = {}
    queries = CFG.li_queries + (LI_AMBASSADOR_QUERIES if CFG.ambassador else [])
    for loc in CFG.li_locations:
        for q in queries:
            is_amb = q in LI_AMBASSADOR_QUERIES
            win = 0 if is_amb else max(days, CFG.wide_window.get(loc, 0))
            for p in range(1, pages + 1):
                try:
                    cards = li_search(q, loc, win, p, None if is_amb else CFG.linkedin_experience)
                except Exception as e:
                    log(f"[linkedin] '{q}' @ {loc} p{p} FAILED: {e}")
                    break
                time.sleep(1.2)
                if not cards:
                    break
                for c in cards:
                    if c["id"] in pool:
                        continue
                    kind = classify(c["title"])
                    if not kind:
                        continue
                    if kind == "ambassador" and UNIVERSITY_EMPLOYER_RE.search(c["company"] or ""):
                        continue  # a university recruiting for itself
                    ok, country = location_ok(c["location"] or loc)
                    if not ok:
                        continue
                    pool[c["id"]] = {
                        "source": "linkedin", "li_id": c["id"], "company": c["company"],
                        "title": c["title"], "location": c["location"] or loc, "country": country,
                        "terms": terms_in(c["title"]), "posted": c["date"], "url": c["url"], "description": None,
                        "kind": kind, "visa": visa_check(country, "")[0], "visa_evidence": None,
                    }
    n_amb = sum(1 for v in pool.values() if v["kind"] == "ambassador")
    log(f"[linkedin] {len(pool)} unique matching cards: {len(pool)-n_amb} jobs, {n_amb} ambassador")
    return list(pool.values())


# ---- source 3: company watchlist via public ATS APIs -----------------------
def _json(url: str, data: dict | None = None) -> dict | list:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _ats_jobs(c: dict) -> list[dict]:
    """Normalise one company's board to [{title, location, posted, url}]."""
    ats, slug = c["ats"], c["slug"]
    out = []
    if ats == "greenhouse":
        for j in _json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")["jobs"]:
            out.append({"title": j["title"], "location": (j.get("location") or {}).get("name", ""),
                        "posted": (j.get("first_published") or j.get("updated_at") or "")[:10], "url": j["absolute_url"]})
    elif ats == "lever":
        for j in _json(f"https://api.lever.co/v0/postings/{slug}?mode=json"):
            ts = j.get("createdAt")
            out.append({"title": j["text"], "location": (j.get("categories") or {}).get("location", ""),
                        "posted": date.fromtimestamp(ts / 1000).isoformat() if ts else "", "url": j["hostedUrl"]})
    elif ats == "ashby":
        for j in _json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")["jobs"]:
            loc = j.get("location") or ""
            if j.get("isRemote"):
                loc = f"Remote; {loc}".strip("; ")
            out.append({"title": j["title"], "location": loc, "posted": (j.get("publishedAt") or "")[:10], "url": j["jobUrl"]})
    elif ats == "workday":
        tenant, wd, site = slug.split("/")
        base = f"https://{tenant}.{wd}.myworkdayjobs.com"
        for q in CFG.ats_terms:
            r = _json(f"{base}/wday/cxs/{tenant}/{site}/jobs", {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q})
            for j in r.get("jobPostings", []):
                m = re.search(r"(\d+)\+? days? ago", j.get("postedOn", ""), re.I)
                posted = (date.today() - timedelta(days=int(m.group(1)))).isoformat() if m else (date.today().isoformat() if "today" in j.get("postedOn", "").lower() else "")
                out.append({"title": j["title"], "location": j.get("locationsText", ""), "posted": posted,
                            "url": f"{base}/en-US/{site}{j['externalPath']}"})
    return out


def _ats_rows(c: dict, jobs: list[dict], discovered: bool = False) -> list[dict]:
    out, seen_urls = [], set()
    for j in jobs:
        t = j["title"]
        if j["url"] in seen_urls:
            continue
        kind = classify(t, ats=True)
        if not kind:
            continue
        ok, country = location_ok(j["location"])
        if ok and country == "unknown":
            # Some boards put the city in the title and "In-Office" in the location.
            ok, country = location_ok(t)
        if not ok:
            continue
        seen_urls.add(j["url"])
        out.append({"source": "ats", "company": c["name"], "title": t, "location": j["location"], "country": country,
                    "terms": terms_in(t), "posted": j["posted"] or None, "url": j["url"], "description": None,
                    "tier": c.get("tier"), "kind": kind, "discovered": discovered,
                    "visa": visa_check(country, "")[0], "visa_evidence": None})
    return out


BOARD_PATTERNS = [
    ("greenhouse", re.compile(r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?!embed/)([A-Za-z0-9_-]+)/jobs", re.I)),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_app\?(?:[^#]*&)?for=([A-Za-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([A-Za-z0-9_.-]+)/", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)/", re.I)),
]


def discover_boards(watchlist: list[dict]) -> list[dict]:
    """Every Greenhouse/Lever/Ashby board that appears anywhere in the Simplify feeds
    (any role, any term) and is not already on the watchlist. Simplify often lists a
    company's engineering roles more reliably than its other roles, so the board itself
    is the place to look."""
    have = {(c.get("ats"), (c.get("slug") or "").lower()) for c in watchlist}
    have_names = {norm_company(c["name"]) for c in watchlist}
    found = {f"{b['ats']}:{b['slug']}": b for b in load_json(DISCOVERED_FILE, [])}
    try:
        feed = simplify_feed()
    except Exception:
        feed = []
    for x in feed:
        u = x.get("url", "") or ""
        for ats, pat in BOARD_PATTERNS:
            m = pat.search(u)
            if not m:
                continue
            slug = urllib.parse.unquote(m.group(1)).lower()
            name = (x.get("company_name") or slug).strip()
            if (ats, slug) not in have and norm_company(name) not in have_names:
                found.setdefault(f"{ats}:{slug}", {"name": name, "ats": ats, "slug": slug})
            break
    boards = sorted(found.values(), key=lambda b: b["name"].lower())
    try:
        DISCOVERED_FILE.write_text(json.dumps(boards, indent=1, ensure_ascii=False))
    except OSError:
        pass
    return boards


DISCOVER_MAX_AGE_DAYS = 200  # older open posts are usually evergreen shells, unless the title names a target term


def _discover_keep(r: dict) -> bool:
    t = r["title"].strip()
    if r["kind"] == "ambassador":
        return True
    if CFG.discover_include_re and not CFG.discover_include_re.search(t):
        return False
    if CFG.discover_exclude_re and CFG.discover_exclude_re.search(t):
        return False
    posted = r.get("posted") or ""
    if posted and not r.get("terms"):
        try:
            if (date.today() - date.fromisoformat(posted[:10])).days > DISCOVER_MAX_AGE_DAYS:
                return False
        except ValueError:
            pass
    return True


def discovered_candidates(watchlist: list[dict]) -> tuple[list[dict], int, int]:
    boards = discover_boards(watchlist)

    def one(b: dict):
        try:
            return [r for r in _ats_rows(b, _ats_jobs(b), discovered=True) if _discover_keep(r)], True
        except Exception:
            return [], False

    out, ok = [], 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for rows, good in ex.map(one, boards):
            out += rows
            ok += good
    log(f"[discover] {len(out)} matching rows across {ok}/{len(boards)} boards found via Simplify (not on watchlist)")
    return out, ok, len(boards)


def load_watchlist() -> list[dict]:
    data = load_json(COMPANIES_FILE, None) or load_json(COMPANIES_EXAMPLE, {})
    return data.get("companies", [])


def ats_candidates() -> tuple[list[dict], list[str]]:
    companies = load_watchlist()
    out, failed = [], []
    for c in companies:
        if not c.get("ats"):
            continue
        try:
            jobs = _ats_jobs(c)
        except Exception as e:
            failed.append(f"{c['name']} ({e})")
            continue
        out += _ats_rows(c, jobs)
        time.sleep(0.3)
    log(f"[ats] {len(out)} matching rows across {len(companies)} watchlist companies; {len(failed)} boards failed")
    return out, failed


# ---- source 4: apmlist.com status diff (PM searches only) ------------------
def apmlist_snapshot() -> dict:
    """{'Company|table': {'status':..., 'href':...}} from apmlist's two tables."""
    html = fetch(APMLIST_URL)
    snap = {}
    tables = re.findall(r"<table[\s\S]*?</table>", html, re.I)
    for ti, table in enumerate(tables[:2]):
        label = "apm" if ti == 0 else "intern"
        for row in re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", table, re.I):
            cells = [clean(c) for c in re.findall(r"<td[^>]*>([\s\S]*?)</td>", row, re.I)]
            if len(cells) < 2 or cells[0] in ("Company", ""):
                continue
            href = re.search(r'href="([^"]+)"', row)
            snap[f"{cells[0]}|{label}"] = {"company": cells[0], "table": label, "status": cells[1],
                                          "href": decode_entities(href.group(1)) if href else None}
    return snap


def apmlist_changes() -> dict:
    if not CFG.use_apmlist:
        return {"ok": True, "enabled": False, "changes": [], "open_intern": []}
    try:
        now = apmlist_snapshot()
    except Exception as e:
        log(f"[apmlist] FAILED: {e}")
        return {"ok": False, "changes": [], "open_intern": []}
    prev = load_json(APMLIST_STATE, {})
    changes = [{**v, "from": prev.get(k, {}).get("status")} for k, v in now.items()
               if prev and prev.get(k, {}).get("status") != v["status"]]
    APMLIST_STATE.write_text(json.dumps(now, indent=1, ensure_ascii=False))
    open_intern = [v for v in now.values() if v["table"] == "intern" and v["status"].lower() == "open"]
    log(f"[apmlist] {len(now)} rows, {len(changes)} status changes since last run, {len(open_intern)} intern rows marked Open")
    return {"ok": True, "enabled": True, "changes": changes, "open_intern": open_intern, "first_snapshot": not prev}


# ---- dedup against the application tracker ---------------------------------
def applied_match(company: str, title: str, applied: list[dict]) -> bool:
    c = slugify(company)
    t = set(slugify(title).split("-"))
    for a in applied:
        ac = slugify(a.get("company", ""))
        if not ac or (ac not in c and c not in ac):
            continue
        at = set(slugify(a.get("role", "")).split("-"))
        # Same company + strong title overlap = already applied.
        if len(t & at) >= max(2, int(0.6 * len(at))):
            return True
    return False


# ---- run -------------------------------------------------------------------
def run(days: int, li_pages: int, max_detail: int, discover: bool = True) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    seen = load_json(SEEN_FILE, {"seen": {}})
    applied = load_json(APPLIED_FILE, [])

    ats_pool, ats_failed = ats_candidates() if CFG.use_ats else ([], [])
    apm = apmlist_changes()
    pool = simplify_candidates(days) + ats_pool
    disc_ok = disc_total = 0
    if discover and CFG.use_discover and CFG.simplify_feeds:
        disc_pool, disc_ok, disc_total = discovered_candidates(load_watchlist())
        pool += disc_pool
    pool += linkedin_candidates(days, li_pages)

    today = date.today().isoformat()
    new, skipped_seen, skipped_applied = [], [], []
    url_index = {v.get("url", "").rstrip("/"): v for v in seen["seen"].values()}
    for j in pool:
        key = make_key(j["company"], j["title"], j["url"])
        prev = seen["seen"].get(key) or url_index.get(j["url"].rstrip("/"))
        if prev:
            skipped_seen.append({"company": j["company"], "title": j["title"], "location": j["location"],
                                 "url": j["url"], "first_seen": prev.get("first_seen"), "status": prev.get("status")})
            continue
        if applied_match(j["company"], j["title"], applied):
            skipped_applied.append({"company": j["company"], "title": j["title"], "url": j["url"]})
            seen["seen"][key] = {**j, "first_seen": today, "status": "already-applied"}
            continue
        j["key"] = key
        new.append(j)

    # Bounded LinkedIn detail fetch for season + closed-state + description snippet.
    fetched = 0
    for j in new:
        if j["source"] != "linkedin" or fetched >= max_detail:
            continue
        try:
            d = li_detail(j["li_id"])
            fetched += 1
            time.sleep(1.2)
        except Exception as e:
            log(f"[linkedin] detail {j['li_id']} FAILED: {e}")
            continue
        if not d.get("found") or not d.get("isActive", True):
            j["status"] = "expired"
            continue
        desc = d.get("description") or ""
        j["description"] = desc[:900]
        j["visa"], j["visa_evidence"] = visa_check(j["country"], desc)
        j["seniority"] = d.get("seniority")
        j["terms"] = terms_in(j["title"] + " " + desc)
        if not j["terms"] and CFG.stale_re and CFG.stale_re.search(j["title"] + " " + desc):
            j["stale_term"] = True

    # Merge the same posting arriving from several sources or cities. Prefer the row
    # with a direct employer URL (ats/simplify) over a LinkedIn mirror.
    SRC_RANK = {"ats": 0, "simplify": 1, "linkedin": 2}
    new.sort(key=lambda j: SRC_RANK.get(j["source"], 9))
    merged: list[dict] = []
    for j in new:
        hit = next((m for m in merged if same_role(m, j)), None)
        if hit:
            if j["location"] and j["location"] not in (hit["location"], *(hit.get("also_in") or [])):
                hit.setdefault("also_in", []).append(j["location"])
            hit.setdefault("also_seen_as", []).append(f"{j['source']}: {j['title']}")
            if not hit.get("description") and j.get("description"):
                hit["description"] = j["description"]
            if hit.get("visa") in (None, "unknown") and j.get("visa") not in (None, "unknown"):
                hit["visa"], hit["visa_evidence"] = j["visa"], j.get("visa_evidence")
            seen["seen"][j["key"]] = {**{kk: vv for kk, vv in j.items() if kk not in ("key", "description")},
                                      "first_seen": today, "status": "duplicate-of-" + hit["key"]}
        else:
            merged.append(j)
    new = merged

    for j in new:
        seen["seen"][j["key"]] = {**{k: v for k, v in j.items() if k not in ("key", "description")},
                                  "first_seen": today, "status": j.get("status", "new")}
    SEEN_FILE.write_text(json.dumps(seen, indent=1, ensure_ascii=False))

    present = [j for j in new if j.get("status") != "expired"]
    present.sort(key=lambda j: (j.get("posted") or ""), reverse=True)
    print(json.dumps({
        "date": today,
        "window_days": days,
        "wide_window_days": CFG.wide_window,
        "counts": {"pool": len(pool), "new": len(present), "skipped_seen": len(skipped_seen),
                   "skipped_applied": len(skipped_applied), "expired": len(new) - len(present),
                   "visa_blocked": sum(1 for j in present if j.get("visa") == "blocked"),
                   "visa_unknown": sum(1 for j in present if j.get("visa") == "unknown"),
                   "ambassador": sum(1 for j in present if j.get("kind") == "ambassador")},
        "applied_rows_loaded": len(applied),
        "candidates": present,
        "skipped_seen_items": sorted(skipped_seen, key=lambda x: x.get("first_seen") or "", reverse=True),
        "skipped_applied_items": skipped_applied,
        "ats_boards_failed": ats_failed,
        "discovered_boards": {"checked_ok": disc_ok, "total": disc_total},
        "apmlist": apm,
    }, indent=1, ensure_ascii=False))
    return 0


def show_config() -> int:
    pat = lambda r: r.pattern if r else None
    print(json.dumps({
        "name": CFG.name, "job_types": CFG.job_types, "terms": CFG.terms,
        "window_days": CFG.window_days, "wide_window_days": CFG.wide_window,
        "countries": CFG.countries, "cities": CFG.cities, "remote_ok": CFG.remote_ok,
        "needs_sponsorship_in": CFG.sponsor_countries,
        "unknown_countries": [c for c in CFG.countries if c not in COUNTRIES],
        "linkedin": {"enabled": CFG.use_linkedin, "queries": CFG.li_queries, "locations": CFG.li_locations,
                     "experience_levels": CFG.linkedin_experience},
        "simplify_feeds": CFG.simplify_feeds, "simplify_categories": sorted(CFG.simplify_categories),
        "ats_watchlist": CFG.use_ats, "watchlist_size": len(load_watchlist()),
        "discover_boards": CFG.use_discover, "apmlist": CFG.use_apmlist, "ambassador_programs": CFG.ambassador,
        "regex": {"job_type": pat(CFG.jobtype_re), "job_type_ats": pat(CFG.ats_jobtype_re),
                  "include": pat(CFG.include_re), "exclude": pat(CFG.exclude_re),
                  "term": pat(CFG.term_re), "stale_term": pat(CFG.stale_re)},
    }, indent=1, ensure_ascii=False))
    return 0


def check(title: str, location: str) -> int:
    ok, country = location_ok(location) if location else (True, "unknown")
    print(json.dumps({
        "title": title, "kind_linkedin": classify(title), "kind_ats": classify(title, ats=True),
        "role_ok": role_ok(title), "terms": terms_in(title),
        "location": location, "location_ok": ok, "country": country,
        "visa_check_applies": visa_check(country, "")[0] != "n/a",
    }, indent=1))
    return 0


def main() -> int:
    global CFG
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--days", type=int, default=None, help="default: window_days in config.json")
    r.add_argument("--li-pages", type=int, default=2)
    r.add_argument("--max-detail", type=int, default=30)
    r.add_argument("--no-discover", action="store_true",
                   help="skip the sweep of non-watchlist boards found in the Simplify feeds")
    sub.add_parser("config")
    c = sub.add_parser("check")
    c.add_argument("--title", required=True)
    c.add_argument("--location", default="")
    d = sub.add_parser("detail")
    d.add_argument("id")
    k = sub.add_parser("key")
    k.add_argument("--company", required=True)
    k.add_argument("--title", required=True)
    k.add_argument("--url", default="")
    a = ap.parse_args()
    if a.cmd == "key":
        print(make_key(a.company, a.title, a.url)); return 0
    if a.cmd == "detail":
        jid = normalize_li_id(a.id)
        if not jid:
            log("bad id"); return 1
        print(json.dumps(li_detail(jid), indent=1, ensure_ascii=False)); return 0
    CFG = load_config()
    if a.cmd == "run":
        return run(a.days or CFG.window_days, a.li_pages, a.max_detail, discover=not a.no_discover)
    if a.cmd == "config":
        return show_config()
    if a.cmd == "check":
        return check(a.title, a.location)
    return 1


if __name__ == "__main__":
    sys.exit(main())
