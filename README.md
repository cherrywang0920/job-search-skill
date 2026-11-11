# job-search: a daily job & internship finder skill for Claude

A [Claude Code](https://claude.com/claude-code) skill that does your morning job scan for you.
It pulls fresh postings from several sources, drops the ones you've already seen or applied
to, rates each new one 0-10 against your profile, and writes a short ranked report.

It works for any role (software, product, design, data, marketing, finance...), any job type
(internship, co-op, new grad, full-time) and any country. The first time you use it, Claude
asks you a few rounds of questions and saves your answers into the skill, so it is set up for
you rather than for whoever wrote it.

It **only searches**. It does not apply to anything or write cover letters.

## What a run looks like

```
# New internships – 2027-01-12
Found 9 new (3 high, 4 medium, 2 low). Skipped: 41 already seen, 2 already applied.
Sources: simplify ok / ats ok (0 boards failed) / discovery ok / linkedin ok

## High
| # | Rating | Company | Role                        | Location      | Term        | Visa | Posted     | Link |
|---|--------|---------|-----------------------------|---------------|-------------|------|------------|------|
| 1 | 8/10   | Acme    | Software Engineering Intern | Toronto, ON   | Summer 2027 |      | 2027-01-11 | link |
- **1. Acme – Software Engineering Intern**: backend + infra, matches your Go/Kubernetes work; small cohort.
  Check: asks for 2029 grads, apply anyway.
...
```

## Where the jobs come from

| Source | What it catches |
|---|---|
| [SimplifyJobs](https://github.com/SimplifyJobs) internship / new-grad feeds | Structured listings with exact terms, locations and sponsorship info (US and Canada) |
| Company watchlist | Public Greenhouse, Lever, Ashby and Workday job boards of companies you pick, checked every run |
| Discovery sweep | ~1,000 more company boards found in the Simplify feeds, filtered strictly to your roles |
| LinkedIn guest search | Your queries × your locations, last N days, low volume |
| Careers pages | Companies with no public API (Google, Apple, Meta...) get a careers-page spot-check every run |
| apmlist.com (optional) | Status changes for APM / PM intern programs |
| Ambassador watchlist (optional) | Campus/student ambassador programs, checked weekly |

Everything is deduplicated across runs and across sources, and matched against your
application tracker (Google Sheet, Excel/CSV, Notion, or none) so roles you've applied to don't
come back.

## Install

You need Claude Code (CLI, desktop app or IDE extension) and Python 3.9+. The scraper uses only
the Python standard library, so there is nothing to `pip install`.

```bash
git clone https://github.com/cherrywang0920/job-search-skill ~/.claude/skills/job-search
```

Then open Claude and say:

> set up my job search

Claude will ask about 15 quick questions in five rounds: your name and background, what roles
and job types you want, when you want to start, which countries and cities, your work
authorization, industries and dream companies, and where you track applications. It then writes
your personal `config.json`, `profile.md` and `companies.json`, tests the filters, and runs a
first search.

After that, just say **"find new jobs"** or **"anything new?"**. To change something later:
**"update my job search: also look in Germany"**, **"stop showing me banks"**, **"add Spotify to my
watchlist"**.

### Optional connectors
- **Google Sheets** (or Google Drive) connector if your tracker is a Google Sheet.
- **Notion** connector if your tracker is a Notion database.
Excel/CSV trackers and "no tracker" need nothing extra.

### Run it every morning
During onboarding Claude can set up a scheduled daily run. Unattended runs stall on permission
prompts, so add an allowlist to `~/.claude/settings.json`, for example:

```json
{
  "permissions": {
    "allow": [
      "Bash(python3 ~/.claude/skills/job-search/scripts/job_search.py:*)",
      "Edit(~/.claude/skills/job-search/**)",
      "Write(~/Job Search Reports/**)",
      "WebSearch"
    ]
  }
}
```

Add `WebFetch(domain:...)` entries for the careers sites you want spot-checked, and
adjust the reports path if you chose a different one.

## Your data stays local

`config.json`, `profile.md`, `companies.json`, `ambassador_programs.json` and `state/` are
git-ignored. They live only in your skill folder, so `git pull` updates the skill without touching
your settings. Nothing is sent anywhere except the job-board requests themselves.

## Files

```
SKILL.md                         instructions Claude follows on every run
references/onboarding.md         the onboarding interview + how answers map to config
references/role-presets.md       title filters and queries for common role families
scripts/job_search.py            the scraper (stdlib Python)
config.example.json              config schema with an example
profile.example.md               profile + 0-10 scoring rubric template
companies.example.json           starter watchlist (~110 companies, mostly tech)
ambassador_programs.example.json starter campus ambassador watchlist
```

Useful script commands:

```bash
python3 scripts/job_search.py config                                   # show effective filters
python3 scripts/job_search.py check --title "Data Analyst Intern" --location "Dublin, Ireland"
python3 scripts/job_search.py run --days 7                             # search the last week
```

## Limitations

- SimplifyJobs mostly covers US and Canadian roles. Outside North America the search leans on
  LinkedIn and your company watchlist, so building a good watchlist matters more.
- The LinkedIn guest endpoints are unofficial and rate-limited. The skill keeps volume low; keep
  it that way and use it for your own job search only.
- Ratings are only as good as `profile.md`. Sharing a resume during onboarding helps a lot.
- Job boards change. If a watchlist company stops returning results, its board slug probably
  moved.

## Credits

LinkedIn parsing and the dedup key were adapted from
[MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) (MIT). Listings
data from [SimplifyJobs](https://github.com/SimplifyJobs). PM program statuses from
[apmlist.com](https://apmlist.com).

## License

MIT
