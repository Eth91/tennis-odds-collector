#!/usr/bin/env python3
"""proj-1.1 features (NBA_PROJ11_PREREG.md): one row of features per proj-1.0 row, by family F0..F6.

Point in time: every F1-F6 value for a game on date d comes from the player's (or team's) games on earlier
dates. Each family column is an EWMA over his previous appearances (half-life 15), shrunk toward his position
group's league rate from earlier dates, and entered as log(rate / group rate). F0 is availability: who is
missing from the box score and who starts. Those "this game" inputs are the pre-registered optimistic proxy
for what is known at tip − 30. They use lineup status and box-score presence only, never minutes or stats.
"""
from collections import defaultdict, deque

import numpy as np

import nba_stats_fetch as F

HL, HL_TEAM = 15, 10
K_MIN, K_ATT = 100.0, 20.0               # pseudo-minutes (rates, minute-weighted shares); pseudo-attempts (FG%)
REG_GAMES, REG_MIN = 7, 24.0

# family -> [(kind, column, mode)]; mode: "rate" per minute, "wavg" minute-weighted average,
# ("ratio", made_column) for a made/attempted ratio whose attempts are `column`
SPECS = {
    "F1": [("adv", c, "wavg") for c in ("USG_PCT", "AST_PCT", "OREB_PCT", "DREB_PCT", "TM_TOV_PCT", "PIE")]
          + [("adv", "POSS", "rate")]
          + [("usage", c, "wavg") for c in ("PCT_FGA", "PCT_FG3A", "PCT_FTA", "PCT_AST", "PCT_REB", "PCT_TOV",
                                            "PCT_STL", "PCT_BLK", "PCT_PTS")],
    "F2": [("pt_Possessions", c, "rate") for c in ("TOUCHES", "FRONT_CT_TOUCHES", "TIME_OF_POSS")]
          + [("pt_Drives", c, "rate") for c in ("DRIVES", "DRIVE_FGA", "DRIVE_PASSES", "DRIVE_TOV")]
          + [("pt_Passing", c, "rate") for c in ("PASSES_MADE", "POTENTIAL_AST", "SECONDARY_AST", "FT_AST")]
          + [("pt_Rebounding", c, "rate") for c in ("REB_CHANCES", "OREB_CHANCES", "DREB_CHANCES", "REB_CONTEST")]
          + [("pt_CatchShoot", c, "rate") for c in ("CATCH_SHOOT_FGA", "CATCH_SHOOT_FG3A")]
          + [("pt_PullUpShot", c, "rate") for c in ("PULL_UP_FGA", "PULL_UP_FG3A")]
          + [("pt_ElbowTouch", "ELBOW_TOUCHES", "rate"), ("pt_PostTouch", "POST_TOUCHES", "rate"),
             ("pt_PaintTouch", "PAINT_TOUCHES", "rate"), ("pt_SpeedDistance", "DIST_MILES", "rate")],
    "F3": [("shotloc", z + "_FGA", "rate") for z in ("RA", "PAINT", "MID", "C3", "AB3")]
          + [("shotloc", z + "_FGA", ("ratio", z + "_FGM")) for z in ("RA", "PAINT", "MID", "C3", "AB3")]
          + [("scoring", c, "wavg") for c in ("PCT_PTS_2PT_MR", "PCT_PTS_3PT", "PCT_PTS_FB", "PCT_PTS_FT",
                                              "PCT_PTS_PAINT", "PCT_AST_FGM", "PCT_UAST_FGM")],
    "F4": [("hustle", c, "rate") for c in ("DEFLECTIONS", "CONTESTED_SHOTS", "LOOSE_BALLS_RECOVERED",
                                            "SCREEN_ASSISTS", "BOX_OUTS", "CHARGES_DRAWN")]
          + [("defense", c, "wavg") for c in ("PCT_STL", "PCT_BLK", "DEF_RATING")]
          + [("pt_Defense", "DEF_RIM_FGA", "rate"), ("pt_Defense", "DEF_RIM_FGA", ("ratio", "DEF_RIM_FGM"))],
    "F6": [("misc", c, "rate") for c in ("PTS_OFF_TOV", "PTS_2ND_CHANCE", "PTS_FB", "PTS_PAINT")]
          + [("pt_Efficiency", c, "rate") for c in ("DRIVE_PTS", "CATCH_SHOOT_PTS", "PULL_UP_PTS",
                                                    "PAINT_TOUCH_PTS", "POST_TOUCH_PTS", "ELBOW_TOUCH_PTS")],
}
TEAM_SPECS = {"team_adv": ("PACE", "OFF_RATING", "DEF_RATING"),
              "team_opp": ("OPP_FGA", "OPP_FG3A", "OPP_REB", "OPP_AST", "OPP_TOV")}
