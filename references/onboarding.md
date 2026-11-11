# Onboarding

Run this when `config.json` or `profile.md` is missing from the skill folder, or when the user
says "set up my job search". Goal: learn enough to search well, then write the user's own
`config.json`, `profile.md`, `companies.json` (and `ambassador_programs.json` if wanted) into this
skill folder. Nothing personal ever goes into the `*.example.*` files.

## How to ask

- Ask in **short rounds of at most four questions**. If an `AskUserQuestion`-style tool is
  available, use it with multiple-choice options (users can always pick "Other" and type);
  otherwise ask in plain chat with the options listed. Free-text answers (names, titles, cities)
  are fine in chat.
- Open with one line on what's about to happen: "I'll ask about 15 quick questions in five rounds
  so the search only shows you jobs that fit. Takes about three minutes."
- Don't ask what you can already see. If the user shares a resume, read it and pre-fill school,
  grad date, experience and skills, then just confirm.
- Never invent anything about the user. Unknowns stay blank in `profile.md`.
- Skip questions that don't apply (no grad date or ambassador question for an experienced
  professional; no sponsorship follow-up for someone authorized everywhere).

## Round 1: About you

1. **What should I call you?** (first name or nickname; used in reports)
2. **Where are you in your career?** Student (undergrad) / Student (master's or PhD) / Recent
   graduate / Working professional / Career switcher
3. If a student or recent grad: **school, program/major, degree level, and graduation month +
   year.** (one free-text answer is fine)
4. **Want to share your resume, portfolio or LinkedIn?** A file path, a link, or pasted text.
   Optional, but it makes the 0-10 match ratings much more accurate. Read it now if given.

## Round 2: What you're looking for

5. **What type of role?** (multi-select) Internship / Co-op / New-grad or entry-level full-time /
   Experienced full-time / Part-time or contract
6. **Which roles or job titles?** Free text, e.g. "software engineer, mostly backend", "product
   manager or product designer", "data analyst", "marketing coordinator". Then ask: **only these
   titles, or also adjacent roles?** (e.g. for PM: product ops, technical PM, UX research)
7. **When do you want to start?** For internships/co-ops: seasons + year (Summer 2027, Fall 2027,
   Winter 2027 / January co-op, Spring 2027; several allowed). For full-time: a month/year, "as
   soon as possible", or "any time". For experienced roles also ask **seniority**: entry /
   mid / senior / staff+.
8. **Anything you definitely don't want?** Titles, keywords, or kinds of work to always filter
   out (e.g. "no sales", "no hardware", "nothing unpaid", "no call-centre support").

## Round 3: Where

9. **Which countries are you searching in?** (multi-select from the common ones the script knows:
   United States, Canada, United Kingdom, Ireland, Germany, Netherlands, France, Spain,
   Switzerland, Singapore, India, Australia, Japan, ... + Other). Don't assume the US or Canada.
10. **Specific cities, or anywhere in those countries?** And **remote / hybrid / on-site**: which
    are OK? Open to relocating?
11. **Work authorization in each of those countries.** For each: citizen or permanent resident /
    already authorized (work permit, OPT/CPT, graduate visa, etc.) / would need employer
    sponsorship / not sure. If they need sponsorship, ask which kind if they know (e.g. J-1 or
    H-1B in the US, Skilled Worker in the UK), and whether to **flag** roles that won't sponsor
    (default) or **hide** them.

## Round 4: Preferences

12. **Industries or domains you're excited about, and any to avoid?** (e.g. AI, fintech, gaming,
    climate, healthcare, consumer apps, government, defense)
13. **Dream companies?** Any number. These go on the watchlist and get called out in reports.
    Also: **company size preference**: big tech / mid-size / startups / no preference.
14. **Any other dealbreakers or must-haves?** e.g. must be paid, minimum pay, no relocation,
    language requirements, needs to be in-person, no unpaid "ambassador" gigs.

## Round 5: Logistics

15. **Do you keep an application tracker?** Google Sheet (share the link) / Excel or CSV file
    (path) / Notion database / None. It's read-only: the search uses it to hide roles you've
    already applied to. Ask which columns hold company and role if it's not obvious from a peek.
16. **Where should daily reports go?** Default `~/Job Search Reports/`.
17. **How often will you run it?** Daily (2-day window, recommended) / A few times a week (4-day
    window) / Weekly (7-day window). Offer to set up a **scheduled daily run** (see step 8).
