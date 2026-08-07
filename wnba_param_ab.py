#!/usr/bin/env python3
"""wnba_param_ab — paired A/B for ONE model constant at a time.

Replays historical slates walk-forward, runs the REAL prop_edges under two values of a single
constant, grades both against REAL archived book lines, and reports only what CHANGED.

Paired by construction: identical logs, identical lines, identical gates — the ONLY difference
is the constant. Whatever error the replay carries is shared by both arms and cancels in the
diff, so the diff is trustworthy even where the absolute numbers are not.

  python3 wnba_param_ab.py ROLE_FLOOR 22 20

ONE KNOWN BLIND SPOT, and it matters for ROLE_FLOOR specifically: the archive
(wnba_props_hist) is main-line-only. Players whose book ladder is milestone-only are absent
from it — and those are disproportionately the low-minute players a lower floor would admit.
So a null result here is weak evidence, not proof. Reported explicitly at the end.
"""
import sys, statistics as st, math
from collections import defaultdict

sys.path.insert(0, "/home/ubuntu")
sys.argv_backup = list(sys.argv)
sys.argv = ["x"]
import wnba_replay as R
import wnba_tonight as T, wnba_wowy as W, wnba_slip as S
sys.argv = sys.argv_backup

STATS = {"points": "pts", "rebounds": "reb", "assists": "ast"}


def run_arm(days, players, setter):
    """Replay every slate with the constant set by `setter`. -> graded rows."""
    setter()
    out = []
    for day in days:
        R._ASOF["day"] = day
        lines = R._load_date(day)
        if not lines:
            continue
        logs, played = {}, defaultdict(set)
        for n, v in players.items():
            lg = R.full_log(v["id"])
            logs[n] = lg
            if R.on(lg, day):
                played[v["team"]].add(n)
        by_team = defaultdict(dict)
        for n, v in players.items():
            by_team[v["team"]][n] = v

        for team, roster in by_team.items():
            if not played[team]:
                continue
            outs = []
            for o in roster:
                if o in played[team]:
                    continue
                ol = R.before(logs[o], day)
                reg = [g for g in ol if (g.get("min") or 0) > 0]
                if len(reg) < 5 or st.mean(g["min"] for g in reg[-10:]) < 20:
                    continue
                outs.append((st.mean(g["min"] for g in reg[-10:]), o, ol, reg))
            if not outs:
                continue
            outs = sorted(outs, key=lambda x: -x[0])[:3]
            out_logs = [o[2] for o in outs]
            out_names = {o[1] for o in outs}
            out_dm = [{str(g.get("date") or "")[:10]: g.get("min") or 0 for g in lg}
                      for lg in out_logs]
            vac = {k: round(sum(st.mean([g[STATS[k]] for g in o[3][-10:]]) for o in outs), 1)
                   for k in STATS}

            for n, v in roster.items():
                if n in out_names or n not in lines:
                    continue
                blog = R.before(logs[n], day)
                if len(blog) < 4:
                    continue
                try:
                    w = W.wowy_multi(blog, out_logs)
                    if w["n_without"] < 2 and len(out_logs) > 1:
                        w = max([W.wowy(blog, ol) for ol in out_logs],
                                key=lambda x: x["n_without"])
                except Exception:
                    continue
                if w["n_without"] < 1:
                    continue
                proj = w["without"]["min"]["mean"]
                r5 = [g["min"] for g in blog[:5] if g["min"] > 8]
                if r5:
                    proj = max(proj, st.median(r5))
                if proj - w["with"]["min"]["mean"] <= 0.3:
                    continue
                try:
                    edges = T.prop_edges(n, blog, proj, w, vac, None, out_logs=out_dm) or []
                except Exception:
                    continue
                g = R.on(logs[n], day)
                for e in edges:
                    e = dict(e, player=n, team=team, date=day,
                             out_player=", ".join(sorted(out_names)))
                    av = R.actual(g, e.get("stat"))
                    if av is None or e.get("line") is None:
                        continue
                    res, u = R.settle(e.get("side") or "over", av, float(e["line"]),
                                      float(e.get("dec") or 0))
                    if res is None:
                        continue
                    e["result"], e["units"] = res, u
                    out.append(e)
    # apply the real selection gates per slate
    kept_all = []
    byday = defaultdict(list)
    for r in out:
        byday[r["date"]].append(r)
    for day, rs in byday.items():
        kept, _ = S.current_selection(rs)
        kept_all += kept
    return kept_all


def tally(rows):
    w = sum(1 for r in rows if r["result"] == "win")
    l = sum(1 for r in rows if r["result"] == "loss")
    u = sum(r["units"] for r in rows)
    return w, l, round(u, 2)


def main():
    a = sys.argv[1:]
    if len(a) < 3:
        sys.exit("usage: wnba_param_ab.py <CONST> <baseline> <candidate> [start] [end]")
    const, base_v, cand_v = a[0], float(a[1]), float(a[2])
    start = a[3] if len(a) > 3 else "2026-05-10"
    end = a[4] if len(a) > 4 else "2026-08-05"

    import sqlite3
    con = sqlite3.connect(f"file:{R.HIST}?mode=ro", uri=True)
    days = [d for (d,) in con.execute(
        "SELECT DISTINCT game_date FROM props WHERE game_date BETWEEN ? AND ? ORDER BY 1",
        (start, end))]
    con.close()
    players = W.players()
    print(f"{const}: {base_v:g} (baseline) vs {cand_v:g} (candidate)")
    print(f"{len(days)} slates {start}..{end}\n")

    base = run_arm(days, players, lambda: setattr(T, const, base_v))
    cand = run_arm(days, players, lambda: setattr(T, const, cand_v))
    setattr(T, const, base_v)

    bk = {(r["date"], r["player"], r["stat"], r["line"], r.get("side")) for r in base}
    ck = {(r["date"], r["player"], r["stat"], r["line"], r.get("side")) for r in cand}
    added = [r for r in cand if (r["date"], r["player"], r["stat"], r["line"], r.get("side")) not in bk]
    lost = [r for r in base if (r["date"], r["player"], r["stat"], r["line"], r.get("side")) not in ck]

    bw, bl, bu = tally(base)
    cw, cl, cu = tally(cand)
    aw, al, au = tally(added)
    lw, ll, lu = tally(lost)
    print(f"  baseline  {bw}-{bl}  {bu:+.2f}u   ({len(base)} bets)")
    print(f"  candidate {cw}-{cl}  {cu:+.2f}u   ({len(cand)} bets)")
    print(f"\n  ADDED by the change   {aw}-{al}  {au:+.2f}u")
    print(f"  LOST  by the change   {lw}-{ll}  {lu:+.2f}u")
    print(f"  NET                   {cu - bu:+.2f}u")
    if added:
        print("\n  sample of added bets:")
        for r in sorted(added, key=lambda x: -x["units"])[:10]:
            print(f"    {r['date']} {r['player']:<22} {r['stat']:<9} "
                  f"{r.get('side','over')} {r['line']:<5g} {r['result']:<5} {r['units']:+.2f}u")
    print("\n  CAVEAT: the archive is main-line-only, so players whose book ladder is")
    print("  milestone-only are absent. For a floor change that is exactly the population")
    print("  most affected — treat a null here as weak evidence, not proof.")


if __name__ == "__main__":
    main()
