# Analysis plan: do emission events rise before serious accidents at Texas plants?

Version: 1.0, frozen 2026-10-02, before any outcome analysis.
Date written: 2026-10-02

This plan is written before anyone has compared emission events with accidents.
Every change after it is frozen is listed, with its date and reason, in the
"Deviations" section at the end. Git history on the private repository records
when each version was written.

---

## The plan in plain words

- **The question.** Texas plants report small pollution upsets to the state
  (TCEQ "emission events"). Plants with large amounts of dangerous chemicals
  report serious accidents to the EPA (the Risk Management Program, RMP). We
  test whether a plant's small events become more frequent in the months before
  it has a serious accident.
- **Main test.** For each accident, we compare the plant's event rate in the
  90 days before it with the same plant's event rate at other times in the same
  year, after allowing for things that changed for everyone (storms, reporting
  rules, the economy). Comparing each plant with itself removes plant size and
  reporting habits as explanations.
- **Main outcome.** Every RMP-reportable accident. Narrower accident groups
  (fires and explosions, injuries and deaths, harm outside the fence) are
  tested as fixed backups.
- **Other angles.** Whether event-heavy plants have more accidents than
  similar plants, whether events help predict accidents in years the model
  never saw, and whether a second, independent source of incident reports
  (the National Response Center) shows the same thing.
- **Guarding against mistakes.** A shuffle test with fake accident dates, a
  test that should come out null if the method is honest, a long list of
  robustness checks fixed in advance, and a second independent implementation
  of the main model.
- **What we report.** Effects with confidence ranges, by sector, unit type and
  cause. Never a named plant. The result gets reported whether it is strong,
  weak or null.

---

## 1. What has been looked at before writing this plan

Seen while building and checking the data (counts only):

- TCEQ: 103,614 incident reports (January 31, 2003 to October 2, 2026), counts
  by year, region and event type; 71,027 are unplanned "EMISSIONS EVENT"; 4,350
  distinct regulated entities (RNs) have at least one report.
- RMP: 2,408 Texas facilities ever registered; 1,020 de-duplicated Texas
  accidents, 651 on or after January 31, 2003; counts by year (about 20 to 40
  a year, falling to 10 in 2022 and 4 in 2025, consistent with late reporting);
  167 with fire and 35 with explosion since 2003.
- Matching: 396 RMP facilities link to an RN that has emission events; 358 of
  the 651 accidents (112 fire, 24 explosion) are at those facilities; 900 RMP
  facilities link to any TCEQ RN.

Also seen while preparing the analysis (still no comparison of events with
accidents):

- the number of accidents in each plant-year, used to size the power
  simulation;
- the cause text of the 1,000 development-sample events, used to write the
  cause rules;
- the distribution of event counts in 90-day windows (57% of plant-days have
  none);
- model fits on fake accident dates only.

Not looked at: any count of emission events in relation to real accident
dates, and no model has been fit to real accident data.

## 2. Data

| Source | Use | Snapshot |
|---|---|---|
| TCEQ Air Emission Event Report Database, every incident page and per-incident contaminant export | Exposure (the warning sign) | Crawled October 2 to 3, 2026; byte-for-byte archive with SHA-256 per page |
| EPA RMP database via the Data Liberation Project (CC BY-SA 4.0) | Outcome, plant size, sector, registration dates | Commit recorded in `data/manifests/rmp_source.json`; data current to Dec 31, 2025 |
| EPA Facility Registry Service, Texas file | Linking TCEQ RNs to RMP facilities | Downloaded October 2, 2026, hash in manifest |
| EPA ECHO and ICIS-Air | Inspections, violations, enforcement (competing indicators, confounders) | Same |
| EPA combined emissions (NEI, TRI, GHGRP) | Plant size over time | Same |
| NOAA Storm Events | Storms and freezes by county | Same |
| National Response Center reports | Independent replication outcome | Same |

More sources were added on 2026-10-03, before any outcome analysis; see
Deviation D1 at the end for each one's role.

All downloads and every derived Texas slice are listed with SHA-256 hashes in
`data/manifests/`. The TCEQ list of incidents was proven complete three ways
(by start date, end date, and by region with no dates; region and event type
totals both equal 103,614).

## 3. Definitions

### 3.1 Plant

A plant is a connected group of TCEQ RNs and RMP facility IDs that share an
EPA Facility Registry Service REGISTRY_ID (program `TX-TCEQ ACR` for RNs,
`RMP` for RMP IDs). Building plants as connected groups settles the cases
where one RN maps to several RMP IDs or the reverse: their events and
accidents are pooled. Sensitivity R7 keeps only one-to-one links.

### 3.2 Time at risk

A plant is at risk from the later of February 1, 2003 and five years before its
first RMP submission, to the earlier of its RMP de-registration effective date
and the end of the study window.

Primary study window for accidents: June 1, 2003 to December 31, 2023. The
start leaves room for a full 90-day exposure window; the end leaves at least
two years for late RMP reporting. Sensitivity R8 uses 2003 to 2021 and 2003 to
2025.

### 3.3 Outcome (accidents)

From the RMP accident table, de-duplicated by the Data Liberation Project rule
(same facility and same day in different submissions is one accident), which
we re-check from the file that keeps duplicates.

- **O1, primary (confirmed by the author, 2026-10-02):** any RMP-reportable accident. By rule these already involve a
  death, injury, significant property damage, or known offsite effect, so the
  definition involves no judgment on our side.
- **O2:** fire or explosion (`RE_Fire` or `RE_Explosion` is Yes).
- **O3:** harm to people: any death or injury among workers, responders or the
  public, or any offsite death.
- **O4:** harm outside the fence. Any of: offsite deaths, hospitalization,
  medical treatment, evacuation, shelter in place, offsite property damage, or
  a Yes on the environmental damage flags (kills, minor defoliation, water
  contamination, soil contamination). The free-text "other environmental
  damage" field is not used, because reading it would take judgment.
- **O5, replication:** serious National Response Center reports at fixed
  facilities in Texas (fire, injury, fatality or evacuation), linked to plants
  by the rules in section 6.4.

### 3.4 Exposure (the warning sign)

- **Primary:** the number of unplanned emission events (event type
  `EMISSIONS EVENT`) at the plant whose start date falls in the 90 days ending
  8 days before the day in question (days -97 to -8).
- **Why the 7-day gap:** an accident is often itself reported to TCEQ as an
  emission event, and the upset that leads straight into it can be reported
  too. Counting those would make the test circular. The gap removes them.
  Sensitivity R2 uses gaps of 0, 1 and 30 days. Separately, we identify the TCEQ
  report that matches each accident (same plant, start within 2 days) and
  describe how often accidents appear in both systems.
- Events with an UNKNOWN start date use the end date; if both are unknown the
  event is excluded and counted.
- **Count occurrences, not report forms.** Reports with the same RN, the same
  start date and time, and the same event type count as one occurrence. There
  are 4,070 such extra reports, 4% of the total. They usually have consecutive
  incident numbers and the same report date, as when one outage trips several
  units and each gets its own report. Sensitivity R13 counts every report
  instead.
- **Reports that say they duplicate another report** (frozen rule
  `report_status.duplicate` in `rules/cause_rules.json`, about 0.6% of reports)
  are not counted.
- **Reports later found below the reportable amount** (about 4.5%) are
  counted: an upset still happened, and small upsets are exactly the warning
  sign under study. So are reports marked filed in error (about 0.8%).
  R17 drops both groups.

Secondary exposures (each with a written rule, fixed before linking to
accidents):

- severity: total pounds released (contaminants reported in pounds);
- duration of events;
- recurrence: repeat events at the same emission point within 30 days;
- event type: unplanned plus excess opacity; maintenance, startup and shutdown
  reports separately (these largely stop after about 2010);
- cause category and unit type (section 4).

## 4. Cause categories and unit types, without AI

Rules are keyword and pattern lists applied by code to the cause text and to
emission point and unit names. The categories:

- **Cause:** equipment failure (pump, compressor, valve, seal, leak, rupture),
  instrument or control failure, power loss or electrical, weather (lightning,
  freeze, hurricane, flood), process upset or unit trip, operator error or
  procedure, third-party or upstream supply, other or unknown.
- **Unit type:** flare, tank, compressor, heater or furnace, cracking or
  reforming unit, cooling tower, loading, other.

Procedure:

1. The rules are written using a random development sample of 1,000 events,
   with no accident information attached.
2. The rules are frozen and committed.
3. **Validation is done by people, independently of the rules.** The author, and ideally a
   second person, hand-code a separate random sample of 400 events. We report
   percent agreement and Cohen's kappa between the rules and the hand codes.

Only after this are categories linked to accidents.

## 5. Hypotheses and analyses

One primary test. Everything else is secondary or exploratory, as labeled.

### 5.1 H1, primary: events rise before accidents at the same plant

- **Data:** plant-day panel for linked plants.
- **Model:** conditional Poisson regression stratified by plant and calendar
  year (fixed effects for each plant-year).
  - Outcome: accident (O1) on that day.
  - Predictor: log(1 + primary exposure count).
  - Seasons: 12 month-of-year effects.
  - Statewide shocks: log(1 + the number of event occurrences at every other
    plant in Texas in the same window). Storms, freezes, reporting-rule
    changes and economic swings show up here, using one parameter instead of
    one per calendar month.
  - Formula: `y ~ x + xs | plant_year + month_of_year`, fit with pyfixest
    `fepois`, dropping groups with no accidents (separation check).
- **Post-accident days:** kept. Restarts after an accident cause their own
  upsets, which raises the event count in the days after. Those days mostly
  serve as comparisons, which pushes the estimate toward no effect, so this
  is a conservative choice.
  - The one way restarts could fake a rise is a chain: accident, restart
    upsets, then a second accident. R15 drops second accidents within 120
    days of an earlier one at the same plant.
  - Dropping all post-accident days instead was tested in the power
    simulation. It biased the estimate upward when a real effect exists:
    a planted 1.3 came out 1.39, and a planted 1.5 came out 1.68. It is kept
    only as R16, with that bias stated.
- **Effect:** rate ratio per doubling of (1 + events), with 95% confidence
  interval from standard errors clustered by plant.
- **Test:** two-sided, alpha 0.05.
- **Confirmation by shuffle test:** accident dates are moved at random within
  the same plant and year 10,000 times. If this p value is above 0.05 while the
  model's is below, the result is reported as not robust.
- **Picture:** event rate by month from 24 months before to 12 months after
  accidents, relative to each plant's own average, beside the same curve for
  fake accident dates.

### 5.2 H1, secondary versions (Holm correction within this family)

- outcomes O2, O3, O4;
- windows of 30, 180 and 365 days, and a lag profile (0 to 3, 3 to 6, 6 to 12,
  12 to 24 months before);
- dose and severity: top quarter of the plant's own distribution versus the
  rest; pounds released; recurrence;
- real-time version: count events by report date, so only what a regulator
  could have seen at the time is used.

### 5.3 H2, between plants: do event-heavy plants have more accidents?

- **Cohort:** plant-year panel of all 900 RMP facilities linked to a TCEQ RN,
  including those that never reported an event.
- **Model:** Poisson regression of accidents in a year on log(1 + events in
  the prior year).
- **Adjusted for:**
  - staff numbers, the largest regulated chemical quantity and the number of
    processes (from RMP);
  - sector;
  - emissions from the EPA combined inventory;
  - accidents in the prior five years;
  - year.
- **Standard errors:** clustered by plant.
- **H2b:** adds federal inspections, violations and enforcement in the prior
  year, to test whether events add information beyond what regulators
  already track.

### 5.4 H3, forward test: prediction in years the model never saw

- **Data:** plant-quarter panel.
- **Fit and test:** the H2 model is fit on 2004 to 2015 and tested unchanged on
  2016 to 2023. We compare a baseline model (size, sector, prior accidents,
  inspections and violations) with the same model plus events.
- **Measures:**
  - area under the ROC and precision-recall curves;
  - share of accidents in the top 10 percent of flagged plant-quarters;
  - calibration slope.
- **Uncertainty:** confidence intervals by bootstrap over plants.
- **No tuning:** the models are fixed in advance, and no machine learning is
  used.

### 5.5 H4, replication with an independent outcome (secondary)

H1 is repeated with O5 (National Response Center) as the outcome. That source
covers plants outside the RMP program too, so the panel widens to every RN with
emission events.

### 5.6 Exploratory (estimates with intervals, no claims of significance)

- **Breakdowns:** by sector (refining, chemicals, gas processing, other), by
  region group, by cause category and by unit type.
- **Which events matter most:** which cause categories and unit types carry
  the signal.
- **Concordance:** how often RMP accidents also appear in TCEQ reports.

## 6. Controls, checks and safeguards

### 6.1 Things that could fake a result, and how each is handled

