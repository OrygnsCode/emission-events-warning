# Data dossier: plants, links and the RMP filings

Written 2026-10-04, before any outcome analysis. This file covers how plants are defined and linked, and the
structure of the EPA Risk Management Plan (RMP) filings. No accident record was read. The accident tables (section
6 of the RMP) and the facility field that records whether a plant had accidents were left out of every count
below, so that the analysis stays blind to outcomes until the main test is run.

## Definition of a plant

A plant is a group of TCEQ site numbers (RNs) and EPA RMP facility IDs that the linking rules identify as the same
physical place. The table was frozen on 2026-10-04 after the author's review (hashes in
`data/frozen/link_table_freeze.json`; the method is described in plan deviations D2, D3 and D5).

| Measure | Count |
|---|---|
| Plants (all groups, linked or not) | 6,037 |
| Plants that join at least one RN to at least one RMP ID | 1,140 |
| ...of which have emission event reports | 596 |
| ...one RN to one RMP ID | 854 |
| ...joined only by the EPA registry (no hand review needed) | 790 |
| Texas RMP facilities ever registered | 2,408 |
| ...inside linked plants | 1,221 |
| ...inside linked plants that have event reports | 669 |
| Plants with an RMP risk period (enter the main test's risk set) | 2,328 |

The links were made as follows:

- 1,373 links came from the EPA Facility Registry and 296 from IDs listed in the filings themselves. These were
  accepted by rule.
- The author reviewed 375 location- and name-based pairs and 86 chain links by hand. This added 106 links and
  removed 33 previously accepted ones.
- 28 chain flags remain after review, and each one was examined.
- A rerun from scratch reproduced the frozen hashes exactly.

Most linked plants are simple: the median plant has one RN and one RMP ID, and the largest has eight of each.

### Known gaps in the plant table

- 2,351 RNs with event reports have no coordinates. They are mostly oil and gas leases and pipelines, which rarely
  file an RMP. Only 66 are gas processing plants (industry code 211112 or 211130 in the Central Registry).
- 1,188 of the 2,408 Texas RMP facilities are not in a linked plant. (The 1,221 RMP IDs in linked plants include one,
  joined through the EPA registry, that is not among the 2,408.) Plan D5 counts 66 of these unlinked facilities with
  RMP accident records, mostly water treatment, cold storage and food plants that seldom file TCEQ event reports.
  This 66 is unrelated to the 66 gas processing sites above.
- TCEQ has been asked for its own site coordinates through a public information request. If they arrive, they will
  be used only for check R29.

## The RMP filings (structure only)

The Texas slice of the EPA RMP database (`data/slices/rmp_raw/`) has 10,305 filings from 2,408 facilities, 1999 to
2025.

Filings come in waves at the five-year resubmission deadlines: 1,525 in 1999, 1,062 in 2004, 762 in 2009, 622 in
2014, 507 in 2019 and 472 in 2024. Filings between waves are corrections and updates. The median facility has 4
filings; one has 28.

985 facilities deregistered at some point. A plant's risk period in the study ends at its latest deregistration
date (`src/build_tables.py`). The latest filing of 219 facilities is from 1999, so many plants left the program
early, before the study window.

The largest groups by process industry code are:

| Industry | Code | Process records |
|---|---|---|
| Basic chemicals | 3251 | 4,750 |
| Petroleum refining | 3241 | 4,376 |
| Water and sewage | 2213 | 3,375 |
| Oil and gas extraction | 2111 | 2,143 |
| Resins and plastics | 3252 | 1,147 |
| Warehousing and storage | 4931 | 978 |

Of 21,122 process records, 14,777 are Program 3 (the full process safety program), 4,318 are Program 2 and 2,027
are Program 1.

1,516 of 10,305 filings mark their own coordinates as not valid. The EPA registry (FRS) coordinates are present on
96.7% of filings and were used by the linking rules.

The fields used by H2 (staff numbers, program level, industry code, prevention program dates) are in the facility,
process and prevention tables. Missing values are handled as written in the plan (D2 note). The staff field is 0
on 811 of 10,305 filings and blank on 5, and the filings do not state whether 0 means none or not given. A written
rule is needed before H2 uses staff numbers (proposal P4 in `docs/data_dossier/README.md`). Status note (added
2026-10-06): decided on 2026-10-04 in plan D6 item 3: a staff count of 0 is treated as missing, with the result keeping
0 shown beside it.

The change history tables record every correction to a filing, including the old and new values. This dossier did
not open the accident change history.

## Other sources in the project

Each of these is a secondary source or a check. None is needed for the main test.

| Source | Use in the plan | State |
|---|---|---|
| CSB investigations, NRC reports, OSHA severe injuries and inspections, news candidates | Completeness and dating checks of RMP; outcome O6 | Downloaded and sliced to Texas; read only under their written rules |
| EIA refinery data, BLS employment (QCEW), Census business patterns, Federal Reserve Board industrial production (G.17 files; FRED was not reachable) | Plant and market covariates for H2 and context | Downloaded; not yet summarized |
| NOAA storm events, lightning, hurricane tracks, GHCN weather | Weather context for the cause rules and robustness checks | Downloaded; storm and hurricane dates match the weather wordings found in the event text |
| EPA ECHO and ICIS-Air (inspections, violations, stack tests) | Context for reporting behaviour; possible R-check | Downloaded and sliced |
| TCEQ notices of violation and enforcement, agreed orders, compliance history | Context; the event text shows enforcement letters prompting late reports | Downloaded |
| TROPOMI satellite NO2 and SO2, CAMPD power plant hourly data | Exploratory only | Downloaded; not used in any frozen analysis |

Air monitors, wind, satellites, fenceline benzene, complaints, 311 and the emissions inventory are described in
their own dossiers in this folder.
