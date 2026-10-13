# Data dossier: TCEQ emission event reports

Written 2026-10-04, before any outcome analysis. No accident record was read for this file, the RMP accident table
was not opened, and nothing here uses accident dates.

## Methods

| Level | What | Size |
|---|---|---|
| Processed by code, every row | All parsed report pages (`data/derived/details_table.parquet`), the contaminant table, the event table | 103,614 reports, 575,698 contaminant rows |
| Read by a person, report by report | A stratified sample: 2,058 reports at linked plants (by year and event type) and 1,000 elsewhere | 3,058 reports (550 with every field, 2,508 with cause, actions and basis trimmed to the first 200 characters) |
| Counted by code after the reading | Every wording found in the reading, over all 103,614 reports (`src/census_event_text.py`, output `data/derived/event_text_census.json`) | 22 phrase lists |

The reading notes, kept batch by batch, are stored outside the repository because they quote company text. Their
findings are summarized below. This file names no plant.

## The source in numbers

The database holds 103,614 reports from March 2003 to September 2026.

| Event type | Reports |
|---|---|
| Emissions event | 71,027 |
| Maintenance | 12,812 |
| Air startup | 7,650 |
| Excess opacity | 7,240 |
| Air shutdown | 4,885 |

By report form, 86,000 are final, 17,610 initial only, 2 additional information and 2 interim. Reports per year fall
from about 7,500 (2004) to about 2,000 (2024). Maintenance, startup and shutdown reports mostly stop after 2010.

14 reports have no usable date, and one has an end date in the year 3000 (a typing error on an air startup report).
Both groups are outside the primary count.

The reports that can enter the main test are emissions events at plants with an RMP risk period, dated from 97 days
before June 1, 2003 to December 31, 2021, after the same-start merge. There are 29,192 such reports at 508 plants.
Half of these plants have 9 or fewer reports, and the busiest 1% of plants hold 13.8% of the reports.

## Findings from the reading and their implications

### 1. Some reports describe an upset that did not happen

Companies file within 24 hours, before they know the amounts. The final report often states later that the event
was below the reportable amount, was cancelled, did not occur, or should not have been filed. The wordings found
(described, not quoted) were: retracted as not reportable; a request to rescind the initial report; a statement
that it was a non-event or did not take place; the activity was cancelled; it should not have been reported; a
request to delete the incident; the agency code UML0 (no reportable amount); and emissions zeroed out. The exact
patterns are `NARROW_NON_EVENT` in `src/census_event_text.py`.

- The frozen rules (rules v1.0) flag 4,607 reports: 218 duplicates, 3,887 not reportable and 874 filed in error.
  A report can carry more than one flag (365 carry two or three), so the three counts add up to more than 4,607.
- Narrow phrase lists written after the reading find 1,448 more reports that the frozen rules miss. Among the main
  test's 29,192 reports, they find 209 (0.7%).
- In 25 randomly drawn hits from the main test's reports, about 22 truly state that the report was withdrawn,
  empty, or below the reportable amount.
- Wider lists were tried first and rejected because they matched boilerplate. For example, one operator includes in
  every report a sentence stating that the event did not require an emergency response.

The plan deliberately keeps below-threshold reports in the primary count, because an upset still happened and small
upsets are the warning sign under study; R17 drops them. A report stating that the event never happened, or was
cancelled, is different, because there was no upset. These reports are 0.7% of the total, so they cannot move the
main result much. Proposal P1 below adds them to R17.

### 2. One upset can produce several reports

The plan merges reports with the same plant, start time and event type (4,070 extra reports). The reading showed
further ways in which one upset receives several incident numbers:

- split notifications, where a report states that it is one of several notifications for a single incident (for
  example the sixth of nine), one per emission point or account;
- separate reports per pollutant kind, for example one for the unburned hydrocarbons and another for the
  combustion products of the same flaring;
- continuations, where a report states that it continues an earlier incident number, which is common when a third
  party shuts a site in for days;
- re-dated pre-notices, where a report states that it is the same event as an earlier notice, with a date change;
- plain duplicates in other words, where reports state that they were entered twice, reported twice, or duplicate
  another STEERS entry. The exact patterns are `NARROW_DUPLICATE` in `src/census_event_text.py`.

Over all reports, 2,617 cite another existing incident number in their text. Of 3,349 such pairs at the same plant
site, 1,890 are within 7 days of each other, and only 635 are already merged by the same-start rule. Among the main
test's reports, 291 cite another of those reports at the same plant within 7 days, and the narrow
duplicate/continuation phrases find 97 that the frozen rules miss.

For a few plants the count therefore runs slightly high, because long upsets are counted once per report. This
affects about 1% of the reports (361 of the 29,192 are found by either count, each report counted once). R13
already tests the opposite direction (count every report). Proposal P2 adds the direction that merges more.

### 3. An upset at one plant can be reported under another plant's number

This was the most common pattern in West Texas. Field sites (wells, batteries, boosters) flare when the gas plant
they sell to goes down, and they file under their own number, giving the gas plant's failure as the cause. The name
of one gas plant (and the field around it) appears in about 4,700 reports filed under 253 site numbers. On the Gulf
Coast the same happens through shared utilities: a steam or power supplier fails, a shared refinery fuel gas system
overpressures, or a neighbour's piping failure upsets a unit next door. Among the main test's reports, 3.9% have
"third party" as the first-matched cause, and 7.6% have power.

