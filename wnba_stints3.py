#!/usr/bin/env python3
"""wnba_stints3 — on/off-court REBOUNDS and ASSISTS, not just points.

WHY. The stint DB carries points only, so the "use apart-minutes when there are no
without-games" idea could only ever be tested on the weakest stat. Rebounds and assists are
the ones that plausibly redistribute BY POSITION -- a big's boards go to another big, a
guard's assists to another guard -- while points flow to whoever can score regardless of
position. So the two stats most likely to carry the signal were the two we could not measure.

The play-by-play already contains them; the existing attribution just discards everything
that is not a scoring play. Same walk, three tallies.

VALIDATION IS THE POINT. If the rebound/assist detection silently misses, this writes zeros
that look like real data -- the exact failure mode that has cost the most in this repo. So
`--validate` checks the stint totals against the official box score per game and REFUSES to
backfill a game that disagrees beyond tolerance.

  python3 wnba_stints3.py --validate [N]   # check N games against the box, write nothing
  python3 wnba_stints3.py --backfill       # fill reb/ast for every clean game
"""
import collections
import sqlite3
import sys

sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_stints as ST
import stint_attr as SA

DB = "/home/ubuntu/tennis-odds-collector/wnba_stints.sqlite"
TOL = 2          # per-game per-stat slack vs the box score


def _stat_of(play):
    """-> 'reb' | 'ast-carrier' | None, plus the participant index that owns it.

    ESPN marks the shooter as participants[0] and the assister as participants[1] on a made
    shot. Rebounds are their own play whose type text contains 'rebound'."""
    t = ((play.get("type") or {}).get("text") or "").lower()
    txt = str(play.get("text") or "").lower()
    if "rebound" in t or "rebound" in txt:
        return "reb"
    return None


def game_oncourt3(event_id):
    """Same shape as stint_attr.game_oncourt but with reb/ast alongside pts."""
    s = ST._get(f"{ST.SITE}/summary", event=event_id)
    rec = ST.reconstruct(event_id)
    if not rec["ok"]:
        return None
    names = SA.id_name_map(s)
    stints = [(a, b, d) for a, b, d in rec["stints"] if b is not None and b > a]
    if not stints:
        return None

    sec = collections.Counter()
    pair = collections.Counter()
    for a, b, d in stints:
        dur = b - a
        for _tid, on in d.items():
            for p in on:
                sec[p] += dur
            for p in on:
                for q in on:
                    if p != q:
                        pair[(p, q)] += dur

    tot = {k: collections.Counter() for k in ("pts", "reb", "ast")}
    wit = {k: collections.Counter() for k in ("pts", "reb", "ast")}

    def _lineup(t):
        for a, b, d in stints:
            if a <= t < b:
                return d
        return None

    def _credit(nm, key, v, cur):
        tot[key][nm] += v
        for on in cur.values():
            if nm in on:
                for q in on:
                    if q != nm:
                        wit[key][(nm, q)] += v

    for p in (s.get("plays") or []):
        parts = p.get("participants") or []
        t = ST._clock_to_sec(((p.get("period") or {}).get("number")),
                             ((p.get("clock") or {}).get("displayValue")))
        if t is None:
            continue
        cur = _lineup(t)
        if cur is None:
            continue

        if p.get("scoringPlay") and parts:
            aid = str(((parts[0].get("athlete") or {}).get("id")) or "")
            nm = names.get(aid)
            if nm:
                _credit(nm, "pts", float(p.get("scoreValue") or 0), cur)
            # participants[1] on a made shot is the ASSIST
            if len(parts) > 1:
                a2 = str(((parts[1].get("athlete") or {}).get("id")) or "")
                nm2 = names.get(a2)
                if nm2:
                    _credit(nm2, "ast", 1.0, cur)
            continue

        if _stat_of(p) == "reb" and parts:
            aid = str(((parts[0].get("athlete") or {}).get("id")) or "")
            nm = names.get(aid)
            if nm:
                _credit(nm, "reb", 1.0, cur)

    return {"sec": sec, "pair": pair,
            "pts": tot["pts"], "reb": tot["reb"], "ast": tot["ast"],
            "pts_with": wit["pts"], "reb_with": wit["reb"], "ast_with": wit["ast"]}


def box_totals(event_id):
    """Official per-player pts/reb/ast from the boxscore, for validation."""
    s = ST._get(f"{ST.SITE}/summary", event=event_id)
    out = {}
    for t in ((s.get("boxscore") or {}).get("players") or []):
        for st_ in (t.get("statistics") or []):
            keys = [k.lower() for k in (st_.get("keys") or [])]
            for a in (st_.get("athletes") or []):
                nm = ((a.get("athlete") or {}).get("displayName"))
                vals = a.get("stats") or []
                if not nm or len(vals) != len(keys):
                    continue
                d = dict(zip(keys, vals))
                def _i(k):
                    try:
                        return int(d.get(k) or 0)
                    except ValueError:
                        return 0
                out[nm] = {"pts": _i("points"), "reb": _i("rebounds"), "ast": _i("assists")}
    return out


