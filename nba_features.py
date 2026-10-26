#!/usr/bin/env python3
"""Feature table for NBA_FILTER_SEARCH_PREREG.md — one row per (candidate, stat) with a real line.

The universe is nba_pricing_realline.walk(), the same one every NBA test used. Every feature is known
before tip: season-to-date numbers use games STRICTLY before the bet's date; shot-zone and play-type
profiles come from the PRIOR season; team rates are divided by the league's rate on the same date, so a
league-wide shift between seasons (pace rising, say) cannot pose as a team effect.

    python nba_features.py            # build nba_features.sqlite (table `features`)
    python nba_features.py --verify   # look-ahead checks against direct recomputation
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import random
import sqlite3
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import nba_coldstart as C
import nba_injury_report as I
import nba_margin_refit as RF
import nba_pricing as P
import nba_pricing_realline as PR
import nba_wowy as N
import wnba_tonight as T

HERE = Path(__file__).resolve().parent
OUT = HERE / "nba_features.sqlite"
LOGS = HERE / "nba_gamelogs.sqlite"
PROF = HERE / "nba_profiles.sqlite"
TRAIN_END, VALID_END = "2024-07-01", "2025-02-01"
PLAYTYPES = ["Isolation", "Transition", "PRBallHandler", "PRRollman", "Postup", "Spotup",
             "Handoff", "Cut", "OffScreen"]
ZONES = ["ra", "paint", "mid", "c3", "ab3"]
STAT_PARTS = {"points": ("pts",), "rebounds": ("reb",), "assists": ("ast",),
              "pra": ("pts", "reb", "ast"), "pts_reb": ("pts", "reb"), "pts_ast": ("pts", "ast"),
              "reb_ast": ("reb", "ast")}
TEAM_KEYS = ("pts", "fga", "fta", "fg3a", "oreb", "dreb", "reb", "ast", "tov", "blk")


def block_of(date):
    return "TRAIN" if date < TRAIN_END else "VALIDATE" if date < VALID_END else "HOLDOUT"


def season_label(date):
    y = C.season_of(date)
    return f"{y}-{(y + 1) % 100:02d}"


def prev_label(date):
    y = C.season_of(date) - 1
    return f"{y}-{(y + 1) % 100:02d}"


def pos_group(p):
    p = (p or "").upper()
    return p[:1] if p[:1] in ("G", "F", "C") else "F"


class Teams:
    """Season-to-date team and league aggregates from the box scores, queried strictly before a date."""

    def __init__(self, pos):
        con = sqlite3.connect(f"file:{LOGS}?mode=ro", uri=True)
        pc = sqlite3.connect(f"file:{PROF}?mode=ro", uri=True)
        self.tg = {(g, t): (d, h, o) for g, t, d, h, o in pc.execute(
            "SELECT game_id, team, date, home, opp FROM team_games")}
        box = defaultdict(lambda: defaultdict(float))            # (gid, team) -> totals
        grp = defaultdict(lambda: defaultdict(float))            # (gid, team, group) -> min, pts, reb, ast
        date_of = {}
        for gid, date, team, pid, mn, *v in con.execute(
                "SELECT game_id, date, team, player_id, min, pts, fga, fta, fg3a, oreb, dreb, reb, "
                "ast, tov, blk FROM logs_full"):
            b = box[(gid, team)]
            for k, x in zip(TEAM_KEYS, v):
                b[k] += x or 0
            gg = grp[(gid, team, pos_group(pos.get(pid)))]
            gg["min"] += mn or 0
            gg["pts"] += v[0] or 0
            gg["reb"] += v[6] or 0
            gg["ast"] += v[7] or 0
            date_of[gid] = date
        con.close()
        poss = lambda b: b["fga"] + 0.44 * b["fta"] - b["oreb"] + b["tov"]
        self.team_rows = defaultdict(list)                       # (team, season) -> [(date, rec)]
        league_daily = defaultdict(lambda: defaultdict(float))   # (season, date) -> totals
        for (gid, team), b in box.items():
            meta = self.tg.get((gid, team))
            if not meta:
                continue
            d, home, opp = meta
            ob = box.get((gid, opp))
            if not ob:
                continue
            rec = {"g": 1, "pts_for": b["pts"], "pts_ag": ob["pts"], "poss_for": poss(b),
                   "poss_ag": poss(ob), "reb_ag": ob["reb"], "ast_ag": ob["ast"], "fga_ag": ob["fga"],
                   "fg3a_ag": ob["fg3a"], "fta_ag": ob["fta"], "oreb_ag": ob["oreb"],
                   "dreb_for": b["dreb"], "blk_for": b["blk"]}
            for g in ("G", "F", "C"):
                og = grp.get((gid, opp, g), {})
                for k in ("min", "pts", "reb", "ast"):
                    rec[f"{g}_{k}_ag"] = og.get(k, 0.0)
            s = season_label(d)
            self.team_rows[(team, s)].append((d, rec))
            L = league_daily[(s, d)]
            for k, x in rec.items():
                L[k] += x
        self.cum = {}
        for key, rows in self.team_rows.items():
            rows.sort(key=lambda r: r[0])
            self.cum[key] = self._cumulate(rows)
        self.league = {}
        by_season = defaultdict(list)
        for (s, d), tot in league_daily.items():
            by_season[s].append((d, dict(tot)))
        for s, rows in by_season.items():
            rows.sort(key=lambda r: r[0])
            self.league[s] = self._cumulate(rows)

    @staticmethod
    def _cumulate(rows):
        dates, cum, run = [], [], defaultdict(float)
        for d, rec in rows:
            for k, x in rec.items():
                run[k] += x
            dates.append(d)
            cum.append(dict(run))
        return dates, cum

    @staticmethod
    def _before(dc, date):
        dates, cum = dc
        i = bisect.bisect_left(dates, date)                      # strictly before
        return cum[i - 1] if i else None

    def team(self, team, date):
        return self._before(self.cum.get((team, season_label(date)), ([], [])), date)

    def lg(self, date):
        return self._before(self.league.get(season_label(date), ([], [])), date)

    def prev_game(self, team, date):
        dates = [d for d, _ in self.team_rows.get((team, season_label(date)), [])]
        i = bisect.bisect_left(dates, date)
        return dates[i - 1] if i else None


def defense(t, L):
    """Rates for a team's season-to-date defense, each relative to the league on the same date."""
    if not t or not L or t["g"] < 5:
        return {}
    r = lambda num, den: num / den if den else None
    out = {
        "pace": r(t["poss_for"] + t["poss_ag"], 2 * t["g"]) / r(L["poss_for"] + L["poss_ag"], 2 * L["g"]),
        "def_rtg": r(t["pts_ag"], t["poss_ag"]) / r(L["pts_ag"], L["poss_ag"]),
        "reb_ag": r(t["reb_ag"], t["poss_ag"]) / r(L["reb_ag"], L["poss_ag"]),
        "ast_ag": r(t["ast_ag"], t["poss_ag"]) / r(L["ast_ag"], L["poss_ag"]),
        "fg3a_rate_ag": r(t["fg3a_ag"], t["fga_ag"]) / r(L["fg3a_ag"], L["fga_ag"]),
        "fta_rate_ag": r(t["fta_ag"], t["fga_ag"]) / r(L["fta_ag"], L["fga_ag"]),
        "oreb_rate_ag": r(t["oreb_ag"], t["oreb_ag"] + t["dreb_for"]) /
                        r(L["oreb_ag"], L["oreb_ag"] + L["dreb_for"]),
        "blk": r(t["blk_for"], t["g"]) / r(L["blk_for"], L["g"]),
        "net": 100 * (t["pts_for"] - t["pts_ag"]) / max(1.0, t["poss_for"]),
    }
    for g in ("G", "F", "C"):
        for k in ("pts", "reb", "ast"):
            a, b = t[f"{g}_{k}_ag"], t[f"{g}_min_ag"]
            la, lb = L[f"{g}_{k}_ag"], L[f"{g}_min_ag"]
            out[f"dvp_{g}_{k}"] = (a / b) / (la / lb) if b and lb and la else None
    return out


