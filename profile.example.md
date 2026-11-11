# <Name>'s profile (for fit assessment)

Template. Onboarding copies this to `profile.md` (git-ignored) and fills in every `<...>`.
Source of truth is the user's resume / portfolio: <path or link, or "none shared">. This file
is a summary for quick fit checks only. Never claim anything that isn't in it or the resume.

## Who
- <Name>. <Career stage: e.g. "3rd-year undergrad" / "recent grad" / "4 years as a ...">.
- <School, program/major, degree level, graduation month + year>   (omit if not a student)
- Based in <city, country>. <Open to relocating to ... / not relocating>. Remote: <ok / not ok>.

## Work authorization
- <Country A>: <citizen / permanent resident / authorized via ...>. No visa check needed.
- <Country B>: <needs employer sponsorship (kind, if known)>. A posting that requires existing
  work authorization or citizenship here is a real blocker.
- Blocked roles: <flag with ⚠ (default) / hide entirely>.

## Targets
- Job type: <internship / co-op / new grad / full-time ...>
- Roles: <core titles>. Adjacent roles worth surfacing as Medium: <list, or "none">.
- Start: <terms or date>.
- Never show: <exclusions from onboarding>.

## Experience
<3-6 bullets from the resume: role, company, dates, one line of what they did. Leave out if no
resume was shared.>

## Skills
<comma-separated list from the resume>

## Preferences
- Domains they're excited about (score 2): <...>
- Neutral (score 1): <...>
- Avoid (score 0): <...>
- Dream companies (call out in reports): <...>
- Company size: <big tech / mid-size / startups / no preference>
- Dealbreakers: <must be paid, minimum pay, language, in-person ...>

## Eligibility rules
- `grad_year_rule`: <soft | strict>. **soft** (default): a posting asking for a different
  graduation year is at most -1 with a note "asks for <year> grads, apply anyway"; never send a
  role to Low or below 5/10 for a grad-year window alone. **strict**: treat a grad-year mismatch as
  ineligible (Low).
- Degree level: <e.g. "undergrad: MBA-only, PhD-only and Master's-only postings are Low">.
- A past year in the posting body is not the term: postings published recently that say an
  older season are usually stale copy. Check the publish date and sibling postings first.

## Match rating (0-10), required on every listed role

One integer per role = how good this opportunity actually is for <Name>: match quality
discounted by realistic odds. Be honest and use the low end; an inflated score is useless.

- **Role match (0-4)**: <core titles>: 4. Adjacent (<adjacent roles>): 2-3. Title-only or stretch
  match: 1.
- **Eligibility (0-3)**: right level, right term, location fits, no work-authorization blocker: 3.
  -1 for an unstated term, -1 for a field-of-study mismatch they could still argue, -2 for a
  `blocked` visa, -3 for a hard gate (wrong degree level, wrong term entirely, wrong country).
  Grad-year windows follow `grad_year_rule` above.
- **Domain fit (0-2)**: from the Preferences section above.
- **Odds adjustment (-2 to +1)**: -1 to -2 for famous high-volume programs with thousands of
  applicants per seat; +1 when the pool is likely small (smaller company, niche domain,
  local-only, posting is days old).

Anchors: **9-10** rare, strong role and domain, eligible, winnable. **7-8** strong match, either
very competitive or one real gap. **5-6** decent with a real gap. **3-4** notable blocker.
**1-2** effectively ineligible, listed only for completeness.

Always name the single biggest thing dragging the score down. Never round up to be encouraging.

## Fit rubric (quick signal)
- **High**: <core roles> at a company in a preferred domain; eligible; target location; target
  term.
- **Medium**: core roles in a neutral/avoid domain, or an adjacent role.
- **Low**: hard eligibility gate (degree level, term, country); the core of the job is something
  they excluded; title matches but the work clearly doesn't.

## Campus ambassador programs   (delete this section if not wanted)
Rate on the same 0-10 scale, judged on brand relevance to <Name>'s interests, whether their
school/country is eligible, whether it is remote-friendly, and whether it is real (training,
community, resume-worthy) rather than unpaid promo work. Skip commission-only sales, nightlife
promo, and flyer-handing gigs.
