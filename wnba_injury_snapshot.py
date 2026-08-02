"""wnba_injuries_board.json — SINGLE writer for the board's 🏥 injury section.

Called from wnba_alert (fullscan, fetching glog) AND wnba_watch (25s scratch poll,
cache-only glog) so the section live-updates as players go on/off the report or
@UnderdogWNBA rules someone out. One module so the two callers cannot drift.

Merge order: official-report cache rows first (they carry the injury reason and survive
overnight when the live precedence narrows), live rulings overlaid — a fresh ruling beats
a 16h-old report line. Impact filter is the scan's exact gate: >=20 mpg OR >=10 ppg.
n_without = games the player's team played without them (union of top-5 teammates' logs).
"""
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "wnba_injuries_board.json"


def cached_glog(pid):
    """Game log from wnba_wowy's DISK CACHE only — never the network. Safe for the 25s
    watch path: a cache miss costs a blank n-badge, not a fetch storm."""
    try:
        import wnba_wowy as W
        ent = W._glog_load().get(str(pid))
        return (ent or {}).get("log") or []
    except Exception:                                             # noqa: BLE001
        return []


def write_snapshot(pl, inj, glog_fn):
    """pl = wnba_wowy.players() dict; inj = merged live statuses {name: status};
    glog_fn(pid) -> game-log rows (may be cache-only). Returns row count or None."""
    try:
        merged = {}
        rep_stamp = ""
        try:
            rc = json.loads((HERE / "wnba_injury_report_cache.json").read_text())
            rep_stamp = str(rc.get("stamp") or "")
            for rr in rc.get("rows") or []:
                rsn = str(rr.get("reason") or "")
                rsn = rsn.replace("Injury/Illness - ", "").replace("; -", "").strip(" ;-")
                merged[rr.get("player")] = {"status": str(rr.get("status") or ""),
                                            "reason": rsn, "src": "report"}
        except Exception:                                         # noqa: BLE001
            pass
        for nm, stt in (inj or {}).items():
            prev = merged.get(nm) or {}
            merged[nm] = {"status": str(stt), "reason": prev.get("reason", ""),
                          "src": "live"}

        team_dates = {}

        def tdates(tm):
            if tm not in team_dates:
                mates = sorted((v for v in pl.values()
                                if v.get("team") == tm and (v.get("gp") or 0) >= 3),
                               key=lambda v: -(v.get("min") or 0))[:5]
                ds = set()
                for v in mates:
                    for g in glog_fn(v["id"]) or []:
                        if g.get("date"):
                            ds.add(g["date"][:10])
                team_dates[tm] = ds
            return team_dates[tm]

        snap = []
        for nm, rec in merged.items():
            v = pl.get(nm)
            if not v or not ((v.get("min") or 0) >= 20 or (v.get("pts") or 0) >= 10):
                continue
            nw = None
            try:
                mine = {g["date"][:10] for g in glog_fn(v["id"]) or [] if g.get("date")}
                td = tdates(v.get("team"))
                if td:
                    nw = len(td - mine)
            except Exception:                                     # noqa: BLE001
                nw = None
            snap.append({"player": nm, "team": v.get("team"), "status": rec["status"],
                         "reason": rec.get("reason", ""), "src": rec.get("src", ""),
                         "mpg": round(v.get("min") or 0, 1),
                         "ppg": round(v.get("pts") or 0, 1), "n_without": nw})
        snap.sort(key=lambda r: (0 if r["status"].lower().startswith(("out", "doubt")) else 1,
                                 r["team"] or "", -(r["mpg"] or 0)))
        tmp = OUT.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                   "report_stamp": rep_stamp, "rows": snap}))
        tmp.replace(OUT)                    # atomic: the 20s baker must never read a torn file
        return len(snap)
    except Exception as e:                                        # noqa: BLE001
        print(f"injury snapshot skipped: {e}")
        return None
