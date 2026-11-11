# Role presets

Starting points for `config.json` → `roles`. Pick the closest family (or merge two), then
tailor to the user's answers. All entries are regex fragments matched as whole words,
case-insensitive (`\w*` = any word ending; in JSON write it as `\\w*`).

Always add the seniority excludes for intern / new-grad searches:
`senior, sr\.?, staff, principal, director, lead, head of, vp`
(add `manager` too, except for product/project/program manager searches).

LinkedIn query pattern: `<title> <job-type word>`, where the job-type word is `intern`,
`internship`, `co-op`, `new grad`, or nothing for full-time.

---

## Product management
- include: `product`, `apm`, `product manag\w*`, `associate product`
- exclude: `engineer\w*`, `software`, `developer`, `marketing`, `sales`, `account`, `finance`,
  `data scien\w*`, `analyst`, `hardware`, `mechanical`, `electrical`, `industrial`, `design`
  (drop `design` if they also want design roles)
- discover include: `product\s+(?:manag\w*|intern\w*|strategy|owner|operations|&)`, `associate product`, `apm`
- discover exclude: `support`, `scientist`, `engineer\w*`, `developer`
- queries: product manager, product management, associate product manager
- ATS terms: `product intern`, `product manager`
- Simplify categories: `Product`, `Product Management`
- adjacent: product ops, technical PM, program manager, product analyst, UX research
- `apmlist: true` for APM / PM intern searches

## Product / UX / UI design
- include: `ux`, `ui`, `ui/ux`, `user experience`, `product design\w*`, `interaction design\w*`,
  `design`, `designer`
- exclude: `graphic`, `industrial`, `mechanical`, `electrical`, `interior`, `fashion`, `packaging`,
  `apparel`, `cad`, `ic design`, `chip`, `physical design`, `engineer\w*`, `software`,
  `developer`, `marketing`, `brand\w*`, `sales`
  (drop `graphic` / `brand\w*` for visual or brand designers)
- discover include: `product\s+design\w*`, `ux`, `ui`, `ui/ux`, `user experience`,
  `interaction design\w*`, `web design\w*`, `(?:product|ux|ui|web)\s*(?:&|and)\s*\w*\s*design\w*`
- discover exclude: `game design`, `audio`, `lighting`, `multimedia`, `artist`, `front-?end`,
  `engineer\w*`
- queries: product design, product designer, UX design, UX designer
- ATS terms: `design intern`, `product designer`
- Simplify categories: `Product` (design roles mostly land here; others are caught by title)
- adjacent: UX research, content design, design systems, UX engineering

## Software engineering
- include: `software`, `swe`, `developer`, `engineer\w*`, `backend`, `back-end`, `frontend`,
  `front-end`, `full[- ]stack`, `mobile`, `ios`, `android`, `platform`, `infrastructure`, `devops`,
  `sre`
- exclude: `hardware`, `electrical`, `mechanical`, `civil`, `chemical`, `structural`, `sales`,
  `support engineer`, `field engineer`, `recruit\w*`
- discover exclude: `firmware`, `rf`, `asic`, `fpga`, `silicon`, `test technician`, `manufacturing`
- queries: software engineer, software developer, software engineering
- ATS terms: `software intern`, `engineering intern`
- Simplify categories: `Software`, `Software Engineering`

## Data science / analytics / ML
- include: `data`, `analytics`, `analyst`, `machine learning`, `ml`, `ai`, `data scien\w*`,
  `business intelligence`, `bi`, `research scientist`
- exclude: `hardware`, `electrical`, `mechanical`, `sales`, `data entry`, `data center`,
  `data hall`, `clinical`, `financial analyst` (unless wanted)
- queries: data science, data analyst, machine learning, analytics
- ATS terms: `data intern`, `machine learning intern`
- Simplify categories: `AI/ML/Data`, `Data Science, AI & Machine Learning`

## Quant / trading
- include: `quant\w*`, `trading`, `trader`, `quantitative`, `research`
- exclude: `sales`, `operations`, `compliance`, `hardware`
- queries: quantitative trader, quantitative researcher, quant developer
- ATS terms: `quant intern`, `trading intern`
- Simplify categories: `Quant`, `Quantitative Finance`

## Hardware / electrical / embedded
- include: `hardware`, `electrical`, `embedded`, `firmware`, `asic`, `fpga`, `silicon`, `rtl`,
  `verification`, `pcb`, `analog`, `digital design`
- exclude: `sales`, `support`, `technician` (unless wanted)
- queries: hardware engineer, electrical engineer, embedded software
- ATS terms: `hardware intern`, `electrical intern`
- Simplify categories: `Hardware`

## Marketing / growth / content
- include: `marketing`, `growth`, `content`, `social media`, `brand\w*`, `communications`, `seo`,
  `community`
- exclude: `sales`, `door[- ]to[- ]door`, `commission\w*`, `telemarketing`, `engineer\w*`
- queries: marketing, growth marketing, content marketing, social media
- ATS terms: `marketing intern`, `growth intern`
- Simplify categories: `[]` (not well covered by Simplify; LinkedIn and the watchlist do the work)

## Business / consulting / strategy / finance
- include: `business`, `strategy`, `consult\w*`, `operations`, `finance`, `investment`, `banking`,
  `analyst`, `corporate development`
- exclude: `engineer\w*`, `software`, `sales representative`, `teller`, `collections`
- queries: business analyst, strategy, consulting, investment banking analyst
- ATS terms: `business intern`, `strategy intern`
- Simplify categories: `[]`

## Anything else
Build it from the user's own words: put the core nouns of their target titles in
`title_include`, the obvious false-positive neighbours in `title_exclude`, and run `check` on a
few real titles until it behaves. Set `simplify_categories` to `[]` if none of Simplify's
categories fit.
