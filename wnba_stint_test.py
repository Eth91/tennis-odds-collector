#!/usr/bin/env python3
"""Can ON/OFF-COURT minutes substitute for missing without-games?

THE IDEA (user, 2026-08-06). When a beneficiary has 0-2 career games without the injured
teammate, WOWY has no usable sample and the play is never flagged. But those two have shared
the floor and been apart WITHIN games. Use the apart-minutes as the sample. The book has the
same blind spot, so these lines should move slowly.

FILTERS (user's first cut): starters only, >=50 minutes apart, same position.

TWO THINGS TO KNOW GOING IN
  * The stint DB carries POINTS ONLY (onfloor: sec+pts; pairs: sec+pts_with). No reb/ast. The
    n=1 speed pilot found rebounds worked and points were a coin flip -- so this test can only
    address the weaker stat. A null here does NOT clear the idea for rebounds.
  * A broad version of this was in the model and was REMOVED 2026-08-06: its rate signal
    measured rho~0 on 30k+ observations. This is a narrower, filtered version of the same
    family, which is why it is worth a second look -- but the prior is negative.

Walk-forward throughout: stints and logs are read only from games BEFORE the slate.
"""
import sys, sqlite3, statistics as st, math
from collections import defaultdict

sys.path.insert(0, "/home/ubuntu")
_argv = list(sys.argv); sys.argv = ["x"]
import wnba_replay as R
import wnba_wowy as W
sys.argv = _argv

STINT = "/home/ubuntu/tennis-odds-collector/wnba_stints.sqlite"
MIN_APART_MIN = 50.0
STARTER_MIN = 25.0
MAX_NWO = 2                      # the population that is currently un-flaggable


def load_stints():
    c = sqlite3.connect(f"file:{STINT}?mode=ro", uri=True)
    ok = {e for (e,) in c.execute("SELECT event_id FROM games WHERE status='ok'")}
    on = defaultdict(list)       # player -> [(date, sec, pts)]
    for e, d, p, sec, pts in c.execute("SELECT event_id,game_date,player,sec,pts FROM onfloor"):
        if e in ok:
            on[p].append((d, sec or 0.0, pts or 0.0))
    pair = defaultdict(list)     # (player, mate) -> [(date, sec, pts_with)]
    for e, d, p, m, sec, pw in c.execute(
            "SELECT event_id,game_date,player,mate,sec,pts_with FROM pairs"):
        if e in ok:
            pair[(p, m)].append((d, sec or 0.0, pw or 0.0))
    c.close()
    return on, pair


def apart_rate(on, pair, player, mate, before):
    """Points-per-minute for `player` while `mate` was OFF the floor, from games before `before`.
    -> (pts_per_min, minutes_apart) or None."""
    tot_s = tot_p = 0.0
    for d, sec, pts in on.get(player, []):
        if d >= before:
            continue
        tot_s += sec; tot_p += pts
    wi_s = wi_p = 0.0
    for d, sec, pw in pair.get((player, mate), []):
        if d >= before:
            continue
        wi_s += sec; wi_p += pw
    s = tot_s - wi_s
    p = tot_p - wi_p
    if s <= 0:
        return None
    return (p / (s / 60.0), s / 60.0)


