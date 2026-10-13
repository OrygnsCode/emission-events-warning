# Cause codebook for hand checks

This is what a person uses to code the 400-event validation sample. The coder
sees only the event's cause text, never what the rules said. Agreement between
the coder and the rules is reported in the paper (percent agreement and Cohen's
kappa).

## How to code one event

1. Read the cause text.
2. Tick **every** category the text clearly describes (there can be several).
3. Pick **one primary cause** using the order below: go down the list and stop
   at the first category you ticked. Outside triggers come first because they
   start the chain. For example, "lightning knocked out power and the
   compressor tripped" is primary **weather** (with power and upset also ticked).
4. If the text gives no cause at all (for example only "SO2 exceeded 500 lb" or
   only "did not reach a reportable quantity"), the primary cause is **unknown**.
5. Separately, tick the report-status boxes if they apply.

## Categories, in priority order

| Order | Category | Tick it when the text says... | Examples |
|---|---|---|---|
| 1 | Weather | weather or a natural event played a part | storm, lightning, freeze, ice, heavy rain, high wind, hurricane, flood, extreme cold |
| 2 | Third party | another company or outside facility caused it | the gas buyer's plant went down; downstream pipeline could not take our gas; third-party steam supplier tripped; "due to [another company] having compressor problems" |
| 3 | Power or electrical | loss or disturbance of electric power, or an electrical fault | power outage, power dip, lost utility power, breaker, transformer, electrical short |
| 4 | Operator or procedure | a person's action or a procedure caused it | operator error, valve left open, inadvertently opened or added, procedure not followed, wrong valve |
| 5 | Instrument or control | a measuring, control or safety-logic device failed or gave a false signal | failed transmitter, false high level, PLC or DCS fault, analyzer, thermocouple, controller malfunction |
| 6 | Equipment | a physical part failed, leaked or wore out | leak, rupture, crack, hole, seal or gasket failure, bad compressor valves, broken part, corrosion, plugging |
| 7 | Process upset | the process went out of normal range or a unit tripped, with no deeper cause above | high pressure, unit tripped, compressor went down, foaming, hydrates, carryover, loss of cooling |
| 8 | Maintenance or startup | planned work, repairs, startup or shutdown activity | maintenance, repair work, startup, restart, pigging, tie-in, cleaning |
| 9 | Unknown | none of the above can be told from the text | "under investigation" with nothing else; text missing |

Notes:

- **Tick what the text says, not what you guess.** "Compressor went down"
  alone is a process upset, even though a broken part may be the real reason.
- **Third party** means a different company or facility. The plant's own
  steam unit or own pipeline is not a third party.
- **A failed instrument that then leaks** (for example a leaking analyzer)
  counts as both instrument and equipment. The order makes it primary
  instrument.

## Report status (separate from cause)

- **Duplicate:** the text says it duplicates another report.
- **Not reportable:** the text says the event turned out below the reportable
  amount.
- **Filed in error:** the text says the report was retracted, withdrawn or filed
  by mistake.
