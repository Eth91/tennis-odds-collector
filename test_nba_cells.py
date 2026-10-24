"""Amendment 8: the STALE-LINE / GAP / MINUTES-BAND cells, forward only. MUTANTS in test_mutants()."""
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_clv as V
import nba_flags as F

TIP = "2026-01-10T00:00:00"
CUT = "2026-01-09T12:00:00"


def build(mod):
    d = pathlib.Path(tempfile.mkdtemp())
    sh = F._shadow(d / "s.sqlite")
    q = sqlite3.connect(d / "q.sqlite")
    q.execute("CREATE TABLE quotes (seen_at TEXT, book TEXT, gid TEXT, tip_utc TEXT, pid INTEGER, player TEXT,"
              " stat TEXT, line REAL, side TEXT, odds REAL)")

    def rung(t, pid, line, over, stat="points", book="fd"):
        for side, o in (("over", over), ("under", 1.91 if over is not None else None)):
            q.execute("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)", (t, book, "G", TIP, pid, "", stat, line, side, o))

    def flag(fid, pid, logged, news, tier="wowy", stat="pts", line=10.5, margin=4.0, ev=None, d_min=None):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, x, b, stat, line, odds, gid, gtime, "
                   "pid, news_at, margin, ev, d_min) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (fid, logged, "2026-01-09", tier, "T", "X", f"p{pid}", stat, line, 1.91, "G", TIP + "Z", pid,
                    news, margin, ev, d_min))
    # 1 STALE: FD posted 10:00, news 13:00, unmoved (price +0.02) at the 13:05 flag
    rung("2026-01-09T10:00:00", 1, 10.5, 1.91); rung("2026-01-09T13:04:00", 1, 10.5, 1.93)
    flag("s", 1, "2026-01-09T13:05:00", "2026-01-09T13:00:00+00:00", d_min=-1.0)
    # 2 LATE: FD posted 10:00, moved the price 0.10 at 13:02, before the 13:05 flag
    rung("2026-01-09T10:00:00", 2, 10.5, 1.91); rung("2026-01-09T13:02:00", 2, 10.5, 1.81)
    flag("l", 2, "2026-01-09T13:05:00", "2026-01-09T13:00:00+00:00", d_min=2.9)
    # 3 POSTED-AFTER: FD's first quote at 14:00, after the 13:00 news
    rung("2026-01-09T14:00:00", 3, 10.5, 1.91)
    flag("p", 3, "2026-01-09T14:05:00", "2026-01-09T13:00:00+00:00", margin=6.5, d_min=3.0)
    # 4 UNKNOWN news time; GAP NORMAL at exactly 2x (6.0); band 3-8 at exactly 8
    rung("2026-01-09T10:00:00", 4, 10.5, 1.91)
    flag("u", 4, "2026-01-09T13:05:00", None, margin=6.0, d_min=8.0)
    # 5 priced: EV 0.21 = LARGE; band > 8
    rung("2026-01-09T10:00:00", 5, 20.5, 1.91)
    flag("e", 5, "2026-01-09T13:05:00", "2026-01-09T13:00:00+00:00", tier="priced", stat="points", line=20.5,
         ev=0.21, d_min=8.5)
    # 6 cold: margin 10.5 > 2x5 = LARGE, no d_min
    rung("2026-01-09T10:00:00", 6, 30.5, 1.91, stat="pra")
    flag("c", 6, "2026-01-09T13:05:00", "2026-01-09T13:00:00+00:00", tier="cold", stat="pra", line=30.5, margin=10.5)
    # 7 BEFORE the cutover: no cells at all
    rung("2026-01-09T10:00:00", 7, 5.5, 1.91)
    flag("b", 7, "2026-01-09T11:00:00", "2026-01-09T10:30:00+00:00")
    sh.commit(); q.commit()
    mod.SHADOW, mod.LINES, mod.AMEND8_CUTOVER = d / "s.sqlite", d / "q.sqlite", CUT
    return {r["flag_id"]: r for r in mod.collect()}


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    rows = build(mod)
    c = {k: (r.get("cells") or {}) for k, r in rows.items()}
    want(c["s"].get("STALE LINE") == "STALE", "posted before the news, unmoved (price +0.02) at the flag = STALE")
    want(c["l"].get("STALE LINE") == "LATE", "posted before the news, price moved 0.10 before the flag = LATE")
    want(c["p"].get("STALE LINE") == "POSTED-AFTER", "first posted after the news = POSTED-AFTER")
    want(c["u"].get("STALE LINE") == "UNKNOWN", "no news time = UNKNOWN")
    want(c["p"].get("GAP") == "LARGE" and c["u"].get("GAP") == "NORMAL" and c["s"].get("GAP") == "NORMAL",
         "wowy pts gap: 6.5 LARGE, exactly 6.0 (2x) NORMAL, 4.0 NORMAL")
    want(c["e"].get("GAP") == "LARGE" and c["c"].get("GAP") == "LARGE", "priced EV 0.21 LARGE; cold margin 10.5 LARGE")
    want([c[k].get("MINUTES BAND") for k in ("s", "l", "p", "u", "e", "c")] == ["<0", "0-3", "3-8", "3-8", ">8", "n/a"],
         "bands: -1 <0 · 2.9 0-3 · 3.0 3-8 · 8.0 3-8 · 8.5 >8 · cold n/a")
    want("cells" not in rows["b"], "a flag logged before the cutover gets no cells (forward only)")
    return ok


def test_cells():
    assert check(V)


def test_mutants():
    src = pathlib.Path(V.__file__).read_text()
    for name, a, b in (
            ("any price change still STALE", "if m1 and m1[0] == m0[0] and abs(m1[1] - m0[1]) < PRICE_EPS:",
             "if m1 and m1[0] == m0[0]:"),
            ("not forward-only", 'if r["logged_at"] >= AMEND8_CUTOVER:', "if True:"),
            ("gap at 1x", 'return "LARGE" if m > 2 * thr else "NORMAL"', 'return "LARGE" if m > thr else "NORMAL"'),
            ("band 8 exclusive", 'else "3-8" if d <= 8 else ">8"', 'else "3-8" if d < 8 else ">8"'),
            ("news time ignored", "m0 = close_of(q, r[\"gid\"], r[\"pid\"], stat, _utc_naive(r[\"news_at\"]), books=PRIMARY_BOOKS)",
             "m0 = close_of(q, r[\"gid\"], r[\"pid\"], stat, _utc_naive(r[\"logged_at\"]), books=PRIMARY_BOOKS)")):
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_clv_mut8.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({name}) — must fail:")
            assert not check(importlib.import_module("nba_clv_mut8")), name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_clv_mut8", None)


if __name__ == "__main__":
    test_cells()
    test_mutants()
    print("test_nba_cells: OK")
