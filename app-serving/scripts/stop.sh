#!/bin/sh
# Stop everything this demo starts and verify its ports are free. The serving
# bridge cancels and deletes its platform agent on SIGTERM; give it a moment.
HERE=$(cd "$(dirname "$0")/.." && pwd)
pkill -TERM -f "scripts/serving-bridge.js" 2>/dev/null
pkill -f "mosquitto -c $HERE/mosquitto/mosquitto.conf" 2>/dev/null
pkill -f "$HERE/scripts/replayer.js" 2>/dev/null
pkill -f "vite dev --port 5180" 2>/dev/null
sleep 3
busy=0
for p in 1890 9008 9100 5180; do
	if lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1; then
		echo "port $p still held by: $(lsof -nP -iTCP:$p -sTCP:LISTEN | awk 'NR==2{print $1" (pid "$2")"}')"
		busy=1
	fi
done
[ $busy -eq 0 ] && echo "all ports free (1890 · 9008 · 9100 · 5180)"
