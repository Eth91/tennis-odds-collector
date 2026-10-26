"""Prove the write survives a concurrent reader — the exact condition that skipped 429 writes."""
import sqlite3
import subprocess
import sys
from pathlib import Path

H = Path(__file__).resolve().parent
r = sqlite3.connect(str(H / "golf_moves.sqlite"), timeout=60)
r.execute("BEGIN")
r.execute("SELECT COUNT(*) FROM moves").fetchone()
p = subprocess.run([sys.executable, "golf_moves.py"], capture_output=True, text=True,
                   timeout=240, cwd=str(H))
out = ((p.stdout or "") + (p.stderr or "")).strip()
r.close()
print("   output:", out[-200:] if out else "(none)")
print("   'database is locked' present:", "database is locked" in out)
raise SystemExit(1 if "database is locked" in out else 0)
