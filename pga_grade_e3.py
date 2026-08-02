"""Grade E3 flags — birdies, matchups, top-N and make-the-cut.

WHY THIS EXISTS. `pga_grade.py` grades E1's matchbets and nothing else. Its very first filter is

    rs, os_ = sn.get(norm(runner)), sn.get(norm(opp))
    if rs is None or os_ is None: continue

and `pga_e3` writes `opp` as an empty string for every flag it logs. So `sn.get(norm(""))` is
always None and EVERY e3 row is skipped — including e3's own matchups. The paper ledger would have
filled up and graded nothing, and `pga_evidence.md` would have sat on INSUFFICIENT DATA forever
while looking like it was working. This module grades what e3 actually writes.

CONSERVATIVE BY CONSTRUCTION. A paper record must never award itself a win on a judgement call, so
anything ambiguous is left UNGRADED (returns None) rather than guessed. An ungraded bet costs us
sample size; a wrongly graded one corrupts the record.

SETTLEMENT RULES, matched to how FanDuel actually pays:

  birdies O/U   lines are always X.5, so no push is possible. Graded only when that player has
                all 18 holes of that round on the board. A birdie-or-better is a hole whose
                scoreType is negative — ESPN carries NO `par` field on a hole, so counting
                `value < par` silently returns zero for everyone (verified).
  matchups      lower total wins; a tie is a PUSH (two-way golf matchups void on a tie). Round-N
                graded when both players have that round; 72-hole when both have four rounds.
  top-N         "(Incl. Ties)" pays in full whenever finishing position <= N. The plain market
                applies DEAD-HEAT reduction: if k players tie across the cutoff for s remaining
                places, the stake returns s/k. Both are graded only once the event is final.
  make-the-cut  a player who has a third round made the cut. Graded only once the field's cut is
                actually determined (some players have 3+ rounds and some have exactly 2).

POSITIONS ARE COMPUTED, NOT READ. ESPN exposes an `order` field, but it is live-updating and
means different things mid-event. Finishing position here is derived from 72-hole totals, with
missed-cut players placed below every player who completed — the same construction the majors
backtest used.
"""
import datetime as dt
import re
import sqlite3
from pathlib import Path

import pga_field as F
import pga_e1 as E1

HERE = Path(__file__).resolve().parent
PAPER = HERE / "pga_paper.sqlite"


def _norm(s):
    return E1.norm(s or "")


def birdie_counts(rnd):
    """{normalised player: birdies-or-better} for a COMPLETED round `rnd` (1-based)."""
    out = {}
    for c in F.competitors():
        nm = ((c.get("athlete") or {}).get("displayName") or "").strip()
        ls = c.get("linescores") or []
        if not nm or len(ls) < rnd:
            continue
        holes = ls[rnd - 1].get("linescores") or []
        if len(holes) < 18:
            continue                                   # round not finished — do not grade
        out[_norm(nm)] = sum(
            1 for h in holes
            if str(((h.get("scoreType") or {}).get("displayValue") or "")).startswith("-"))
    return out


def positions(scores):
    """{normalised player: (position, n_tied_at_that_position)} from 72-hole totals.

    Missed-cut players are ranked below everyone who completed, which is how they finish.
    """
    full = {p: sum(v[:4]) for p, v in scores.items() if len(v) >= 4}
    if not full:
        return {}
    out = {}
    tot = sorted(full.values())
    for p, t in full.items():
        better = sum(1 for x in tot if x < t)
        out[p] = (better + 1, sum(1 for x in tot if x == t))
    base = len(full)
    for p, v in scores.items():
        if p not in out:
            out[p] = (base + 1, 1)                     # missed cut / withdrew
    return out



VOID_FIELD_MIN = 20      # players who must already have a score for round k before "no score for
                         # THIS player" can mean withdrawal rather than "the round is still running"


