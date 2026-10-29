"""nba_watch.py: the 170 s perl alarm (SIGALRM) must release /tmp/nba-cycle.lock (2026-10-28: an alarm-killed run left it
orphaned for 30 minutes, stopping all line collection). Uses a temporary lock path, never the live one."""
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent


def run(handler):
    lock = pathlib.Path(tempfile.mkdtemp()) / "lock"
    code = f"""
import pathlib, signal, sys, time
sys.path.insert(0, {str(HERE)!r})
import nba_watch as W
W.LOCK = pathlib.Path({str(lock)!r})
if {handler!r}:
    for s in (signal.SIGALRM, signal.SIGTERM):
        signal.signal(s, W._exit_on_signal)
with W.cycle_lock() as got:
    assert got and W.LOCK.is_dir()
    signal.alarm(1)
    time.sleep(20)
"""
    r = subprocess.run([sys.executable, "-c", code], timeout=60)
    return r.returncode, lock.exists()


def test_alarm_releases_the_lock():
    rc, left = run(handler=True)
    assert rc == 142 and not left, (rc, left)          # 128 + SIGALRM, as nba_watch.sh logs it, and the lock is gone


def test_without_the_handler_the_lock_is_orphaned():
    rc, left = run(handler=False)
    assert rc != 0 and left, (rc, left)                # the old behavior, so the test above can tell them apart


if __name__ == "__main__":
    test_alarm_releases_the_lock()
    test_without_the_handler_the_lock_is_orphaned()
    print("test_nba_watch_lock: OK")
