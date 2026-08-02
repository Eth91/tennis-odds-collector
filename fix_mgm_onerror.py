"""Fix the JS syntax error that killed the whole script block (and with it, the tabs).

The generated attribute contained raw single quotes inside a single-quoted JS string:

    + '" onerror="if(this.src.indexOf('book-mgm')>-1)this.src=_TTMGM_FALLBACK" alt="'
                                      ^ terminates the string

The Python source wrote \\' , which is a PYTHON escape — it emits a bare ' into the JS. To emit an
escaped quote the source would need \\\\' . Rather than rely on getting that right through two
layers of escaping, the guard is rewritten with no quotes at all: `this.onerror=null` already
prevents the retry loop, which is the only thing the indexOf test was doing.

Consequence of the bug: the 18KB script block failed to parse, so showTab() never defined, so the
TT / PGA / Tracker tabs were dead on the live board.
"""
import ast
import io
import shutil
import subprocess
import tempfile
import os
import re

P = "dashboard.py"
lines = io.open(P, encoding="utf-8").read().split("\n")

TARGET = "onerror="
hits = [i for i, ln in enumerate(lines) if TARGET in ln and "_TTMGM_FALLBACK" in ln]
assert len(hits) == 1, f"expected 1 onerror line, found {len(hits)}"
i = hits[0]
old = lines[i]

# rebuild the line without any inner quotes
new = "            + '\" onerror=\"this.onerror=null;this.src=_TTMGM_FALLBACK\" alt=\"'"
lines[i] = new
s = "\n".join(lines)
assert "indexOf(" not in s or "book-mgm" not in s.split("indexOf(")[1][:40]
ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.prejsfix.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  line %d rewritten" % (i + 1))
print("   was:", old.strip()[:90])
print("   now:", new.strip()[:90])
