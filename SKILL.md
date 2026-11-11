---
name: job-search
description: Use this skill whenever the user asks to find, search, scrape, or check for new job or internship postings, asks to set up or change their job search preferences, or when a scheduled daily job-search task runs. On first use (no config.json or profile.md in this folder) it runs a short onboarding interview and saves the user's name, target roles, locations, seasons and preferences into the skill. Each run calls scripts/job_search.py (SimplifyJobs feeds + company job-board watchlist + board discovery + LinkedIn guest search), dedupes against past runs and the user's application tracker, rates every new posting 0-10 against profile.md, and writes a dated markdown report. Searching only; it does not apply to jobs or write application materials.
---

# Daily job search

Finds newly posted jobs or internships that match the user's target roles, locations and
start dates, skips anything already seen or already applied to, and produces a short ranked
report with a 0-10 match rating on every role.

## 0. First run: onboarding

Before anything else, check this skill folder for `config.json` and `profile.md`.

- **Either file is missing** → this user has not been onboarded. Follow
  `references/onboarding.md` from start to finish, then continue with step 1 only if the user
  wants a first search now.
- **The user asks to change their preferences** ("I'm also looking in Germany now", "add UX
  research", "stop showing me banks") → follow the "Updating preferences later" section of
  `references/onboarding.md`. Edit only what changed.
- A scheduled run that finds no config must not start onboarding on its own: write a one-line
  note telling the user to open a chat and say "set up my job search", and stop.

Throughout this file, "the user" means the person described in `profile.md`. Address them by
the name stored there.

## Files in this folder

| File | What it is | Personal? |
|---|---|---|
| `scripts/job_search.py` | The scraper (stdlib Python only). Every filter comes from `config.json`. | no |
| `config.json` | Machine-readable search settings written by onboarding. Schema: `config.example.json`. | **yes** |
| `profile.md` | Who the user is + the scoring rubric. Template: `profile.example.md`. | **yes** |
| `companies.json` | The user's company watchlist. Starter list: `companies.example.json`. | **yes** |
| `ambassador_programs.json` | Optional campus ambassador watchlist (students only). Starter: `ambassador_programs.example.json`. | **yes** |
| `state/seen_jobs.json` | Every posting ever surfaced (dedup memory). Don't hand-edit. | **yes** |
| `state/applied.json` | Rows from the user's application tracker, rewritten each run. | **yes** |
| `references/onboarding.md` | The onboarding interview and how to turn answers into config. | no |
| `references/role-presets.md` | Ready-made title filters and queries for common role families. | no |

The personal files are git-ignored, so the user can `git pull` skill updates without losing them.

Sources, in priority order:
1. **SimplifyJobs feeds** (`sources.simplify_feeds`): structured internship / new-grad listings,
   mostly US and Canada. Term, location and date filtering is exact here.
2. **Company watchlist** (`companies.json`): rows with an `ats` slug are checked every run through
   public Greenhouse / Lever / Ashby / Workday APIs. Rows with `ats: null` get a careers-page spot-check: the ones tagged `"check": "daily"`
   every run, the rest on Mondays (step 3b).
3. **Discovery sweep**: every Greenhouse/Lever/Ashby board that appears in the Simplify feeds but
   is not on the watchlist (~1,000 boards, cached in `state/discovered_boards.json`), with stricter
   title filters. ~80 seconds. Rows carry `discovered: true`. `--no-discover` skips it. When a
   discovered company keeps producing good roles, suggest adding it to `companies.json`.
4. **LinkedIn guest search** (`roles.linkedin_queries` × `locations.linkedin_locations`).
5. **apmlist.com** status diff (only when `sources.apmlist` is true; product-management searches).
   A hint only; it lags real postings and is sometimes wrong.

## Steps

### 1. Refresh the applied list from the tracker
Read `config.json` → `tracker`. Read only; never edit the tracker from this skill.

- `google-sheet`: use the **Google Sheets connector** (`get_values` on the spreadsheet ID in
  `tracker.location`, range from `tracker.range`, or call `get_spreadsheet` first for the tab
  name). Prefer it over the Drive connector's `read_file_content`, which returns a cached rendering
  that can lag behind the live sheet. Use Drive only as a fallback and say so in the report.
- `excel` / `csv`: read the local file at `tracker.location` (Python `csv`; for .xlsx use
  `openpyxl` if installed, otherwise ask the user to export a CSV).
- `notion`: query the database with the Notion connector.
- `none`: keep the existing `state/applied.json`. When the user mentions in chat that they applied
  somewhere, append `{"company": ..., "role": ...}` to it.

Write every data row as `{"company": ..., "role": ...}` into `state/applied.json` (a JSON array),
using `tracker.company_column` / `tracker.role_column`. Include rejected and ghosted rows too. If
the tracker can't be read, keep the existing file and say so in the report.

### 2. Run the scraper
```bash
python3 <this skill folder>/scripts/job_search.py run --li-pages 2 --max-detail 30
```
`--days` defaults to `window_days` in config. Use `--days 3` on Mondays (weekend backlog) and
after a skipped day. Countries listed in `locations.wide_window_days` always get at least that
many days (markets like Canadian co-ops post in bursts and stay open for weeks). Takes 1-3
minutes. stderr has per-source counts; stdout is JSON:
`{date, window_days, counts{...}, applied_rows_loaded, candidates[...], skipped_seen_items[...], skipped_applied_items[...], ats_boards_failed[...], discovered_boards{...}, apmlist{...}}`.

Each candidate: `source` (simplify|ats|linkedin), `company`, `title`, `location`, `country`,
`terms` (season hints; empty means unknown), `posted`, `url`, `kind` (`job` | `ambassador`),
`description` (LinkedIn snippet if fetched), `stale_term` (only past-year dates found), `also_in`
(other cities for the same posting), `visa` + `visa_evidence`, `sponsorship` and `degrees`
(Simplify only). The same posting from several sources is merged automatically, keeping the direct
employer URL and listing the rest under `also_seen_as`.

If `[simplify] FAILED`, `[apmlist] FAILED`, `ats_boards_failed` is non-empty, or `[linkedin] ...
FAILED` appears for every query, name the outage in the report. Never present a job that didn't
come from real script or search output.

**"Already seen" is not a black box.** `skipped_seen_items` lists postings dropped because they
were surfaced on an earlier day, with `first_seen` (= the date of the report they appeared in). If
today's report would be empty or thin, add a short "Seen earlier, still open" list so nothing good
silently disappears. Never list items whose `status` is `not-applicable` there (the user ruled them
out; set that status in `seen_jobs.json` when they do).

### 3. Fit-assess every candidate
Read `profile.md`, then give each candidate High / Medium / Low **and an integer 0-10 match
rating** built from the rubric there. The rating is required on every row of every section. Score
honestly, name the biggest drag in the bullet, and never round up to be encouraging.

- `terms` empty and no target-term hint in title/description → keep it, mark "term unknown". If
  `stale_term` is true → Low.
- **A past year in the posting body is often stale copy-paste, not the real term.** If the text
  says e.g. "summer 2026" but the posting was published recently, or sibling postings at the same
  company name the target year, treat it as the target term and note "body says <year>, likely
  stale copy". Check the ATS publish date (Greenhouse `first_published`) before downgrading.
- Degree-level gates (MBA-only, PhD-only, Master's-only) follow `profile.md`.
- Graduation-year windows follow the `grad_year_rule` in `profile.md` (default **soft**: at most
  -1 and a note "asks for <year> grads, apply anyway"; never "ineligible" for a grad year alone).
- Companies on the user's dream list or in the `big` tier → call it out.
- For a promising LinkedIn row with no description, you may run
  `python3 .../job_search.py detail <li_id>` (at most 5 extra per run).
- Don't invent deadlines, sponsorship, pay, or requirements. Only report what the data says.
- **Visa / work authorization**: `visa` is only checked in countries where `profile.md` says the
  user needs sponsorship. `blocked` (posting requires existing work authorization, citizenship, or
  says it does not sponsor) → mark the row ⚠ with the quote; it is a warning, not an automatic Low,
  unless `profile.md` says to treat it as a hard blocker. `sponsors` → note as a plus. `unknown` is
  never treated as blocked. For a High-fit role whose visa is `unknown`, spend one extra fetch to
  resolve it (`detail <li_id>` or WebFetch the posting; at most 5 per run).

### 3b. Spot-check the no-API companies (daily list every run, the rest on Mondays)
Companies with `ats: null` have no public API, so each check is a page fetch and costs real time
and usage. They are split in two:

- **Every run:** `ats: null` companies tagged `"check": "daily"` in `companies.json`. These are
  the user's must-not-miss companies whose roles the Simplify feeds do *not* list (onboarding
  picks them; keep the list to roughly 10-15).
- **Mondays (or when asked):** every other `ats: null` company. Big companies whose roles already
  appear in the Simplify feeds only need this weekly backstop.
- **Applied → weekly.** A daily-tagged company that already has any row in `state/applied.json`
  drops to the Monday pass (don't edit its tag). Companies often post a second batch later, so it
  keeps being checked weekly rather than never, and the role already applied to is filtered out
  by the tracker dedup anyway.

Open each `careers_url` with WebFetch (or a browser if WebFetch gets a JS shell) and look for
matching roles, several fetches at a time in parallel. One fetch per company, no pagination. If a
page can't be read (JS shell, 403), say so in one line and move on. To move a company between
the lists, add or remove its `"check": "daily"`. Anything found goes into the report as source "careers page" and must be
added to `state/seen_jobs.json` (`job_search.py key --company X --title Y` gives the key; add an
entry with today's `first_seen`) so it dedups next time. If apmlist is enabled, a company flipping
to "Open" is a prompt to check its careers page that day, not proof a role exists.

### 3c. Mondays: ambassador programs (only if `ambassador_programs` is true in config)
Read `ambassador_programs.json`. For `tier` `top` / `high`, open each `url` and read the current
application status; do `mid` / `watch` only on the first Monday of a month or when asked. Skip
`skip_check: true` entries. `status_seen` is a hint, never evidence. Check the `eligibility` field
against the user's country and school, and say "eligibility unconfirmed, check the form" when
unknown. When a status changed, update `status_seen` with today's date and the new text. Report
only programs that are open, newly opened, or closing within two weeks; a one-line "still closed:
X, Y" is enough for the rest.

### 4. Write the report
Save to `<reports_dir>/YYYY-MM-DD.md` (`reports_dir` from config; create the folder if missing)
and paste the same content as the chat reply. **Never overwrite an existing report for the same
day**: append a `## Re-run at HH:MM` section with only the delta.

Re-read the tracker right before writing and drop any candidate (and any "Seen earlier" row) the
user has applied to since step 1.

```
# New <job type>s – YYYY-MM-DD
Found N new (H high, M medium, L low). Skipped: X already seen, Y already applied.
Sources: simplify ok / ats ok (N boards failed) / discovery ok / linkedin ok
Visa: N roles flagged no-sponsorship, M unresolved      (omit when the user needs no sponsorship)

## High
| # | Rating | Company | Role | Location | Term | Visa | Posted | Link |
|---|--------|---------|------|----------|------|------|--------|------|
- **1. Company – Role**: one line on why it fits; one line on anything to check (visa quote, degree wording, deadline if stated).

## Medium
(same table, no bullets)

## Low / probably skip
| Rating | Company | Role | Location | Biggest drag | Link |   (one row each, never collapse to a count)

## Campus ambassador programs      (only when there are any; omit otherwise)
## apmlist changes                 (only if enabled and non-empty; say it is unverified)
## Seen earlier, still open        (only when the new count is small: company, role, first_seen, link)
```

- **Every row in every section carries a clickable link to the posting**, and so does any position
  named in the chat reply.
- Rating column: "N/10". Visa column: blank where no sponsorship is needed, "⚠ no sponsorship" when
  blocked, "sponsors" when explicit, "?" when unresolved. Drop the column if the user needs no
  sponsorship anywhere. Term column: drop it for full-time searches with no target term.
- **LinkedIn posted dates are unreliable.** LinkedIn's date often reflects a repost or relevance
  bump. For `source: linkedin` rows in High and Medium only, check the real date once (the
  company's own careers/ATS page, or a web search for the exact title + company and read the date
  off an aggregator). Write the confirmed date (`~2026-09-01 (confirmed)`), or `LinkedIn only,
  unverified`. Never call a LinkedIn role "fresh" or "just posted" without this check.
- Sort each section by rating (highest first), then newest posted. Keep it short: this is a
  morning scan, not an analysis.

### 5. Hand-off
End with: "Say the number(s) of any role you want to look at more closely." and stop. This skill
does not apply, draft cover letters, or add rows to the tracker.

## Manual invocations
- "find new jobs" / "anything new?" → steps 1-5 with the default window.
- "search the last week" → `--days 7`.
- "check this posting <linkedin url>" → `job_search.py detail <url>` and summarise.
- "why didn't X show up?" → `job_search.py check --title "<title>" --location "<location>"` shows
  which filter dropped it; then search `skipped_seen_items` / `seen_jobs.json`.
- "set up my job search" / "change my preferences" → `references/onboarding.md`.
- "reset job search memory" → only on an explicit request; delete `state/seen_jobs.json`.

## Rules
1. Never fabricate a posting. Everything shown must trace to script output or a real search hit.
2. Always dedup against both `seen_jobs.json` (the script does it) and the tracker (step 1).
3. Only the user's target countries, job types and terms (from config); flag "term unknown" rather
   than guessing.
4. Never silently drop a role for visa reasons, and never claim a role sponsors or doesn't without
   quoted evidence from the posting.
5. Keep LinkedIn volume low: don't raise `--li-pages` above 3 or `--max-detail` above 40. The
   LinkedIn guest endpoints are for light personal use.
6. Search only. Do not apply, do not draft materials, do not edit the tracker.
