# Data dossier: sources for warning-sign checks V2 to V5

Written 2026-10-04, before any check was run. This file describes the data each check would use and what those
data can and cannot show. It compares nothing with the event reports or with accidents. The exact rule for each
check is added to the plan (deviation D6) before the check is run.

## V2. Satellite fire detections (NASA FIRMS)

### Data

FIRMS provides satellite heat detections for Texas from three instruments:

| Instrument | Years | Detections |
|---|---|---|
| MODIS | 2000 to 2024 | 363,652 |
| VIIRS on Suomi NPP | 2012 to 2024 | 891,987 |
| VIIRS on NOAA-20 | 2018 to 2024 | 530,759 |

FIRMS labels each detection. Most are labelled "presumed vegetation fire". Gas flares fall under "other static
land source": 173,492 VIIRS detections on Suomi NPP and 123,779 on NOAA-20. VIIRS detections are split about evenly
between night and day. MODIS detects few flares (9% of its detections are at night), and its resolution is too
coarse for single plants.

474 of the 580 event sites at plants with an RMP risk period have at least one VIIRS detection within 1 km. The
median site has 66 detections and the busiest has 10,184. Plants that flare continuously appear hot on most clear
nights.

### What the data can and cannot show

VIIRS passes over about twice a day, so it can show whether a reported flaring day was hotter than the same
plant's other days. Small flares, and flares under cloud, are missed, so a detection rate below 100% is expected
and does not indicate a failure of the reports.

A 1 km radius takes in neighbouring plants in dense industrial areas. Plants with another flaring plant inside the
radius need to be flagged or dropped.

Coverage starts in 2012, so V2 covers 2012 to 2021 of the primary window. VIIRS Nightfire, which measures flare
heat directly, will be added only if EOG grants the license.

## V3. Refinery fenceline benzene (EPA CEDRI reports)

### Data

Since 2018 every refinery has sampled benzene at its fence line every two weeks. Each sampling period reports Δc,
the highest sampler minus the lowest, which measures the refinery's own contribution. A rolling annual average of
Δc is reported alongside, and EPA's action level for that average is 9 µg/m³.

We downloaded 1,195 zip files containing 1,190 workbooks and parsed them by the template's own field names
(`src/parse_fenceline.py`). The workbooks spell refinery names in 57 ways. A hand-made crosswalk
(`data/manual/fenceline_crosswalk.csv`) maps every spelling to one of 26 refineries and terminals with crude
splitters. Each row of the crosswalk gives its basis: the RN written in the workbook, EPA's own filing index, or
the Central Registry.

The result is 5,359 two-week periods across 26 main sampler rings, plus two extra rings filed alongside. Most rings
have about 220 periods from January 2018 to mid-2026, which is complete.

### Problems found and how they were handled

- The same period is often filed several times (one file per attachment, plus revisions). For each refinery and
  period the latest submission is kept. 51 periods have different values in different submissions.
- Some workbooks carry wrong labels. One refinery's workbook says "West Refinery" but carries the East refinery's
  RN and EPA filing. Two refineries give the EPA registry number instead of the TCEQ RN, and one gives an air
  account number. The crosswalk records each case.
- One refinery files two sampler rings together. The second ring is identified by its zip file names; without that
  step it would appear as two readings every two weeks.
- From 2023, three facilities' workbooks hold only one period per quarter, about 4 a year instead of 26. The rest
  are not in the files EPA serves. Quarterly averages for those three facilities are therefore single readings
  from 2023 on, and must be flagged in V3.
- 17 periods have impossible or unusual dates (end before start, or longer than 18 days). They are flagged in the
  table, not corrected.
- 67 workbooks hold no periods. These are early 2019 first filings in an older layout that were later resubmitted,
  and one company's supplemental weather data. Every refinery's 2019 periods are still complete from other
  filings.

### Distribution of values

Median two-week Δc is 3.9 µg/m³ (10th to 90th percentile 1.3 to 12.2). Samplers below detection make up 5.3% of
sample rows. As written in the filings, the rolling annual Δc reached the action level in 161 of 808
refinery-quarters, at 14 of 26 facilities. This was not checked against EPA's own published figures. Some periods
carry comments stating that an offsite source affected the reading.

### What the data can and cannot show

Fenceline monitoring starts in 2018, so V3 covers 2018 to 2021 of the primary window, at refineries only. It
measures benzene, which most emission events do not report. V3 therefore tests whether quarters with many events
are also high-benzene quarters; it does not test individual events.