| Threat | Handling |
|---|---|
| Bigger plants have more of everything | Within-plant design (H1); size covariates (H2) |
| Some plants report more diligently | Within-plant design; plant-by-year strata absorb slow drift |
| Reporting rules and statewide trends changed | Plant-year strata absorb year-level change; the statewide event count absorbs shifts within a year; R14 uses one effect per calendar month |
| Storms and freezes cause bursts of both | Statewide event count; R5 removes storm periods by county using NOAA; R6 uses the regional instead of statewide event count |
| The accident is itself an emission event | 7-day gap, R2, and the concordance check |
| Restart upsets after accidents | Kept as comparison days (conservative); R15 drops accident chains; R16 drops all post-accident days |
| Late RMP reporting | Window ends 2023; R8 |
| Linking errors | Connected-group plant definition; R7 one-to-one links only |
| One plant drives the result | Leave-one-plant-out influence check (R10) |

### 6.2 Robustness checks (fixed list)

- **R1:** windows of 30, 180 and 365 days.
- **R2:** gaps of 0, 1 and 30 days.
- **R3:** add excess opacity events; all event types.
- **R4:** count events by report date.
- **R5:** drop days whose window overlaps a county-level hurricane, tropical
  storm, winter storm, ice storm or extreme cold event (NOAA).
- **R6:** event count in the plant's own TCEQ region instead of statewide.
- **R7:** one-to-one plant links only.
- **R8:** study end 2021 or 2025.
- **R9:** merge accidents at the same facility within 3 days.
- **R10:** leave each plant out in turn.
- **R11:** conditional logistic (any accident) and negative binomial versions.
- **R12:** strata by plant only, with year and month-of-year effects.
- **R13:** count every report rather than merged occurrences.
- **R14:** one fixed effect per calendar month (`y ~ x | plant_year + year_month`),
  reported where it converges.
- **R15:** drop accidents that come within 120 days after an earlier accident at
  the same plant (their days only). This can only push the estimate toward no
  effect.
- **R16:** drop days 1 to 120 after every accident, as cases and as comparisons.
  It is known from simulation to overstate a real effect.
- **R17:** also drop reports that their text marks as not reportable or filed
  in error.

### 6.3 Tests that should come out null if the method is honest

- **N1:** accidents at other plants in the same county and sector should not
  be predicted by this plant's events, once the statewide event count is in.
  A clear positive result would point to shared shocks rather than a
  plant-level warning sign.
- **N2:** the shuffle test of section 5.1.

### 6.4 Linking National Response Center reports (for H4)

Deterministic rules only:

1. same county;
2. normalized company or site name tokens match;
3. street number match where available.

Every candidate match for a serious report is checked by hand by the author. We
report the number checked and rejected.

### 6.5 Power, before any outcome analysis

We plant known effects (rate ratios 1.0 to 1.5 per doubling of events) on fake
accident dates drawn within the same plant-years, then rerun the H1 model to see
how often each is detected. This uses the real event data and the number of
accidents in each plant-year, but never the real accident days, so it reveals
nothing about the answer.

Result: 300 fake datasets per effect size, run on 2026-10-02; the code is
`src/power_h1.py` and the output is `data/derived/power_h1.json`. The panel has
165 plants, 347 plant-years and 418 accidents.

| Planted rate ratio | Detected at p < 0.05 | Median estimate | Median 95% interval |
|---|---|---|---|
| 1.0 (no effect) | 4.7% (false alarms) | 0.99 | 0.81 to 1.22 |
| 1.1 | 14% | 1.11 | 0.90 to 1.36 |
| 1.2 | 37% | 1.18 | 0.98 to 1.44 |
| 1.3 | 76% | 1.30 | 1.07 to 1.61 |
| 1.4 | 92% | 1.39 | 1.13 to 1.70 |
| 1.5 | 97% | 1.48 | 1.21 to 1.82 |

The test has about 80% power for a rate ratio of about 1.32 per doubling of
events. Its false-alarm rate is correct, and its estimates are unbiased. A null
result will be reported as an upper limit on the size of any rise, not as
proof of no effect.

### 6.6 Independent check of the code

The H1 estimate is computed twice: once with an established library
(pyfixest), and once with a separate implementation of the conditional
Poisson likelihood written from scratch in NumPy. They must agree to three
decimal places before results are reported.

## 7. How results will be read

- **Strong support:** H1 rate ratio above 1, p below 0.05, the shuffle test
  agrees, and most robustness checks point the same way.
- **Null:** we report the upper end of the confidence interval as the largest
  effect the data allow ("if there is a rise, it is smaller than X").
- **Prediction, not cause:** the claim is that events are a warning sign, not
  that they cause accidents.

## 8. Reporting and privacy

- No plant, company or RN is named anywhere in outputs, tables, figures or text.
- Results by sector, unit type, cause and region group. Any table cell with
  fewer than 5 plants is suppressed or merged. No maps with plant locations.
- All pre-specified analyses are reported, including those that come out null,
  in a full results table in the appendix.
- Data derived from RMP carry the CC BY-SA 4.0 license.
- Nothing is made public without the author's approval.

## 9. Reproducibility

- One command rebuilds every table and figure from the archived data.
- Software versions are pinned.
- The TCEQ snapshot date, the RMP commit and every file hash are listed in
  the paper's appendix.
- Optional, recommended: register this frozen plan on OSF with an embargo, so
  its date is certified by a third party without making it public.

## 10. Decisions still open

- O1 as the primary outcome: confirmed by the author on 2026-10-02.
- Who does the hand coding (section 4) and the National Response Center link
  checks (section 6.4), and whether a second coder is available. Neither
  affects the primary test.
- Whether a professor reviews the plan (recommended). Any change that comes
  from a review is logged under Deviations with its date and reason.
- Whether to register the frozen plan on OSF with an embargo (recommended;
  needs the author's account).

## Changes made before freezing (no outcome analysis involved)

| Date | Change | Reason |
|---|---|---|
| 2026-10-02 | O1 confirmed as primary | Author's decision |
| 2026-10-02 | Events counted as occurrences; R13 added | 4,070 reports share plant, start time and type with another report (data check, no outcomes) |
| 2026-10-02 | Reports whose text says they duplicate another are not counted; R17 added | Found while writing the cause rules on the development sample (0.6% duplicates, 4.5% not reportable, 0.8% filed in error) |
| 2026-10-02 | O4 uses only yes/no environmental flags | The other field is free text and would need judgment |
| 2026-10-02 | Post-accident days kept in the primary analysis; R15 and R16 added | Power simulation on fake dates showed that dropping them biased real effects upward (1.3 estimated as 1.39, 1.5 as 1.68), while keeping them gave unbiased estimates (1.30 and 1.51) |
| 2026-10-02 | Primary time controls changed from one effect per calendar month to month-of-year effects plus the statewide event count; calendar-month version kept as R14 | In the power simulation on fake accident dates, the calendar-month version failed to converge on some datasets (about 246 month effects against about 365 accidents) and dropped about 20% of plant-days |

## Deviations (after freezing)

### D1, 2026-10-03: more outside data collected, no analysis changed

The aim was to add every public source that could make the study stronger.
This entry is written before any of the new data is downloaded, and before
any outcome analysis of any kind. **It adds no hypothesis test and changes
nothing in H1 to H4, R1 to R17, N1 or N2.** Any analysis that uses these
sources must first be added to this plan as its own dated entry, written
before outcome data is examined, saying exactly what is computed and whether
it is a check, a robustness test or description. Until then the new data is
used only for the roles below.

Roles: **V** = checks that the TCEQ events are real (validation of the
exposure); **O** = second ways to define a serious accident (secondary
outcomes, never replacing O1); **C** = possible controls for robustness
checks; **L** = better plant linking; **D** = description and context.

| Source | Role | Join to plants |
|---|---|---|
| EPA AQS hourly monitor data, Texas (SO2, ozone, NO2, CO, PM, wind, temperature, hourly HAPs and VOCs incl. benzene and 1,3-butadiene), plus site list | V, C | Distance to plant, wind direction |
| TCEQ CAMS and auto-GC hourly data (H2S and gaps not in AQS) | V | Distance to plant |
| NASA FIRMS yearly US fire and hot-spot files (MODIS 2000+, VIIRS 2012+), static-source flag | V | Distance to plant |
| EOG yearly flare-site lists and World Bank flare-volume file | V, D | Distance to plant |
| VIIRS Nightfire nightly data, only if the academic license is granted | V | Distance to plant |
| Iowa Environmental Mesonet hourly airport weather, all Texas stations | C | Nearest station |
| NOAA GHCN-Daily, all Texas stations | C | Nearest stations |
| NOAA HURDAT2 hurricane tracks | C | Distance to track |
| NOAA NLDN daily lightning counts (0.1 degree cells) | C | Plant cell and neighbours |
| OpenFEMA disaster declarations, Texas | C | County and dates |
| EIA weekly and monthly refinery runs and utilization (PADD 3, Texas Gulf Coast), daily spot prices | C | Statewide or regional time series |
| Federal Reserve industrial production and capacity use (chemicals, refining) | C | National time series |
| EIA refinery capacity by refinery (1994 on), EIA-860 and EIA-923 | C, L | Name, city, plant code |
| EPA CAMPD hourly unit data, Texas | C | Facility ID, location |
| EIA electric disturbance (OE-417) tables | C | Date and region |
| TCEQ Point Source Emissions Inventory (2010 on; emission-event and MSS columns 2016 on) | V, C, L | RN, air account |
| TCEQ Central Registry (RN, CN, programs, owner history) | L | RN, CN |
| TCEQ spills, agreed orders, judgments, SEPs, compliance history ratings | C, O, D | RN or name |
| EPA ECHO enforcement cases and penalties; ICIS-Air HPV history and stack tests; legacy AFS | C | FRS registry ID |
| OSHA severe injury reports (2015 on) | O | Name, address, location, with hand checks |
| OSHA inspections, violations (incl. 1910.119 process safety citations), accidents | O, C | Name and address, with hand checks |
| CSB investigations and CSB accidental release reports (2020 on) | O, V | Name and city, by hand |
| EPA refinery fenceline benzene reports (2019 on) | V, C | Name and address |
| News article list from GDELT, strict use only: publication batch time, website and link, filtered by written keyword rules, then hand checks; none of GDELT's machine tags | V of accident dates, O | By hand |
| City of Houston 311 air pollution requests | V, D | Location |
| Census County Business Patterns, BLS QCEW (Texas, by county and industry) | D | County |
| HIFLD Next layers (refineries, gas plants, power plants, RMP and TRI facilities), OpenStreetMap industrial areas | L | Location |
| Sentinel-5P TROPOMI SO2 and NO2 (2018 on), Texas window | D | Distance, long averages only |
| Regulatory history: 30 TAC 101 amendment record, Texas Health and Safety Code 382.0215 and 382.0216, EPA RMP rules (1996, 2004, 2017, 2019, 2024, 2026 proposal) | D | Dates |
| Published outside tallies of Texas emission events | V of completeness | Year totals |

Rules that keep this honest:
- No source here is coded with machine learning by us. Where a source's own
  fields may be machine-coded (OSHA injury codes, GDELT tags, the TROPOMI
  layer-height product), those fields are not used.
- Each download is recorded with URL, size, SHA-256 and time in the
  manifest, as before.
- Not obtainable, recorded so nobody thinks they were skipped: Texas Tier II
  chemical inventories (TCEQ states they are confidential under Texas
  Government Code chapter 418); PHMSA, NFIRS and some BLS files (the sites'
  own firewalls refuse this machine); Wayback Machine archives (refused);
  GOES lightning (about 5 TB with no way to cut out Texas, replaced by NLDN
  counts).

### D1 addendum, 2026-10-03: what was actually obtained

Written after the downloads finished and before any outcome analysis. Nothing in the frozen analyses changed.

- Collected as listed in D1, with these differences:
  - **Federal Reserve series:** FRED is refused by this machine's proxy, so the same G.17 industrial production and
    capacity files were taken from the Federal Reserve Board's own site.
  - **VIIRS Nightfire nightly data:** not obtained. It needs a signed license; the author applied on 2026-10-03 and
    approval is pending. NASA FIRMS hot spots and the yearly flare lists stand in for now.
  - **NASA FIRMS:** 2000 to 2024 only (2025 final files not yet released; no NOAA-21 yearly files exist).
  - **NOAA lightning counts:** 1987 to 2026; NOAA's 1986 file contains a directory listing, not data.
  - **EPA CAMPD:** 1997 to 2025 (the 1995, 1996 and 2026 files are not offered).
  - **TCEQ continuous monitors:** only the 21 hydrogen sulfide sites (1997 to 2026), plus all other
    parameters those sites reported; everything else comes from EPA AQS.
  - **Sentinel-5P:** reprocessed product where it exists (2018 to mid-2022), operational product after.
  - **Texas Tier II, PHMSA, NFIRS, Wayback Machine, GOES lightning:** not obtainable here (reasons in
    `docs/data_sources.md`).
- **News article links (GDELT), strict use:** rules were fixed and committed (`rules/gdelt_url_rules.json`)
  before any GDELT file was downloaded. Coverage: 400,075 of the 400,204 files in GDELT's own list for
  2015-02-18 onward (128 files are not on GDELT's server, mostly 75 on 2022-11-11 and 28 on 2015-05-29; one more
  has a size and checksum that disagree with the list and was processed as served), plus the daily files
  for 2013-04-01 to 2015-02-18 (685 of 689, four not on the server). 731.8 million article rows scanned; 996,870
  distinct hits for the written rules, of which 85,457 have a Texas place word or come from a Texas news
  website. These are candidates only. Every use needs a hand check, and the report states that GDELT's own
  coding is automated and not used.
- A few short stretches of the run had two copies of the GDELT downloader running at once, and the disk was briefly
  full once; the affected files were retried and every record was checked afterwards (0 problems,
  `data/manifests/download_check.json`). The 56,774 resulting duplicate hit rows were removed in `derived/`,
  while the raw hit files were kept as written.

### D2, 2026-10-03: decisions on late reporting, dates, linking, rule changes and disasters; analyses using the new data

Decided on 2026-10-03, before any outcome analysis. The measurements behind them use the accident
records alone (when accidents were filed, how dates were corrected); nothing compares accidents with emission
events. Sections 1 to 9 stay as frozen; where this entry differs, this entry applies, and both versions are
reported.

**1. Study window: the primary window now ends December 31, 2021 (was 2023).**
- *Why:* filing lag, measured on accidents from 2005 to 2018 (every one of them has had at least 7 years to be
  filed): 50% are filed within 1 year, 79% within 3 years, 96% within 5 years. Applied to the December 2025
  data, the expected share already filed is about 98% for 2020, 92% for 2021, 84% for 2022, 72% for 2023,
  58% for 2024 and 34% for 2025. 2023 would enter the primary test about a quarter incomplete.
- *What is reported:* the 2021 primary result, with the original frozen choice (end 2023) shown beside it at
  equal prominence, plus end 2022 and end 2025. R8 becomes these four ends. **R8b:** end 2025, with each
  accident year weighted by the inverse of its expected completeness (stated as a model-dependent check).
- *Power:* the power simulation (section 6.5) is rerun on the new window and the new linking (item 3) before
  any outcome analysis, using fake accident dates as before.

**2. Accident dates.**
- *Found:* 162 accident rows sit in filings received before the accident date. Every one of them was added
  later through a correction to that filing (the correction dates are in EPA's change history), so none is a
  date error. 7 accidents had their date changed by the plant (EPA keeps the old date).
- *Rule:* each accident takes the date in the latest version of the record (the corrected date).
  **R18:** use the original dates for the 7 changed accidents.
- *Possible doubles:* pairs at the same facility, from different filings, 1 to 31 days apart, with the same
  chemicals and the same release-type flags (4 pairs found), and accidents within 3 days of another at the same
  facility (17). Each is reviewed by hand, seeing only the two accident records (never events, never other
  accidents), with this written rule: merge when duration, release source, consequences and weather fields agree
  or differ only where one record is blank; otherwise keep both. A merged accident takes the date from the most
  recent filing. Every decision is listed with its reason. R9 (merge everything within 3 days) stays; **R19:**
  merge nothing.

**3. Plant linking: extended to every Texas RMP facility.**
- Steps, applied to all 2,408 Texas RMP facilities whether or not they had an accident:
  1. the existing EPA registry links (section 3.1);
  2. address match to the TCEQ Central Registry (street number, normalized street name, and city or ZIP);
  3. location match: RMP coordinates within 1 km of a TCEQ site's coordinates (Point Source Emissions
     Inventory, spills, monitor and permit records), together with at least one shared name word that is not a
     generic word (company, plant, inc, and similar, listed in the linking code);
  4. every match from steps 2 and 3 that step 1 did not already make is reviewed by hand, seeing only names,
     addresses, coordinates and industry codes, never events or accidents. Decisions and reasons are listed.
- The finished link table is frozen and hashed before any outcome analysis. Counts are reported: links by
  step, rejected candidates and reasons.
- **R20:** the original registry-only links. R7 (one-to-one links only) stays.

**4. Reporting-rule changes.** Texas emission-event reporting rules changed effective 2006-01-05 (HB 2129
amendments), 2014-04-17 and 2015-07-30 (small-source reporting removed).
**R21:** H1 estimated separately in 2003 to 2005, 2006 to 2014 and 2015 to the window end, with a test of
whether the three estimates differ.

**5. Disasters.**
- **R22:** drop days whose exposure window or the day itself falls within a FEMA major-disaster or emergency
  incident period for the plant's county, for hurricanes, tropical storms, severe storms, floods, severe ice
  and winter storms and fires, plus the 7 days after each period ends.
- **R23:** drop days within 7 days of a hurricane or tropical storm passing within 150 km of the plant
  (NOAA HURDAT2).
- **R24:** drop March 1 to December 31, 2020 (COVID shutdowns and restarts; the FEMA COVID declarations cover
  every county for years, so they are handled by dates instead).

**6. New controls (robustness only).**
- **R25:** add, for the plant: days in the window with a hard freeze (minimum below 28 F), days with
  thunderstorms or lightning in the plant's 0.1 degree cell, and the highest wind gust (nearest airport station
  with data, NOAA NLDN lightning counts).
