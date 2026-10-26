#!/usr/bin/env python3
"""proj-1.1, live and shadow only (NBA_PROJ11_PREREG.md, Prospective). Nothing here is a pick, and nothing is
shown as one: forecasts are logged beside proj-1.0's at the same cutoff, under their own version, and graded
nightly against results, FanDuel's close and proj-1.0.

Two jobs:
  --refresh   heavy, when box scores change: proj-1.0's means, the family features up to yesterday for every
              slate player, the ridge weights for the slate's month (rows before that month), the analog pool
              rebuilt around proj-1.1's means. Writes nba_proj11_cache.pkl.
  --forecast  light, every few minutes: F0's game-day inputs from the latest lineup snapshot
              (nba_lineups.sqlite, Expected or Confirmed) and the latest official report status
              (nba_news.sqlite), both as seen now. Then μ', the joint draws, and the probabilities at the
              board's main lines. Logged until tip − 30 min.
  --prospective OUT_JSON  nightly: grade proj-1.1's record and compare it with proj-1.0 on the same props.
The candidate's families, λ and blend weight come from nba_proj11_config.json, written from the development
run (PROJ11_RESULTS.json) by --write-config. Nothing is chosen here.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import pickle
import sqlite3
import zlib
from pathlib import Path

import numpy as np

import nba_proj11 as P
import nba_proj11_feat as FT
import nba_proj_data as PD
import nba_project as NP

VERSION = "proj-1.1-dev"
HERE = PD.HERE
CONFIG = HERE / "nba_proj11_config.json"
CACHE = HERE / "nba_proj11_cache.pkl"
LINEUPS = HERE / "nba_lineups.sqlite"
NEWS = HERE / "nba_news.sqlite"
LOG = HERE / "nba_proj_log.sqlite"
PROPS = Path(os.environ.get("NBA_PROPS_JSON", "/home/ubuntu/tennis-odds-collector/docs/nba_props.json"))
OUT_STATUSES = ("Out", "Doubtful")
NEED, REPLICATE = 2000, 2000


def write_config(results=P.OUT_JSON, path=CONFIG):
    """The candidate (A_keep) as the development run chose it: kept families, λ, its 2023-24 blend weight."""
    r = json.loads(Path(results).read_text())
    cfg = {"kept": r["kept"], "lambda": r["lambda"]["chosen"], "blend_w": r["blend_w"].get("A_keep", NP.PROJ_BLEND_W),
           "from": f"{Path(results).name} generated {r['generated_at']}"}
    Path(path).write_text(json.dumps(cfg, indent=1))
    return cfg


def load_config(path=CONFIG):
    cfg = json.loads(Path(path).read_text())
    cfg["hash"] = hashlib.sha1(json.dumps({k: cfg[k] for k in ("kept", "lambda", "blend_w")}, sort_keys=True)
                               .encode()).hexdigest()[:10]
    cfg["version"] = f"{VERSION}:{cfg['hash']}"
    return cfg


def _load(cache):
    try:
        return pickle.loads(Path(cache).read_bytes())
    except (OSError, pickle.UnpicklingError, EOFError):
        return None


def refresh11(targets, rows=None, raw=None, cfg=None, cache=CACHE, force=False):
    """Build nba_proj11_cache.pkl for `targets` (dicts: gid, date, pid, team, opp, home). Returns a status line."""
    cfg = cfg or load_config()
    if not cfg["kept"]:
        return "no family was kept by the development run: proj-1.1 has nothing to run"
    raw_m = os.path.getmtime(FT.F.RAW) if raw is None and FT.F.RAW.exists() else 0
    key = (NP._cache_key(NP.GAMELOGS, NP.MATCHUP), raw_m, cfg["hash"])
    want = {(t["gid"], t["pid"]): t for t in targets}
    old = _load(cache)
    if not force and old and old.get("key") == key and set(want) <= set(old["at"]):
        return f"cache current ({len(old['at'])} players)"
    if rows is None:
        rows, _, pos = PD.load_box(NP.GAMELOGS, NP.MATCHUP, NP.PROFILES)
    else:
        pos = {}
    grp = {r["pid"]: r["group"] for r in rows}
    keys = sorted(want)
    slate = [dict(want[k], season=PD.season_of(want[k]["date"]),
                  group=grp.get(want[k]["pid"]) or PD.group_of(pos.get(want[k]["pid"])) or "F") for k in keys]
    out, ot = NP.walk(rows, NP.PROJ_CONFIG, targets=slate, consts=NP.PROJ_CONSTS)
    mu_h, mu_t = np.array([o["m1"] for o in out]), np.array([o["m1"] for o in ot])
    nh_h, rs_h = np.array([o["n_hist"] for o in out], float), np.array([o["rest"] for o in out], float)
    trows = [dict(t, min=0.0, pts=0.0, reb=0.0, ast=0.0, fg3m=0.0, stl=0.0, blk=0.0, tov=0.0, fga=0.0, fta=0.0,
                  team_poss=0.0, name="", target=True) for t in slate]
    X, names, fams, rep = FT.build(rows + trows, raw)
    fams, names = np.array(fams), list(names)
    cols = np.isin(fams, cfg["kept"])
    kn = [n for n, c in zip(names, cols) if c]
    Xh, Xt = X[:len(rows)][:, cols].astype(float), X[len(rows):][:, cols].astype(float)
    full_t = X[len(rows):]
    Y = np.array([[r[s] for s in NP.STATS] for r in rows], float)
    Y[:, 0] = np.round(Y[:, 0])
    run = type("R", (), {"mu": {"m1": mu_h}, "Y": Y})()
    R = P.residual_targets(run)
    date = np.array([r["date"] for r in rows])
    mu_p = P.apply_residual(mu_h, P.residual_walk(date, Xh, R, cfg["lambda"]))
    month = min(t["date"] for t in slate)[:7] + "-01"
    wmu, wsd, W = P.fit_weights(Xh, R, date < month, cfg["lambda"])
    first = min(t["date"] for t in slate)
    lo = (dt.date.fromisoformat(first) - dt.timedelta(days=NP.POOL_DAYS)).isoformat()
    pool = (date >= lo) & (date < first)
    hist = np.array([r["season"] == "2022-23" for r in rows])
    f22 = NP.features(mu_p[hist], nh_h[hist], rs_h[hist], NP.PROJ_CONFIG)
    scale = np.where(f22.std(0) > 0, f22.std(0), 1.0)
    pick = lambda n: full_t[:, names.index(n)].astype(float)
    obj = {"key": key, "version": cfg["version"], "at": {k: j for j, k in enumerate(keys)}, "slate": slate,
           "mu10": mu_t, "n_hist": [o["n_hist"] for o in ot], "rest": [o["rest"] for o in ot],
           "X": Xt, "names": kn, "wmu": wmu, "wsd": wsd, "W": W, "month": month,
           "share": {"start": pick("F0:start_share10"), "min": pick("F0:min_share10"), "usg": pick("F0:usg_share10")}
           if "F0" in cfg["kept"] else None,
           "regulars": rep.get("regulars", {}), "pool_mu": mu_p[pool], "pool_y": Y[pool],
           "pool_f": NP.features(mu_p[pool], nh_h[pool], rs_h[pool], NP.PROJ_CONFIG), "scale": scale,
           "through": max(r["date"] for r in rows), "coverage": rep.get("coverage"),
           "made_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    tmp = Path(str(cache) + ".tmp")
    tmp.write_bytes(pickle.dumps(obj))
    os.replace(tmp, cache)
    return f"projected {len(keys)} players ({cfg['version']}), box scores through {obj['through']}"


def latest_lineups(db, now):
    """{(gid, team): {"starters": set, "inactive": set, "status": str}} from the newest snapshot of each ET date seen
    at or before `now`. Empty when there is none."""
    out = {}
    if not Path(db).exists():
        return out
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    stamp = now.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    for (d,) in con.execute("SELECT DISTINCT date_et FROM snaps WHERE fetched_at <= ?", (stamp,)).fetchall():
        b = con.execute("SELECT body FROM snaps WHERE date_et = ? AND fetched_at <= ? ORDER BY fetched_at DESC LIMIT 1",
                        (d, stamp)).fetchone()
        for g in json.loads(zlib.decompress(b[0])).get("games", []):
            for side in ("homeTeam", "awayTeam"):
                t = g[side]
                st = {p["personId"] for p in t["players"] if p.get("position")}
                stat = {p.get("lineupStatus") for p in t["players"] if p.get("position")}
                out[(g["gameId"], t["teamAbbreviation"])] = {
                    "starters": st, "inactive": {p["personId"] for p in t["players"] if p.get("rosterStatus") == "Inactive"},
                    "status": "Confirmed" if stat == {"Confirmed"} else ("Expected" if st else "none")}
    return out


def latest_status(db, now, dates):
    """{(game_date, team, pid): status}: the newest official report entry published at or before `now`."""
    out = {}
    if not Path(db).exists() or not dates:
        return out
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    stamp = now.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    q = (f"SELECT game_date, team, pid, status FROM snapshots WHERE pid IS NOT NULL AND published_at <= ? "
         f"AND game_date IN ({','.join('?' * len(dates))}) ORDER BY published_at")
    for d, team, pid, status in con.execute(q, [stamp, *sorted(dates)]):
        out[(d, team, int(pid))] = status
    return out


def live_inputs(hit, lineups, status):
    """F0's game-day columns for every cached target, and what they rest on (for the audit table)."""
    names = hit["names"]
    Xt = hit["X"].copy()
    audit = []
    if hit.get("share") is None:
        return Xt, audit
    col = {n: names.index(n) for n in FT.F0_PROXY if n in names}

    def outs(team, date, gid):
        lu = lineups.get((gid, team))
        o = {}
        for p, (m, u) in hit["regulars"].get(team, {}).items():
            st = status.get((date, team, p))
            if st in OUT_STATUSES or (lu and p in lu["inactive"]):
                o[p] = (m, u)
        return o
    for j, t in enumerate(hit["slate"]):
        lu = lineups.get((t["gid"], t["team"]))
        mo, oo = outs(t["team"], t["date"], t["gid"]), outs(t["opp"], t["date"], t["gid"])
        ss, ms, us = (float(hit["share"][k][j]) for k in ("start", "min", "usg"))
        starts = (1.0 if t["pid"] in lu["starters"] else 0.0) if lu and lu["starters"] else ss   # unknown: his start share
        mo_u = sum(u for _, u in mo.values())
        vals = {"F0:starts_today": starts, "F0:starts_missing": 0.0, "F0:starts_x_minshare": starts * ms,
                "F0:mates_out_n": float(len(mo)), "F0:mates_out_min": sum(m for m, _ in mo.values()) / 240.0,
                "F0:mates_out_usg": mo_u, "F0:opp_out_n": float(len(oo)), "F0:opp_out_usg": sum(u for _, u in oo.values()),
                "F0:mates_out_usg_x_usg": mo_u * us}
        for n, k in col.items():
            Xt[j, k] = vals[n]
        audit.append((t["gid"], t["pid"], lu["status"] if lu else "none", starts, len(mo), len(oo)))
    return Xt, audit


