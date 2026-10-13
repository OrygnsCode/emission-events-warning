# Phase 4 result: do small emission events rise before serious accidents?

The primary analysis was run on 2026-10-05 with the code and inputs locked in the analysis plan (deviation D8, commit `fa451ac`; the SHA-256 values listed there all matched at the start of the run). Full numbers: `data/manifests/h1_primary_result.json`. Figure: `docs/figures/h1_picture.png` (table: `docs/figures/h1_picture.csv`).

## Result

At Texas plants with an EPA Risk Management Plan, the number of unplanned emission events a plant reported in the 3 months before a serious accident (days 97 to 8 before) was not higher than on that plant's other days in the same year.

| | Primary (accidents to 2021) | Original plan (accidents to 2023) |
| --- | --- | --- |
| Accidents / plants | 545 / 216 | 571 / 223 |
| Rate ratio of an accident when recent events double | 0.88 (95% range 0.75 to 1.02) | 0.87 (0.75 to 1.01) |
| p value (model) | 0.097 | 0.062 |
| p value (10,000 permutations of accident dates) | 0.117 | 0.084 |

## Interpretation

This is a null result: we found no evidence that events rise before accidents.

The plan specified that a null result be reported as the largest effect the data still allow. A first version of this report, written on the run date, gave that bound as the upper limit of the primary interval (1.02, that is, a rise of under about 2.4% per doubling of events). That statement was withdrawn on 2026-10-05 after a review of the models in Phase 5 (plan D10, addendum 2), for the following reason.

An accident is itself reported to TCEQ, mostly on the accident day. Those reports fall in the look-back windows of the comparison days that follow, which pulls this design below 1; the slightly-below-1 estimate here is that effect, not evidence that events protect against accidents. The pre-run power check could not reveal it, because its simulated accidents generate no reports. When each plant's reports from the accident day and the 2 days after are removed from the counts, with every day kept, the same test gives 1.05 (0.85 to 1.29). The same removal around simulated accident dates gives 1.03, so it adds little bias of its own. The bound the data support is therefore that rises of more than about 30% in accident risk per doubling of recent events are unlikely (upper limits of 1.26 to 1.33 across the versions of this check for the 90-day main test). Details: `docs/phase5_results.md`, section 2. The locked numbers in the table above are unchanged.

Before the run, the power check estimated that the test would detect a 20% rise per doubling about half the time and a 30% rise about 8 times in 10.

## Figure

The figure shows events at each plant month by month, from 2 years before to 1 year after its accidents, relative to the plant's own average, beside the same curve for random days in the same plant and year:

- In the months before accidents the two curves are similar (single months differ by chance); if anything, the accident curve is slightly lower in the last 6 months.
- The only jump is in the accident month itself (about 1.9 against 1.3). This is the accident and its own reports, which the test excludes by design with its 7-day gap, so that an accident cannot count as its own warning.

## Verification

1. Two programs that share no code (pyfixest and a separately written NumPy program) give the same coefficient to within 7e-11, so the rate ratios agree to 10 decimal places.
2. A standard Poisson regression with an indicator for every plant-year (statsmodels) gives the same coefficient (difference under 1e-10) and nearly the same standard error (0.1125 against 0.1123), so the same result, 0.88 (0.75 to 1.02) (`data/manifests/h1_third_fit.json`).
3. Accident counts rebuilt directly from the accident table match on every one of 153,138 plant-days (2021) and 161,168 (2023).
4. Exposure was rebuilt independently: 1,400 plant-days recomputed from the raw event table, with no differences (first checked before the run; repeated and stored in `data/manifests/stored_checks.json`).
5. The permutation test and the model agree: neither p value is below 0.05.
6. Before the run, with simulated accident dates, a planted effect of 1.5 was recovered as 1.46 and 1.43 and the figure rose before the simulated accidents; with no effect planted, results centred on 1.00 with the expected 5 to 6% false positives.

## Scope

- This report covers the primary question only: the count of unplanned events in a 90-day window ending one week before, at the same plant.
- The secondary and robustness analyses are reported in `docs/phase5_results.md`: other outcomes (fires and explosions, injuries, harm outside the fence), other windows and gaps, severity (pounds released), cause categories, reporting-rule periods, disasters, the post-accident checks R15 and R16, and the comparison between plants (H2). They were registered in advance and are reported whatever they show; none replaces the primary result.
- The result concerns prediction, not cause.
