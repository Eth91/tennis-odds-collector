"""NBA port · flag-time engine — injuries × (WOWY priors | cold-start) × live lines -> SHADOW.

  1. nba_injuries.json (ESPN feed) -> OUT players whose report date is <= NEWS_DAYS old,
     resolved to an NBA person id on their CURRENT team (nba_rosters.state).
  2. Two disjoint beneficiary tiers:
       wowy — B has a measured with/without split vs X (nba_wowy.sqlite pairs, n_out >= 2).
              proj = rate × (base_min + d_min); bet OVER at proj - line >= MARGIN[stat].
       cold — B has NO such split. X's vacated minutes go to the [12, 32]-min rotation in
              proportion to minutes played (nba_coldstart.redistribute — the SAME function
              the real-line test ran); bet OVER at proj - line >= COLD_MARGIN.
  3. Freshest NBA main lines in fanduel_props.sqlite (best over price across books).
  4. Pre-game only: the slate is games with status 1 (not started) on today's ET date.

⚠️ NOTHING HERE PLACES A BET. Both tiers failed on real lines on 2026-10-22:
   wowy — nba_margin_refit.py: at the shipped margins pts −2.58%, pra −1.96%, reb −2.55%,
          every CI crosses zero; the always-over null is −6.56%.
   cold — NBA_COLDSTART_PREREG.md, executed by nba_coldstart_realline.py: PRA>=5 KILL
          (−8.61% pooled, −18.19% second half), PTS>=5 THIN (n=33).
   So every flag goes to the SHADOW table nba_shadow.sqlite, graded by --grade, and only a
   tier listed in LIVE_TIERS may also write a PAPER bet to bet_ledger. Adding one requires a
   new pre-registered test that passes; see NBA_PORT_WHAT_TRANSFERS.md.

⚠️ MAC-ONLY. Slate, rosters and this season's box scores come from cdn.nba.com, which
   403s the Oracle VM even with browser impersonation (2026-10-22). On a host that cannot
   reach it this exits 2 with the reason, rather than printing "0 flags" — which is what it
   did, silently, through four stacked blind inputs before this rewrite.

    python nba_flags.py             # flag -> shadow (and paper, for LIVE_TIERS only)
    python nba_flags.py --dry-run   # print, write nothing
    python nba_flags.py --grade     # settle shadow rows from ESPN box scores
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import nba_coldstart as C
import nba_rosters as R

HERE = Path(__file__).resolve().parent
INJ = HERE / "nba_injuries.json"
WOWY = HERE / "nba_wowy.sqlite"
LINES_DB = HERE / "fanduel_props.sqlite"
LEDGER = HERE / "bet_ledger.sqlite"
SHADOW = HERE / "nba_shadow.sqlite"
ET = ZoneInfo("America/New_York")

LIVE_TIERS = frozenset()               # tiers allowed to write PAPER bets. EMPTY — see above.
NEWS_DAYS = 2                          # absence game 1-2 (news window)
INJ_MAX_AGE_H = 3.0                    # an injury file older than this is a blind input
STATS = ("pra", "pts", "reb")          # ast/fg3m gated off (48.5% Oct-Nov / 53.7%)
MARGIN = {"pra": 5.0, "pts": 3.0, "reb": 2.0}          # wowy tier (measured negative)
LEDGER_STAT = {"pra": "pra", "pts": "points", "reb": "rebounds"}   # fd_lines stat keys
LINE_MAX_AGE_MIN = 90
STAR_MIN, ACTIVE_DAYS, MIN_PRIOR_APPS = 28.0, 12, 5    # == nba_wowy / the cold-start test

# ESPN team abbrevs (injury feed) -> NBA tricodes
TEAM_FIX = {"GS": "GSW", "SA": "SAS", "NO": "NOP", "NY": "NYK", "UTAH": "UTA",
            "WSH": "WAS", "PHX": "PHX", "CHA": "CHA"}

SHADOW_DDL = """CREATE TABLE IF NOT EXISTS flags (
    flag_id TEXT PRIMARY KEY, logged_at TEXT, game_date TEXT, tier TEXT, team TEXT,
    x TEXT, b TEXT, stat TEXT, line REAL, odds REAL, proj REAL, margin REAL,
    gid TEXT, gtime TEXT, matchup TEXT, actual REAL, result TEXT, graded_at TEXT)"""


def fold(s):
    """ascii-fold + lower + strip punctuation — 'Kristaps Porziņģis' == 'Kristaps Porzingis'."""
    n = unicodedata.normalize("NFKD", s or "")
    n = "".join(c for c in n if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", "", n.lower()).split())


def outs_in_window(now):
    """({fold(name): (name, tricode)} for fresh OUTs, file age in hours or None)."""
    if not INJ.exists():
        return {}, None
    try:
        d = json.loads(INJ.read_text())
    except (ValueError, OSError):
        return {}, None
    try:
        age_h = (now - dt.datetime.fromisoformat(d["fetched_at"])).total_seconds() / 3600
    except (KeyError, ValueError, TypeError):
        age_h = None
    out = {}
    for name, v in (d.get("injuries") or {}).items():
        if (v.get("status") or "").lower() != "out":
            continue
        try:
            age = (now.astimezone(ET).date() - dt.date.fromisoformat(v.get("date") or "")).days
        except ValueError:
            continue
        if 0 <= age <= NEWS_DAYS:
            team = (v.get("team") or "").upper()
            out[fold(name)] = (name, TEAM_FIX.get(team, team))
    return out, age_h


def slate(sched, today_et):
    """{tricode: (gid, utc, matchup)} for games on today's ET date that have NOT started."""
    games = {}
    for g in sched:
        if g["date_et"] != today_et or g["status"] != 1:
            continue
        mu = f"{g['away']} @ {g['home']}"
        for t in (g["home"], g["away"]):
            games[t] = (g["gid"], g["utc"], mu)
    return games


