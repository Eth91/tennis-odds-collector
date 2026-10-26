"""nba_flags.shadow_record: the cycle log's record counts the way the speed test does: voids out,
one opportunity per (tier, player, stat, game) at its earliest flag. MUTANT: voids counted."""
import importlib
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_flags as F


def build(mod):
    sh = mod._shadow(pathlib.Path(tempfile.mkdtemp()) / "s.sqlite")
    for fid, at, tier, pid, stat, line, odds, result, void in (
            ("a1", "2026-01-09T10:00", "wowy", 1, "pra", 19.5, 1.90, "win", None),
            ("a2", "2026-01-09T12:00", "wowy", 1, "pra", 18.5, 1.80, "win", None),     # re-flag: same opportunity
            ("b1", "2026-01-09T10:00", "wowy", 2, "pts", 6.5, 1.90, "loss", "amend6: x"),  # void
            ("c1", "2026-01-09T10:00", "wowy", 3, "pts", 8.5, 2.00, "loss", None),
            ("d1", "2026-01-09T10:00", "priced", 1, "points", 20.5, 2.00, "win", None)):
        sh.execute("INSERT INTO flags (flag_id, logged_at, game_date, tier, team, x, b, stat, line, odds, gid, pid, "
                   "result, void_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (fid, at, "2026-01-09", tier, "T", "X", f"p{pid}", stat, line, odds, "G", pid, result, void))
    sh.commit()
    return mod.shadow_record(sh)


def check(mod):
    r = build(mod)
    w = r.get("wowy")
    ok = bool(w and w[:2] == (1, 2) and abs(w[2] + 0.1) < 1e-9 and r.get("priced") == (1, 1, 1.0))
    print(f"   {'ok ' if ok else 'BAD'} wowy 1-1 (re-flag once, void out, earliest price) · priced 1-0 — got {r}")
    return ok


def test_shadow_record():
    assert check(F)


def test_mutant_voids_counted():
    src = pathlib.Path(F.__file__).read_text()
    a = '"WHERE result IS NOT NULL AND void_reason IS NULL ORDER BY logged_at"'
    assert src.count(a) == 1
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "nba_flags_mutg.py").write_text(src.replace(a, '"WHERE result IS NOT NULL ORDER BY logged_at"'))
    sys.path.insert(0, str(d))
    try:
        assert not check(importlib.import_module("nba_flags_mutg"))
    finally:
        sys.path.remove(str(d))
        sys.modules.pop("nba_flags_mutg", None)


if __name__ == "__main__":
    test_shadow_record()
    test_mutant_voids_counted()
    print("test_nba_grade_summary: OK")
