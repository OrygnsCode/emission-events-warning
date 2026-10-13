# Warning-sign checks V1 to V5: results

These checks test whether independent sources record something at the same place and time as an emission event reported to TCEQ. They use no accident data. The rules for each check were fixed in `analysis_plan.md` (section D6) before any check was run. A later full review of the code found several places where the code did not follow those rules. These were corrected, and section D7 of the plan lists each one with the numbers before and after. All numbers below are from the corrected code and come from the result files in `data/manifests/`.

## V1. Air monitors downwind (`v1_result.json`)

For each reported event we used the nearest state or EPA air monitor within 10 km that measures the reported pollutant, restricted to hours when the wind blew from the plant toward the monitor. Each event was compared with the same monitor in the same month and hour of day, with wind from the same direction, in other years on days with no reported event nearby. The placebo repeats the calculation for the same clock hours one year earlier (or later), when nothing was reported.

| Pollutant | Events checked | Plants | Downwind level relative to normal (95% CI) | Placebo |
| --- | --- | --- | --- | --- |
| SO2 | 767 | 48 | 1.91x (1.55 to 2.22) | 0.85x |
| 1,3-butadiene | 376 | 24 | 2.99x (1.99 to 7.48) | 0.98x |
| VOC (total) | 265 | 39 | 1.22x (1.02 to 1.49) | 0.90x |
| Benzene | 380 | 30 | 1.35x (1.15 to 1.58) | 1.14x |
| NOx | 933 | 61 | 1.17x (1.10 to 1.24) | 1.12x |
| H2S | 399 | 15 | 1.01x (0.81 to 1.32) | 1.27x |

SO2 and 1,3-butadiene are clearly higher downwind during reported events, and the placebo shows no rise. For these two pollutants the reports agree with what the monitors recorded.

Total VOC and benzene are higher during events than in the placebo, but by less, and the peak-hour comparison below does not support them. We treat them as weak support. NOx is only slightly above its placebo and gives little signal either way. H2S shows no rise.

Most events could not be checked, because no monitor with data was within 10 km or the wind never blew from the plant toward the monitor. The checked events come from the plants counted in the table, which are a small share of all plants. A few large episodes account for much of each ratio; for SO2, leaving out the plant with the largest excess still gives 1.84x.

Peak hours were compared as the share of events whose highest downwind hour exceeds the 95th percentile of normal hours, against the placebo for the same events:

| Pollutant | Events | Placebo |
| --- | --- | --- |
| SO2 | 34% | 19% |
| 1,3-butadiene | 33% | 29% |
| NOx | 27% | 26% |
| Benzene | 27% | 30% |
| VOC | 24% | 30% |
| H2S | 22% | 30% |

Only SO2 is clearly above its placebo.

Data checks: where EPA and TCEQ both report, their values agree hour for hour (benzene and butadiene on over a million hours after the unit conversion; wind, SO2 and NOx with no time shift). Three events and one set of comparison hours were recomputed by hand and matched exactly.

## V2. Satellite flare detections at night (`v2_result.json`)

The VIIRS satellite instrument detects hot spots at night. For plants that reported flaring, nights during the first 72 hours of a reported flaring event were compared with other nights at the same plant and month in other years, at least 2 days away from any report at that plant. Plants with a neighbour within 1 km were excluded, so that a detected flare cannot belong to the plant next door.

A flare was detected on 14.9 percent of event nights and 2.9 percent of ordinary nights. Comparing each plant only with itself, the odds of a satellite detection are about 6.6 times higher on event nights (95% CI 4.0 to 10.5, 128 plants). A simpler cross-check gives 5.5.

Two sensitivity analyses were added after the results were seen and do not replace the main estimate. Counting only nights whose 8 p.m. to 6 a.m. window overlaps the event gives 10.6 (6.4 to 17.0), and using clock time instead of solar time gives 6.7. The result holds or increases under each.

## V3. Refinery fenceline benzene (`v3_result.json`)

EPA requires refineries to report benzene at their fence line every two weeks. For 26 Texas refineries, 2018 to 2021, quarters with more reported events were compared with quarters with fewer events at the same refinery.

No association was found: doubling the number of events changes fenceline benzene by about -1.8 percent (95% CI -9 to +6 percent). The raw averages do rise with the number of events, but the rise disappears once each refinery is compared with itself. It therefore reflects which refineries report more events, not what happens when they do.

For 2022 to 2025, shown as description only, there are 360 refinery-quarters. The rank correlation of event reports with fenceline benzene is 0.22, again before comparing each refinery with itself.

## V4. Public complaints (`v4_result.json`)

TCEQ air complaints, counted by county and day, are about 9 percent higher on days with a reported event in the county (rate ratio 1.09, 95% CI 1.03 to 1.15). Each complaint is counted once, although the source file lists some complaints several times.

Houston 311 air and odor calls within 5 km of a plant are about 25 percent higher on event days (rate ratio 1.25, 95% CI 1.13 to 1.39).

Sensitivity analyses added after the results were seen examined days on which an event that started earlier is still running. Leaving those days out, or counting them as event days, gives 1.06 (0.99 to 1.14) for TCEQ complaints and 1.21 to 1.26 for Houston 311. The 311 result is therefore robust, while the TCEQ complaint result is small and not robust.

## V5. Annual emissions inventory (`v5_result.json`)

Plants also report yearly totals to TCEQ's emissions inventory, and these totals include event emissions. The comparison covers the 326 plants present in both sources and every inventory year from 2016 to 2021 (1,812 plant-years).

- The event reports and the inventory rank plant-years in a similar order (rank correlation 0.78, 95% CI 0.74 to 0.82; 0.75 to 0.81 for each of SO2, H2S, NOx and CO).
- Where both list tons, the event reports sum to a median of 73 percent of the inventory figure (95% CI 66 to 79 percent), and 59 percent are within a factor of 2.
- 421 plant-years have inventory event tons but nothing in the event reports, and 34 have the reverse. 110 plant-years with events have no inventory record at all.

## Summary

Four of the five checks support the event reports as real signals. Satellites detect far more flaring on event nights, downwind monitors record more SO2 and butadiene, Houston 311 calls near plants rise on event days (TCEQ complaints rise only slightly, and not robustly), and the event reports track the annual inventory. Benzene does not hold up well: there is no association at the refinery fence line and only weak support from the hourly monitors. H2S shows no rise at the monitors.

These checks do not test whether events come before accidents. That is the Phase 4 analysis, which awaits the author's approval.