def latest_lines(now):
    """({(fold(player), stat): (line, best_over_dec, ts)}, status). status 'ok' or the
    reason the engine is blind to prices."""
    if not LINES_DB.exists():
        return {}, f"no {LINES_DB.name}"
    con = sqlite3.connect(f"file:{LINES_DB}?mode=ro", uri=True)
    ts = con.execute("SELECT MAX(collected_at) FROM fd_lines WHERE sport='nba'").fetchone()[0]
    if not ts:
        con.close()
        return {}, "no NBA rows in fd_lines — nothing collects NBA prop lines"
    try:
        age = (now.replace(tzinfo=None) - dt.datetime.fromisoformat(ts)).total_seconds() / 60
    except ValueError:
        age = 1e9
    if age > LINE_MAX_AGE_MIN:
        con.close()
        return {}, f"newest NBA lines are {age:.0f} min old (> {LINE_MAX_AGE_MIN})"
    rows = con.execute(
        "SELECT player, stat, line, side, odds, COALESCE(book,'fd') FROM fd_lines "
        "WHERE sport='nba' AND collected_at=?", (ts,)).fetchall()
    con.close()
    two = {}
    for player, stat, line, side, odds, book in rows:
        two.setdefault((fold(player), stat, line), {}).setdefault(side, []).append(odds)
    out = {}
    for (pf, stat, line), sides in two.items():
        if "over" not in sides or "under" not in sides:      # alt X+ rungs are over-only
            continue
        best_over = max(sides["over"])
        cur = out.get((pf, stat))
        if cur is None or abs(best_over - 1.9091) < abs(cur[1] - 1.9091):
            out[(pf, stat)] = (line, best_over, ts)
    return out, "ok"


def _team_apps(apps, pid, tri):
    """The player's appearances FOR THIS TEAM — the cold-start test's played_by was
    team-scoped, so the live rotation must be too, or forward shadow is not comparable."""
    return [a for a in apps.get(pid, []) if a[3] == tri]


def _mean_last10(ap):
    last = ap[-10:]
    return sum(a[1] for a in last) / len(last)


