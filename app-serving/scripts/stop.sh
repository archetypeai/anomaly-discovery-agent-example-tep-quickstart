#!/bin/sh
# Stop everything this demo starts and verify its ports are free. The serving
# bridge cancels and deletes its platform agent on SIGTERM; give it a moment.
# npm starts the bridge and replayer with `--app=tep-serving`, which is what is
# matched: the RED example's bridge and app/'s replayer share their script names.
HERE=$(cd "$(dirname "$0")/.." && pwd)
pkill -TERM -f "serving-bridge.js --app=tep-serving" 2>/dev/null
for i in 1 2 3 4 5 6 7 8 9 10; do
	pgrep -f "serving-bridge.js --app=tep-serving" >/dev/null 2>&1 || break
	sleep 1
done
pkill -f "mosquitto -c $HERE/mosquitto/mosquitto.conf" 2>/dev/null
pkill -f "replayer.js --app=tep-serving" 2>/dev/null
pkill -f "vite dev --port 5180" 2>/dev/null
sleep 1
busy=0
for p in 1890 9008 9100 5180; do
	if lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1; then
		echo "port $p still held by: $(lsof -nP -iTCP:$p -sTCP:LISTEN | awk 'NR==2{print $1" (pid "$2")"}')"
		busy=1
	fi
done
[ $busy -eq 0 ] && echo "all ports free (1890 · 9008 · 9100 · 5180)"