def profiles():
    con = sqlite3.connect(f"file:{PROF}?mode=ro", uri=True)
    zones = {(s, p): dict(zip(ZONES, v)) for s, p, *v in con.execute(
        "SELECT season, pid, ra, paint, mid, c3, ab3 FROM player_zones")}
    oz = {(s, I.TEAMS.get(t)): dict(zip(ZONES, v)) for s, t, *v in con.execute(
        "SELECT season, team, ra, paint, mid, c3, ab3 FROM team_opp_zones")}
    oz_lg = {}
    for s in {k[0] for k in oz}:
        oz_lg[s] = {z: st.mean(v[z] for (ss, _), v in oz.items() if ss == s and v[z]) for z in ZONES}
    pt = defaultdict(dict)
    for s, p, typ, f in con.execute("SELECT season, pid, playtype, freq FROM player_playtypes"):
        pt[(s, p)][typ] = f
    dpt = defaultdict(dict)
    for s, t, typ, ppp in con.execute("SELECT season, team, playtype, ppp FROM team_def_playtypes"):
        dpt[(s, t)][typ] = ppp
    dpt_lg = {}
    for s in {k[0] for k in dpt}:
        dpt_lg[s] = {typ: st.mean(v[typ] for (ss, _), v in dpt.items() if ss == s and typ in v)
                     for typ in PLAYTYPES}
    con.close()
    return zones, oz, oz_lg, pt, dpt, dpt_lg


