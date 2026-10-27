"""NBA_ML1_PREREG.md: the Tracker's checkpoints and features on the side-by-side's synthetic day, with no look-ahead.
MUTANTS in test_mutants()."""
import importlib
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_ml1 as M
import nba_replay as RP
import test_nba_sxs as T


def rows(mod=M, cut=None):
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = T.stores(tmp)
    if cut:                                                    # drop every quote after `cut`: earlier rows must not change
        import sqlite3
        q = sqlite3.connect(p["lines"])
        q.execute("DELETE FROM quotes WHERE seen_at > ?", (cut,))
        q.commit()
    day = RP.Day(T.D, p["lines"], p["news"], p["matchup"], RP.History(p["gamelogs"], p["matchup"]))
    tr = mod.Tracker(mod.StatHistory(p["gamelogs"], p["matchup"]))
    RP.run_day(day, [tr])
    return tr.rows


def check(mod=M):
    rs = rows(mod)
    f = lambda r, k: r["x"][mod.FEATURES.index(k)]
    labels = sorted({(r["label"], r["t"]) for r in rs})
    ok = labels == [("cp30", "2026-11-01T23:40:00"), ("cp60", "2026-11-01T23:20:00"), ("news", "2026-11-01T17:00:30")]
    ok &= sorted({r["t"] for r in rs if r["label"] != "news"}) == ["2026-11-01T23:20:00", "2026-11-01T23:40:00"]
    dk = next(r for r in rs if r["label"] == "cp30" and r["pid"] == T.B and r["book"] == "dk" and r["side"] == "over")
    q = RP.q_close({(11.5, "over"): 1.85, (11.5, "under"): 1.95, (10.5, "over"): 1.70}, "over", 10.5)
    ok &= dk["line"] == 10.5 and abs(f(dk, "ev_fd") - (q * 1.91 - 1)) < 1e-9 and f(dk, "ev_fd_missing") == 0.0   # DK's main 10.5 vs FanDuel's 10.5 alternate
    fdb = next(r for r in rs if r["label"] == "cp30" and r["pid"] == T.B and r["book"] == "fd" and r["side"] == "over")
    fdu = next(r for r in rs if r["label"] == "cp30" and r["pid"] == T.B and r["book"] == "fd" and r["side"] == "under")
    ok &= f(fdb, "line_move_open") == 1.0 and f(fdu, "line_move_open") == -1.0   # FanDuel 10.5 -> 11.5: toward the over
    news = [r for r in rs if r["label"] == "news" and r["pid"] == T.B]
    ok &= bool(news) and all(f(r, "team_news_min") < 1.0 and f(r, "team_out") == 1.0 for r in news)
    return bool(ok)


def test_tracker():
    assert check()


def test_no_lookahead():
    full = {(r["t"], r["pid"], r["book"], r["side"]): r["x"] for r in rows() if r["t"] <= "2026-11-01T17:00:30"}
    cut = {(r["t"], r["pid"], r["book"], r["side"]): r["x"] for r in rows(cut="2026-11-01T17:00:30")
           if r["t"] <= "2026-11-01T17:00:30"}
    assert full and full == cut


def test_mutants():
    src = pathlib.Path(M.__file__).read_text()
    for tag, a, b in (("ev_fd ignores the price", '"ev_fd": (q_fd * odds - 1)', '"ev_fd": (q_fd - 0.5)'),
                      ("unsigned line move", '"line_move_open": (line - open_m[0]) * sgn', '"line_move_open": abs(line - open_m[0])'),
                      ("news never fires", '                fire[g] = "news"\n', '                pass\n'),
                      ("earliest checkpoint label", 'fire[g] = f"cp{min(crossed)}"', 'fire[g] = f"cp{max(crossed)}"')):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_ml1_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            assert not check(importlib.import_module("nba_ml1_mut")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_ml1_mut", None)
