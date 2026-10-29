#!/usr/bin/env python3
"""JS publish gate for the Pickz board (pickz_bake.sh runs this after every bake): `node --check` on
every inline <script> of docs/index.html. Exit 0 = every block parses; 1 = a block fails, so the bake
rolls back to the previous page; 2 = it cannot check (no page or no node), which also blocks the
publish, loudly.

Recreated 2026-10-23. The original was missing, so every pickz bake since at least 2026-08-12 rolled
back. The board stayed fresh only because the WNBA loop (vm_loop.sh, retired 2026-10-23) also baked it,
without the gate."""
import os
import re
import shutil
import subprocess
import sys
import tempfile

PAGE = "docs/index.html"
if not os.path.exists(PAGE) or not shutil.which("node"):
    print("jscheck: cannot check (no page or no node)")
    sys.exit(2)
h = open(PAGE, encoding="utf-8").read()
blocks = re.findall(r"<script>(.*?)</script>", h, re.S)
bad = 0
for i, b in enumerate(blocks):
    if len(b) < 40:
        continue
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(b)
    r = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
    os.unlink(f.name)
    if r.returncode:
        bad += 1
        print(f"block {i}: {r.stderr.strip()[:300]}")
print(f"jscheck: {len(blocks)} blocks, {bad} failing")
sys.exit(1 if bad else 0)