def build():
    tg_games, names, pos = PR.load_games()
    lines = PR.load_lines()
    teams = Teams(pos)
    zones, oz, oz_lg, pt, dpt, dpt_lg = profiles()
    cnt = defaultdict(int)
    rows = []
    for c in PR.walk(tg_games, names, lines, cnt):
        date, team, gid, X, B, brow = c["date"], c["team"], c["gid"], c["X"], c["B"], c["brow"]
        meta = teams.tg.get((gid, team))
        if not meta:
            continue
        _, home, opp = meta
        pb = c["played_by"]
        b_apps, x_apps = pb[B], pb[X]
        season = C.season_of(date)
        cur = [a for a in b_apps if C.season_of(a[0]) == season]
        b10 = b_apps[-10:]
        # B's and X's share of their team's volume over the prior franchise games they played
        tsum = lambda apps, k: sum(a[2][k] for a in apps)
        team_fga = {g: sum(r["fga"] for r in pbox.values()) for _, g, pbox in c["prior"]}
        team_ast = {g: sum(r["ast"] for r in pbox.values()) for _, g, pbox in c["prior"]}
        team_reb = {g: sum(r["reb"] for r in pbox.values()) for _, g, pbox in c["prior"]}
        team_use = {g: sum(r["fga"] + 0.44 * r["fta"] for r in pbox.values()) for _, g, pbox in c["prior"]}
        share = lambda apps, k, tot: (sum(a[2][k] for a in apps) / max(1.0, sum(tot.get(a[1], 0) for a in apps)))
        out_r, in_r = c["b_out"], c["b_in"]
        mean = lambda xs: sum(xs) / len(xs) if xs else None
        dmin = mean([r["min"] for r in out_r]) - mean([r["min"] for r in in_r])
        dfga = mean([r["fga"] for r in out_r]) - mean([r["fga"] for r in in_r])
        tD = defense(teams.team(opp, date), teams.lg(date))
        tO = defense(teams.team(team, date), teams.lg(date))
        prv = prev_label(date)
        bz = zones.get((prv, B))
        bpt = pt.get((prv, B), {})
        ozd = oz.get((prv, opp))
        ozl = oz_lg.get(prv)
        dpd, dpl = dpt.get((prv, opp), {}), dpt_lg.get(prv, {})
        rest = lambda t: ((dt.date.fromisoformat(date) - dt.date.fromisoformat(teams.prev_game(t, date))).days
                          if teams.prev_game(t, date) else None)
        bgrp = pos_group(pos.get(B))
        base = {
            "date": date, "block": block_of(date), "gid": gid, "team": team, "opp": opp,
            "x_pid": X, "b_pid": B, "b_name": c["nm"], "aidx": c["aidx"], "home": home,
            "b_min_l10": mean([a[2]["min"] for a in b10]),
            "b_usage_share": sum(a[2]["fga"] + 0.44 * a[2]["fta"] for a in b_apps) /
                             max(1.0, sum(team_use.get(a[1], 0) for a in b_apps)),
            "b_3pa_rate": tsum(b_apps, "fg3a") / max(1.0, tsum(b_apps, "fga")),
            "b_fta_rate": tsum(b_apps, "fta") / max(1.0, tsum(b_apps, "fga")),
            "x_min_l10": mean([a[2]["min"] for a in x_apps[-10:]]),
            "x_fga_share": share(x_apps, "fga", team_fga),
            "x_ast_share": share(x_apps, "ast", team_ast),
            "x_reb_share": share(x_apps, "reb", team_reb),
            "pw": P.A.position_compat(P.norm_pos(pos.get(B, "")), [P.norm_pos(pos.get(X, ""))]),
            "d_min": dmin, "d_fga": dfga, "n_out": len(out_r),
            "rest": rest(team), "opp_rest": rest(opp),
            "net_gap": (tO.get("net") - tD.get("net")) if tO.get("net") is not None and tD.get("net") is not None else None,
        }
        base["abs_net_gap"] = abs(base["net_gap"]) if base["net_gap"] is not None else None
        base["b2b"] = int(base["rest"] == 1) if base["rest"] is not None else None
        for k in ("pace", "def_rtg", "reb_ag", "ast_ag", "fg3a_rate_ag", "fta_rate_ag", "oreb_rate_ag", "blk"):
            base[f"opp_{k}"] = tD.get(k)
        for z in ZONES:
            base[f"b_{z}"] = bz[z] if bz else None
            base[f"opp_{z}_fg"] = (ozd[z] / ozl[z]) if ozd and ozl and ozd.get(z) else None
        for typ in PLAYTYPES:
            base[f"b_pt_{typ}"] = bpt.get(typ)
            base[f"opp_pt_{typ}"] = (dpd[typ] / dpl[typ]) if typ in dpd and dpl.get(typ) else None
        # matchup interactions — B's style against the opponent's weakness (None when unknown)
        mul = lambda a, b: a * b if a is not None and b is not None else None
        base["m_rim"] = mul(base["b_ra"], base["opp_ra_fg"])
        base["m_paint"] = mul(base["b_paint"], base["opp_paint_fg"])
        three = (base["b_c3"] or 0) + (base["b_ab3"] or 0) if bz else None
        o3 = mul(0.5, (base["opp_c3_fg"] or 0) + (base["opp_ab3_fg"] or 0)) if ozd else None
        base["m_three"] = mul(three, o3)
        base["m_3pa"] = mul(base["b_3pa_rate"], base["opp_fg3a_rate_ag"])
        base["m_ft"] = mul(base["b_fta_rate"], base["opp_fta_rate_ag"])
        for typ, key in (("PRBallHandler", "m_pnr"), ("Spotup", "m_spot"), ("Postup", "m_post"),
                         ("Isolation", "m_iso"), ("PRRollman", "m_roll"), ("Transition", "m_trans")):
            base[key] = mul(base[f"b_pt_{typ}"], base[f"opp_pt_{typ}"])
        base["m_usage_def"] = mul(dfga, tD.get("def_rtg"))
        base["m_min_pace"] = mul(dmin, tD.get("pace"))
        for stat, ladder in c["best"].items():
            ml = T._main_line(ladder)
            if ml is None or stat not in STAT_PARTS:
                continue
            parts = STAT_PARTS[stat]
            val = lambda r: sum(r[p] for p in parts)
            avg_cur = mean([val(a[2]) for a in cur]) if len(cur) >= 5 else mean([val(a[2]) for a in b10])
            dvps = [tD.get(f"dvp_{bgrp}_{p}") for p in parts]
            min_out = sum(r["min"] for r in out_r)
            d_sh = dmin * len(out_r) / (len(out_r) + N.K_DMIN)
            base_rate = sum(val(a[2]) for a in b10) / max(1e-9, sum(a[2]["min"] for a in b10))
            rate = (sum(val(r) for r in out_r) + base_rate * N.K_MIN) / (min_out + N.K_MIN)
            actual = sum(brow[p] for p in parts)
            ov = ladder[ml][0]
            rows.append(dict(base, stat=stat, line=ml, price=ov, implied=1 / ov,
                             line_vs_avg=ml - avg_cur, line_vs_l10=ml - mean([val(a[2]) for a in b10]),
                             d_stat=mean([val(r) for r in out_r]) - mean([val(r) for r in in_r]),
                             wowy_margin=rate * (mean([a[2]["min"] for a in b10]) + d_sh) - ml,
                             opp_dvp=st.mean(dvps) if all(v is not None for v in dvps) else None,
                             actual=actual, won=int(actual > ml),
                             units=(ov - 1) if actual > ml else -1.0))
    con = sqlite3.connect(OUT)
    con.execute("DROP TABLE IF EXISTS features")
    cols = list(rows[0].keys())
    con.execute(f"CREATE TABLE features ({', '.join(cols)})")
    con.executemany(f"INSERT INTO features VALUES ({','.join('?' * len(cols))})",
                    [[r.get(k) for k in cols] for r in rows])
    con.commit()
    con.close()
    by = defaultdict(int)
    for r in rows:
        by[r["block"]] += 1
    print(f"universe {dict(cnt)} -> {len(rows):,} candidate-stat rows {dict(by)} · {len(cols)} columns -> {OUT.name}")


