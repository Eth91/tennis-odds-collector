"""Title the evidence report with the version it is actually measuring, read from the manifest."""
import io
P="wnba_validate.py"; s=io.open(P).read()
old = '''    L = [f"# WNBA v1.0 — cumulative evidence", "",'''
new = '''    try:
        _ver = json.loads(FREEZE.read_text()).get("version", "v?")
    except Exception:                                          # noqa: BLE001
        _ver = "v?"
    L = [f"# WNBA {_ver} — cumulative evidence", "",'''
if "_ver = json.loads" in s:
    print("  = title already dynamic"); raise SystemExit(0)
assert old in s, "title anchor missing"
io.open(P,"w").write(s.replace(old,new,1))
print("  + report title reads the manifest version")
