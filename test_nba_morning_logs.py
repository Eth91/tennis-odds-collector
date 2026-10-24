"""nba_morning_check.log_lines tolerates a log with a split multi-byte character (2026-10-24 crash)."""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_morning_check as M


def test_split_utf8_does_not_crash():
    p = pathlib.Path(tempfile.mkdtemp()) / "nba_cycle.log"
    p.write_bytes("2026-10-24T08:00:00Z flags  rc=0 proj 14.2 ".encode() + b"\xb7 next\n" + "ok · fine\n".encode())
    lines = M.log_lines(p)
    assert len(lines) == 2 and lines[1] == "ok · fine" and "rc=0" in lines[0]
    assert M.log_lines(p.with_name("missing.log")) == []
