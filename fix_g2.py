"""G2 — the gate that guards real money — was grading prices against the WRONG TOURNAMENT.

Found while answering "can we backtest instead of waiting". Two independent defects:

  WRONG EDITION  The results lookup was
                     WHERE event LIKE '%' || toks[0] || '%' ORDER BY date DESC LIMIT 1
                 For "PGA Rocket Classic 2026" that is toks[0]='Rocket', which matches the
                 2025 Rocket Classic — the most recent PLAYED edition. So the gate graded
                 2026 collected prices against 2025 outcomes. Every one of the n=4 "gradeable
                 closes" was a 2026 price scored against a different year's tournament. The
                 real n is 0. Same class of bug as the course-name token contamination.

  NOT A CLOSE    The price was MAX(collected_at) per runner, i.e. the most recent price ever
                 seen. During a live tournament that is an IN-PLAY price, not a close, and
                 grading a live price against the result it already reflects would flatter the
                 model enormously. A close must be the last price before the relevant round
                 begins — the event start for a 72-hole matchup, and start+(N-1) days for
                 '18 Hole Matchbet (Round N)'.

Both fixed here, and the gate now reports how many markets it DROPPED for lack of a
same-edition result, so an empty gate can never again read as a passing one.
"""
import ast
import io

p = "pga_ruler.py"
s = io.open(p, encoding="utf-8").read()

start = s.index("def g2_gate(verbose=True):")
end = s.index('if __name__ == "__main__":', start)
old = s[start:end]