def void_dnps(con, scores):
    """Settle round-scoped flags whose player never teed off. Returns how many were voided.

    A withdrawal produces the same observation as an unfinished round — no score — so this only
    fires once the FIELD has demonstrably completed that round. Without that guard it would void
    live bets mid-round, which is far worse than a stale row on the board.
    """
    import re as _re
    done = {}
    for _p, _rs in (scores or {}).items():
        for k in range(1, 5):
            if len(_rs) >= k:
                done[k] = done.get(k, 0) + 1
    n = 0
    for key, market, runner, stream in con.execute(
            "SELECT key, market, runner, stream FROM flags WHERE result IS NULL").fetchall():
        rm = _re.search(r"Round\s+(\d)", market or "")
        if not rm:
            continue                                  # 72-hole markets settle at event end
        k = int(rm.group(1))
        if done.get(k, 0) < VOID_FIELD_MIN:
            continue                                  # round not finished for the field — leave it
        m = _re.search(r"^(.*?)\s+(over|under)\s+[\d.]+$", (runner or "").strip(), _re.I)
        who = _norm(m.group(1)) if m else None
        if who is None:
            continue
        rs = scores.get(who)
        if rs is not None and len(rs) >= k:
            continue                                  # they DID play it; the normal grader owns it
        con.execute("UPDATE flags SET result='V', pnl=0.0, graded_at=? WHERE key=?",
                    (__import__("datetime").datetime.utcnow().replace(microsecond=0).isoformat(), key))
        n += 1
    return n

def grade_one(stream, market, runner, odds, ctx):
    """(result, pnl) or None when the bet is not yet decidable. Never guesses."""
    scores, pos, cut_known, final = ctx["scores"], ctx["pos"], ctx["cut_known"], ctx["final"]

    if stream.startswith("E3-birdies"):
        m = re.search(r"^(.*?)\s+(over|under)\s+([\d.]+)$", runner.strip(), re.I)
        rm = re.search(r"Round\s+(\d)", market or "")
        if not m or not rm:
            return None
        who, side, line = _norm(m.group(1)), m.group(2).lower(), float(m.group(3))
        # NB: dict.setdefault evaluates its default eagerly, so the obvious one-liner refetched
        # the whole scoreboard on every single birdie row. Cache explicitly.
        _r = int(rm.group(1))
        _cache = ctx.setdefault("bird", {})
        if _r not in _cache:
            _cache[_r] = birdie_counts(_r)
        counts = _cache[_r]
        if who not in counts:
            return None
        n = counts[who]
        won = (n > line) if side == "over" else (n < line)
        return ("W", odds - 1.0) if won else ("L", -1.0)

    if stream.startswith("E3-rscore"):
        # ROUND-SCOPED: settles as soon as that round's score exists, exactly like birdies.
        # There was no branch here at all, so every round-score flag fell through to None and
        # never settled — 11 of them on the Rocket Classic alone.
        m = re.search(r"^(.*?)\s+(over|under)\s+([\d.]+)$", runner.strip(), re.I)
        rm = re.search(r"Round\s+(\d)", market or "")
        if not m or not rm:
            return None
        who, side, line = _norm(m.group(1)), m.group(2).lower(), float(m.group(3))
        k = int(rm.group(1))
        rs = scores.get(who)
        if rs is None or len(rs) < k:
            return None                                # that round not in the book yet
        sc = rs[k - 1]
        if sc == line:
            return ("P", 0.0)                          # lines are half-strokes, but never assume
        won = (sc > line) if side == "over" else (sc < line)
        return ("W", odds - 1.0) if won else ("L", -1.0)

    if stream.startswith("E3-match"):
        # Strip the market boilerplate BEFORE splitting. Using `.split(")")[-1]` only worked
        # when the market carried a parenthesised round ("18 Hole Matchbet (Round 1) A vs B");
        # for "72 Hole Matchbet A vs B" it left the prefix glued to player A, the opponent never
        # resolved, and every 72-hole matchup silently returned None instead of grading.
        _m = re.sub(r"^.*?Matchbet\s*(?:\([^)]*\))?\s*", "", market or "").strip()
        mm = re.search(r"^(.+?)\s+vs\.?\s+(.+)$", _m)
        if not mm:
            return None
        a, b = _norm(mm.group(1)), _norm(mm.group(2))
        me = _norm(runner)
        opp = b if me == a else (a if me == b else None)
        if opp is None:
            return None
        rs, os_ = scores.get(me), scores.get(opp)
        if rs is None or os_ is None:
            return None
        rm = re.search(r"Round\s+(\d)", market or "")
        if rm:
            k = int(rm.group(1))
            if len(rs) < k or len(os_) < k:
                return None
            x, y = rs[k - 1], os_[k - 1]
        else:
            if len(rs) < 4 or len(os_) < 4:
                return None
            x, y = sum(rs[:4]), sum(os_[:4])
        if x == y:
            return ("P", 0.0)                          # two-way golf matchups push on a tie
        return ("W", odds - 1.0) if x < y else ("L", -1.0)

    if stream.startswith("E3-top"):
        if not final:
            return None
        n = re.search(r"top(\d+)", stream)
        if not n:
            return None
        N = int(n.group(1))
        pr = pos.get(_norm(runner))
        if pr is None:
            return None
        p, tied = pr
        incl = "TIE" in str(market).upper()
        if p > N:
            return ("L", -1.0)
        if incl or tied == 1 or p + tied - 1 <= N:
            return ("W", odds - 1.0)                   # clear of the boundary, or ties pay full
        share = max(0, N - p + 1) / float(tied)        # DEAD HEAT across the cutoff
        return ("W", odds * share - 1.0)

    if stream.startswith("E3-cut"):
        if not cut_known:
            return None
        m = re.search(r"^(.*?)\s+(make|miss)$", runner.strip(), re.I)
        if not m:
            return None
        who, side = _norm(m.group(1)), m.group(2).lower()
        rs = scores.get(who)
        if rs is None:
            return None
        made = len(rs) >= 3
        if not made and not cut_known:
            return None
        won = made if side == "make" else (not made)
        return ("W", odds - 1.0) if won else ("L", -1.0)

    return None


