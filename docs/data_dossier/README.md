# Data dossier

This folder describes each dataset in the project: what it holds, how it was read, what problems were found, and
what these mean for the analysis. It was written on 2026-10-04, before any outcome analysis and before any
warning-sign check was run. No accident record was read for any of these files.

| File | Covers |
|---|---|
| [tceq_events.md](tceq_events.md) | TCEQ emission event reports and contaminants. All 103,614 reports processed by code; 3,058 read one by one |
| [monitors_wind.md](monitors_wind.md) | EPA and TCEQ air monitors and wind; V1 coverage |
| [checks_sources.md](checks_sources.md) | Satellites (V2), fenceline benzene (V3), complaints and Houston 311 (V4), emissions inventory (V5) |
| [plants_links_rmp.md](plants_links_rmp.md) | The plant table and links; RMP filings (structure only); other sources in one line each |

The numbers were produced by `src/census_event_text.py`, `src/census_monitors.py`, `src/parse_fenceline.py` and
`src/census_psei.py`. Their summary outputs are copied to `data/manifests/`.

## Proposed decisions for the author (plan deviation D6, none adopted yet)

Status note (added 2026-10-06): decided on 2026-10-04 in plan D6, which the author approved that day. P1 became the
R17 extension and P2 became R30 (D6 item 1), P3 the severity rules (item 2) and P4 the H2 staff rule (item 3). P5
was approved in a wider form (item 4 and the D6 note): TCEQ's AutoGC monthly summary pages for every site that
measured benzene, 1,3-butadiene or total non-methane organics, 2003 to 2021. The final V1 to V5 rules are D6 items 6
to 11, as corrected in plan D7, and they differ from the proposals below in several details. The proposals are kept
below as first written.

None of these proposals changes a primary rule of the registered plan. P1 to P3 are robustness checks or rules for
a measure not yet used, and P4 and P5 fill gaps. The V1 to V5 rules turn the plan's one-line descriptions of the
warning-sign checks into exact rules, as the plan requires before the checks are run.

| ID | Proposal | Details |
|---|---|---|
| P1 | Extend R17 to also drop reports whose text says the event never happened, was cancelled or was withdrawn. | 209 of the main test's 29,192 reports beyond the frozen rules. See `tceq_events.md` section 1. |
| P2 | New check R30: count as one occurrence any report that cites another report at the same plant within 7 days, or uses split, continuation or duplicate wording. | About 1% of the main test's reports. See `tceq_events.md` section 2. |
| P3 | Rules for the severity measure, which has not been used yet: sum four non-overlapping families (SO2, H2S, NOx, CO); report VOC separately without double counting; treat 0.0001 as zero; leave out CO2 and inert gases; treat opacity over 100% as missing. | See `tceq_events.md` section 5. |
| P4 | Treat RMP staff numbers of 0 (811 filings) as missing in H2, and show the result with 0 kept beside it. | |
| P5 | Download TCEQ's own hourly organics pages for the gas chromatograph sites, 2015 to 2021, from the same public pages and with the same polite fetching already used for H2S. | The AQS files lose most hourly benzene sites after 2014. |

### Proposed exact rules for the warning-sign checks

These rules use no accident data. Each check is reported with its uncertainty, whatever the result.

#### V1, air monitors

| Element | Rule |
|---|---|
| Unit | One event with one monitor of the event's pollutant family (SO2, NOx, H2S, benzene, 1,3-butadiene, total organics) within 10 km, with data in the event hours. |
| Event hours | From the reported start to the reported end, capped at 72 hours, converted to local standard time. |
| Downwind hours | Event hours when the wind at the monitor site blows from the plant toward the monitor, within ±30 degrees. If the site has no wind data for that hour, the nearest airport is used. |
| Comparison hours | Same monitor, same calendar month and hour of day, same wind sector, in other years, and not within 30 days of any event at that plant. |
| Measures | The ratio of mean concentration in downwind event hours to comparison hours, pooled by family, with a 95% interval from a bootstrap that resamples plants. The share of events whose highest downwind hour is above the 95th percentile of comparison hours. Events with no downwind hour are counted and reported rather than dropped. |

#### V2, satellite heat (VIIRS, 2012 to 2021)

| Element | Rule |
|---|---|
| Unit | A plant-night. |
| Event nights | Nights during unplanned events whose text or unit names mention a flare, compared with other nights at the same plant in the same month of other years. |
| Measure | The ratio of detection rates within 1 km, from a conditional logistic model with plant-month strata. |
| Exclusions | Plants with another event site within 1 km are left out, and their number is reported. |

Superseded (note added 2026-10-06): the final V2 rule is plan D6 item 8 with plan D7 fix 6. The unit is a site-night
(RN and local evening date). Event nights are nights that overlap the first 72 hours of a flaring episode, with the
flare wording searched in the cause, actions and emission point names only. Comparison nights are at the same RN in
the same calendar month of other years, with no reported event of any type at that RN within 2 days. The measure is
the odds ratio from a conditional logistic model with RN-by-calendar-month strata, with detection rates shown beside
it.

#### V3, fenceline benzene (2018 to 2021; to 2025 shown as description)

| Element | Rule |
|---|---|
| Unit | A refinery-quarter. |
| Measure | The mean two-week Δc of the main sampler ring against the number of unplanned events at that refinery's plant in the quarter, in a linear model on log Δc with refinery and quarter effects. |
| Exclusions | Quarters with fewer than 4 sampling periods are dropped and counted. |

#### V4, complaints

| Element | Rule |
|---|---|
| (a) TCEQ air complaints | Complaints received per county-day in the event's county on days 0 to 2 after the event start, compared with the same county on the same weekdays in the same month of other years. RN attribution is not used, because investigators fill it in. |
| (b) Houston 311 | "Air Pollution" cases within 5 km of the event site on days 0 to 2, compared with the same site and month in other years, 2011 to 2021. Cases with coordinates of 0 are dropped. |
| Measure | For both, a rate ratio with plant-clustered 95% intervals. |

#### V5, emissions inventory (2016 to 2021)

| Element | Rule |
|---|---|
| Unit | A site-year present in both sources. |
| Measure | Inventory emissions-event tons against the sum of reported event pounds divided by 2,000, for the four families in P3, reported as the rank correlation and the distribution of the ratio. |
| Also counted | Site-years with inventory event tons but no event reports, and the reverse. |

## Restrictions on outputs

Raw report or complaint text is never quoted, because it contains private individuals' names and phone numbers
and the names of agency staff. No output names or ranks any Houston plant.
