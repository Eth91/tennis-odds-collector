# Why the shadow flags lose, and what to do about it (2026-10-27)

Development data, 2026-10-22..26. The sample is small, so every number here is a lead, not a finding.
Sources: `nba_news_latency.py` and the VM's `nba_clv.py`.

## The record
- **77 graded flags:** 38 wins, 39 losses, ROI −8.3% at the flagged odds.
- **By tier:**
  - wowy −18% (n 34)
  - wowy_v0 +6.6% (n 29)
  - priced −7.9% (n 13)
  - cold −100% (n 1)
- **Cells (nba_clv):**
  - absence 3–4 (a 3rd or 4th straight missed game) −38.5% (n 6 graded);
  - x24–28 (the absent player averaged 24–28 min) −54% (n 8);
  - the game-day wowy and priced cells were positive (n 6–12 each).

## How fast FanDuel moves on official news
After an official report newly lists a regular (≥ 20 min) Out or Doubtful:

| | FanDuel | DraftKings |
|---|---|---|
| first observation after the report | ~3 s (nba_watch fetch) | ~6 min |
| teammates' props moved by then | **0.7%** | 19% |
| moved before tip | 46% | 47% |
| lag when they move: median (p75) | **3 min** (16) | 15 min (49) |
| moved in the hour before the report | 18% | 20% |

## Diagnosis
1. **Most flags come long after the news.** 64 of 77 were logged 2+ hours after the news they cite. By
   then FanDuel has priced the absence, which it does within minutes. Betting a fairly priced line costs
   about the vig, and −7% is roughly that.
2. **The fast flags are too few to judge:** 7 within 5 minutes.
3. **Weak absences lose.** The two losing cells, absence 3–4 and x24–28, are the ones where the absence
   is old news or the absent player matters less. The market has already adjusted, or there is little to
   adjust.
4. **Not a stale-data problem.** The flags price at the lines fetched right after detection.

## What should win, if anything does
- **Act inside the window.** FanDuel's teammate lines are unchanged seconds after a report and move about
  3–16 minutes later.
  - Blind teammate overs at that stale price earned small CLV (+0.28 points, ROI +1.6%, 15 events).
  - The model should pick *which* teammates. That is S1 (`NBA_S1_PREREG.md`): proj-1.1.1 re-run with the
    new absence, signalling only where it beats FanDuel's stale price by ≥ 5 points.
  - S1 runs every minute on the VM from 2026-10-27, research only. Its bar: CLV lower bound > 0 at 300
    signals; ROI at 500.
- **Recommendation for the flag engine** (the owner's call, not changed here):
  - treat flags logged hours after their news as information only;
  - keep the card to fresh news, which is what S1 tests.