# NBA.com shot-location zone names -> short names (corner 3 = left + right)
ZONES = {"Restricted Area": "RA", "In The Paint (Non-RA)": "PAINT", "Mid-Range": "MID",
         "Left Corner 3": "C3", "Right Corner 3": "C3", "Above the Break 3": "AB3"}


def _table(j):
    """(columns, rows) of a stats.nba.com response; shot-location headers are flattened as ZONE_FGM / ZONE_FGA."""
    rs = j["resultSets"]
    rs = rs[0] if isinstance(rs, list) else rs
    hdr = rs["headers"]
    if hdr and isinstance(hdr[0], dict):                            # shot locations: grouped headers
        groups, cols = hdr[0]["columnNames"], hdr[-1]["columnNames"]
        span = hdr[0].get("columnsToSkip", 0)
        out, gi = [], 0
        for k, c in enumerate(cols):
            if k < span:
                out.append(c)
            else:
                g = groups[(k - span) // 3] if (k - span) // 3 < len(groups) else "?"
                out.append(f"{ZONES.get(g, g)}_{c}")
        return out, rs["rowSet"]
    return hdr, rs["rowSet"]


def parse_player_kind(kind, raw):
    """{(date, pid): {column: value}} for one player-level kind; zone columns summed (corner 3 = left + right)."""
    out = {}
    for d, j in raw.items():
        cols, rows = _table(j)
        ix = defaultdict(list)
        for k, c in enumerate(cols):
            ix[c].append(k)
        pk = ix["PLAYER_ID"][0]
        for r in rows:
            rec = {}
            for c, ks in ix.items():
                vals = [r[k] for k in ks if isinstance(r[k], (int, float))]
                if vals:
                    rec[c] = float(sum(vals)) if len(ks) > 1 else float(vals[0])
            out[(d, int(r[pk]))] = rec
    return out


def parse_team_kind(raw, abbr_of):
    out = {}
    for d, j in raw.items():
        cols, rows = _table(j)
        ix = {c: k for k, c in enumerate(cols)}
        for r in rows:
            ab = abbr_of.get(int(r[ix["TEAM_ID"]]))
            if ab:
                out[(d, ab)] = {c: float(r[k]) for c, k in ix.items() if isinstance(r[k], (int, float))}
    return out


def team_abbrs(raw_starters):
    out = {}
    for j in raw_starters.values():
        cols, rows = _table(j)
        ix = {c: k for k, c in enumerate(cols)}
        for r in rows:
            out[int(r[ix["TEAM_ID"]])] = r[ix["TEAM_ABBREVIATION"]]
    return out


def starters_of(raw_starters):
    s = set()
    for d, j in raw_starters.items():
        cols, rows = _table(j)
        k = cols.index("PLAYER_ID")
        s |= {(d, int(r[k])) for r in rows}
    return s, set(raw_starters)


def kinds_for(families):
    """The fetch kinds a set of families reads (F0 and F5 need the starters feed: starts, and team ids)."""
    k = {kind for f in families if f in SPECS for kind, _, _ in SPECS[f]}
    if "F5" in families:
        k |= set(TEAM_SPECS)
    if "F0" in families or "F5" in families:
        k.add("starters")
    return k


def build(rows, raw=None, families=("F0", "F1", "F2", "F3", "F4", "F5", "F6")):
    """(X float32 [n_rows, n_features], names, family of each feature, report). raw: {kind: {date: json}} —
    loaded from nba_stats_fetch's store when None. Rows in any order; computed by date.
    A row with target=True (a game not played yet, live) gets features from earlier dates and never updates any
    state; its F0 same-game proxy columns are NaN, to be filled from the live lineups and injury report."""
    raw = raw if raw is not None else {k: F.load(k) for k in kinds_for(families)}
    n = len(rows)
    order = sorted(range(n), key=lambda i: rows[i]["date"])
    by_date = defaultdict(list)
    for i in order:
        by_date[rows[i]["date"]].append(i)
    pids = sorted({r["pid"] for r in rows})
    pix = {p: k for k, p in enumerate(pids)}
    grp = {"G": 0, "F": 1, "C": 2}
    cols_out, fams, blocks, report = [], [], [], {"missing_columns": {}, "coverage": {}}
    dec = 0.5 ** (1 / HL)

    for fam in families:
        if fam in ("F0", "F5"):
            continue
        spec = SPECS[fam]
        parsed = {k: parse_player_kind(k, raw.get(k, {})) for k in sorted({s[0] for s in spec})}
        seen_cols = {k: set().union(*[set(v) for v in p.values()]) if p else set() for k, p in parsed.items()}
        spec_ok = []
        for kind, col, mode in spec:
            need = [col] + ([mode[1]] if isinstance(mode, tuple) else [])
            miss = [c for c in need if c not in seen_cols[kind]]
            if miss:
                report["missing_columns"].setdefault(fam, []).append(f"{kind}.{'/'.join(miss)}")
            else:
                spec_ok.append((kind, col, mode))
        C = len(spec_ok)
        if not C:
            continue
        Sn = np.zeros((len(pids), C)); Sd = np.zeros((len(pids), C))
        Ln = np.zeros((3, C)); Ld = np.zeros((3, C))
        X = np.zeros((n, C), np.float32)
        miss_flag = np.zeros(n, np.float32)
        kmode = np.array([K_ATT if isinstance(m, tuple) else K_MIN for _, _, m in spec_ok])
        cov = [0, 0]
        for d in sorted(by_date):
            ii = by_date[d]
            p = np.array([pix[rows[i]["pid"]] for i in ii]); g = np.array([grp.get(rows[i]["group"], 1) for i in ii])
            prior = np.where(Ld[g] > 0, Ln[g] / np.where(Ld[g] > 0, Ld[g], 1), 0.0)
            rate = (Sn[p] + kmode * prior) / (Sd[p] + kmode)
            eps = 1e-6 + 0.01 * np.abs(prior)
            X[ii] = np.log((np.abs(rate) + eps) / (np.abs(prior) + eps))
            miss_flag[ii] = (Sd[p].sum(1) == 0)
            # update: decay every appearance; add values where the feed has the player-game
            Sn[p] *= dec; Sd[p] *= dec
            for k, i in enumerate(ii):
                r = rows[i]
                if r.get("target"):
                    continue
                num, den = np.zeros(C), np.zeros(C)
                got = False
                for c, (kind, col, mode) in enumerate(spec_ok):
                    rec = parsed[kind].get((d, r["pid"]))
                    if rec is None:
                        if kind == "pt_Rebounding" and r["min"] > 0:        # the feed omits zero-chance games
                            den[c] = r["min"]
                        continue
                    got = True
                    v = rec.get(col)
                    if v is None:
                        continue
                    if mode == "rate":
                        num[c], den[c] = v, r["min"]
                    elif mode == "wavg":
                        num[c], den[c] = v * r["min"], r["min"]
                    else:
                        num[c], den[c] = rec.get(mode[1], 0.0), v
                cov[0] += got; cov[1] += 1
                Sn[p[k]] += num; Sd[p[k]] += den
                Ln[g[k]] += num; Ld[g[k]] += den
        report["coverage"][fam] = round(cov[0] / max(cov[1], 1), 4)
        names = [f"{fam}:{kind}.{col}" + (".pct" if isinstance(mode, tuple) else "") for kind, col, mode in spec_ok]
        blocks += [X, miss_flag[:, None]]
        cols_out += names + [f"{fam}:missing"]
        fams += [fam] * (C + 1)

    if "F5" in families:
        abbr = team_abbrs(raw.get("starters", {}))
        tp = {k: parse_team_kind(raw.get(k, {}), abbr) for k in TEAM_SPECS}
        tcols = [(k, c) for k, cs in TEAM_SPECS.items() for c in cs]
        teams = sorted({r["team"] for r in rows} | {r["opp"] for r in rows})
        tix = {t: k for k, t in enumerate(teams)}
        Tn = np.zeros((len(teams), len(tcols))); Td = np.zeros((len(teams), len(tcols)))
        Lg = np.zeros(len(tcols)); Lc = 0.0
        dt_ = 0.5 ** (1 / HL_TEAM)
        X = np.zeros((n, 2 * len(tcols)), np.float32)
        miss = np.zeros(n, np.float32)
        cov = [0, 0]
        for d in sorted(by_date):
            ii = by_date[d]
            lg = Lg / Lc if Lc else np.zeros(len(tcols))
            eps = 1e-6 + 0.01 * np.abs(lg)
            for i in ii:
                for side, t in ((0, rows[i]["team"]), (1, rows[i]["opp"])):
                    q = tix[t]
                    v = (Tn[q] + 3 * lg) / (Td[q] + 3)
                    X[i, side * len(tcols):(side + 1) * len(tcols)] = np.log((np.abs(v) + eps) / (np.abs(lg) + eps))
                    miss[i] = max(miss[i], float(Td[q].sum() == 0))
            for t in {rows[i]["team"] for i in ii}:
                recs = [tp[k].get((d, t)) for k in TEAM_SPECS]
                cov[1] += 1
                if all(r is not None for r in recs):
                    cov[0] += 1
                    vals = np.array([tp[k][(d, t)].get(c, np.nan) for k, c in tcols])
                    if np.isfinite(vals).all():
                        q = tix[t]
                        Tn[q] = Tn[q] * dt_ + vals; Td[q] = Td[q] * dt_ + 1
                        Lg += vals; Lc += 1
        report["coverage"]["F5"] = round(cov[0] / max(cov[1], 1), 4)
        blocks += [X, miss[:, None]]
        cols_out += [f"F5:{'own' if s == 0 else 'opp'}.{k}.{c}" for s in (0, 1) for k, c in tcols] + ["F5:missing"]
        fams += ["F5"] * (2 * len(tcols) + 1)

    if "F0" in families:
        X0, n0 = f0_features(rows, by_date, raw.get("starters", {}), report)
        blocks.insert(0, X0)
        cols_out = n0 + cols_out
        fams = ["F0"] * len(n0) + fams
    X = np.concatenate(blocks, 1).astype(np.float32) if blocks else np.zeros((n, 0), np.float32)
    return X, cols_out, fams, report


F0_PROXY = ("F0:starts_today", "F0:starts_x_minshare", "F0:mates_out_n", "F0:mates_out_min", "F0:mates_out_usg",
            "F0:opp_out_n", "F0:opp_out_usg", "F0:mates_out_usg_x_usg", "F0:starts_missing")


def f0_features(rows, by_date, raw_starters, report):
    """Availability and lineups. Same-game inputs (the proxy): starts today (the starters feed) and which
    regulars are absent from the box score. History inputs: his start share and minute share over his last 10
    appearances, his usage share over his team's last 10 games."""
    starters, dates_with = starters_of(raw_starters)
    n = len(rows)
    names = ["F0:starts_today", "F0:starts_missing", "F0:start_share10", "F0:min_share10", "F0:usg_share10",
             "F0:starts_x_minshare", "F0:mates_out_n", "F0:mates_out_min", "F0:mates_out_usg",
             "F0:opp_out_n", "F0:opp_out_usg", "F0:mates_out_usg_x_usg"]
    X = np.zeros((n, len(names)), np.float32)
    last_app = defaultdict(lambda: deque(maxlen=10))        # pid -> (started, minutes)
    team_hist = defaultdict(lambda: deque(maxlen=10))       # team -> [{pid: (min, usage)}]
    games = defaultdict(lambda: defaultdict(list))          # date -> team -> row indices
    for d, ii in by_date.items():
        for i in ii:
            games[d][rows[i]["team"]].append(i)

    def regs(team):
        h = team_hist[team]
        if len(h) < 10:
            return {}
        played = defaultdict(list)
        for g in h:
            for pid, (mn, u) in g.items():
                played[pid].append((mn, u))
        tot_u = sum(u for g in h for (_, u) in g.values()) / len(h)
        return {pid: (np.mean([m for m, _ in v]), np.mean([u for _, u in v]) / tot_u if tot_u else 0.0)
                for pid, v in played.items() if len(v) >= REG_GAMES and np.mean([m for m, _ in v]) >= REG_MIN}

    regulars = {}
    for d in sorted(by_date):
        out_info = {}
        for team, ii in games[d].items():
            here = {rows[i]["pid"] for i in ii if not rows[i].get("target")}
            if all(rows[i].get("target") for i in ii):
                regulars[team] = regs(team)                   # live: the team's regulars as of this date
            rg = regs(team)
            out = {p: v for p, v in rg.items() if p not in here}
            out_info[team] = (len(out), sum(m for m, _ in out.values()) / 240.0, sum(u for _, u in out.values()))
        for team, ii in games[d].items():
            opp = rows[ii[0]]["opp"]
            mo, oo = out_info.get(team, (0, 0.0, 0.0)), out_info.get(opp, (0, 0.0, 0.0))
            h = team_hist[team]
            tot_u = (sum(u for g in h for (_, u) in g.values()) / len(h)) if h else 0.0
            for i in ii:
                r = rows[i]
                la = last_app[r["pid"]]
                st_known = d in dates_with
                st = float((d, r["pid"]) in starters) if st_known else 0.0
                ss = np.mean([s for s, _ in la]) if la else 0.0
                ms = np.mean([m for _, m in la]) / 48.0 if la else 0.0
                us = (np.mean([g[r["pid"]][1] for g in h if r["pid"] in g]) / tot_u) if tot_u and any(r["pid"] in g for g in h) else 0.0
                X[i] = [st, 0.0 if st_known else 1.0, ss, ms, us, st * ms, mo[0], mo[1], mo[2], oo[0], oo[2], mo[2] * us]
                if r.get("target"):
                    X[i, [names.index(c) for c in F0_PROXY]] = np.nan
        # update after the date
        for team, ii in games[d].items():
            ii = [i for i in ii if not rows[i].get("target")]
            if not ii:
                continue
            team_hist[team].append({rows[i]["pid"]: (rows[i]["min"], rows[i]["fga"] + 0.44 * rows[i]["fta"] + rows[i]["tov"])
                                    for i in ii})
            for i in ii:
                last_app[rows[i]["pid"]].append((float((d, rows[i]["pid"]) in starters), rows[i]["min"]))
    report["coverage"]["F0_starters"] = round(len(dates_with & set(by_date)) / max(len(by_date), 1), 4)
    report["regulars"] = regulars
    return X, names