18. Students only: **Also look for campus/student ambassador programs?** (Figma, GitHub, AI
    companies...) Yes / No.
19. Students only, when graduation date matters: **Some postings ask for a specific graduation
    year. Should I still show you ones where yours doesn't match?** Yes, flag them (soft,
    recommended: companies often make exceptions) / No, hide them (strict).

## Turning answers into files

### 1. `config.json`
Copy `config.example.json` and fill it in. Field by field:

- `name`: answer 1.
- `job_types`: from answer 5, using `internship`, `co-op`, `new-grad`, `full-time`. Part-time or
  contract → `full-time` (no job-type title filter) plus a `title_include` that names it.
- `terms`: internships/co-ops: `"Season YYYY"` strings exactly like Simplify's (`Summer 2027`,
  `Fall 2027`, `Winter 2027`, `Spring 2027`). A "January co-op" is `Winter YYYY` and usually also
  `Spring YYYY`. Full-time: `[]` (no term filter). `term_hints`: optional extra phrases that
  signal the right cohort, e.g. `"class of 2028"` for someone graduating in 2028.
- `roles`: start from the closest family in `references/role-presets.md`, then tailor:
  - `title_include`: words a matching title must contain (answer 6, plus adjacent roles if wanted).
  - `title_exclude`: seniority words (`senior`, `staff`, `principal`, `director`, `lead`...), the
    preset's excludes, and everything from answer 8. For an undergrad add `mba` and `phd`. For an
    internship-only search add `new grad\\w*`; for a new-grad-only search add `intern`,
    `internship`. Don't exclude a word that appears in the user's own target titles.
  - `discover_title_include` / `discover_title_exclude`: stricter filters for the discovery sweep
    (boards from every kind of company). Leave include `[]` to reuse `title_include`.
  - `linkedin_queries`: 3-9 searches, each a target title + the job-type word ("intern", "co-op",
    "new grad", or nothing for full-time). Every query costs requests in every LinkedIn location,
    so keep queries × locations under ~30.
  - `ats_search_terms`: two short phrases for Workday board searches, e.g. `"data intern"`.
  - `simplify_categories`: the preset's categories. Simplify's are `Software`,
    `Software Engineering`, `Product`, `Product Management`, `AI/ML/Data`,
    `Data Science, AI & Machine Learning`, `Quant`, `Quantitative Finance`, `Hardware`. Leave `[]`
    if none fit (titles are then matched on `title_include` alone).
- `locations`:
  - `countries`: names exactly as in the script's `COUNTRIES` table (`United States`, `Canada`,
    `United Kingdom`, `Germany`, ...). A country the table doesn't know can be added through
    `extra_city_markers`: `{"Estonia": ["tallinn", "tartu"]}` creates it.
  - `cities`: lowercase city names if the user only wants specific cities; `[]` = anywhere.
  - `remote`: whether remote roles with no stated country are kept.
  - `linkedin_locations`: what to type into LinkedIn's location box, usually the country names;
    cities work too ("Greater London", "Berlin, Germany").
  - `wide_window_days`: `{"Canada": 21}` for Canadian co-op/internship searches (those post in
    September bursts and stay open for weeks). Leave `{}` otherwise.
- `work_authorization`: one entry per target country: `"authorized"` or
  `"needs-sponsorship"` (append the kind in parentheses if known, e.g.
  `"needs-sponsorship (H-1B)"`). Only `needs-sponsorship` countries get visa checks.
- `window_days`: 2 for daily, 4 for a few times a week, 7 for weekly.
- `sources`:
  - `simplify_feeds`: Simplify only covers **US and Canada** postings well. If neither country is
    a target, set `[]` (that also disables discovery). Otherwise:
    - internships/co-ops → `https://raw.githubusercontent.com/SimplifyJobs/Summer<YEAR>-Internships/dev/.github/scripts/listings.json`,
      where `<YEAR>` is the summer of the recruiting cycle (the year of the latest target term).
      The repo is renamed each cycle, so **verify the URL returns JSON** before saving (a quick
      Python `urllib` fetch). If the next year's repo doesn't exist yet, use the current one.
    - new grad → `https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json`.
    - experienced full-time → `[]`.
  - `linkedin_experience_levels`: LinkedIn's `f_E` filter. Internship → `["1"]`; new grad →
    `["2"]`; experienced → `["3","4"]` (mid/senior) as answered; mixed → combine; `[]` = none.
  - `apmlist`: `true` only for product-management intern / APM searches.
  - `ats_watchlist`, `discover_boards`, `linkedin`: leave `true` unless a source doesn't fit.