def flags(dry=False):
    now = dt.datetime.now(dt.timezone.utc)
    today_et = now.astimezone(ET).date().isoformat()
    blind, why = [], Counter()

    outs, inj_age = outs_in_window(now)
    if inj_age is None:
        blind.append(f"{INJ.name} unreadable")
    elif inj_age > INJ_MAX_AGE_H:
        blind.append(f"{INJ.name} is {inj_age:.1f}h old (> {INJ_MAX_AGE_H}h)")
    blank = [n for n, (_, t) in outs.items() if not t]
    if blank:
        blind.append(f"{len(blank)} OUT player(s) have no tricode")

    try:
        sched = R.schedule()
        boxes, n_failed = R.season_boxes(sched)
    except R.Blind as e:
        print(f"nba flags: BLIND — cdn.nba.com unreachable from this host ({e}). "
              f"Slate, rosters and box scores are Mac-only; nothing evaluated.")
        sys.exit(2)
    if n_failed:
        blind.append(f"{n_failed} final box score(s) failed to fetch (retried next run)")
    games = slate(sched, today_et)
    apps, cur_team, name = R.state(today_et, boxes)
    lines, lstat = latest_lines(now)
    if lstat != "ok":
        blind.append(lstat)

    # OUT name -> person id on the CURRENT team; ambiguous or unknown names are counted
    by_fold = defaultdict(set)
    for pid, nm in name.items():
        by_fold[fold(nm)].add(pid)
    out_pid = {}
    for f, (nm, tri) in outs.items():
        cands = [p for p in by_fold.get(f, ()) if cur_team.get(p) == tri]
        if len(cands) != 1:
            why["out_unresolved" if not cands else "out_ambiguous"] += 1
            continue
        out_pid[cands[0]] = (nm, tri)

    con = sqlite3.connect(f"file:{WOWY}?mode=ro", uri=True)
    pairs = con.execute("SELECT x_id, b_id, b_name, n_out, d_min, rate_pts, rate_reb, "
                        "rate_pra FROM pairs").fetchall()
    base_min = {r[0]: r[1] for r in con.execute("SELECT b_id, base_min FROM baselines")}
    con.close()
    has_prior = {(x, b) for x, b, *_ in pairs}

    cands = []
    # ── wowy tier: id join, and B must be on X's CURRENT team (fixes summer moves) ──
    for x_id, b_id, b_name, n_out, d_min, r_pts, r_reb, r_pra in pairs:
        if x_id not in out_pid:
            continue
        xname, tri = out_pid[x_id]
        if cur_team.get(b_id) != tri:
            why["wowy_b_not_on_team"] += 1
            continue
        if tri not in games:
            why["no_game_today"] += 1
            continue
        if b_id in out_pid or b_id not in base_min:
            continue
        rates = {"pts": r_pts, "reb": r_reb, "pra": r_pra}
        for stat in STATS:
            cands.append(("wowy", tri, xname, b_id, stat,
                          rates[stat] * (base_min[b_id] + d_min), MARGIN[stat]))

    # ── cold tier: exactly the pre-registered rule, through the shared function ──
    season = C.season_of(today_et)
    today = dt.date.fromisoformat(today_et)
    for x_id, (xname, tri) in out_pid.items():
        if tri not in games:
            why["no_game_today"] += 1
            continue
        xa = _team_apps(apps, x_id, tri)
        if len(xa) < 10 or _mean_last10(xa) < STAR_MIN:
            why["x_not_a_star_here"] += 1
            continue
        bm = {}
        for p, t in cur_team.items():
            if t != tri:
                continue
            pa = _team_apps(apps, p, tri)
            if (len(pa) >= MIN_PRIOR_APPS
                    and (today - dt.date.fromisoformat(pa[-1][0])).days <= ACTIVE_DAYS):
                bm[p] = _mean_last10(pa)
        for b_id, pmin in C.redistribute(bm, x_id, _mean_last10(xa)).items():
            if b_id in out_pid or (x_id, b_id) in has_prior:
                continue
            rate = C.per_min_rate(_team_apps(apps, b_id, tri), C.season_of, season)
            if not rate:
                continue
            for stat in STATS:
                cands.append(("cold", tri, xname, b_id, stat, rate[stat] * pmin, C.COLD_MARGIN))

    out_flags = []
    for tier, tri, xname, b_id, stat, proj, margin in cands:
        lk = lines.get((fold(name.get(b_id, "")), LEDGER_STAT[stat]))
        if not lk:
            why["no_line"] += 1
            continue
        line, odds, ts = lk
        if proj - line < margin:
            continue
        gid, gtime, mu = games[tri]
        out_flags.append({"tier": tier, "team": tri, "x": xname, "b": name.get(b_id),
                          "stat": stat, "line": line, "odds": odds, "proj": round(proj, 1),
                          "margin": round(proj - line, 1), "gid": gid, "gtime": gtime,
                          "matchup": mu})

    new_shadow = new_paper = 0
    if not dry and out_flags:
        sh = sqlite3.connect(SHADOW)
        sh.execute(SHADOW_DDL)
        stamp = now.replace(microsecond=0, tzinfo=None).isoformat()
        for f in out_flags:
            fid = f"{f['tier']}|{fold(f['b'])}|{f['stat']}|{f['line']}|{today_et}"
            cur = sh.execute("INSERT OR IGNORE INTO flags VALUES "
                             "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL)",
                             (fid, stamp, today_et, f["tier"], f["team"], f["x"], f["b"],
                              f["stat"], f["line"], f["odds"], f["proj"], f["margin"],
                              f["gid"], f["gtime"], f["matchup"]))
            new_shadow += cur.rowcount
        sh.commit()
        sh.close()
        paper = [f for f in out_flags if f["tier"] in LIVE_TIERS]
        if paper:
            import bet_ledger as BL
            led = sqlite3.connect(LEDGER)
            led.execute(BL.DDL)
            for f in paper:
                bid = f"nba|{fold(f['b'])}|{f['stat']}|{f['line']}|over|{today_et}"
                if led.execute("SELECT 1 FROM bets WHERE bet_id=?", (bid,)).fetchone():
                    continue
                led.execute("INSERT INTO bets VALUES "
                            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (bid, stamp, "nba", f["matchup"], f["b"], LEDGER_STAT[f["stat"]],
                             f["line"], "over", f["odds"], 1.0, None, None, f["line"],
                             f["tier"], f["gtime"], "open", None, None, None, None, None,
                             None))
                new_paper += 1
            led.commit()
            led.close()

    for b in blind:
        print(f"  !! BLIND: {b}")
    for f in out_flags:
        print(f"  [NBA {f['tier']}] {f['b']} ({f['team']}) {f['stat'].upper()} O{f['line']:g} "
              f"@{f['odds']:.2f} · proj {f['proj']} (+{f['margin']}) · {f['x']} OUT · "
              f"{f['matchup']}")
    tiers = Counter(f["tier"] for f in out_flags)
    print(f"nba flags: {len(outs)} fresh OUT ({len(out_pid)} resolved) · {len(games) // 2} "
          f"game(s) left today · lines: {lstat if lstat == 'ok' else 'BLIND'} · "
          f"candidates {Counter(c[0] for c in cands)} -> flags {dict(tiers)} · "
          f"shadow +{new_shadow} · paper +{new_paper} (live tiers: "
          f"{', '.join(sorted(LIVE_TIERS)) or 'none'})" + (" · DRY-RUN" if dry else ""))
    if why:
        print(f"  skipped: {dict(why)}")
    return out_flags