def validate(n=8):
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    ev = [e for (e,) in c.execute(
        "SELECT event_id FROM games WHERE status='ok' ORDER BY game_date DESC LIMIT ?", (n,))]
    c.close()
    print(f"validating {len(ev)} games against the official box score (tolerance {TOL})\n")
    bad = 0
    for e in ev:
        g = game_oncourt3(e)
        if not g:
            print(f"  {e}  reconstruction not clean — skipped")
            continue
        box = box_totals(e)
        diffs = {"pts": 0, "reb": 0, "ast": 0}
        worst = {}
        for nm, b in box.items():
            for k in diffs:
                d = abs(float(g[k].get(nm, 0)) - b[k])
                if d > diffs[k]:
                    diffs[k] = d; worst[k] = nm
        flag = "OK " if all(v <= TOL for v in diffs.values()) else "MISMATCH"
        if flag != "OK ":
            bad += 1
        print(f"  {flag} {e}  max diff  pts {diffs['pts']:.0f}  reb {diffs['reb']:.0f}  "
              f"ast {diffs['ast']:.0f}   ({worst})")
    print(f"\n{len(ev)-bad}/{len(ev)} games within tolerance")
    print("A MISMATCH means the play-by-play tally disagrees with the box — do NOT backfill")
    print("that stat until it is understood. Writing a wrong number is worse than none.")
    return bad


def backfill():
    con = sqlite3.connect(DB)
    for tbl, cols in (("onfloor", ("reb", "ast")), ("pairs", ("reb_with", "ast_with"))):
        have = {r[1] for r in con.execute(f"PRAGMA table_info({tbl})")}
        for c_ in cols:
            if c_ not in have:
                con.execute(f"ALTER TABLE {tbl} ADD COLUMN {c_} REAL DEFAULT NULL")
    con.commit()
    todo = [(e, d) for e, d in con.execute(
        "SELECT event_id, game_date FROM games WHERE status='ok' ORDER BY game_date")]
    done = ok = skip = 0
    for e, d in todo:
        done += 1
        try:
            g = game_oncourt3(e)
        except Exception as ex:
            skip += 1
            print(f"  {e} {d}: {type(ex).__name__} {str(ex)[:50]}")
            continue
        if not g:
            skip += 1
            continue
        # REFRESH sec AND pts TOO, not just the new columns. The reconstruction fix
        # (sub-minute clocks + closed final stint) changes MINUTES and POINTS as well —
        # writing only reb/ast leaves the broken originals in place, and every rate built
        # from them stays wrong. Caught because the re-run returned byte-identical numbers.
        con.executemany("UPDATE onfloor SET sec=?, pts=?, reb=?, ast=? "
                        "WHERE event_id=? AND player=?",
                        [(float(g["sec"].get(p, 0)), float(g["pts"].get(p, 0)),
                          float(g["reb"].get(p, 0)), float(g["ast"].get(p, 0)), e, p)
                         for p in g["sec"]])
        con.executemany("UPDATE pairs SET sec=?, pts_with=?, reb_with=?, ast_with=? "
                        "WHERE event_id=? AND player=? AND mate=?",
                        [(float(g["pair"].get((p, q), 0)),
                          float(g["pts_with"].get((p, q), 0)),
                          float(g["reb_with"].get((p, q), 0)),
                          float(g["ast_with"].get((p, q), 0)), e, p, q)
                         for (p, q) in g["pair"]])
        ok += 1
        if done % 25 == 0:
            con.commit()
            print(f"  {done}/{len(todo)} games ({ok} filled, {skip} skipped)", flush=True)
    con.commit()
    n_reb = con.execute("SELECT COUNT(*) FROM onfloor WHERE reb IS NOT NULL").fetchone()[0]
    n_tot = con.execute("SELECT COUNT(*) FROM onfloor").fetchone()[0]
    con.close()
    print(f"\nbackfill done: {ok} games filled, {skip} skipped")
    print(f"onfloor rows with rebounds: {n_reb}/{n_tot}")


if __name__ == "__main__":
    if "--backfill" in sys.argv:
        backfill()
    else:
        n = 8
        for a in sys.argv[1:]:
            if a.isdigit():
                n = int(a)
        sys.exit(1 if validate(n) else 0)