def verify(n=40):
    """Look-ahead checks: recompute a sample of season-to-date values straight from the box scores
    with `date < bet date`, and confirm profiles are from the prior season."""
    con = sqlite3.connect(f"file:{OUT}?mode=ro", uri=True)
    cols = [r[1] for r in con.execute("PRAGMA table_info(features)")]
    rows = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM features WHERE opp_def_rtg IS NOT NULL")]
    random.seed(7)
    pick = random.sample(rows, min(n, len(rows)))
    lg = sqlite3.connect(f"file:{LOGS}?mode=ro", uri=True)
    lg.execute(f"ATTACH DATABASE 'file:{PROF}?mode=ro' AS p")
    bad = 0
    for r in pick:
        s = season_label(r["date"])
        q = """SELECT SUM(o.pts), SUM(o.fga + 0.44*o.fta - o.oreb + o.tov) FROM
               (SELECT game_id, team, SUM(pts) pts, SUM(fga) fga, SUM(fta) fta, SUM(oreb) oreb, SUM(tov) tov
                FROM logs_full WHERE season=? AND date < ? GROUP BY game_id, team) o
               JOIN p.team_games tgm ON tgm.game_id = o.game_id AND tgm.opp = ? AND tgm.team = o.team"""
        pts_ag, poss_ag = lg.execute(q, (s, r["date"], r["opp"])).fetchone()
        ql = """SELECT SUM(pts), SUM(fga + 0.44*fta - oreb + tov) FROM logs_full WHERE season=? AND date < ?"""
        lpts, lposs = lg.execute(ql, (s, r["date"])).fetchone()
        direct = (pts_ag / poss_ag) / (lpts / lposs)
        if abs(direct - r["opp_def_rtg"]) > 1e-6:
            bad += 1
            print(f"  MISMATCH {r['date']} {r['opp']}: stored {r['opp_def_rtg']:.6f} direct {direct:.6f}")
    print(f"look-ahead check: opponent defensive rating recomputed with date < bet date on {len(pick)} "
          f"rows -> {len(pick) - bad} match")
    # PROFILE SEASON: each stored shot-zone share must equal the PRIOR season's value — checked only
    # on rows where the prior and the current season differ, so the check can actually catch a leak
    # (the first version asked a question no row could fail).
    pz = {(s, p): ra for s, p, ra in lg.execute("SELECT season, pid, ra FROM p.player_zones")}
    disc = leaks = 0
    for r in rows:
        if r["b_ra"] is None:
            continue
        prior, cur = pz.get((prev_label(r["date"]), r["b_pid"])), pz.get((season_label(r["date"]), r["b_pid"]))
        if prior is None or cur is None or abs(prior - cur) < 1e-9:
            continue
        disc += 1
        if abs(r["b_ra"] - prior) > 1e-9:
            leaks += 1
    print(f"profile season check: {disc:,} rows where prior and current season differ -> "
          f"{disc - leaks:,} use the PRIOR season, {leaks} do not")
    return bad == 0 and leaks == 0 and disc > 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.verify:
        sys.exit(0 if verify() else 1)
    build()