def grade():
    """Settle shadow rows for past dates from ESPN box scores (bet_ledger.settle_nba).
    A row whose player is not found stays ungraded and is retried — never a void."""
    if not SHADOW.exists():
        print("nba shadow: no table yet")
        return
    import bet_ledger as BL
    today_et = dt.datetime.now(dt.timezone.utc).astimezone(ET).date().isoformat()
    sh = sqlite3.connect(SHADOW)
    sh.execute(SHADOW_DDL)
    todo = sh.execute("SELECT flag_id, b, stat, line, gtime FROM flags "
                      "WHERE result IS NULL AND game_date < ?", (today_et,)).fetchall()
    done = 0
    for fid, b, stat, line, gtime in todo:
        actual = BL.settle_nba(b, LEDGER_STAT[stat], gtime)
        if actual is None:
            continue
        sh.execute("UPDATE flags SET actual=?, result=?, graded_at=? WHERE flag_id=?",
                   (actual, "win" if actual > line else "loss",
                    dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), fid))
        done += 1
    sh.commit()
    for tier, n, w, u in sh.execute(
            "SELECT tier, COUNT(*), SUM(result='win'), "
            "SUM(CASE WHEN result='win' THEN odds-1 ELSE -1 END) FROM flags "
            "WHERE result IS NOT NULL GROUP BY tier"):
        print(f"  shadow {tier}: {w}-{n - w}  {u:+.2f}u  ROI {100 * u / n:+.1f}%  (n={n})")
    print(f"nba shadow: graded {done} of {len(todo)} pending")
    sh.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--grade", action="store_true")
    a = ap.parse_args()
    grade() if a.grade else flags(dry=a.dry_run)
