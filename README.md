# Do Small Releases Warn of Serious Chemical Accidents?

Code and data for the paper [*Do Small Releases Warn of Serious Chemical Accidents? Testing Emission Events as a Leading Indicator at Texas Plants*](https://doi.org/10.5281/zenodo.TODO).

Texas plants have to tell the state within 24 hours whenever they release more air pollution than their permits
allow. The state publishes every one of those emission event reports, more than 100,000 since 2003. Plants that hold
large amounts of dangerous chemicals also report their serious accidents to the EPA under the Risk Management
Program (RMP). Put the two together and you can test something process safety has long taken for granted: that the
small releases pile up before the big accident.

We wrote the test down and registered it on OSF (https://osf.io/nf426) before comparing a single accident with the
events. Across 545 serious accidents at 216 Texas plants from 2003 to 2021, a plant's emission events in the three
months before an accident were no more frequent than at its other times in the same year. Doubling a plant's recent
events changes its accident risk by a factor of 1.05, with a 95% range of 0.85 to 1.29. Along the way we found that
accidents report themselves: on accident days plants filed about 22 times their usual number of reports, and until
those are taken out, events look as if they protect plants from accidents.

This repo has what you need to check all of that: the code behind every number in the paper, the tables it ran on,
the hand-review answers, the frozen rules, the registered plan with its dated list of changes, and every result
file.

## What is in here

| Folder | What it holds |
|---|---|
| `src/` | every script, from downloading the public data to the figures in the paper |
| `rules/` | the frozen rules for coding causes, filtering news links and linking plants (hashes in `docs/osf_registration_hashes.txt` and `data/frozen/link_table_freeze.json`) |
| `docs/` | the analysis plan as registered, with deviations D1 to D16 added below it as they happened; the results reports; the cause codebook; notes on every data source |
| `data/derived/`, `data/frozen/`, `data/master/` | the tables the analysis runs on |
| `data/slices/`, `data/external/` | the few small public downloads the analysis reads directly |
| `data/manual/` | the author's hand-review answers: plant links, National Response Center and OSHA links, the 400 hand-coded causes, and the news check |
| `data/louisiana/` | the dates used for the Louisiana planned-work check |
| `data/manifests/` | every result file, and the SHA-256 hash of every download and table |
| `figures/` | the figures in the paper |

## Reproduce

```
pip install -r requirements.txt
python src/run_all.py
```

That reruns every step from the tables, in the order the work was done, and writes each result over its stored copy
in `data/manifests/`. Afterwards `git diff data/manifests` shows anything that came out different. Expect the recorded
run times to change, and a few results to move in about the tenth significant figure, from the order in which the
computer adds numbers up; nothing that is reported changes. The whole run takes about 10 hours on a four-core
laptop, most of it in the power simulations, the multiverse and the 10,000-shuffle test of the main result. The
multiverse can be stopped and continued with `python src/phase5_multiverse.py --resume`.

The power checks were run before the plan's deviation D8 merged one more pair of duplicate accident records, so
`run_all.py` runs them on the accident table as it was then (`--before-d8` in `src/power_h1.py`); that reproduces the
stored results exactly. `power_h1.json` is the file registered on OSF; a rerun adds a `links` field that the script
gained later, with the same numbers.

`python src/run_all.py --list` shows the steps, and `--only` or `--skip` runs part of them. For the main test alone:

```
python src/run_all.py --only h1
```

The results are written up in `docs/phase4_results.md` (the registered main test) and `docs/phase5_results.md`
(everything else), and every change to the plan is listed with its reason in `docs/analysis_plan.md`.

## Rebuild the tables from the public sources

Everything above starts from the tables in `data/`. Those tables are built from public downloads by the scripts in
`src/`, in this order. It takes a few days, most of it the crawl of TCEQ's site at a polite pace.

1. **TCEQ event reports.** `get_incident_lists.py` (with `--by start`, `--by end` and `--by region`),
   `build_master.py`, `check_lists.py`, `check_totals.py`, then `crawl.py --endpoint details` and
   `crawl.py --endpoint export`.
2. **Everything else.** `fetch_external.py`, `fetch_more.py`, `fetch_tceq_open_data.py`, `fetch_tceq_monitors.py`,
   `fetch_tceq_gc.py`, `fetch_tceq_agc.py`, `fetch_fenceline.py`, `fetch_gdelt.py` and `finalize_gdelt.py`,
   `fetch_tropomi.py`, then `record_derived.py` and `check_downloads.py`, which compares every file with its
   recorded hash. The RMP database comes from the Data Liberation Project at the commit recorded in
   `data/manifests/rmp_source.json`; point `RMP_SPREADSHEETS` at its spreadsheet folder.
3. **Texas cuts.** `make_slices.py rmp frs echo icis poll noaa nrc`, `slice_rmp_raw.py`, `slice_census.py`,
   `storm_zones.py`.
4. **Tables.** `quality_pass.py`, `quality_summary.py`, `verify.py`, `verify_export.py`, `classify_causes.py all`,
   `build_details_table.py`, `build_site_tables.py`, `parse_location_text.py`, `census_event_text.py`,
   `build_plants.py`, `link_plants_v2.py`, `accident_doubles.py`, `build_tables.py`, `build_tables.py v2`,
   `r18_dates.py`, `h1_exclusions.py`, `plant_attributes.py`, `outcome_link_candidates.py`, `csb_candidates.py`,
   `census_monitors.py`, `census_psei.py`, `v1_hourly.py`, `parse_fenceline.py`. A few of these write a short
   summary next to their tables in `data/derived/`, and `data/manifests/` keeps a copy of each.

The steps that needed a person (the plant-link review, the National Response Center and OSHA link review, the cause
coding and the news check) were done on offline pages made by `make_link_review_page.py`,
`make_outcome_review_page.py`, `make_coding_page.py`, `make_news_review_page.py` and `make_news_settle_page.py`. The
answers are in `data/manual/`, and the scripts above read them from there.

The TCEQ pages as we downloaded them in October 2026 are archived with the paper on Zenodo
(`tceq_pages_2026-10.tar`, about 390 MB). Unpack it in this folder to get `data/raw/`, run `python src/rebuild_state.py`, and the crawler will only
fetch what is missing.

## What is not here, and why

- **Most of the downloads.** They are public and add up to about 15 GB, so only the few small files the analysis
  reads directly are here, in `data/slices/` and `data/external/`. Every download is listed in `data/manifests/` with
  its address, date and SHA-256 hash, and the scripts above download it again. The TCEQ pages, which are the part most
  likely to change or disappear, are on Zenodo.
- **What two checks need.** The air monitor check (V1) needs the hourly monitor and airport wind files, and the
  complaints check (V4) needs TCEQ's complaint records and Houston's 311 requests, about 7 GB together.
  `run_all.py` skips those two checks, saying so, until the files are downloaded. The weather controls in robustness
  check R25 read only a small table of station values (`data/derived/r25_weather_*.parquet`), which
  `phase5_robust2.py` writes from the downloads the first time it runs.
- **Personal contact details.** Some public records carry the names, phone numbers and email addresses of people,
  such as a plant's emergency contact. The copies here leave out those contact fields. EPA's RMP facility table
  (`data/slices/rmp_raw/tblS1Facilities.csv.gz`) keeps only the columns the analysis reads, with each operator name
  replaced by a code (the same name always gets the same code, which is all check R28 uses). The National Response
  Center and OSHA candidate file (`data/derived/outcome_link_items.json`) keeps the record keys, dates and candidate
  site IDs, without names or addresses. In the TCEQ report text (`data/derived/details_table.parquet`), email
  addresses and phone numbers read `[email]` and `[phone]`, in 288 of the 103,614 reports; any name written into
  that text stays as TCEQ published it. The EPA registry file (`data/slices/frs_program_tx_relevant.csv.gz`) keeps
  the three columns the analysis reads. These files therefore no longer match the hashes recorded when they were
  made; every result comes out the same.
- **The review pages.** The offline pages used for the hand reviews hold copies of the records they show. The
  scripts that make them are here, and so are the answers.
- **The paper's LaTeX source.** The paper itself is on Zenodo.
- **The working history.** The study was done in a private working repository, and this one starts from a clean
  copy of it. A few records name a commit of that working repository (the OSF registration,
  `data/frozen/link_table_freeze.json`); the SHA-256 hashes recorded next to them are what to check.

No plant or company is named or ranked in the paper or in the results. The tables identify sites by the public ID
numbers TCEQ and EPA give them (TCEQ's regulated entity number, EPA's RMP facility ID), so anyone can check how the
two databases were linked. Copies of public records keep the site and company names those records carry, and a few
input files hold names because names are what they match on: the refinery fenceline crosswalk, the news search
words, and the sites typed in during the news check.

## Citing this

> Okwor, D. (2026). *Do Small Releases Warn of Serious Chemical Accidents? Testing Emission Events as a Leading Indicator at Texas Plants.* Zenodo. https://doi.org/10.5281/zenodo.TODO

Registered plan: https://osf.io/nf426

## License

Code is MIT (see [LICENSE](LICENSE)). The paper is under CC BY 4.0. The tables, hand-review answers and results in
`data/` are under CC BY-SA 4.0, because many of them are built from the RMP data as released by the Data Liberation
Project under that license.
