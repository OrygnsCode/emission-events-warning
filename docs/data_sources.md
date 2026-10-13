# Data sources and file locations

All files listed below were downloaded by script between 2026-10-02 and 2026-10-04. Each download is recorded in
`data/manifests/external_downloads.jsonl.gz` (URL, size, SHA-256 of the bytes as served, and time). Texas cuts of
national files are also recorded in `data/manifests/slices.jsonl` (rows, SHA-256 of the cut file, and the rule
used). `src/check_downloads.py` re-reads every file and compares it with these records
(`data/manifests/download_check.json`).

## Storage

This repository holds the code, plan, rules, manifests and the tables the analysis runs on. The downloaded data
themselves are not in it. Every downloaded file is listed with its source, date and SHA-256 hash in `data/manifests/`,
and can be downloaded again from the public sources with the scripts in `src/`. The TCEQ report pages as downloaded
are archived with the paper on Zenodo. Files recorded as stored gzipped carry `.gz` at the end of the name; gunzip
them to obtain the bytes that the manifest hash refers to.

National files that already have a Texas cut were not copied. Their hashes are kept so that a fresh download can be
checked. These are the ECHO exporter, ICIS-Air and combined emissions zips, the NRC decade workbooks, two
national EPA facility registry layers, a national electricity zip, and Census County Business Patterns.

## Roles

The Role column in the tables below uses these codes. None of these sources changes the frozen plan (see
Deviation D1).

| Code | Role |
|---|---|
| V | Checks that reported events are real |
| O | Other ways to define a serious accident |
| C | Possible controls |
| L | Better plant linking |
| D | Description |

## First round (before the plan was frozen)

| Source | Years | Role | Terms |
|---|---|---|---|
| TCEQ Air Emission Event Report Database, every incident page and export | 2002 to Oct 2026 | exposure | Texas public records |
| EPA RMP accident histories (Data Liberation Project mirror; Texas cut of raw tables including change histories) | 1994 to 2025 | outcome | CC BY-SA 4.0 |
| EPA Facility Registry Service, Texas | current | L | public domain |
| EPA ECHO exporter and ICIS-Air (Texas cuts) | current | C | public domain |
| EPA combined emissions (NEI, TRI, GHGRP) | various | C | public domain |
| NOAA Storm Events | 2003 to 2026 | C | public domain |
| National Response Center incident reports (Texas cut) | 1990 to 2026 | O (H4) | public domain |
| TCEQ open data: complaints, notices of violation, citations, notices of enforcement | complaints 2002 to 2026; notices of enforcement from 2010; notices of violation and citations mostly 2021 on | C | Texas open data |

## Second round (Deviation D1)

| Source | Years | Role | Terms and notes |
|---|---|---|---|
| EPA AQS hourly monitor data, Texas cut: SO2, ozone, NO2, CO, PM, wind, temperature, pressure, humidity, hourly toxics (HAPS), speciated VOCs, NOx/NOy, plus daily files and annual summaries | 1980 to 2026 | V, C | public domain; a lead file has no Texas rows |
| TCEQ continuous monitor monthly pages for hydrogen sulfide sites (21 sites) | 1997 to 2026 | V | pages for recent months are marked "not official until certified" |
| Iowa Environmental Mesonet, hourly airport weather, all Texas stations | to Oct 2026 | C | free, citation requested |
| NOAA GHCN-Daily, Texas stations | to 2026 | C | public domain |
| NOAA HURDAT2 hurricane tracks | 1851 to 2025 | C | public domain |
| NOAA NLDN lightning strike counts, 0.1 degree cells, Texas box | 1987 to 2026 | C | the 1986 file on NOAA's server holds a directory listing, not data |
| OpenFEMA disaster declarations | all | C | public |
| EIA refinery runs, utilization, prices; refinery capacity by refinery; EIA-860, EIA-923; grid disturbance tables | 1985 to 2026 | C, L | public domain |
| Federal Reserve Board G.17 industrial production and capacity files (all series, including chemicals, refining, oil and gas extraction) | 1919 to 2026 | C | public; taken from the Board's own site because FRED refused requests from the cloud server used for processing at download time (FRED pages loaded normally on 2026-10-06) |
| EPA CAMPD hourly and daily power-plant emissions, Texas | 1997 to 2025 | C | public domain; 1995, 1996 and 2026 files not offered |
| HIFLD Next mirror layers (refineries, gas processing, power plants, RMP and TRI facilities and others) | current | L | mirror of federal data; the original HIFLD portal was shut down in 2025 |
| OpenStreetMap industrial areas, Texas | current | L | ODbL |
| NASA FIRMS hot-spot detections, Texas box (MODIS, VIIRS S-NPP, NOAA-20) with the static-source flag | 2000 to 2024 | V | NASA open data; 2025 final files not yet released |
| EOG annual flare-site lists and World Bank flare volume file | 2012 to 2025 | V, D | credit requested; EOG nightly data require a signed license (applied for 2026-10-03, pending) |
| Sentinel-5P TROPOMI SO2 and NO2, Texas window (reprocessed product where available, operational otherwise) | 2018 to 2026 | D | Copernicus open licence |
| TCEQ Point Source Emissions Inventory, TCEQ Central Registry, spills, agreed orders, judgments, SEPs, compliance history | various | V, C, L, O | Texas open data |
| TCEQ rules history (30 TAC 101), Texas statutes, EPA RMP rule texts (Federal Register, eCFR) | 1996 to 2026 | D | public |
| EPA ECHO case and enforcement files; legacy AFS | | C | public domain |
| EPA refinery fenceline benzene reports (WebFIRE), all report types | 2018 to 2026 (sampling periods; one terminal from late 2016; reports filed from 2019) | V, C | public domain |
| OSHA severe injury reports; OSHA inspections, violations, accidents (Texas cuts) | 1970s to 2026 | O, C | public domain |
| Chemical Safety Board investigations list and release reports | 1998 to 2026 | O, V | public domain |
| GDELT article links, strict use (rules in `rules/gdelt_url_rules.json`): 731.8 million article rows scanned, 996,870 distinct rule hits, 85,457 with a Texas place word or Texas news site (unchecked candidates) | 2013 to 2026 | V, O | GDELT terms; GDELT's automated tags are not used; 128 files missing on GDELT's server (see the plan, D1 addendum) |
| City of Houston 311 service request files | 2011 to 2026 | V, D | open data |
| Census County Business Patterns; BLS QCEW (Texas cut) | 1986 to 2025 | D | public |
| Outside tallies of Texas emission events (two watchdog reports) | 2011 to 2022 | V (completeness) | published reports |

## Not yet obtained (rechecked 2026-10-06)

| Source | Status |
|---|---|
| Texas Tier II chemical inventories | TCEQ's own page states that they are confidential under Texas Government Code chapter 418 and are released only to filers, local emergency planners and fire departments. |
| PHMSA pipeline incident files | The PHMSA website returned HTTP 403 to downloads from the cloud server used for processing. The files are public and can be downloaded with a web browser. |
| Internet Archive (Wayback Machine) page copies | The Internet Archive closes connections from the cloud server. The pages load normally from an ordinary internet connection. |
| NFIRS and BLS pages | Earlier download attempts failed. Both sites loaded normally on 2026-10-06, so the downloads can be retried if needed. |
| GOES satellite lightning | About 5 TB, with no way to extract Texas alone; replaced by the NLDN counts. |
| EPA refinery fenceline dashboard export | Requires a live browser session; the WebFIRE reports hold the same quarterly values. |