def forecast11(now=None, cfg=None, cache=CACHE, lineups_db=LINEUPS, news_db=NEWS, log_db=LOG, props_path=PROPS):
    """Log proj-1.1 forecasts for the board's main lines (FanDuel, else DraftKings) until tip − 30 min."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cfg = cfg or load_config()
    hit = _load(cache)
    if hit is None or hit.get("version") != cfg["version"]:
        return "no proj-1.1 cache for this config yet (nba_proj11_live.py --refresh)"
    payload = json.loads(Path(props_path).read_text())
    gmap = {g["gid"]: g for g in payload.get("games", [])}
    lineups = latest_lineups(lineups_db, now)
    status = latest_status(news_db, now, {t["date"] for t in hit["slate"]})
    Xt, audit = live_inputs(hit, lineups, status)
    f = ((Xt - hit["wmu"]) / hit["wsd"]) @ hit["W"]
    mu = P.apply_residual(hit["mu10"], f)
    tf = NP.features(mu, np.array(hit["n_hist"], float), np.array(hit["rest"], float), NP.PROJ_CONFIG)
    nb = NP.neighbors(tf, hit["pool_f"], NP.PROJ_CONFIG["K"], hit["scale"])
    d = NP.Dist(mu, hit["pool_mu"], hit["pool_y"], nb)
    items = []
    for p in payload.get("props", []):
        j = hit["at"].get((p["gid"], p["pid"]))
        g = gmap.get(p["gid"])
        bk = next((b for b in ("fd", "dk") if (p["books"].get(b) or {}).get("main") is not None), None)
        if j is None or g is None or bk is None or p["market"] not in PD.MARKET_PARTS:
            continue
        line = p["books"][bk]["main"]
        r = next((r for r in p["books"][bk]["rungs"] if r[0] == line), None)
        if not r or not r[1] or not r[2]:
            continue
        sub = NP.Dist.__new__(NP.Dist)
        sub.vals, sub.mu = d.vals[j:j + 1], d.mu[j:j + 1]
        po, pu, pp = sub.probs(p["market"], [line])
        pc = float(po[0] / max(po[0] + pu[0], 1e-9))
        items.append({"gid": p["gid"], "pid": p["pid"], "market": p["market"], "tip": g.get("utc"), "line": line,
                      "book": bk, "over": r[1], "under": r[2], "p_over": pc, "p_push": float(pp[0]),
                      "p_blend": float(NP.blend(np.array([pc]), np.array([NP.no_vig(r[1], r[2])]), cfg["blend_w"])[0]),
                      "mean": round(float(sub.mean(p["market"])[0]), 2)})
    n = NP.log_forecasts(log_db, items, now, version=cfg["version"])
    _log_inputs(log_db, audit, now, cfg["version"], {(it["gid"], it["pid"]) for it in items}, gmap)
    return f"logged {n} forecasts ({cfg['version']}); lineups seen for {sum(1 for a in audit if a[2] != 'none')} of {len(audit)} players"


def _log_inputs(db, audit, now, version, keep, gmap):
    """What F0 rested on, per player, at the last build before the cutoff (same rule as the forecasts)."""
    con = sqlite3.connect(db, timeout=30)
    con.execute("CREATE TABLE IF NOT EXISTS p11_inputs (gid TEXT, pid INTEGER, version TEXT, logged_at TEXT, "
                "lineup TEXT, starts REAL, mates_out INTEGER, opp_out INTEGER, PRIMARY KEY (gid, pid, version))")
    stamp = now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    for gid, pid, lu, st, mo, oo in audit:
        g = gmap.get(gid)
        if (gid, pid) not in keep or g is None:
            continue
        tip = dt.datetime.fromisoformat(str(g["utc"]).replace("Z", "+00:00"))
        if now >= tip - dt.timedelta(minutes=NP.CUTOFF_MIN):
            continue
        con.execute("INSERT OR REPLACE INTO p11_inputs VALUES (?,?,?,?,?,?,?,?)", (gid, pid, version, stamp, lu, st, mo, oo))
    con.commit()
    con.close()


def prospective11(out_json, cfg=None, log_db=LOG, lines_db=HERE / "nba_lines.sqlite", matchup_db=NP.MATCHUP):
    """proj-1.1's record graded as proj-1.0's is, plus the pre-registered decision lines: vs proj-1.0 on the same
    props and lines, and vs FanDuel's close, at >= 2,000 graded props, replicated on the next 2,000."""
    import nba_proj_eval as E
    cfg = cfg or load_config()
    r11, r10 = [], []
    out = E.prospective(log_db, lines_db, matchup_db, out_json, version=cfg["version"], recs_out=r11)
    E.prospective(log_db, lines_db, matchup_db, str(out_json) + ".p10.tmp", version=NP.VERSION, recs_out=r10)
    Path(str(out_json) + ".p10.tmp").unlink(missing_ok=True)
    k10 = {r["key"]: r for r in r10}
    pair = sorted([(r, k10[r["key"]]) for r in r11 if r["key"] in k10], key=lambda x: (x[0]["date"], x[0]["key"]))
    out["paired_with_proj10"] = len(pair)
    dec = {"proj11_minus_proj10": None, "proj11_minus_close": None, "replication": None}
    if pair:
        y = np.array([a["y"] for a, _ in pair])
        l11 = E.logloss(np.array([a["p"] for a, _ in pair]), y)
        l10 = E.logloss(np.array([b["p"] for _, b in pair]), y)
        dates = [a["date"] for a, _ in pair]
        out["proj11_minus_proj10"] = list(E.boot_ci(l11 - l10, dates, reps=1000))
    wc = sorted([r for r in r11 if r["pc"] is not None], key=lambda r: (r["date"], r["key"]))
    if len(wc) >= NEED:
        first, nxt = wc[:NEED], wc[NEED:NEED + REPLICATE]
        diff = lambda rr: E.logloss(np.array([r["p"] for r in rr]), np.array([r["y"] for r in rr])) - \
            E.logloss(np.array([r["pc"] for r in rr]), np.array([r["y"] for r in rr]))
        m, lo, hi = E.boot_ci(diff(first), [r["date"] for r in first], reps=1000)
        rel = E.reliability(np.array([r["p"] for r in first]), np.array([r["y"] for r in first]))
        rel_ok = all(abs(mf - ob) <= .03 for n, mf, ob in rel if n >= 200 and mf is not None)
        dec["proj11_minus_close"] = {"n": NEED, "mean": m, "lo": lo, "hi": hi, "reliability_ok": rel_ok}
        if len(nxt) >= REPLICATE:
            m2, lo2, hi2 = E.boot_ci(diff(nxt), [r["date"] for r in nxt], reps=1000)
            dec["replication"] = {"n": REPLICATE, "mean": m2, "lo": lo2, "hi": hi2}
    if len(pair) >= NEED:
        pp = pair[:NEED]
        y = np.array([a["y"] for a, _ in pp])
        m, lo, hi = E.boot_ci(E.logloss(np.array([a["p"] for a, _ in pp]), y) - E.logloss(np.array([b["p"] for _, b in pp]), y),
                              [a["date"] for a, _ in pp], reps=1000)
        dec["proj11_minus_proj10"] = {"n": NEED, "mean": m, "lo": lo, "hi": hi}
    beats = bool(dec["proj11_minus_close"] and dec["proj11_minus_close"]["hi"] < 0 and dec["proj11_minus_close"]["reliability_ok"]
                 and dec["replication"] and dec["replication"]["hi"] < 0)
    out["decisions"] = dec
    out["verdicts"] = [
        "proj-1.1 better than proj-1.0 (paired, FanDuel lines): " + (
            "not enough prospective evidence" if not isinstance(dec["proj11_minus_proj10"], dict) else
            ("YES" if dec["proj11_minus_proj10"]["hi"] < 0 else "NO")),
        "proj-1.1 beats FanDuel's close (model alone, then replicated): " + (
            "not enough prospective evidence" if not dec["proj11_minus_close"] else
            ("YES" if beats else ("NO" if dec["replication"] or dec["proj11_minus_close"]["hi"] >= 0 else
                                  "first 2,000 pass; waiting on the replication sample")))]
    out["config"] = {k: cfg[k] for k in ("kept", "lambda", "blend_w", "hash")}
    Path(out_json).write_text(json.dumps(out, default=float))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-config", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--forecast", action="store_true")
    ap.add_argument("--prospective", metavar="OUT_JSON")
    a = ap.parse_args()
    if a.write_config:
        print("nba_proj11_live --write-config:", write_config())
    if a.refresh:
        targets, rows = NP.slate_targets()
        print("nba_proj11_live --refresh:", refresh11(targets, rows=rows, force=a.force))
    if a.forecast:
        print("nba_proj11_live --forecast:", forecast11())
    if a.prospective:
        o = prospective11(a.prospective)
        print("nba_proj11_live --prospective:", {k: o.get(k) for k in ("graded", "paired_with_proj10", "verdicts")})


if __name__ == "__main__":
    main()