def main():
    margins = [float(x) for x in (sys.argv[1:] or [0.0, 1.0, 2.0])]
    on, pair = load_stints()
    players = W.players()
    con = sqlite3.connect(f"file:{R.HIST}?mode=ro", uri=True)
    days = [d for (d,) in con.execute(
        "SELECT DISTINCT game_date FROM props WHERE game_date>='2026-05-10' ORDER BY 1")]
    con.close()

    cand = []
    for day in days:
        R._ASOF["day"] = day
        lines = R._load_date(day)
        if not lines:
            continue
        logs, played = {}, defaultdict(set)
        for n, v in players.items():
            lg = R.full_log(v["id"]); logs[n] = lg
            if R.on(lg, day):
                played[v["team"]].add(n)
        by_team = defaultdict(dict)
        for n, v in players.items():
            by_team[v["team"]][n] = v

        for team, roster in by_team.items():
            if not played[team]:
                continue
            for out_name, ov in roster.items():
                if out_name in played[team]:
                    continue
                olog = R.before(logs[out_name], day)
                reg = [g for g in olog if (g.get("min") or 0) > 0]
                if len(reg) < 5 or st.mean(g["min"] for g in reg[-10:]) < 20:
                    continue
                opos = (ov.get("position") or "")
                for n, v in roster.items():
                    if n == out_name or n not in played[team] or n not in lines:
                        continue
                    if (v.get("position") or "") != opos or not opos:
                        continue                                    # SAME POSITION
                    blog = R.before(logs[n], day)
                    if len(blog) < 6:
                        continue
                    try:
                        w = W.wowy_multi(blog, [olog])
                    except Exception:
                        continue
                    if w["n_without"] > MAX_NWO:
                        continue                                    # only the blind spot
                    if w["with"]["min"]["mean"] < STARTER_MIN:
                        continue                                    # STARTERS ONLY
                    ar = apart_rate(on, pair, n, out_name, day)
                    if not ar:
                        continue
                    rate, mins = ar
                    if mins < MIN_APART_MIN:
                        continue                                    # >=50 MIN APART
                    r5 = [g["min"] for g in blog[:5] if g["min"] > 8]
                    proj_min = st.median(r5) if r5 else w["with"]["min"]["mean"]
                    proj = rate * proj_min
                    lad = lines[n].get("points") or {}
                    two = {k: v2 for k, v2 in lad.items() if v2 and v2[0] and v2[1]}
                    if not two:
                        continue
                    line = min(two, key=lambda x: abs(two[x][0] - two[x][1]))
                    price = two[line][0]
                    g = R.on(logs[n], day)
                    if not g or g.get("pts") is None or abs(g["pts"] - line) < 1e-9:
                        continue
                    cand.append({"date": day, "player": n, "out": out_name,
                                 "nwo": w["n_without"], "mins_apart": round(mins, 1),
                                 "rate36": round(rate * 36, 1), "proj": round(proj, 1),
                                 "line": line, "price": price,
                                 "hit": 1 if g["pts"] > line else 0})

    print(f"candidates passing all filters: {len(cand)}")
    if not cand:
        print("  none — the filters (starter + same position + 50 min apart + n_without<=2)")
        print("  leave nothing to test on this archive.")
        return
    print(f"\n{'margin':<8}{'n':>5}{'record':>10}{'hit':>8}{'breakeven':>11}{'edge':>8}{'units':>9}")
    for m in margins:
        sel = [c for c in cand if c["proj"] - c["line"] >= m]
        if len(sel) < 5:
            print(f"{m:<8.1f}{len(sel):>5}   (too thin)")
            continue
        w_ = sum(c["hit"] for c in sel); l_ = len(sel) - w_
        u = sum((c["price"] - 1.0) if c["hit"] else -1.0 for c in sel)
        be = st.mean([1.0 / c["price"] for c in sel])
        hit = w_ / len(sel)
        print(f"{m:<8.1f}{len(sel):>5}{f'{w_}-{l_}':>10}{100*hit:>7.1f}%{100*be:>10.1f}%"
              f"{100*(hit-be):>+7.1f}{u:>+9.2f}u")
    print("\nsample:")
    for c in sorted(cand, key=lambda x: -(x["proj"] - x["line"]))[:8]:
        print(f"  {c['date']} {c['player']:<22} w/o {c['out']:<20} nwo={c['nwo']} "
              f"apart={c['mins_apart']:.0f}m rate36={c['rate36']} proj={c['proj']} "
              f"line={c['line']:g} {'WIN' if c['hit'] else 'loss'}")
    print("\nNOTE: points only — the stint DB has no reb/ast. The n=1 pilot found rebounds")
    print("work and points are a coin flip, so this cannot clear the idea for rebounds.")


if __name__ == "__main__":
    main()