- **R26:** add statewide refinery utilization (EIA, Texas Gulf Coast monthly) and the Federal Reserve chemical
  and refining output indexes for the window.

**7. New outcomes (secondary or exploratory, each with a written definition).**
- **O6, secondary:** OSHA severe injury reports (hospitalization, amputation or loss of an eye; 2015 on) and
  OSHA fatality and catastrophe investigations, at establishments linked to plants by the same address and
  location rules as item 3, with hand review. H1 is repeated with O6 for the years it covers.
- **O7, descriptive only:** CSB investigations and CSB accidental release reports in Texas (too few to test).
- **Completeness and dating checks, descriptive:** serious Texas plant accidents found in CSB, NRC, OSHA and
  the hand-checked GDELT news candidates are compared with RMP: how many are missing from RMP, and how far
  RMP dates differ from first news reports.

**8. Checking the warning sign itself (uses no accident data, so it can run first).**
- **V1:** air monitors. For each unplanned event at a linked plant with an EPA or TCEQ monitor within 10 km,
  compare the hourly concentration of the reported pollutant family (SO2, NOx, benzene, 1,3-butadiene,
  hydrogen sulfide, VOCs) during the event, when the wind blew from the plant, with the same hours on matched
  non-event days at the same monitor (same month, same wind sector, other years). Reported as the ratio and its
  interval, and the share of events with a detectable rise.
- **V2:** satellite heat. NASA FIRMS detections within 1 km of the plant on nights during reported flaring or
  release events versus other nights at the same plant. VIIRS Nightfire is added if the license is granted.
- **V3:** refinery fenceline benzene (2019 on): quarterly fenceline values versus the number of reported events
  at that refinery in the same quarter.
- **V4:** complaints. TCEQ complaints and Houston 311 air complaints within 5 km in the 3 days after events
  versus matched days.
- **V5:** amounts. Emission-event totals in the Point Source Emissions Inventory (2016 on) versus the sum of
  reported pounds in the event database for the same site and year.
- **V6:** count check against the published watchdog tallies (already done: within a few percent for most
  years once definitions are matched).

**9. Showing every reasonable choice (multiverse).** H1 is also run over every combination of: window end
(2021, 2022, 2023, 2025), gap (0, 1, 7, 30 days), window length (30, 90, 180, 365 days), events counted
(unplanned; plus opacity; all types), linking (registry only; full; one-to-one) and doubles (merged; not).
The full spread of estimates is shown in one figure and a table. The primary result stays the primary result;
this shows whether it depends on any one choice.

**10. Order of work.** Linking (item 3) and the doubles review (item 2), then the power rerun, then the
warning-sign checks (item 8), then the frozen analyses with these additions, then an independent adversarial
review of the full analysis, then the report. The author's 400-event cause check is needed before the cause
breakdowns. Registration of this plan on OSF is decided separately by the author.

**D2 note, 2026-10-03 (missing covariates, H2 only):** a covariate missing in a plant's filing (for example staff
numbers) takes the most recent non-missing value from that plant's RMP filings; plant-years still missing a
covariate are dropped from H2 and counted. This was stated in the preregistration form and is recorded here so the
two match.

### Registration, 2026-10-03

