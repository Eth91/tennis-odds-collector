"""The drawer does not collapse: it hides, but leaves the card tall and empty.

THE MISS. The old `.bwrap` carried `overflow:hidden; min-height:0` — that pair is the CONTRACT that
lets a `grid-template-rows:0fr` row actually clip its child. Without it the child keeps its
intrinsic height and the row grows to fit, so closing the drawer removes the visible content but
not the space it occupied.

When I rebuilt the drawer under the `dw-*` namespace I carried over the padding, the background and
the radius — but not the one property that made the collapse work. The rename is exactly why:
`.bwrap { overflow:hidden; min-height:0 }` was a bare, unscoped rule far from everything else I was
editing, so nothing pointed at it.

Also consolidates FOUR accumulated `#wnba .bars` padding rules into one. Same accumulation problem
that produced three `.bars.open` rules earlier — every pass added another instead of editing the
existing one.
"""
import ast
import io
import re
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "CUPERTINO-COLLAPSE" in s:
    print("  = already applied")
    raise SystemExit(0)

# strip every accumulated .bars / .bars.open / .dw padding rule; one block replaces them
pats = [
    r"  #wnba \.bars \{\{[^}]*\}\}\n",
    r"  #wnba \.bars\.open \{\{[^}]*\}\}\n",
    r"  #wnba \.dw \{\{[^}]*\}\}\n",
    r"  #wnba \.bars\.open \.dw \{\{[^}]*\}\}\n",
]
removed = 0
for p in pats:
    found = len(re.findall(p, s))
    removed += found
    s = re.sub(p, "", s)
print(f"  removed {removed} accumulated drawer rules")

CSS = r"""
  /* ══════════════════ CUPERTINO-COLLAPSE ══════════════════
     THE COLLAPSE CONTRACT. `.bars` is a grid that animates between 0fr and 1fr. A 0fr row only
     clips its child if that child carries BOTH `overflow:hidden` and `min-height:0` — otherwise the
     child keeps its intrinsic height and the row grows to fit it, which is why closing the drawer
     was hiding the content but leaving the space.

     The old .bwrap had this pair. Renaming it to .dw during the rebuild carried the padding, the
     background and the radius across but not this, because the rule lived far away and unscoped.

     This block is also the ONLY place .bars/.dw padding is declared — four rules had accumulated,
     one per pass, each added rather than edited. */
  #wnba .dw {{ overflow:hidden; min-height:0; padding:0; }}
  #wnba .bars {{ padding:0; }}
  #wnba .bars.open {{ padding:4px 12px 12px; }}
  #wnba .bars.open .dw {{ background:var(--cu-grp2); border-radius:10px; padding:14px; }}
"""
a = "</style></head><body>"
assert a in s, "style anchor"
s = s.replace(a, CSS + a, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.precollapse.py")
io.open(P, "w", encoding="utf-8").write(s)

# prove only one of each remains
for name, pat in (("#wnba .bars", r"  #wnba \.bars \{\{"),
                  ("#wnba .bars.open", r"  #wnba \.bars\.open \{\{"),
                  ("#wnba .dw", r"  #wnba \.dw \{\{"),
                  ("#wnba .bars.open .dw", r"  #wnba \.bars\.open \.dw \{\{")):
    n = len(re.findall(pat, s))
    print(f"  {name:22s} rules now: {n}")
    assert n == 1, f"{name} should be declared exactly once"
print("  + collapse contract restored on .dw")