- `ambassador_programs`: answer 18.
- `reports_dir`: answer 16.
- `tracker`: `type` = `google-sheet` | `excel` | `csv` | `notion` | `none`; `location` = sheet ID
  (the long ID in the sheet URL), file path, or database ID; `range` for sheets; column names.
- `schedule`: e.g. `"daily 08:00"` or `"none"`, for reference.

### 2. `profile.md`
Copy `profile.example.md` and fill in every `<...>` placeholder from the answers and resume. Keep
it factual and short. Write the scoring rubric in terms of *this user's* roles, domains and
blockers: the rubric is what makes ratings useful. Remove sections that don't apply.

### 3. `companies.json`
1. Copy `companies.example.json` (a starter list of mostly tech companies, many US/Canada).
2. Ask: **keep the starter list, trim it, or start empty?** Trim rows clearly outside the user's
   countries or interests (e.g. Canadian banks for someone searching only in Germany). Rows without
   no `ats` are checked by fetching their careers page, which costs time and usage, so they are
   checked weekly unless tagged daily (next step).
3. Add each dream company (answer 13). Find its job board: open the careers page and look for a
   `job-boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>`, `jobs.ashbyhq.com/<slug>`, or
   `<tenant>.wdN.myworkdayjobs.com/<site>` link. Verify the slug with the API URL from the file's
   `_comment` (it must return JSON). No public board → add it with `"ats": null` and its
   `careers_url`. Cap this at ~20 lookups during onboarding and say the rest can be added later
   ("add Spotify to my watchlist").
4. **Pick the daily careers-page list.** Among the `ats: null` rows, tag `"check": "daily"` on the
   ones the user most wants (dream companies, preferred domains) **whose roles the Simplify feed
   doesn't already list**: load the configured feed(s) and count rows for that company matching
   the user's `title_include` (any term). Zero matching rows → a daily candidate; Simplify already
   covers the rest, so Monday is enough for them. Keep it to roughly 10-15 and show the user the
   list. Skip this step if `simplify_feeds` is empty (then pick the 10-15 most-wanted).

### 4. `ambassador_programs.json` (only if answer 18 was yes)
Copy `ambassador_programs.example.json`. Re-tier programs by the user's interests (design tools,
AI, developer platforms...) and mark ones they've already applied to `skip_check: true`.

### 5. Seed the state
Create `state/`. Read the tracker once (SKILL.md step 1) to write `state/applied.json`. If the
tracker can't be read (e.g. no Google Sheets connector), say which connector is needed and write
`[]` for now.

### 6. Validate
- `python3 scripts/job_search.py config` → `unknown_countries` must be empty and every regex
  must look sensible. Fix and repeat.
- `python3 scripts/job_search.py check --title "<title>" --location "<city>"` on three titles the
  user **would** want (kind should be `job`, `location_ok` true) and two they **wouldn't** (kind
  `null`). Use realistic titles like "Software Engineering Intern (Summer 2027)". Adjust
  `title_include` / `title_exclude` until all five behave.

### 7. First run
Run SKILL.md steps 2-4 with `--days 7`. Tell the user the first run is bigger than usual: every
open matching role on the watchlist boards shows up once, and only new ones after that.

### 8. Schedule (if wanted)
If the user wants a daily run, create a scheduled task with whatever scheduling tool this
environment offers (e.g. the desktop app's scheduled tasks, or `/schedule`), with the prompt "Run
the job-search skill" at the time they choose. Mention the permission allowlist in the README so
the unattended run doesn't stall on prompts.

### 9. Wrap up
Summarise in a few lines: what was saved (roles, countries, terms, watchlist size, tracker), where
reports go, and how to change anything ("tell me 'update my job search' any time").

## Updating preferences later

When the user wants a change, edit only the affected fields:

| They say | Change |
|---|---|
| new / different roles | `roles.*` (all five lists) and the role-match part of `profile.md` |
| new country or city | `locations.*`, `work_authorization`, maybe `simplify_feeds` |
| new season / year | `terms`, `term_hints`, and the Simplify feed year |
| "stop showing me X" | `title_exclude`, or the domain section of `profile.md` |
| new dream company | `companies.json` (look up its board as in step 3) |
| new tracker | `tracker` |

Then re-run `config` and a couple of `check` calls. When the recruiting cycle rolls over (a new
SimplifyJobs `Summer<YEAR>-Internships` repo appears), update the feed URL and `terms`.
