"""nba_cycle.sh's lock: it waits for a busy lock to free (a per-minute nba_watch run) instead of skipping at once, and
still skips when it stays busy. Runs the script's lock block alone, on a temporary lock path."""
import pathlib
import subprocess
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent


def block(lock, log, wait):
    src = (HERE / "nba_cycle.sh").read_text()
    body = src[src.index("# --- lock"):src.index("# --- end lock")]
    return f'LOCK="{lock}"; LOG="{log}"; LOCK_WAIT_S={wait}\nstamp(){{ date -u +%FT%TZ; }}\n{body}\necho TOOK\n'


def run(hold_s, wait):
    d = pathlib.Path(tempfile.mkdtemp())
    lock, log = d / "lock", d / "log"
    lock.mkdir()                                         # someone (nba_watch) holds it
    p = subprocess.Popen(["bash", "-c", block(lock, log, wait)], stdout=subprocess.PIPE, text=True)
    time.sleep(hold_s)
    if lock.exists():
        lock.rmdir()                                     # ...and lets go
    out, _ = p.communicate(timeout=60)
    return out, log.read_text() if log.exists() else "", lock.exists()


def test_waits_for_the_lock():
    out, log, held = run(hold_s=3, wait=10)
    assert "TOOK" in out and "skipped" not in log, (out, log)


def test_skips_when_it_stays_busy():
    out, log, _ = run(hold_s=8, wait=4)
    assert "TOOK" not in out and "skipped" in log, (out, log)


if __name__ == "__main__":
    test_waits_for_the_lock()
    test_skips_when_it_stays_busy()
    print("test_nba_cycle_lock: OK")
