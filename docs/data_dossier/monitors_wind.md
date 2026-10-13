# Data dossier: air monitors and wind (for check V1)

Written 2026-10-04, before V1 was run. Every hourly row of the sources below was processed by code
(`src/census_monitors.py`; outputs in `data/derived/monitors/`). Nothing here compares monitor values with event
dates. That comparison is V1, and its exact rule is added to the plan (D6) first.

## Sources

| Source | Contents | Span | Size |
|---|---|---|---|
| EPA AQS hourly files (Texas slice) | SO2, NO2/NOx, benzene, 1,3-butadiene, total non-methane organics, wind | 2002 to 2026 | 846 files in the slice; 2,135 wind site-years in 2003 to 2021 |
| TCEQ CAMS monthly reports | Hourly H2S (not in AQS) and everything else the site measured: SO2, NOx, organics, wind, temperature | 1997 to 2026 | 3,156 pages, 31,433 parameter-months at 21 H2S sites |
| IEM airport weather (ASOS) | Wind direction and speed | to 2026 | 238 stations; 229 stations and 3,426 station-years in 2003 to 2021 |

## Completeness, 2003 to 2021

| Measure | Sites | Site-years | Median share of hours present | Site-years at least 75% complete |
|---|---|---|---|---|
| SO2 | 50 | 545 | 96% | 90% |
| NO2 | 69 | 892 | 95% | 92% |
| Benzene (hourly gas chromatograph) | 31 | 251 | 81% | 66% |
| 1,3-butadiene (same instruments) | 31 | 252 | 79% | 60% |
| Total non-methane organics | 31 | 251 | 79% | 63% |
| Wind direction at monitor sites | 179 | 2,135 | 99% | 93% |
| H2S (TCEQ pages) | 21 | 3,275 site-months | 87% of hours valid | |
| Airport wind direction | 229 | 3,426 | 97% | 91% |

## Observations from reading the files

- Values below detection are common for the gases: 67% of SO2 hours and 30% of NO2 hours are below the
  instrument's stated detection limit. These are mostly clean-air hours. V1 looks for a rise above that floor.
- The number of sites with hourly benzene in the AQS files falls from 22 (2006) to 8 (2015 on). The files do not
  give a reason. TCEQ's own monthly pages for those instruments were not downloaded. Fetching them would widen V1's
  benzene coverage after 2014; this is proposal P5 below and requires the author's approval.
- Hourly benzene and butadiene are reported in parts per billion carbon, not parts per billion. Comparisons stay
  within one site and one unit, so no conversion is needed.
  Note added 2026-10-06: this held while V1 used AQS values only. Plan D6 (item 4 and the D6 note) added TCEQ's
  AutoGC pages, which report parts per billion by volume, so V1 converts those values to parts per billion carbon
  (benzene times 6, 1,3-butadiene times 4). The conversion was checked on hours both sources report
  (`data/manifests/v1_unit_check.json`).
- On TCEQ pages, hours without data carry flags in place of values (calibration, span, power failure, quality
  assurance and similar). 87% of H2S hours are valid. Flagged hours are treated as missing.
- Benzene appears in two AQS file groups (organics and hazardous air pollutants). The first count added them
  together and showed sites over 100% complete; it was rerun keeping one group per site. The numbers above are from
  the rerun.

The sources use different clocks:

| Source | Time basis |
|---|---|
| AQS and TCEQ | Local standard time all year |
| Airport data | UTC, as downloaded |
| Event reports | Local clock time as typed by the company. The reports do not say whether daylight saving applies, so summer times are taken as daylight time. |

V1 must convert all times to one clock, because an error of one hour would blur short events.

## Events available to V1

Events eligible for V1 are emissions events at plants with an RMP risk period, June 2003 to 2021, after the
same-start merge. There are 28,478 of them, and 28,332 have a site location. An event counts as covered when a
monitor of the pollutant it reported stood within 10 km and had at least 30 days of data that year.

| Pollutant reported | Events reporting it | Covered by a monitor within 10 km | Plants with covered events | Median distance to nearest |
|---|---|---|---|---|
| SO2 | 13,921 | 2,221 | 65 | 2.8 km |
| NOx | 14,211 | 2,259 | 86 | 4.8 km |
| H2S | 12,480 | 936 | 12 | 1.9 km |
| Benzene | 4,837 | 1,182 | 38 | 5.5 km |
| 1,3-butadiene | 2,339 | 987 | 29 | 5.5 km |
| VOC (as total organics) | 5,184 | 820 | 55 | 4.4 km |

For SO2, NOx and organics about one event in six has a matching monitor nearby; for H2S, one in thirteen; for
benzene, one in four; and for butadiene, two in five. Coverage is concentrated in the Gulf Coast industrial areas
and at a few West Texas sites. 97% of these monitor sites also measure wind on site, so wind direction comes from
the same place as the pollutant.

"Same year with 30 days of data" is a feasibility count, not proof that the monitor ran on the event day. V1
itself checks the hours.

V1 can show whether reported events line up with measured rises downwind. The covered events are not a random
sample: they are at plants that sit near monitors, which are mostly larger Gulf Coast plants. A weak V1 result
would mean that small events often do not reach the monitor, not that they did not happen.

## Proposal

P5. Fetch TCEQ's hourly organics pages for the gas chromatograph sites, 2015 to 2021. These are the same public
report pages already used for H2S, and they would be fetched in the same polite way. They would restore the
benzene and butadiene coverage that the AQS files lose after 2014. This requires the author's approval.

Status note (added 2026-10-06): decided on 2026-10-04 in plan D6 (item 4 and the D6 note). The author approved P5 in a
wider form: TCEQ's AutoGC monthly summary pages for every site that measured benzene, 1,3-butadiene or total
non-methane organics, 2003 to 2021.
