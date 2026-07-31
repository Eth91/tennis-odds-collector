"""The drift check hardcodes 'v1.0' in its OK line. After a re-freeze that is a false statement
printed by the tool whose entire job is detecting false statements about which model is running."""
import io
P="pga_after_event.sh"; s=io.open(P).read()
old = '    print("  OK  v1.0 constants %s + source %s intact" % (now, now_src))'
new = '    print("  OK  %s constants %s + source %s intact" % (_fz.get("version", "?"), now, now_src))'
if new in s:
    print("  = already dynamic"); raise SystemExit(0)
assert old in s, "anchor missing"
io.open(P,"w").write(s.replace(old,new,1))
print("  + drift check prints the manifest's real version")
