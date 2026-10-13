# Pre-written test of the planned-work finding (P1)

Written 2026-10-05, before any of the data named below has been analysed against planned-work reports. The git
commit that adds this file is its timestamp. Nothing in it may change after a test below is run; a change before
that is logged here with its date and reason.

## Why this test exists

Phase 5 found, after seeing results, that planned work (TCEQ maintenance, startup and shutdown reports) starting in
the 7 days before a day goes with a higher chance of a serious RMP accident at the same plant that day (1.66 per
doubling, 95% range 1.27 to 2.19; `docs/phase5_results.md` section 7; `data/manifests/phase5_diag_planned.json`).
It was found by looking, so it is a lead, not a result. This file fixes, in advance, how it will be tested on data
it was not built on.

Data already used to find it, and so **not** usable to confirm it: every RMP accident in the current accident table
(June 2003 to June 2025), at any plant, with any linking. The multiverse used windows ending 2021, 2022, 2023 and 2025,
so the 2022 to 2025 accidents are not fresh either.

## The claim being tested

P1: on days when a plant has planned work that started in the previous 7 days, its rate of serious accidents is
higher than on its other days in the same year.

## Exposure (same in every test)

- Planned-work reports: TCEQ event types MAINTENANCE, AIR STARTUP, AIR SHUTDOWN; same filters as the primary count
  (a date, a linked plant, not in the primary exclusion set, same-start duplicates merged), dated by the work's start.
- planned = log(1 + number of planned-work reports starting in days -7 to -1).
- Also in the model, as in the finding: unplanned = log(1 + EMISSIONS EVENT and EXCESS OPACITY reports starting in
  days -7 to -1), and each count's statewide total minus the plant's own, log(1 + x).
- Reports with an impossible event date (later than the data download, or starting 300 or more days after their
  own report date) are left out and counted. In a same-start group whose kept report is in the filed-in-error
  exclusion set, the earliest other report of the group is kept instead (D10 addendum).

## Model (same in every test)

Conditional Poisson with plant-year strata and month-of-year effects, errors clustered by plant (as the primary
H1 model): `y ~ planned + unplanned + xs_planned + xs_unplanned | plant_year + moy`. Result: rate ratio per doubling
of (1 + planned count), 2^beta, with its 95% range.

## Decision rule (fixed now)

- **Confirmed:** the lower end of the 95% range is above 1.
- **Contradicted:** the upper end of the 95% range is below 1.3 (rules out an effect of the size claimed, or anything
  close to it).
- **Inconclusive:** anything else. Reported as inconclusive, never as "a trend".
- **Power first:** before any real outcome is used, a power check plants a rate ratio of 1.5 on the test's own panel
  with fake outcomes (same method as the Phase 3 power runs, 200 draws). If power to confirm is below 50%, the test is
  still run but is labelled underpowered in its first sentence.
- One primary result per test below. Secondary results (startups only; work notified before it started; days 1 to 3
  and 4 to 7 separately) are reported as description, with no claim.

## The tests, in order of how fresh their data is

**T1. Accidents that happen after the current RMP data** (likely too weak to run; see the change log below). RMP accidents dated after 2025-06-14 (the last accident
date in the current table) at plants linked by the frozen v2 link table, once EPA releases them. Exposure from TCEQ
reports downloaded at that time. Run when at least 40 such accidents are available; until then, not run.

**T2. Another state.** Any state whose regulator publishes planned startup, shutdown and maintenance reports one by
one, with a start date and a facility identifier that can be linked to RMP. Louisiana is checked first. Before any
outcome is looked at, a written note fixes for that state: which report types count as planned work, how sites are
linked, and the study window; it is added to this file with its date. Outcome: RMP accidents in that state, all
years available.

**T3. A different accident record in Texas.** National Response Center reports judged serious (fire, injury,
fatality or evacuation flag) at linked Texas plants, after the author's hand review of links (plan section 6.4).
These records have not been analysed against any event data. Because some describe the same accidents as RMP,
the primary T3 result uses only NRC reports with no RMP accident at the same plant within 3 days. The version with
all serious NRC reports is reported beside it. T3 is the least independent of the three and says so.

## What will be reported

Every test that is run, with its power, its result and the decision, whatever it is. If tests disagree, all are
shown and none is picked. No new version of the exposure, window or model is added after a test's outcome is seen;
any further idea is labelled exploratory, as the finding itself was.

## Changes before any test was run

- 2026-10-05: the date and merge rules in the exposure section were made exact after the data review
  (D10 addendum). No test had been run.
- 2026-10-05: the review of the models found that planned-work reports fell from about 2,000 a year
  (2003 to 2009) to under 150 a year (2023 on). Linked plants: 1,000 to 1,400 a year to 65 to 110. With 40 new
  accidents, fewer than one would be expected to follow planned work, so T1 could not decide anything. Rule added:
  a test whose power check gives below 20% is not run, and the reason is reported instead. T2 and T3, which can
  use the years with many planned reports, become the main tests. No test had been run.

## Test log

- **T3, run 2026-10-06** (plan D11): National Response Center report days with no RMP accident at the same plant
  within 3 days, 205 days at 104 sites. Power check first: 30% (underpowered). Result: 1.37 (0.65 to 2.89),
  inconclusive. Details: `docs/phase5_results.md` section 9, `data/manifests/t3_planned_nrc.json`.
- **T2 in Louisiana, not run (2026-10-12).** Louisiana does not publish planned startup, shutdown and maintenance
  reports in general. The only dated planned-work records are notices under LAC 33:III.319 and 309 and a few
  variances, read from LDEQ documents (`data/louisiana/`; plan D13). At RMP-linked sites they give 21
  dated starts at 16 sites from 2009 to 2025. The power check, run before any Louisiana outcome was looked at and
  with accidents simulated at Texas rates (`src/t2_louisiana_power.py`), gives 7% power at the typical Texas rate
  and 10% even if every site had one accident a year: fewer than one accident would be expected in the week after
  any of these starts. By the rule above, T2 is not run in Louisiana.