This plan (version 1.0 with deviations D1 and D2) was registered on OSF as **osf.io/nf426** (template "OSF
Preregistration", license CC-BY 4.0), under embargo, before any outcome analysis. The five attached files and their
SHA-256 values are listed in `docs/osf_registration_hashes.txt`; the plan PDF there was printed from this file at the
commit named in that list. Any later change is recorded below as a dated deviation.

### D3, 2026-10-04: plant linking rules made specific and tested (after registration, before any outcome analysis)

D2 item 3 described the linking steps in outline. Before building the link table, each step was tested against
the existing EPA registry links, using only names, IDs, addresses and coordinates (no events counted, no
accidents). The tests changed the rules as follows; the full rules are in `rules/linking_rules.json`.

- **Added: IDs the plant wrote in its own RMP filings.** RMP filings have fields for other EPA IDs and the Title V
  permit number. Where one equals an ID TCEQ lists for an RN (hazardous waste EPA IDs, water permits, Title V
  permit numbers), the link is accepted automatically only if the RN is in the same county and has the same street
  address or lies within 1 km. Measured: 91% (listed IDs) and 93% (Title V numbers) of such links equal the
  registry's own RN where the registry has one, and the rest read one by one are mostly a second RN at the same
  site. Matches in a different county are rejected: every one inspected was a number collision with an unrelated
  plant.
- **Address-only and location-plus-name matches are not accepted automatically.** Measured agreement with the
  registry was 69% for exact addresses (large complexes share one address across several companies) and at most
  88% for location plus name. As D2 already required, they go to hand review.
- **Hand review is done by a person (the author), not by software,** on a review page that shows only the two
  records (names, addresses, county, coordinates, industry codes, program IDs), never emission events or
  accidents. Only pairs whose RN reports at least one emission event are reviewed, because only those change the
  exposure in H1; this narrows H2 membership slightly and is reported.
- **Chains:** plants whose members lie more than 5 km apart or hold more than 10 RNs are listed for review.
- **Duplicate accidents (D2 item 2), applied by code:** the written rule is mechanical, so it is applied by
  `src/accident_doubles.py` with no judgment. One condition was made explicit when it was first run: a merge also
  requires the two records to come from different filings. Two records in the same filing are the plant's own
  statement that there were two accidents (the de-duplicated table already merges same-day records across filings).
  Result: 20 candidate pairs, 3 merged, 17 kept, each listed with the fields that disagree in
  `data/derived/accident_doubles.csv`.
- R20 (registry-only links) remains the check against all of this.
- **Review scope, made specific when the queue was built (2026-10-04):** address and location candidates are reviewed
  only for RMP facilities that have no accepted link to an event-reporting RN. For a facility that already has one
  (by registry or its own ID), extra candidates are mostly neighbours inside the same industrial complex, and adding
  them would risk joining different companies' sites. Those candidates are listed in the link file but not added.
- **Plants whose members lie in different counties or more than 5 km apart are reviewed link by link,** including
  registry links: building the table showed that EPA's registry itself joins some unrelated sites (for example a
  facility hundreds of km away given another site's coordinates). A link the reviewer marks as different is removed.

- **Linking rules v1.2 (2026-10-04, before any review answer was used):** name-word frequency is now counted over
  site names plus customer names, the same strings that are compared. Under v1.1, legal-form words (INC, LLC,
  COMPANY, CORPORATION) counted as shared evidence because they are rare in site names alone; 264 of 549 location
  candidates rested on them. Against registry links, location candidates with a shared word agreed 32% of the time
  under v1.1 and 51% under v1.2, and the removed candidates almost never agreed. The review queue fell from 612
  pairs to 375.

- **Review answers recorded (2026-10-04):** the author answered all 612 v1.1 match pairs; the answers are kept in
  `data/manual/link_review_decisions.json` (with the hash of the author's spreadsheet). The 375 pairs in the v1.2
  queue are all among them. A "same plant" answer adds a link only for a pair the current rules send to review, so
  answers on pairs that v1.2 no longer suggests are kept on record but not applied. Nine pairs whose spreadsheet row
  named a different ID than the page pair are held back; the four of them in the v1.2 queue go back to the author.

- **Final link table, frozen 2026-10-04 before any outcome analysis** (hashes in `data/frozen/link_table_freeze.json`):
  accepted automatically 1,669 links (registry 1,373, own IDs 296); the author's review added 106 links (location
  and name 69, address 36, unconfirmed ID 1) and removed 33 accepted links found wrong in the group check
  (registry 25, own ID 8); 72 cross-county ID matches rejected. Result: 6,037 plants, 1,140 joining RMP and TCEQ
  records, 596 of them with an RN that reports emission events (494 before the review); 1,221 of 2,408 Texas RMP
  facilities sit in a joined plant. The 28 groups still flagged by the chain check after review have every link
  reviewed. Tables built on it: `src/build_tables.py v2` (duplicate merges applied); `h1.load("v2")`.

*Wording-only edits on 2026-10-03, no change in meaning: section 4 item 3, D2 item 10, and names replaced by "the author" throughout.*

### D4, 2026-10-04: additions from the literature review (approved by the author, before any outcome analysis)

A review of the process-safety and risk-communication literature (CCPS process safety metrics, API RP 754, HSE
HSG254, the Baker Panel and CSB reports on Texas City, the EPA 2024 RMP rule, work on hindsight bias, outcome
bias and base-rate neglect) led to these additions. None of them changes H1 or any test already listed; each is
written before any outcome analysis.

**1. Framing.** API RP 754 and CCPS treat small releases and demands on safety systems (Tier 3) as leading
indicators of serious process safety events, on the stated belief that the two share causes. This study is
presented as a test of that belief with public data. A null result is reported as evidence about the belief,
with its power stated, not as a failed study.

**2. H1-M, mechanism contrast (secondary, added to the section 5.2 family under Holm correction).**
- Each event's primary cause comes from the frozen cause rules (`rules/cause_rules.json`, section 4). Events are
  split into three counts in the same window: **process control** (primary cause equipment, instrument, process
  upset or operator/procedure), **outside or planned** (weather, third party, power or electrical, maintenance or
  startup) and **unknown**.
- Model: `y ~ log(1 + E_process) + log(1 + E_outside) + log(1 + E_unknown) + xs | plant_year + month_of_year`.
- Test: the difference between the process-control and outside-or-planned coefficients, two-sided, with its 95%
  interval from the plant-clustered covariance.
- Stated in advance: if events warn of weak control of the process, the process-control coefficient is the larger
  one. If the two are about equal, a rise before accidents more likely reflects general activity or reporting at
  the plant than a specific warning. Either outcome is reported.
- Reported together with the agreement between the cause rules and the author's 400-event hand check.

**3. R27, prior accidents.** H1 plus a day-level indicator for an accident at the same plant in the 365 days
before that day. Plant-year strata already absorb a plant's usual accident rate; this checks whether a recent
accident, rather than the events, carries the signal (EPA's 2024 rule cites a past accident as one of the best
predictors of the next).

**4. R28, ownership changes.** H1 dropping plant-days within 365 days after a change of owner or operator, found
where the parent company name or the operator name differs between consecutive RMP filings of a facility at the
plant (compared in upper case, punctuation removed, legal-form words such as INC, LLC, LP, CORPORATION removed). A
new owner can change how events are reported as well as how the plant is run.
- *Considered and not added:* a check on events reported just above the reportable quantity. The event records
  carry permit limits (mostly in pounds per hour), not reportable quantities, so the check cannot be defined
  without outside assumptions.

**5. Usefulness in plain numbers (descriptive, no tests).**
- For three simple flags, fixed now: at least 1, at least 3 and at least 10 unplanned event occurrences at the
  plant in the prior 90 days; and for the top 10% of plant-quarters flagged by the H3 model.
- For each flag, reported as natural frequencies per 1,000 plant-quarters: how many flagged plant-quarters had an
  accident in the next quarter, how many unflagged ones did, the share of accident quarters that were flagged
  (sensitivity), and false alarms per true alarm.
- Every relative result (rate ratios) is shown beside absolute accident rates per 1,000 plant-years, so that a
  large ratio on a rare outcome is not read as a large risk.

**6. Reporting rules (adds to section 8).**
- No number in any public output rests on fewer than 5 plants or fewer than 5 accidents; such cells are merged or
  suppressed. No plant is named or ranked, and no map shows plant locations.
- Wording: "came before", "associated with", "warning sign"; never "caused" or "predicts disasters". Hindsight
  explanations of single accidents are not used as evidence.

**Power rerun (D2 item 1), 2026-10-04,** on the frozen v2 links with merged duplicates, fake accident dates only,
300 runs per planted ratio (files `data/manifests/power_h1_v2_*.json`). Window ending 2021: 216 plants, 426
plant-years, about 546 accidents in the panel; share of runs detecting a planted ratio of 1.2 / 1.3 / 1.4: 54% /
83% / 98% (v1 registry links ending 2023: 37% / 76% / 92%). Window ending 2023: 59% / 91% / 98%. Estimates stay
unbiased (planted 1.3 estimated 1.29 to 1.30). With no planted effect, the 2021 run gave 7.7% of runs below
p = 0.05 in 300 runs; 2,000 further runs gave 5.9% (95% interval 4.9% to 7.0%; R15 5.5%, R16 5.1%), within chance
of 5% but possibly slightly high, as plant-clustered errors can be with about 200 plants. No change: the
shuffle test (section 5.1), which does not rely on those errors, remains the confirmation of any H1 result.

### D5, 2026-10-04: two more ways to locate unlinked sites, tested; the frozen link table is unchanged

About 2,350 of the 4,350 RNs with event reports have no coordinates in any public file (mostly oil and gas leases
and pipelines, which hold no RMP plan); 66 plants with RMP accidents have no TCEQ link (23 water or wastewater,
14 cold storage or food, 11 oil and gas or gas processing, 4 chemical, 14 other). Two mechanical ways to close the
gap were tested before any outcome analysis:
- **Coordinates written in Central Registry location descriptions** (`src/parse_location_text.py`, pattern matching
  only): points for 2,060 RNs; where other coordinates exist, 94.5% lie within 1 km of them (median 0.38 km).
  Only 11 RNs with event reports gained a location, and none produced a new candidate pair.
- **Operator name, county and industry group** (for RNs with no coordinates): against registry links it agreed
  0.4% of the time (one company runs many sites in a county), so it was rejected and not used.
The link table frozen on 2026-10-04 therefore stands. The author is requesting from TCEQ, under the Public Information Act,
for the Central Registry coordinates of every RN; if they arrive, the frozen rules are run unchanged with them added
and the result is reported as **R29** (links with TCEQ's coordinates added) beside the primary result.

### D6, 2026-10-04: data dossier findings, extra checks, and exact rules for the warning-sign checks (approved by the author, before any check or outcome analysis)

The data dossier (`docs/data_dossier/`) read every dataset before any analysis: all 103,614 event reports by code
and 3,058 one by one, every hourly monitor row, the fenceline, complaint, 311, satellite and inventory files, and
the RMP filings by structure only (no accident record was read). The author approved the items below on
2026-10-04. They add checks and rules; no primary rule of the registered plan is changed.

**1. Added robustness checks for H1 (run with the main test, never before it).**
- **R17 extended:** R17 also drops reports whose text says the event never happened, was cancelled, was rescinded,
  voided or should not have been filed (`NARROW_NON_EVENT` in `src/census_event_text.py`; 209 of the 29,192 reports
  that can enter the main test beyond the frozen rules; about 22 of 25 random hits read as correct).
- **R30:** counts as one occurrence any report that names another report's incident number at the same plant
  within 7 days, or that uses split, continuation or duplicate wording (`NARROW_DUPLICATE`); the merged occurrence
  takes the earliest date. This is the opposite direction to R13.

**2. Severity measure (not yet used; rules fixed before first use).** Severity is the sum of pounds in four
families that do not overlap: sulfur dioxide, hydrogen sulfide, nitrogen oxides, carbon monoxide (name lists
`CONTAM_FAMILY` in `src/census_monitors.py`, frozen here). VOC severity is reported separately as the larger of a
report's total-VOC rows and the sum of its single hydrocarbon rows. 0.0001 is read as zero; carbon dioxide,
nitrogen, hydrogen, water and steam are excluded; opacity above 100% is missing.

**3. H2 covariate.** An RMP staff count of 0 (811 filings) is treated as missing, with the result keeping 0 shown
beside it.

**4. More data.** TCEQ's monthly hourly report pages are downloaded for every monitor site that measured benzene
(45201), 1,3-butadiene (43218) or total non-methane organics (43102), 2003 to 2021, the same public pages already
used for H2S (allowed by the site's robots file, which sets no crawl delay). The EPA AQS hourly files keep 8 such
sites after 2014, against 22 in 2006.

**5. Facts checked before writing the rules (no assumption left open).**
- Event report times are local clock time with daylight saving: of 151 events starting on spring-forward days, none
  started in the hour that does not exist (about 4 expected from other Sundays). Events in El Paso and Hudspeth
  counties are read as Mountain time, all others as Central time.
- TCEQ report pages are local standard time all year (stated on each page; checked against airport wind, best fit at
  UTC-6 in both winter and summer); El Paso pages state Mountain Standard Time.
- AQS and TCEQ wind direction is the direction the wind comes from: at six monitors within 8 km of an airport,
  hourly AQS direction agreed with the airport within a median of 9 to 14 degrees.
- AQS hourly rows are matched on their GMT date and time; airport data are in UTC.

**6. Common rules for V1 to V5.**
- **Events:** emissions events at plants with an RMP risk period, June 1, 2003 to December 31, 2021 (later only
  where a check's data start later), after the same-start merge, dropping reports flagged duplicate or filed in
  error by the frozen rules and reports caught by `NARROW_NON_EVENT`. Reports later found below the reportable amount
  are kept.
- **Episodes:** reports at the same RN whose event hours overlap are one episode, from the earliest start to the
  latest end.
- **Event hours:** start to end, converted to UTC by the time-zone rule above. Episodes with a missing end, or an end
  before the start, are left out of V1 and counted; episodes longer than 72 hours use their first 72 hours.
- **Location:** the median of the RN's known points (`tceq_rn_points_raw`).
- Every check reports its counts of what was left out and why, and its result in plain words with a 95% interval,
  whatever it shows.

**7. V1, air monitors.**
- Pairs: each episode with the nearest monitor within 10 km that measures a family the episode reported (SO2, NOx
  as NO2 or NOx, H2S, benzene, 1,3-butadiene, total non-methane organics for VOC) and has at least one valid hour in
  the episode. Values come from AQS where AQS has the site-hour, otherwise from the TCEQ page. Values below
  detection are used as reported.
- Wind: resultant wind direction and speed at the monitor site; if missing that hour, the nearest airport within
  50 km. Hours with wind under 1 m/s are not used.
- Downwind hour: the wind comes from within 30 degrees of the bearing from the monitor to the event site.
- Comparison hours: same monitor, same calendar month and local hour of day, also downwind by the same rule, in other
  years of 2003 to 2021, on days with no reported event of any type at any RN within 10 km of the monitor (from the
  day before to the day after). At least 10 comparison hours are needed.
- Measures, by family: (a) the ratio of mean concentration in downwind episode hours to mean in comparison hours,
  pooled as a ratio of sums over episodes, with a 95% interval from 2,000 bootstrap resamples of plants; (b) the share
  of episodes whose highest downwind hour exceeds the 95th percentile of its comparison hours.
- Placebo: the same calculation for the same clock hours one year earlier (or later if that falls outside the data
  or on an event day), so that (b) is read against the share expected with no event.

**8. V2, satellite heat.** VIIRS night detections (Suomi NPP 2012 to 2021; NOAA-20 2018 to 2021), any FIRMS type.
Unit: RN-night (local evening date). Event nights: nights overlapping an episode whose cause, actions or emission
point names mention a flare (`\bflar`). Comparison nights: same RN and calendar month, other years, no reported event
at that RN within 2 days. RNs with another event-reporting RN within 1 km are left out. Outcome: any detection
within 1 km. Model: conditional logistic regression with RN-by-calendar-month strata; detection rates shown beside
the odds ratio.

**9. V3, fenceline benzene.** Unit: refinery-quarter of the main sampler ring, 2018 to 2021 (2022 to 2025 shown
as description). Value: mean two-week Δc of periods ending in the quarter; quarters with fewer than 4 valid periods
are dropped. Exposure: number of episodes at the refinery's plant in the quarter (RN from
`data/manual/fenceline_crosswalk.csv`). Model: linear regression of log mean Δc on log(1 + episodes) with refinery and
quarter effects, refinery-clustered errors and a wild cluster bootstrap (26 clusters).

**10. V4, complaints.**
- (a) TCEQ air complaints by received date and county, 2003 to 2021. Unit: county-day. Exposure: an episode started
  in the county on that day or the 2 days before. Model: Poisson with county-by-year-by-month and day-of-week
  effects, county-clustered errors. The RN field is not used (investigators fill it in).
- (b) Houston 311 "Air Pollution" cases, 2011 to 2021, within 5 km of an event RN (cases at coordinates 0 dropped).
  Unit: RN-day for RNs with at least one case within 5 km over the period. Exposure: an episode started at the RN on
  that day or the 2 days before. Model: Poisson with RN-by-year-by-month and day-of-week effects, plant-clustered
  errors.

**11. V5, emissions inventory.** Unit: site-year, 2016 to 2021, for RNs in both sources. Inventory emissions-event
tons of the four severity families against the sum of their reported event pounds divided by 2,000, over that
RN's emissions events dated in the year (0.0001 read as zero). Measures: Spearman correlation, median ratio and share
within a factor of 2; counts of site-years with tons in only one source.

**D6 note, 2026-10-04 (where the benzene data are; no rule changed).**
- **Which page has it.** TCEQ's general monthly report pages carry total non-methane organics but not the hourly
  benzene and 1,3-butadiene from the AutoGC instruments. Those are on TCEQ's AutoGC Monthly Summary Report
  (`agc_monthly_summary.pl`, same site, allowed by its robots file), which lists 45 sites. That page is the D6
  item 4 source (`src/fetch_tceq_agc.py`).
- **Sources not used.** TCEQ's newer AQNet service holds AutoGC data only from October 2022. TCEQ's TAMIS system
  disallows robots.
- **Units.** AQS reports these compounds in parts per billion carbon and the TCEQ pages in parts per billion by
  volume. TCEQ values are multiplied by the carbon count (benzene 6, 1,3-butadiene 4). The conversion is checked on
  hours both sources report (`data/derived/vchecks/v1_unit_check.json`).
- **Wind.** AutoGC pages give wind speed without units, so wind always comes from the site's AQS or TCEQ monthly
  records.

### D7, 2026-10-04: fixes from a full review of the warning-sign checks (before any outcome analysis)

The author asked for a full review of the Phase 2 code against the D6 rules before Phase 4. Each finding below was
checked against the data before anything was changed. Where the code did not do what D6 says, the code was fixed and
every check was rerun. No rule of D6 was changed, and no accident data was read. The results before the review are in
commits `a0fef4d` and `cac4b94`.

**Fixed.**
1. **Contaminant names (D6 item 2 list completed).** The frozen name lists missed common spellings of the same
   chemical: "OXIDES OF NITROGEN (NOX)" (10,152 rows in all reports), "NOX (STARTUP/SHUTDOWN)", "BUTADIENE, 1-3"
   (1,376), "SULFER DIOXIDE" (363), "DIHYDROGEN SULFIDE", "HPV HYDROGEN SULFIDE", "CO (STARTUP/SHUTDOWN)". They are added.
   Left out because they are ambiguous: "NITROUS OXIDES" (NOx or N2O, 399 rows), "SULFUR OXIDE(S)" and "SOX" (a group,
   not SO2 alone, 62 rows). Episodes flagged for NOx went from 12,784 to 15,908, butadiene from 2,185 to 2,691, SO2
   from 12,390 to 12,512. The same lists define the D6 item 2 severity measure.
2. **NOx counted twice.** Where a report lists total NOx and also nitrogen dioxide or nitric oxide for the same
   emission point, the parts are left out of sums (762 event rows and 250 inventory rows in V5). This applies to the
   D6 item 2 severity measure as well.
3. **V1 comparison days.** The code blocked only the day an event started (and the day before and after). An event
   blocks every day it runs, from the day before it starts to the day after it ends. An end that is missing, before
   the start, or more than 365 days after it (19 events near monitors) blocks the start day only. Example found: an
   event 2.9 km from a monitor ran from March 17 to July 1, 2019; its days had entered the comparison hours.
4. **Event set rebuilt by committed code** (`python3 src/vchecks_common.py`). The earlier file was made by hand and
   lacked times for 4 reports in the repeated hour on fall-back nights.
5. **Flare flag.** D6 item 8 names cause, actions and emission point names; the code also searched the basis field
   (358 flags came only from it). Removed.
6. **V2.** The 72-hour cap of D6 item 6 is applied to event nights. Comparison nights are cleared of every reported
   event of any type at the RN (23,579 reports), as "no reported event" says, not only of D6 episodes.
7. **V4 (a).** The complaints file repeats a complaint once per NAICS code (89,901 air rows, 71,555 complaints; date
   and county never differ within a complaint). Each complaint now counts once. The dossier counts are corrected.
8. **V5.** The unit is every inventory year of the RNs found in both sources (1,812 site-years), as D6 item 11 says;
   the code had kept only years with a D6 event (1,102). 95% intervals from 2,000 bootstrap resamples of RNs added.
9. **V3.** The 2022 to 2025 description required by D6 item 9 is added.
10. **Dossier.** Houston 311 air cases are 432 to 547 a year in 2011 to 2014 (not about 2,300), and 2011 has 37 with
    coordinates; one verbatim complaint phrase was replaced by a description.

**Checked and found correct.** EPA units (knots, ppb, ppbC); TCEQ page times and units (on 816,000 shared wind hours,
100% within 10% of EPA at zero shift against 46% at one hour); AutoGC benzene and butadiene units (over a million
shared hours); three V1 episodes and one comparison set recomputed by hand; the V2 exact fit; V3, V4 (b) and V5
inputs; the 555 non-event drops (208 beyond all three frozen flags, matching the dossier's 209).

**Left as written (judgment calls for the author, none changes a conclusion).**
- V2 night: noon to noon local solar time. A night of 20:00 to 06:00 would drop 24% of event nights and raise the
  odds ratio (to about 7.8 before the other fixes). Clock time instead of solar time changes the start night of 7.7%
  of flaring episodes.
- V4: reference days include days when an episode that started more than 2 days earlier is still running. Dropping
  them, or counting them as exposed, gives (a) 1.17 either way and (b) between 1.21 and 1.26 (before the complaint
  fix).
- V3: the interval uses the normal value 1.96 with refinery-clustered errors; with t on 25 degrees of freedom it is
  slightly wider. 3 fenceline periods in 2019 may be resubmissions with shifted dates (negligible).

**Results before and after.**

| Check | Before | After |
| --- | --- | --- |
| V1 SO2, downwind vs normal | 1.73 (1.41 to 1.99), placebo 0.89 | 1.91 (1.55 to 2.22), placebo 0.85 |
| V1 NOx | 1.15 (1.09 to 1.22), placebo 1.10 | 1.17 (1.10 to 1.24), placebo 1.12 |
| V1 H2S | 1.03 (0.85 to 1.30), placebo 1.40 | 1.01 (0.81 to 1.32), placebo 1.27 |
| V1 benzene | 1.37 (1.21 to 1.56), placebo 1.86 | 1.35 (1.15 to 1.58), placebo 1.14 |
| V1 1,3-butadiene | 2.88 (1.89 to 7.62), placebo 0.90 | 2.99 (1.99 to 7.48), placebo 0.98 |
| V1 VOC | 1.22 (1.04 to 1.45), placebo 0.92 | 1.22 (1.02 to 1.49), placebo 0.90 |
| V2 odds ratio | 5.88 (3.32 to 9.95) | 6.63 (4.01 to 10.50) |
| V3 per doubling of events | -1.8% (p 0.66) | -1.8% (p 0.65) |
| V4 (a) complaints rate ratio | 1.17 (1.08 to 1.27) | 1.09 (1.03 to 1.15) |
| V4 (b) 311 rate ratio | 1.25 (1.13 to 1.39) | 1.25 (1.13 to 1.39) |
| V5 Spearman, four families | 0.87 (1,102 site-years) | 0.78 (0.74 to 0.82; 1,812 site-years) |

**D7 addendum, 2026-10-05: sensitivity checks for the judgment calls (approved by the author).** The primary rules
stay as written in D6. The alternatives below were added after the results were seen, so they are labelled as
sensitivity checks and never replace a primary result. Each is an option of the same script (the default reproduces
the primary result exactly).

| Check | Primary | Alternative | Result |
| --- | --- | --- | --- |
| V2 odds ratio | noon-to-noon night, solar time: 6.63 (4.01 to 10.50) | night 20:00 to 06:00, solar time | 10.64 (6.40 to 17.03) |
| | | noon-to-noon night, local clock time | 6.74 (4.08 to 10.65) |
| | | night 20:00 to 06:00, local clock time | 10.50 (6.38 to 16.98) |
| V4 (a) complaints rate ratio | 1.09 (1.03 to 1.15) | days with an older episode still running dropped | 1.06 (0.99 to 1.14) |
| | | those days counted as exposed | 1.06 (0.99 to 1.14) |
| V4 (b) 311 rate ratio | 1.25 (1.13 to 1.39) | days with an older episode still running dropped | 1.26 (1.13 to 1.41) |
| | | those days counted as exposed | 1.21 (1.10 to 1.33) |

Commands: `python3 src/v2_satellite.py --night evening` and `--clock clock`; `python3 src/v4_complaints.py --running
drop` and `--running exposed`. Reading: the satellite result holds or grows under every alternative. The Houston 311
result holds. The TCEQ complaint result is small and not robust: under both alternatives its interval includes no
change. The verbatim report phrases in the data dossier were also replaced by descriptions (the exact patterns are in
the code), following the rule that report and complaint text is never quoted.

### D8, 2026-10-05: Phase 4 preparation, before the main test is run (author's go given)

Everything in this entry was done before any real accident date entered the H1 model.

**1. Phase 4 runner.** `src/run_h1.py` runs section 5.1 as amended by D2 for the primary window end (2021) and the
original frozen end (2023): accidents (O1, extended links, merged doubles, linked plants, at-risk days only; others
counted and left out), exposure (days -97 to -8, same-start merge, frozen duplicate rule), the model in pyfixest and
in the independent NumPy program, the 10,000-draw shuffle test, and the picture (events by month from 24 months
before to 12 months after accidents, relative to each plant's average, beside random dates in the same plant-years).
Real accident days are used only with `--real`.

**2. Tests on fake accident dates (no real accident date used).**
- Exposure: 1,400 plant-days (400 random, 1,000 at the 25 busiest plants) recomputed from the raw event table by a
  separately written count: 0 mismatches for the plant count and the statewide count.
- The two programs agree to about 1e-11 on the effect and 0.004% on its standard error in every run.
- 30 fake data sets with a planted ratio of 1.5: median estimate 1.54 (spread 1.21 to 1.71). 100 fake data sets
  with no effect for each window end: median 0.996 (2021) and 1.010 (2023); 6% of each below p 0.05.
- Full runs with 1,000 shuffles: planted 1.5 gave 1.46 (1.25 to 1.71) and 1.43 (1.20 to 1.69), shuffle p 0.001,
  and the picture rose in the 4 months before the fake accidents; no effect gave 0.92 (p 0.33) and, for 2023, a
  chance false alarm of 1.22 (p 0.018), which the 100-draw check above shows is not a bias.
  (`data/manifests/h1_dryrun_*.json`)

**3. Duplicate-accident rule applied across facilities of one plant.** The D2 item 2 rule compared accidents at the
same RMP facility only. One plant (internal ID Q00630) holds two RMP registrations that list accidents on the same
dates at the same minute. The unchanged rule, applied to pairs at different facilities linked to the same plant,
found 2 candidates in the whole table: one merged (all compared fields agree) and one kept (release source differs).
R9 (merge everything within 3 days) shows the other reading. Accidents in the 2021 window: 546 to 545.

**4. Known limitation kept.** The Data Liberation Project notes that a plant may rarely list one accident twice in
one filing. One such likely pair (same facility, same time, same duration and source) is kept as two accidents by
the locked rule (a filing that lists two accidents is the plant's own statement); R9 covers it. The shuffle test
places at most one accident per plant-day; the accident table has 4 plant-days with two accidents (both windows).

**5. Inputs and code locked for the run (SHA-256).**

| File | SHA-256 |
| --- | --- |
| events_v2.csv.gz | fb7803d078c11f8138debe32abd8cb9131201e9226ac1893bc7201589600e45a |
| accidents_v2.csv | bc63014b50308985ef69fb2f5dff7f28c07db38de86f48e05ee7b9b95ef2899a |
| plant_risk_v2.csv | 3425cf32f2e6f45ecb2da7393600f283692f02bd5856776c4ee8c1447b08ac15 |
| plants_v2.csv | 68277497c26ecf9e2691e151f34a54014d916c80fb18c23d1e375ebb46aaa47d |
| plant_members_v2.csv | cbb0e0956a6d2092f44eafaea430ad4920386823a95d2f7293d1fd4a71616eb9 |
| h1_exclusion_sets.json | 306ae9c0bf25db09a543233ab891fb93a2e4f7049f0d3148965c344852b7f9de |
| accident_merges.json | 8dbe25fdc3585bb38547a09f5b0fa6fff58a5af94b1a82ee3e326909787a6abe |
| src/h1.py | 08ec6251762c72f72d36c0c60ce1fe9be9ad4c8d0e734c208c392cbb326140dd |
| src/h1_numpy.py | f5d12b122fa1fd9ae6d0612c2197c2cec6e067f86345f871a714f9e774edfb83 |
| src/permutation_h1.py | 3b65894edf91d4f77041902af4f7194308ce17c1de752303bf884ce5ec48d044 |
| src/run_h1.py | 04d0b7edfc42add55fe42e2a1e5a0f9e0b4ef079f384fa3cece55d19d3e0e6fe |

Software: Python 3.11, pyfixest 0.60.0, pandas 3.0.6, numpy 2.4.6, scipy 1.17.1. The commit that adds this entry is
the code the real run uses; the run itself is `python3 src/run_h1.py --real`.

### D9, 2026-10-05: Phase 5 implementation rules and diagnostics (after the Phase 4 primary result was seen)

Phase 5 runs the secondary, robustness and between-plant analyses already registered (sections 5.2 to 6.4, D2,
D4, D6). Where the plan names an analysis without fixing every detail, the rule below was written into the code
before that analysis was run; the primary result was known at the time, and secondary results were seen as each
finished. Items marked **diagnostic** were added after seeing results and are labelled as such wherever reported;
none replaces a registered result. No registered rule was changed.

**Engine.** One function (`src/phase5_h1.py`) runs every H1 variant; with default settings it reproduces the Phase 4
estimate exactly (difference below 1e-14). Where pyfixest's demeaning does not converge, the exact conditional
likelihood (the method of the independent program, generalized to any number of terms, with step-halving) is used and
the result says so.

**Data window.** A day enters an H1 variant only if its whole exposure window lies inside the TCEQ event data (from
February 1, 2003). This changes nothing for the 90-day primary window; it removes early 2003 days for longer windows.

**Secondary family (5.2, D4 item 2), Holm over 15 tests:** O2, O3, O4; windows 30, 180, 365; the lag profile as four
bins in one model (days 8 to 91, 92 to 183, 184 to 365, 366 to 730 before the day, each with its own statewide count;
the 7-day gap applies to the first bin); dose (the 90-day count above the plant's own 75th percentile over its at-risk
days); pounds (four families of D6 item 2, NOx parts dropped where a total exists for the same emission point (D7),
rows repeated exactly within one occurrence counted once; 0.0001 read as zero); recurrence (an occurrence whose report
names an emission point (upper case, letters and digits only) used by another report at the same RN that started in
the 30 days before); real time (report date); H1-M (process control = equipment, instrument, upset, operator; outside
or planned = weather, third party, power, maintenance or startup; unknown; an occurrence takes the cause of its kept
report). VOC severity: D6 item 2 asks for the larger of total-VOC rows and the sum of single hydrocarbon rows, but no
name list of single hydrocarbons was ever frozen, so VOC is reported on total-VOC rows only, outside the family.

**Plant attributes** (`src/plant_attributes.py`): county = most common county on the plant's TCEQ reports, else its
RMP county; TCEQ region from TCEQ's own complaint records (every row has county and region; 254 counties, 16
regions, no conflicts); sector from RMP process NAICS codes (5-digit codes get their dropped trailing zero back: EPA
stores 324110 as 32411), the sector with most processes, ties to refining, chemicals, gas processing; location =
median TCEQ site point, else RMP filing location.

**Robustness rules.**
- R5: NOAA Storm Events types Hurricane (Typhoon), Tropical Storm, Winter Storm, Ice Storm, Extreme Cold/Wind Chill;
  all are recorded by forecast zone, mapped to counties by name, by name with Coastal/Inland/Northern... and
  County/Island(s) removed, then by the official NWS zone-county file (weather.gov bp18mr25.dbx, downloaded and
  recorded), and five retired West Texas zones by their NWS successors; 3,022 of 3,022 records mapped. A day is
  dropped when its window (days -97 to -8) overlaps an event in the plant's county.
- R18: the seven changed accident dates are found in EPA's change history; five are older records whose current
  record (same facility, corrected date) is used (`data/manifests/r18_original_dates.csv`); two are from 2002.
- R19: no merges, each record with its own filed date.
- R22: FEMA major disasters and emergencies (not fire management grants) of types hurricane, severe storm, flood,
  severe ice storm, winter storm, fire, freezing, plus titles naming a tropical storm and tornado declarations naming
  storms; statewide declarations count for every county; window or day within the incident period or 7 days after.
- R23: HURDAT2 (September 2026 revision) points with status HU or TS, filled hourly between consecutive HU/TS fixes;
  a day is dropped within 7 days either side of a point within 150 km of the plant.
- R25: freeze day = minimum below 28 F (-22.2 tenths of degrees C, units confirmed in NOAA's readme and on the
  February 2021 freeze) at the nearest GHCN station with a minimum that day; lightning day = any NLDN count in the
  plant's 0.1 degree cell; highest wind = largest gust (sustained wind where no gust) at the nearest airport with an
  observation that day, in m/s; all over days -97 to -8.
- R26: EIA Texas Gulf Coast refining district utilization (monthly) and Federal Reserve G.17 series G325 (chemical)
  and G32411 (petroleum refineries), seasonally adjusted, averaged over the window.
- R8b: expected completeness recomputed from filing lags of 2005 to 2018 accidents (first filing that lists each
  accident; 54.5% filed within 1 year, 79.5% within 3, 96.1% within 5), data date December 30, 2025: 2020 97.7%,
  2021 91.5%, 2022 83.9%, 2023 73.9%, 2024 61.0%, 2025 39.4% (D2 gave 98, 92, 84, 72, 58, 34).
- R27: indicator of an accident at the plant in the 365 days before the day (any date, including before the window).
  Its own coefficient is not interpretable as an effect (see the post-accident mechanism below).
- R28: the rule as written (parent or operator name differs between consecutive filings after upper case, punctuation
  and legal-form words are removed); it flags 2,114 changes at 1,079 plants, so it also catches spelling changes.
- R11 negative binomial: NB2 with a separate intercept for each plant-year (kept as a diagonal block, not dummy
  columns), month effects and the statewide count, dispersion by grid maximum likelihood (1.59), plant-clustered
  sandwich errors. Two earlier attempts with dummy columns did not finish (one ran out of memory). Check: with the
  dispersion near 0 the fit reproduces the Poisson estimate to 10 decimal places.
- R12: every at-risk year of plants with an accident, plant, year and month-of-year effects.
- R29: not run (the TCEQ coordinates requested under the Public Information Act have not arrived).

**N1:** each real accident at plant q becomes an outcome at every other linked plant with the same county and sector.
**Concordance:** an accident counts as also in TCEQ when the same plant has a report of any type starting within 2
days. **5.6 region groups:** TCEQ regions 12 (Houston), 10 (Beaumont), 14 (Corpus Christi), all others.

**H2, H3, usefulness** (`src/phase5_h2h3.py`): offset log(share of the year at risk); RMP covariates from each
facility's latest filing by the end of the year (earliest filing before the first one); EPA NEI (EIS) pounds of CO,
NOx, SO2, VOC and primary PM10 from the nearest NEI year, log(1 + tons), with an indicator for no NEI record;
ICIS-Air inspections (full and partial compliance evaluations by end date), violations (violation history by
earliest determination date) and enforcement (formal actions by settlement date), state and EPA records, prior
calendar year, log(1 + count); H3 without year effects (a model fit on past years cannot carry them forward),
tested on 2016 to 2021 and 2016 to 2023.

**Independent outcomes.** H4: NRC incident type FIXED, serious = fire, injury, fatality or evacuation flag; candidate
TCEQ sites by 6.4 (same county, shared name word, street number shown). O6: OSHA fatality and catastrophe records
(with their inspection's establishment and address) and severe injury reports; candidates by address key, by 1 km
plus shared name word, or by ZIP plus shared name word. O7 and the completeness check: CSB Texas investigations
(June 2003 to 2023), RMP accidents in the same city within 7 days or sharing a name word within 30 days. All links
need the author's hand review (`tools/outcome_link_review.html`) before H4 and O6 are run.

**Diagnostics (added after results were seen).**
1. Long windows on fake accident dates (no effect planted; fake accidents cause no events): 90, 180, 365 days give
   0.98, 0.99, 0.97, so the code is not biased.
2. Dropping (window + gap) days after each accident: primary 90 days 1.13 (p 0.36), O4 0.83 (p 0.43), 180 days 1.08
   (p 0.64), dose 1.16 (p 0.32). For the 365-day window and the lag profile this check cannot be used: every accident
   becomes the last remaining day of its plant-year, so the fit only compares the end of the period with its start.
3. A cross-year version of check 2 was stopped before it produced results: its fake-data check placed fake accidents
   in the real accident years and so could not separate design bias from the real year-level pattern.
4. Time scale of R12: strata by plant (1.32), plant by 5-year block (1.13), 3-year (1.09), 2-year (1.00), plant-year
   (0.88).

**Multiverse** (`src/phase5_multiverse.py`, D2 item 9): 1,152 fits, all converged with pyfixest. "Not merged" with
registry-only links uses the registry-only accident table, which has no merges, so those 96 pairs are identical.
Figure and summary table: `src/make_multiverse_figure.py`.

**Exploratory finding after the multiverse: planned work before accidents** (`src/phase5_diag_lastweek.py`,
`src/phase5_diag_planned.py`; found after seeing results, not pre-registered, reported as exploratory). The only
multiverse corner with significant positive estimates (30-day window, gap 0 or 1, all event types, registry-only
links) was traced to TCEQ planned reports (maintenance, startup, shutdown) starting in the 7 days before. Rules used:
planned and unplanned (emission event plus excess opacity) counts in days -7 to -1 as separate terms, each with its own
statewide count; same filters, merge and exclusion set as the primary count; report start, end and initial
notification times parsed from the report fields (format MM/DD/YYYY HH:MM AM); "notified in advance" means the initial
notification came before the start; "finished" means the end date is before the day. Checks: by type, by days,
gap 1, notified in advance, finished or ongoing, the three storm rules (R5, R22, R23, and all three), 200 fake-date
redraws within plant-year, leave one plant out, and accident chains (R15 and R16 rules with 120 days).

Added afterwards (`src/phase5_diag_planned_rmp.py`): RMP contributing factors and initiating event of the 32
accidents with planned work in the week before against the other 513 accidents of the primary set, Fisher exact
tests, descriptive only; free-text fields searched for startup and shutdown words, counts only.

**Errors found and fixed during Phase 5, before the affected results were used:** cause-group and unit-type counts
first counted reports instead of occurrences (fixed; the family was rerun; the cause contrast moved from 1.09 to
1.10); RMP 5-digit NAICS codes first left every refinery out of the refining sector (fixed before any sector
result); a one-day edge in the R26 window averages (fixed before R26 ran).

### D10, 2026-10-05: pre-written test of the exploratory planned-work finding

The planned-work finding of D9 is a lead found after seeing results. `docs/planned_work_test.md` fixes, before any
fresh data is analysed, the exposure, model, decision rule, power check and three tests (later RMP accidents, another
state, National Response Center reports). Data note (corrected the same day after the data review below): one AIR STARTUP report has no readable
start; its end field reads 12/31/3000, so it is dated 3000-12-31 from the end (report dated 2004). It falls in no
window and changed no result; it is left out and counted in the fresh tests.

### D10 addendum, 2026-10-05: review of the data pipeline

The pipeline was rebuilt from the raw files with separately written code: event parsing, the same-start
merge, exclusion sets, RMP Texas filter and accident dedup, the O1 to O4 flags, plant tables, at-risk periods and the
H1 panel all match exactly (153,138 plant-days). No route for accident information into the exposure was found.
Problems found (the locked primary result is not changed; impacts are shown):

- **Lost occurrences (confirmed):** in 32 same-start groups the report the
  merge kept is in the frozen filed-in-error exclusion set, so the occurrence disappeared although other valid reports
  of it exist (17 emission events, 8 at panel plants).
- **Start-year typos (confirmed):** 35 reports start 300 or more days after their own report date (24 emission
  events, 9 at panel plants).
- **Possible early-January year typos (suspected):** about 170 events filed 360 to 380 days after their start,
  mostly January to March starts.
- **Two likely double accidents kept by the written rule (suspected)**, one probably missed link (at most 1 accident),
  and 7 facilities whose risk period ends at a deregistration although they filed later (none in the H1 panel).

Primary H1 with the two confirmed fixes: 0.877 (p 0.094); with every confirmed and suspected fix: 0.884
(0.761 to 1.026, p 0.106); against 0.879 (0.754 to 1.024, p 0.097).

### D10 addendum 2, 2026-10-05: review of the models and code

The H1 fit was rebuilt with separately written code and reproduced the reported numbers exactly (0.8789, 0.6839, 0.4747,
planned work 1.663, R21). Confirmed and acted on:

- **The accident's own reports drive the results below 1.** Removing each plant's events on the accident day and
  the 2 days after (269 of 68,610 events), with every day kept, gives 1.05 (0.85 to 1.29) for the main test, 0.92
  and 0.97 for 180 and 365 days, O4 0.74 (0.51 to 1.07), lag bins 1.12, 0.97, 0.99, 0.96
  (`src/phase5_diag_own_reports.py`). The same removal around fake accident
  dates (60 draws) gives medians 1.03 (90 days) and 1.01 (365 days). The Phase 4 sentence "a rise larger than about
  2% per doubling is ruled out" is withdrawn and replaced by "more than about 30%" (correction note added to
  `docs/phase4_results.md`; the locked numbers are unchanged). An earlier attempt (`src/phase5_diag_clean.py`)
  removed days 1 to K but kept the accident day; its estimates rose with K (to 1.29 at K = 90), a removal bias, and
  it was stopped and is not used.
- **Dose term on the wrong scale:** the top-quarter term is yes/no, so its rate ratio is exp(beta): 0.73 (0.57 to
  0.94), not 0.80; 1.24 after the post-accident drop, not 1.16. P-values and Holm are unchanged. Fixed in
  `src/phase5_family.py` and in the stored results (fields `rr_yes_vs_no`).
- **Planned-work p-value too optimistic:** a within-plant-year shuffle of planned-work dates, accidents fixed
  (`src/phase5_diag_planned_perm.py`, 500 draws), gives p 0.018 two-sided (0.004 one-sided); a second, separately written shuffle gave 0.017. Planned-work reports fell from about 2,000 a year to under 150 a year, so fresh test T1 was
  made subject to a power rule before any test was run (`docs/planned_work_test.md`).
- **H2 aftermath check had no placebo:** removing a month of events at a random time already lowers H2b to about
  1.12; the real rule's 1.09 is below every placebo draw. Wording changed from "a good part" to "part".
- **R27 is not separate support** for the aftermath explanation (its marker almost separates accident days from
  comparison days); wording changed.
- **H3:** 18% of test plant-quarters used a covariate from a filing received after the quarter began; refitting with
  strictly earlier covariates gives AUC 0.7996 and 0.8098 (reported 0.7975 and 0.8080). The usefulness table's
  top-10% row is partly in-sample; labelled.
- Not changed, recorded: pyfixest's convergence flag is not read by the code (it is True for the primary fit);
  `cond_poisson` can declare convergence when its step search stalls (never used for a reported number); the
  negative binomial fit has no iteration-limit check (its alpha-near-0 check passes).

### D11, 2026-10-06: rules for H4 (NRC) and O6 (OSHA), written after the author's link review and before either is run

The author's review (`data/manual/outcome_link_decisions.json`, exported 2026-10-06) answered all 604 NRC reports
with candidates (262 linked, 12 none, 330 can't tell), all 959 OSHA records with candidates (320 linked, 19 none,
620 can't tell) and all 9 CSB events with candidates (9 linked). Only reports the author linked are used; "can't
tell" counts as not linked, as the review page stated.

**H4 (plan 5.5).** Unit: every TCEQ site (RN) with at least one kept unplanned emission event, linked to RMP or not.
Outcome: a day with at least one linked serious NRC report at that RN (several reports on one RN-day count once;
NRC often has several callers for one incident). Exposure, statewide count, window (90 days, gap 7), month-of-year
effects, merge and exclusion rules as in H1, counted by RN; strata: RN-years with at least one outcome day; days:
every calendar day of that year inside the study window whose whole look-back window lies in the event data;
errors clustered by RN. Window ending 2021 (as H1) is the H4 result; ending 2023 is shown beside it. Also shown:
the version with the RN's events on outcome days and the 2 days after removed from the exposure (D10 addendum 2).

**O6 (D2 item 7).** Linked OSHA records (severe injury reports and fatality or catastrophe investigations) at RMP-
linked plants, as the outcome of the H1 model (plants, at-risk days, exposure, strata as in H1). Several records
on one plant-day count once. Years covered: severe injury reports start in 2015, so only outcomes from 2015-01-01 on
are used (strata from 2015); window ending 2021, and 2023 beside it. Also shown with the own-report removal.

**Fresh test T3 of the planned-work lead** (`docs/planned_work_test.md`): run on the H4 panel (RN units) with the
exposure and model fixed there. "No RMP accident at the same plant within 3 days" uses the RN's plant link where it
has one (RNs without a plant link have no RMP accidents by construction). Power check first, as fixed there.

**D11 addition, 2026-10-06, before T3 is run (H4 and O6 results above are already seen; T3 is not):** T3 uses the H4
panel with all linked NRC years (June 2003 to 2023), since the planned-work exposure has never been analysed
against NRC outcomes. Power check: 200 fake-outcome draws on that panel with a planted 1.5 per doubling (outcome
days drawn within each RN-year with probability proportional to (1 + planned count) to the power log2(1.5));
power = share of draws whose 95% range lies above 1.

**D11 results, 2026-10-06:** H4 0.82 (0.66 to 1.01) to 2021, 0.79 (0.65 to 0.96) to 2023; with own reports removed
1.08 (0.88 to 1.33) and 1.04. O6 1.10 (0.79 to 1.54) and 1.08; with own reports removed 1.13 and 1.12. T3: power
30% (underpowered), 1.37 (0.65 to 2.89), inconclusive; all linked reports 1.24 (0.62 to 2.49). Completeness
(descriptive, `src/completeness_check.py`): of serious NRC report days at RMP-linked plants, 35 of 212 have an RMP
accident within 3 days (14 of 74 where a chemical on the RMP list is named; matched by CAS number without leading
zeros or by exact name); OSHA fatality or catastrophe 5 of 63; severe injury 9 of 255.

### D12, 2026-10-06: the news-article completeness check (D2 item 7), written before the sample is drawn

The author chose a random sample instead of checking all 85,457 Texas candidate links. Frame: the Texas candidates
(`data/derived/gdelt_texas_candidates.csv.gz`) with duplicate links removed, article dates June 2003 to 2023. Sample:
500 links drawn at random with numpy seed 20261006. The author answers, per link, blind to RMP accident data:
(1) is it about a fire, explosion, chemical release or injury at a fixed industrial site in Texas (plant,
refinery, terminal, storage; not pipelines, wells, vehicles, trains or homes): yes, no, can't tell; (2) if yes,
which site: one of the suggested Texas RMP facilities (suggested when a non-generic word of the facility's name, or
its city, appears in the link), "a site not in the list" (name and city typed), or "can't tell which"; (3) the
incident date if the article gives one that differs from the article date.
Analysis (descriptive): distinct incidents = same facility and incident dates within 7 days. For each incident at
an RMP-registered facility: is there an RMP accident at that facility within 7 days of the incident date, and how
many days apart. Typed sites are matched to RMP facilities by the linking rules (exact address or shared name word
in the same city); unclear ones are shown back to the author. Caveats stated with the result: articles, not
incidents, are sampled, so heavily covered incidents are more likely to be drawn; not every news-reported incident
meets RMP's reporting criteria.

**D12 note, 2026-10-06:** the sample was drawn as written (frame 69,887 distinct links dated June 2003 to 2023; 500
drawn; list in `data/manifests/news_sample_links.csv`); review page `tools/news_review.html`. R29: the TCEQ Central
Registry coordinates were requested under the Public Information Act on 2026-10-05 (response due by 2026-10-19);
R29 stays pending until they arrive.

**D12 progress, 2026-10-06:** the author answered all 500 links (164 yes, 316 no, 20 can't tell). The strict typed-
site rule matched 88 answers to one RMP facility, left 44 unmatched and 5 with several matches. Some unmatched sites
are plainly RMP facilities whose name words are common (for example a typed name the author picked from the list on
other links), so, as D12 provides, every unmatched or multiply matched typed site (22 sites) goes back to the author
with looser suggestions (`src/make_news_settle_page.py`, `tools/news_settle.html`). Completeness numbers wait for
those answers.

**D12 result and a correction, 2026-10-06.** With the author's settling answers
(`data/manual/news_settle_answers.json`), the 164 "yes" links form 39 distinct incidents from June 2003 on (one
link was about a 1947 event and is out of scope); 25 are at RMP-registered facilities, and 9 of those have an RMP
accident at that facility on the same day (none within 1 to 7 days). Correction to the source notes in D1: the
PHMSA website refuses downloads from the cloud server used here (HTTP 403), and the Internet Archive closes its
connections; both work from an ordinary connection. NFIRS and BLS pages loaded on 2026-10-06. The wording in
`docs/data_sources.md` was corrected accordingly.

**Note, 2026-10-06 (record check of the data notes):** two small inaccuracies in frozen or earlier records, kept as
they are and noted here. (1) `data/frozen/link_table_freeze.json` counts 1,221 RMP IDs in linked plants; one of
them (100000260166, joined through the registry) is not among the 2,408 Texas RMP facilities, so 1,220 Texas
facilities are in linked plants and 1,188 are outside. No analysis uses this count. (2) The D1 table and the D2 V3
description give the refinery fenceline data as "2019 on"; the sampling periods start in 2018 (reports filed from
2019), and D6 item 9 already uses 2018 to 2021.

**Note, 2026-10-06 (stored checks):** some numbers in D8 and D9 were first reported from console output and are
now recomputed and stored in `data/manifests/stored_checks.json` and `data/manifests/h1_third_fit.json`
(`src/stored_checks.py`, `src/h1_third_fit.py`). The exposure recount (1,400 plant-days, 0 differences) and the
statsmodels refit reproduce exactly. The fake-date medians for 90, 180 and 365 days, given in D9 as 0.98, 0.99 and
0.97, are 0.99, 0.99 and 0.96 in the stored rerun (30 draws, a different random seed); the conclusion is unchanged.

### D13, 2026-10-12: downloads from the author's computer, and T2 in Louisiana not run

Some sources refuse connections from the cloud server used for processing, so they were downloaded on the author's
own computer.

- **Check:** 130 files were downloaded. The 68 kept with the project match their size and SHA-256 hash. The other 62
  (EPA's Louisiana facility registry file and 61 batches of LDEQ documents) stay on the author's computer because they
  hold people's names and phone numbers; all 130 matched their hashes on 2026-10-11.
- **Obtained:** PHMSA pipeline incident files (15 zips); the earliest web archive capture of each of the 500 news
  sample links (no page content); LDEQ's document index for seven categories (78,650 rows), the quarterly lists of
  air permits issued (2017 to 2026) and the ERIC annual emissions files.
- **How:** PHMSA files were saved through a web browser after scripts were refused. LDEQ's document system disallows
  automated access in its robots.txt; its document index (a list of documents, not the documents) was saved with 23
  requests to the site's own export function, and the documents themselves were downloaded by hand from a page of
  links, solving each human check (reCAPTCHA). The scanned LDEQ documents were transcribed with an AI model (two
  independent reads, and a third read where they disagreed). The author also transcribed sets A and B by hand from
  the PDFs, and the two matched; the 100-document set C test was not checked by hand. This transcription is an
  exception to the rule that no source is coded with machine learning; the transcribed values are used only in the T2
  power check below and in no result. Only the dates that check uses are in this repository (`data/louisiana/`).
- **Blindness:** no accident data or result files were opened for this work, apart from the opening of
  `docs/planned_work_test.md`, which states the Texas estimate; that is the hypothesis being tested, not a Louisiana
  outcome.
- **T2 in Louisiana:** Louisiana publishes no general planned-work reports; dated starts exist only in notices under
  LAC 33:III.319 and 309 and in a few variances. At RMP-linked sites they give 21 dated starts at 16 sites in 2009 to
  2025. The power check (`src/t2_louisiana_power.py`, `data/manifests/t2_louisiana_power.json`), using simulated
  accidents at Texas rates and no Louisiana accident data, gives 7% (typical rate) and 10% (one accident per site and
  year). Under the rule in `docs/planned_work_test.md`, T2 is not run in Louisiana. No Louisiana outcome was looked at.

### D14, 2026-10-12: strengthening analyses, rules written before they are run

Added after all registered results were seen; items 2 and 3 are exploratory and are reported as such, whatever
they show. Window 90 days, gap 7, end 2021, plant-year strata with month of year, plant-clustered errors, as in H1,
unless stated.

1. **Equivalence statement.** For the registered primary result, the version with the accident's own reports
   removed (D10 addendum 2) and H4, report the upper end of the 90% interval: rises larger than it are rejected at
   the 5% level (one-sided, the two one-sided tests procedure). No equivalence margin is chosen after the fact; the
   bound is reported as it is.
2. **Simulation of the design trap** (`src/sim_design_trap.py`). Real event counts and plant-years; accidents placed
   on random at-risk days of the same plant-years (20 draws). Each simulated accident adds reports at its plant:
   Poisson with mean 0.37 on the accident day and 0.03 on each of the 2 days after (the observed excess:
   `data/manifests/stored_checks.json`). Scenarios: (a) no effect; (b) a planted 1.3 per doubling (accident days
   drawn with probability proportional to (1 + events in the window) to the power log2(1.3)). Fitted naively
   (90 and 365-day windows) and with the removal of D10 addendum 2. Expected: the naive fit falls below the truth,
   more so for the longer window, and the removal brings it back. Descriptive.
3. **Exploratory test A, events involving the plant's own RMP chemicals** (`src/phase5_same_chemical.py`). Exposure:
   kept unplanned emission-event occurrences that list at least one contaminant matching a chemical in any of the
   plant's RMP process chemicals (including components of its flammable mixtures). Matching: contaminant
   description and RMP chemical name (the name before any bracket, and the bracketed synonym) reduced to lower-case
   letters and digits, equal strings, or equal CAS numbers where both have one; the match rate is reported. Shown as
   registered and with the accident's own reports removed.
4. **Exploratory test B, satellite heat** (`src/phase5_satellite_heat.py`). Exposure: the number of nights in the
   window with at least one NASA FIRMS VIIRS (Suomi NPP) night detection within 1 km of any of the plant's
   event-reporting RNs (TCEQ coordinates as in V2); statewide count: the same for all other plants. Accidents from
   2012-04-08 (first day with a full window) to 2021-12-31. Shown as registered and with detections on the accident
   day and the 2 days after removed.
5. **Plain-number translation** of the bound in item 1 against the observed accident rate (33 per 1,000
   plant-years), descriptive.

**D14 change, 2026-10-12, before item 3 was run:** TCEQ contaminant descriptions put synonyms in parentheses
("Propylene (Propene)", "Ethylene (gaseous)") and suffixes such as ", N-", and they carry no CAS numbers. So, on both
sides, each name yields several candidates: the whole name, the part before any bracket or parenthesis, and each
bracketed or parenthesized part, after removing a trailing ", N-" or "N-" prefix; all reduced to lower-case letters
and digits. A contaminant matches when any of its candidates equals any candidate of the RMP chemical. The CAS rule
is dropped (no CAS on the TCEQ side). RMP entries reported as confidential ("CBI") are left out.

**D14 results, 2026-10-12.** Item 1: rises larger than 22% to 29% per doubling are rejected (one-sided 5%) in the
versions with the accident's own reports removed and in H4; the registered primary's bound (0.999) is biased by the
trap. Item 2: with no effect, naive 0.82 (90 days) and 0.55 (365 days), fixed 1.03 and 1.08; with a planted 1.3,
naive 1.00 and 0.61, fixed 1.28 and 1.21 (medians of 20 draws). Item 3: 26% of occurrences matched; 0.91 (0.77 to
1.07) as registered, 1.06 (0.84 to 1.34) with own reports removed. Item 4: 1.09 (0.90 to 1.32), 1.13 (0.93 to 1.38)
with own detections removed; 238 accidents, 132 plants. Item 5: at most about 42 accidents per 1,000 plant-years
against 33 if a plant's recent events doubled.

**Note, 2026-10-12: R29 not run.** The TCEQ Central Registry coordinates were requested under the Texas Public
Information Act (2026-10-05); the author withdrew the request after TCEQ's response. The check was not expected to
change any result: of the 589 accidents in the primary window, 44 are at plants without a TCEQ link, mostly water,
food and cold-storage sites that file no emission events, and at most about 10 could plausibly gain one.

**Note, 2026-10-12: cause-rule agreement (section 4), reported late.** The author's hand coding of the 400-event
validation sample (drawn at random from the 71,027 unplanned events on 2026-10-02, separate from the 1,000-event
development sample, and coded without seeing the rules' output) was compared with the frozen rules
(`src/cause_agreement.py`, `data/manifests/cause_agreement.json`). Primary cause, 9 categories: 72% agreement, Cohen's
kappa 0.67. The three groups used in the process-control contrast: 83%, kappa 0.70. By category, kappa runs from 0.57
(equipment) to 0.86 (weather and power), except operator or procedure, which the rules almost never assign (1 event
against 15 by hand; kappa 0.12). This comparison was registered but had not been computed; no result changes.

### D15, 2026-10-12: the time-scale check with the accident's own reports removed (rule written before it is run)

The time-scale check of D9 (R12, then strata by plant and 5-, 3- and 2-year blocks, then plant-year;
`data/manifests/phase5_diag_era.json`) was run before the design trap was found, so every version keeps each
accident's own reports in the counts. Narrower strata put a larger share of post-accident days among the
comparisons, so part of the fall from 1.32 to 0.88 could be the trap rather than the time scale. The same five
versions are rerun with each plant's reports from the accident day and the 2 days after removed, every day kept, as
in D10 addendum 2 (`src/phase5_diag_era_own_removed.py`, output `data/manifests/phase5_diag_era_own_removed.json`).
Window 90 days, gap 7, end 2021, statewide count unchanged. Exploratory and descriptive; reported whatever it shows.
How it is read, stated now: if the whole-history version stays clearly above the plant-year version, the
long-run association stands as described; if the versions converge, the fall was mostly the trap and the
time-scale reading is withdrawn.

**D15 result, 2026-10-12.** With the accident's own reports removed (269 events), the five versions give: whole
history 1.24 (1.07 to 1.44, p 0.004), same 5-year block 1.11 (0.93 to 1.33), 3-year 1.10 (0.91 to 1.32), 2-year
1.07 (0.87 to 1.31), same year 1.05 (0.85 to 1.29). As registered they were 1.32, 1.13, 1.09, 1.00 and 0.88. Read
by the rule above: the whole-history version stays above the plant-year version and is the only one clearly above
1, so a long-run association remains, but it is smaller than reported in D9, and most of the fall from 1.32 to 0.88
was the trap. The description is revised accordingly: a modest association across a plant's whole history, none
detectable within a few years.

### D16, 2026-10-12: gaps found while checking the paper draft (rules written before anything is run)

Checking the first paper draft against the plan and the results files found the following. Each item states what
is done; all are run after every main result was seen.

1. **Two registered secondary exposures were never run.** Section 3.4 lists "duration of events" and "maintenance,
   startup and shutdown reports separately"; neither has a result. Both are now run in the H1 design (window 90,
   gap 7, end 2021, plant-year strata, month of year, plant-clustered errors), as registered and with the plant's own
   reports from the accident day and the 2 days after removed (`src/phase5_registered_extra.py`). Outside the Holm
   family, which was fixed in D9.
   - *Duration:* for each kept unplanned occurrence (same filters and merge as the primary count), hours from the
     report's start to its end time (`details_table` start and end fields). Unreadable or negative durations are
     left out of the sum and counted; durations are capped at 720 hours (30 days) against typing errors. Exposure:
     log(1 + total hours of occurrences starting in days 97 to 8 before). Statewide control: the primary statewide
     event count.
   - *Planned work, 90 days:* kept maintenance, startup and shutdown reports (same filters as in D9's planned-work
     diagnostic), counted by start day; exposure log(1 + count in days 97 to 8 before); statewide control: the same
     count at all other plants.
2. **The design-trap simulation (D14 item 2) used 0.03 extra reports on each of the 2 days after a simulated
   accident**, described as the observed excess. The observed excess is 0.006 per day: 26 reports on days 1 and 2
   after the 541 accident days against 19.4 expected (`stored_checks.json`). The day-0 excess, 0.37, was right. The
   simulation is rerun with excesses computed in the code from `stored_checks.json` (day 0: (212 - 9.7) / 541; days 1
   and 2: (238 - 212 - 2 x 9.7) / (2 x 541)), same seeds and draws; the earlier figures are replaced and recorded
   here: no effect, naive 0.82 and 0.55, fixed 1.03 and 1.08; planted 1.3, naive 1.00 and 0.61, fixed 1.28 and 1.21.
3. **The removal was calibrated on fake dates only for 2 days after (K = 2).** The same calibration (60 redraws of
   each accident to a random at-risk day of its plant-year, 90-day window) is run for K = 0 and K = 7
   (`src/phase5_removal_calibration.py`).
4. **Four planned-work checks quoted in the results existed only in separate scratch code** (the yes-or-no
   exposure, the two plants with the most cases left out, each calendar year left out, and 2003 to 2005, 2006 to 2010
   and 2011 to 2021 separately). They are rebuilt in `src/phase5_diag_planned_extra.py` on the base model of
   `src/phase5_diag_planned.py` (planned and unplanned last-week counts, each with its own statewide control).
5. **The National Response Center replication is described as covering different sites.** Most of its sites are in
   RMP-linked plants. The overlap is counted (`src/h4_overlap.py`): sites and report days in RMP-linked plants, and
   report days within 3 days of an RMP accident. The `sites_linked_to_rmp_plants` field in `phase5_h4_o6.json` tests
   only that a site has a plant, not that the plant is RMP-linked; it is superseded by this count.

**D16 results, 2026-10-12.** Item 1: duration 0.97 (0.91 to 1.03) as registered, 1.03 (0.96 to 1.10) with own reports
removed; planned work over 90 days 0.90 (0.74 to 1.10) and 0.92 (0.75 to 1.13). Item 2: with the observed excess, no
effect gives naive 0.84 (90 days) and 0.56 (365 days), fixed 1.03 and 1.08; a planted 1.3 gives naive 1.02 and 0.63,
fixed 1.28 and 1.21 (medians of 20 draws); the reading is unchanged. Item 3: on fake dates the removal alone gives
medians of 1.02 (K = 0), 1.03 (K = 2) and 1.06 (K = 7) for the 90-day window, against 1.03, 1.05 and 1.08 on the real
dates, so the rise with K is mostly the removal itself. Item 4: yes or no 1.61 (1.08 to 2.39); two plants left out 1.71;
each year left out 1.57 to 1.77; eras 2.10, 1.33, 1.74. Item 5: 91 of the 105 NRC sites and 193 of the 218 report days
are in RMP-linked plants; 33 report days fall within 3 days of an RMP accident.

**D16 note, 2026-10-13: every result rebuilt from the public tables.** Before the repository was made public, every
script was rerun in order on a copy that held only the files in the repository (`src/run_all.py`), and each result
was compared with the stored one. Almost all agree exactly, and the rest to about the tenth significant figure. Five
stored files had not come from the final code; they are replaced by what the code gives, and no number quoted in the
paper or the results reports changes.
1. `phase5_diag_post_accident.json` had been written by an earlier draft of the code that left a model empty when it
   did not converge. With the final code (the exact conditional likelihood when pyfixest's demeaning fails), the
   lag-profile item now has estimates (none with p below 0.05, none quoted), and the 365-day item still does not
   converge. The yes-or-no dose ratio is now computed from the unrounded coefficient (1.2364; it had been worked out
   from the rounded rate ratio as 1.2365).
2. `phase5_diag_clean.json` held partial results saved while the job was still running. The complete run adds its
   fake-date check (medians of 1.15 for the 90-day window and 1.26 for the 365-day window, 50 draws), which shows
   the rise of that first removal method on dates with no real accident.
3. `paper_precision.json` had been computed before the D16 simulation rerun. It now matches `sim_design_trap.json`
   (naive 0.84 and 0.56, fixed 1.03 and 1.08; with a planted 1.3, naive 1.02 and 0.63, fixed 1.28 and 1.21).
4. Notes that had been added by hand to `phase5_family.json` and `phase5_diag_post_accident.json` are now written by
   the scripts, and the planned-work chain checks in `phase5_diag_planned.json` (`--chains`) are a step of the
   rebuild. The descriptive notes in `completeness_check.json` and `phase5_diag_lastweek.json` now match their
   scripts' current descriptions.
5. The v2 power checks were run on 2026-10-04, before D8 item 3 merged record 8699 into its pair (546 accidents in
   the 2021 window, 545 after). Run on the accident table as it was then (`--before-d8` in `src/power_h1.py`), they
   reproduce exactly. On the final table the shares move by a few points (a planted 1.3 is detected in 87% of runs
   instead of 83% for the 2021 window), about what 300 runs per ratio allow by chance. The stored results stay as
   they were run.

Tables that had been made by one-off commands now have scripts (`build_details_table.py`, `build_site_tables.py`,
`quality_summary.py`, `r18_dates.py`), each checked to give the stored table exactly.