## V4. Complaints

### TCEQ complaints (open data)

The file holds 190,443 complaints from 2002 to 2026 in 243,112 rows; the file repeats a complaint once per NAICS
code, and date and county never differ between the copies. 71,555 complaints are about air (89,901 rows). 57,164
air complaints carry an RN, and 3,265 of those are at plants with an RMP risk period (2,506 in the primary window).
These counts were corrected on 2026-10-04 (plan D7); the earlier version gave row counts.

Reading 120 complaints showed the following.

- The complainant's location is not recorded. There are no coordinates, only the county and sometimes a ZIP code
  or street in the text, so the plan's "within 5 km" rule cannot be applied to TCEQ complaints.
- The RN is filled in by the investigator. It names the source the investigator settled on, often after visiting
  the site. An investigator may also know about a reported event, so tying complaints to plants by RN can lean
  toward plants with reported events. V4 must not rely on RN attribution alone; complaints by county and day are
  the cleaner measure.
- In Harris County many air complaints are referred to the county or city pollution control office and do not
  appear in this file.
- The incident start date is missing in 54% of rows, and "Jan 01, 1800" appears as a placeholder. The received
  date is complete and is the one to use.
- Most air complaints are about dust, outdoor burning, paint booths, farms and landfills rather than plant upsets.
  Some concern flares and refinery odors.
- Complainants' and staff names and phone numbers appear in the text. They are never quoted.

### City of Houston 311

The 311 files hold 5.6 million service requests from 2011 to 2026. 11,046 are "Air Pollution" cases: 432 to 547 a
year in 2011 to 2014, and 587 to 998 a year in 2015 to 2021. Coordinates are 0 for 395 of the 432 cases in 2011,
so 2011 contributes 37 usable cases; from 2012 on almost all cases have coordinates. These figures were corrected
on 2026-10-04 (plan D7). The earlier version said "about 2,300 a year in 2011 to 2014" and "all with coordinates",
which was wrong.

3,941 air cases lie within 5 km of an event site at a plant with an RMP risk period, and 113 of 159 such sites in
the Houston area have at least one case within 5 km. Coordinates of 0 are invalid, and those cases are dropped.

311 covers only the City of Houston. Many plants are in other cities (Pasadena, Deer Park, Baytown, Texas City), so
their neighbours are covered only where the city limits reach. A reading of 35 cases found mostly
neighbourhood nuisances (burning, dust, welding, sewer smell). Some concern industrial odors, including chemical
smells reported across a whole area. Daily counts near any one plant are small, so V4 has little power for single
events and is best read as a pooled check.

## V5. Emissions inventory (TCEQ Point Source Emissions Inventory)

### Data

Each year's inventory (2016 to 2024; `src/census_psei.py`) lists every reporting site's emissions by unit and
contaminant, in three columns of tons: routine, emissions events (EE), and planned maintenance, startup and
shutdown (MSS). Each year has about 1,820 to 1,930 sites and 362,000 to 377,000 rows, and about 700 to 730 sites a
year report EE tons above zero. Statewide EE totals are 16,000 to 21,000 tons a year, except in 2019 (36,160 tons),
when one site alone reported 8,239 tons, 23% of that year's total. Most EE tons are SO2 (47,849 over the nine
years) and CO (47,266), followed by VOC, NOx and light hydrocarbons.

### Problems found

- Routine tons nearly double from 2016 to 2017. Almost all of the increase is nitrogen, an inert gas, which went
  from 6,977 to 868,508 tons. Totals across all contaminants are therefore meaningless, and V5 uses only the four
  pollutant families in P3.
- The inventory is revised after the fact. Older snapshots of 2016 and 2022, retrieved two years earlier, differ
  from the current files: EE tons changed by more than 1% at 16 sites (2016) and 32 sites (2022), and the 2022
  statewide EE total rose from 16,790 to 18,148 tons. V5 uses the current files and states this.
- Small sites below the reporting threshold are not in the inventory at all. Of 16,886 site-years, 8,476 are at
  sites in the plant table and 4,539 are at plants with an RMP risk period; 3,308 of those report EE tons above
  zero.

### What the data can and cannot show

V5 compares two reports by the same company for the same site and year. The inventory's EE column should be the
annual sum of the same events. Agreement shows that the event database is complete and consistent in amounts. It
does not show that the amounts are correct, because both come from the same company's estimates. V5 covers 2016
to 2021 of the primary window.