def main():
    ev = F.event()
    state, _desc = F.status(ev)
    scores = {_norm(k): v for k, v in F.round_scores(ev).items()}
    ctx = {
        "scores": scores,
        "pos": positions(scores),
        # the cut is only KNOWN once some players have a third round and others stopped at two
        "cut_known": any(len(v) >= 3 for v in scores.values())
                     and any(len(v) == 2 for v in scores.values()),
        "final": state == "post" and sum(1 for v in scores.values() if len(v) >= 4) >= 20,
    }
    con = sqlite3.connect(PAPER)
    con.execute(E1.DDL)
    rows = con.execute("SELECT key, stream, market, runner, odds FROM flags "
                       "WHERE (result IS NULL OR result='') AND stream LIKE 'E3-%'").fetchall()
    n = 0
    for key, stream, market, runner, odds in rows:
        try:
            g = grade_one(stream or "", market or "", runner or "", float(odds or 0), ctx)
        except Exception:                                          # noqa: BLE001
            g = None
        if not g:
            continue
        res, pnl = g
        con.execute("UPDATE flags SET result=?, pnl=?, graded_at=? WHERE key=?",
                    (res, round(pnl, 4),
                     dt.datetime.utcnow().replace(microsecond=0).isoformat(), key))
        n += 1
    # settle withdrawals so round-scoped flags cannot sit on the board forever
    try:
        _nv = void_dnps(con, scores)
        if _nv:
            print('pga_grade_e3: voided %d flag(s) whose player never teed off' % _nv)
    except Exception as _ve:
        print('void sweep skipped: %s' % str(_ve)[:70])
    con.commit()
    tot = con.execute("SELECT COUNT(*) FROM flags WHERE stream LIKE 'E3-%'").fetchone()[0]
    done = con.execute("SELECT COUNT(*) FROM flags WHERE stream LIKE 'E3-%' "
                       "AND result IS NOT NULL AND result!=''").fetchone()[0]
    print(f"pga_grade_e3: +{n} newly graded | {done}/{tot} E3 rows settled "
          f"| event state={state} final={ctx['final']} cut_known={ctx['cut_known']}")
    for st, w, l, p, u in con.execute(
            "SELECT stream, SUM(result='W'), SUM(result='L'), SUM(result='P'), "
            "COALESCE(SUM(pnl),0) FROM flags WHERE stream LIKE 'E3-%' AND result IS NOT NULL "
            "AND result!='' GROUP BY stream"):
        print(f"   {st:<24} {w}-{l}-{p}  {u:+.2f}u")
    con.close()


if __name__ == "__main__":
    main()
