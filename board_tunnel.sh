#!/usr/bin/env bash
# Live board exposure: board_server (localhost:8899) + cloudflared quick tunnel (public HTTPS).
# Publishes the current tunnel URL to docs/live_board.json and ntfy's it whenever it changes,
# so the home-screen icon can be re-pointed if a reboot ever churns the quick-tunnel URL.
# GITHUB REMOVED 2026-08-04: this used to git-push docs/live_board.json to the
# fgf9p6ks2f-ux account so a stable Pages board could discover the tunnel and redirect there.
# That account is SUSPENDED and is not being appealed, so the push failed on every run --
# silently, because it went through os.system with an unchecked return code. The discovery
# path was dead while looking healthy: on a tunnel restart the Pages board would have kept
# redirecting to the OLD, dead URL forever. ntfy was the only surviving mechanism, so it is
# now the primary one and it FAILS LOUD. Runs under systemd.
set -u
cd "$HOME/tennis-odds-collector" || exit 1
[ -f "$HOME/wnba-loop.env" ] && . "$HOME/wnba-loop.env"   # provides NTFY_TOPIC

# start the static+SSE server (background); keep a handle so we exit together
python3 board_server.py &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT

publish() {   # $1 = tunnel url
  python3 - "$1" <<'PY'
import json, sys, datetime as dt, subprocess, os
url = sys.argv[1]
p = "docs/live_board.json"
try:
    cur = json.load(open(p)).get("url")
except Exception:
    cur = None
if cur == url:
    sys.exit(0)                                   # unchanged -> no commit/ping
json.dump({"url": url, "ts": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"},
          open(p, "w"))
# The notification is now the ONLY way a churned URL reaches the user, so a
# failure here is a real outage of the discovery path and must not be swallowed.
topic = os.environ.get("NTFY_TOPIC")
if not topic:
    print("WARNING: NTFY_TOPIC unset -- the new tunnel URL can reach nobody:", url)
    sys.exit(0)
import urllib.request
try:
    urllib.request.urlopen(urllib.request.Request(
        f"https://ntfy.sh/{topic}", data=f"Live board: {url}".encode(),
        headers={"Title": "Pickz live board", "Tags": "satellite"}), timeout=8)
    print("published + notified", url)
except Exception as e:
    print("ERROR: tunnel URL changed to %s but ntfy FAILED (%s: %s)" % (url, type(e).__name__, e))
    print("       the board is reachable ONLY at that URL and nothing else knows it")
PY
}
export NTFY_TOPIC

# run cloudflared, parse the assigned trycloudflare URL from its stderr, publish on (re)appearance
stdbuf -oL -eL cloudflared tunnel --no-autoupdate --url http://localhost:8899 2>&1 | \
while IFS= read -r line; do
  u=$(printf '%s' "$line" | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)
  [ -n "$u" ] && publish "$u"
done