A plant's own count therefore misses some of its troubles when they appear only in other operators' reports. This
error is in the exposure, not the outcome, and it does not depend on accident dates, so it weakens a real
association rather than creating a false one. It is stated as a limitation. It cannot be corrected by rule without
naming companies, which the cause rules avoid by design.

### 4. Dates

The final report carries the dates the company settled on. Start times are sometimes corrected after the initial
report, with a note that the start time has changed since the initial report.

In the main test's reports the median time from event start to report is 12 days. 4.2% were filed more than 30
days late, and 223 were filed more than a year late; these come from audit disclosures, stack-test results,
enforcement letters, and backfilled historical events.

When STEERS will not accept a blank time, companies keep the planned time. Start and end times on non-events are
therefore not real (212 reports mention a STEERS outage or an alternate filing route).

The plan counts by event start date, not report date, which is appropriate. Very late reports enter the count at
their true date, so the count reflects what was eventually reported, not what was known at the time. This matters
only for a real-time warning tool, and the usefulness section of the plan states this.

### 5. Amounts

STEERS does not accept a zero, so companies enter placeholders. Of 546,367 pound rows, 1,553 are 0.0001, 2,979 are
0.001 and 4,730 are 0.01. Some of these are real small amounts. 194 opacity rows exceed 100%, and many opacity
values are assumptions rather than readings (for example, 100% assumed for the whole event, or an assumed lower
bound). Carbon dioxide is 15.4% of all reported pounds.

None of this affects the primary exposure, which counts reports. It does affect the severity measure (pounds
released), and proposal P3 sets the rules before that measure is used.

### 6. Initial-only reports

8.9% of the main test's reports are initial only. The reading showed that most are real events whose initial report
served as the final, as their text states; few are abandoned filings. The share is similar across periods: 10.3%
(2003 to 2007), 8.1%, 10.1% and 6.1% (2018 to 2021). No change is proposed, and these reports stay in the count.

### 7. Event type is sometimes wrong

Planned maintenance is sometimes filed as an emissions event, and the reverse. Reports state that they were entered
as an emissions event by mistake, were closed out as an emissions event instead of a startup, or began as planned
maintenance and turned into an upset. These errors run in both directions and are not tied to accident dates, so
they add noise to the count rather than bias.

### 8. Shocks that hit many plants at once

Hurricanes (Rita, Ike, Gustav, Harvey, Delta, Beryl), repeated freezes (worst in February 2011 and February 2021),
and regional power and pipeline outages produce bursts of reports across many plants. In February 2021 the Governor
suspended the emissions event reporting rules (30 TAC 101, Subchapter F), so that month is under-reported. The
statewide count in the model is included to absorb these bursts. The cause rules flag weather as the first-matched
cause in 8.4% of the main test's reports.

### 9. Fires and releases inside the TCEQ data

3.4% of the main test's reports mention a fire or explosion, and others describe leaks with loss of containment.
Some of these are the same incidents that appear in the RMP accident table. The plan's 7-day gap before each
accident keeps such same-incident reports out of the exposure window. The planned match of each accident to its
TCEQ report will show how often this happens.

### 10. Text that must never be quoted

Report text sometimes contains private individuals' names and phone numbers (for example, a landowner whose tractor
hit a pipeline) and the names of agency staff. The project never quotes raw report text in any output.

## Proposals for the author's decision (plan deviation D6, not yet adopted)

These proposals change no primary rule. Each is a robustness check or a rule for a measure that has not yet been
used.

Status note (added 2026-10-06): decided on 2026-10-04 in plan D6, which the author approved that day. P1 became the
R17 extension and P2 became R30 (D6 item 1); P3 became the severity rules (D6 item 2), with the contaminant name
lists completed and NOx parts no longer counted twice under plan D7. The text below is kept as written before that
decision.

P1. Extend R17 with withdrawn reports and non-events. Use the narrow phrase lists in `src/census_event_text.py`
(`NARROW_NON_EVENT`). They flag 209 of the main test's reports beyond the frozen rules.

P2. New check R30: merge cross-referenced reports. Count as one occurrence any report that cites another report at
the same plant within 7 days, or that uses split, continuation or duplicate wording (`NARROW_DUPLICATE`). This is
the merging direction; R13 is the opposite.

P3. Rules for the severity measure, set before its first use. The plan's "total pounds released" adds every row,
but rows overlap and include inert gases. In 259 reports a "natural gas" row sits beside a non-methane or VOC
subtotal of the same gas, and 1,726 reports list a VOC total next to single hydrocarbons that are part of it.
Carbon dioxide is 15.4% of all pounds. The proposed rules are:

- Severity is the sum of four families that do not overlap: sulfur dioxide, hydrogen sulfide, nitrogen oxides and
  carbon monoxide, each matched by its frozen name list.
- VOC severity is reported separately, as the larger of the report's total VOC rows and the sum of its single
  hydrocarbon rows, never both.
- 0.0001 is treated as zero. 0.001 and 0.01 are left as written, because some are real small amounts.
- Carbon dioxide, nitrogen, hydrogen, water and steam are left out.
- Opacity over 100% is treated as missing.

P1 and P2 are expected to affect about 2% of the counted reports (555 of the 29,192, each report counted once).
They are reported so that a reader can see that the main result does not depend on them.

## Reproduction

```
python3 src/census_event_text.py
```

Inputs: `data/derived/details_table.parquet`, `causes.csv.gz`, `events_v2.csv.gz`, `contaminants.csv.gz`,
`plant_risk_v2.csv`. Output: `data/derived/event_text_census.json` (copy in `data/manifests/`).