NEW = '''def _same_edition_event(conr, odds_event, any_ts):
    """Resolve an odds-book event name to the results event for the SAME EDITION.

    The old lookup took the most recent event matching the FIRST token, so "PGA Rocket Classic
    2026" resolved to the 2025 Rocket Classic and the gate scored 2026 prices against 2025
    results. Requires every distinctive token to match AND the year to agree; with no year in
    the name, falls back to the edition starting nearest after the price was collected.
    """
    toks = [t.lower() for t in str(odds_event or "").replace("PGA", "").split()
            if len(t) > 3 and not t.isdigit()]
    if not toks:
        return None, None
    yr = None
    m = re.search(r"\\b(20\\d\\d)\\b", str(odds_event or ""))
    if m:
        yr = m.group(1)
    cands = []
    for eid, d0, evn in conr.execute(
            "SELECT event_id, MIN(date), event FROM rounds GROUP BY event_id").fetchall():
        el = str(evn or "").lower()
        if not all(t in el for t in toks):
            continue
        if yr and not str(d0 or "").startswith(yr):
            continue
        if not yr and any_ts and str(d0 or "") < str(any_ts)[:10]:
            continue                      # an edition that finished before we saw the price
        cands.append((eid, d0))
    if not cands:
        return None, None
    cands.sort(key=lambda z: z[1])
    return cands[0]


def g2_gate(verbose=True):
    """GATE G2 on REAL collected FanDuel matchbet CLOSES: ruler log-loss vs the devigged
    close, on events whose results are in. Ratings are fit AS-OF each event's start date, so
    no result being judged is inside the training set.

    A "close" is the last price collected BEFORE the relevant round begins — the event start
    for a 72-hole matchup, start+(N-1) days for a round-N matchup. It used to be
    MAX(collected_at), which during a live event is an IN-PLAY price that already knows the
    result.
    """
    con = sqlite3.connect(LINES)
    raw = con.execute(
        "SELECT event, market, runner, odds, collected_at FROM golf_lines "
        "WHERE market LIKE '%Matchbet%' AND odds > 1.0").fetchall()
    con.close()
    by_m = defaultdict(list)
    for evn, mkt, run, od, ts in raw:
        by_m[(str(evn).strip(), mkt)].append((run, od, ts))
    conr = sqlite3.connect(DB)
    ll_book, ll_ruler, n_used = [], [], 0
    fits = {}
    n_fam = defaultdict(int)
    dropped = defaultdict(int)
    for (evn, mkt), quotes in by_m.items():
        rm = re.search(r"\\(Round (\\d)\\)", mkt)
        rn = int(rm.group(1)) if rm else None
        eid, edate = _same_edition_event(conr, evn, min(q[2] for q in quotes))
        if not eid:
            dropped["no same-edition result yet"] += 1
            continue
        # the close: last price strictly before the relevant round tees off
        try:
            cutoff = dt.date.fromisoformat(str(edate)[:10])
            if rn:
                cutoff = cutoff + dt.timedelta(days=rn - 1)
        except ValueError:
            dropped["bad event date"] += 1
            continue
        best = {}
        for run, od, ts in quotes:
            if str(ts)[:10] > cutoff.isoformat():
                continue                 # in-play or post-round: not a close
            cur = best.get(run)
            if cur is None or str(ts) > str(cur[1]):
                best[run] = (od, ts)
        if len(best) != 2:
            dropped["no two-sided pre-round close"] += 1
            continue
        (a, (oa, _ta)), (b, (ob, _tb)) = list(best.items())
        if rn:
            sa = conr.execute("SELECT score FROM rounds WHERE event_id=? AND player=? AND "
                              "rnd=?", (eid, a, rn)).fetchone()
            sb = conr.execute("SELECT score FROM rounds WHERE event_id=? AND player=? AND "
                              "rnd=?", (eid, b, rn)).fetchone()
            if not sa or not sb or not sa[0] or not sb[0] or sa[0] == sb[0]:
                dropped["round not both posted / tie"] += 1
                continue
            ya, yb = sa[0], sb[0]
        else:
            sa = conr.execute("SELECT SUM(score), COUNT(*) FROM rounds WHERE event_id=? AND "
                              "player=?", (eid, a)).fetchone()
            sb = conr.execute("SELECT SUM(score), COUNT(*) FROM rounds WHERE event_id=? AND "
                              "player=?", (eid, b)).fetchone()
            if (not sa[0] or not sb[0] or sa[1] != 4 or sb[1] != 4 or sa[0] == sb[0]):
                dropped["72h not both complete / tie"] += 1
                continue
            ya, yb = sa[0], sb[0]
        y = 1.0 if ya < yb else 0.0
        p_book = (1 / oa) / (1 / oa + 1 / ob)             # devigged close
        if edate not in fits:
            R, _ = fit(asof=edate)
            fits[edate] = {norm(k): v for k, v in R.items()}
        p_rul = matchup_prob(fits[edate], a, b, rounds=(1 if rn else 4))
        if p_rul is None:
            dropped["player unrated as-of"] += 1
            continue
        p_rul = min(max(p_rul, 1e-6), 1 - 1e-6)
        ll_book.append(-(y * math.log(p_book) + (1 - y) * math.log(1 - p_book)))
        ll_ruler.append(-(y * math.log(p_rul) + (1 - y) * math.log(1 - p_rul)))
        n_used += 1
        n_fam["R%d" % rn if rn else "72H"] += 1
    conr.close()
    if verbose:
        fam = " ".join("%s=%d" % kv for kv in sorted(n_fam.items())) or "none"
        print(f"G2: {n_used} gradeable closes [{fam}] from {len(by_m)} collected matchup "
              f"markets")
        for k, v in sorted(dropped.items(), key=lambda kv: -kv[1]):
            print(f"     dropped {v:3d}  {k}")
        if n_used < 15:
            print(f"G2: n={n_used} < 15 -> gate INCONCLUSIVE. This is a FORWARD test and "
                  f"cannot be backtested: it needs OUR OWN collected closes, and the "
                  f"collector only has history from the day it started.")
        else:
            lb, lr = st.mean(ll_book), st.mean(ll_ruler)
            gap = (lr - lb) * 100
            verdict = "PASS" if gap <= 2.0 else "FAIL"
            print(f"G2 on {n_used} real FD closes: book logloss {lb:.4f}, ruler {lr:.4f} "
                  f"(gap {gap:+.1f}pts) -> {verdict}")
            return verdict == "PASS", n_used
    return None, n_used


'''
assert "def _same_edition_event(" not in s, "already patched"
s = s[:start] + NEW + s[end:]
# dt is needed in the ruler
if "import datetime as dt" not in s:
    s = s.replace("import math\nimport re", "import datetime as dt\nimport math\nimport re", 1)
ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + g2_gate: same-edition results + a real pre-round close + drop accounting")
