#!/bin/bash
ILIAS_LINK="$1"
PASSCODE="$2"
OUTPUT_MP3="$3"
END_TS="$4"   # optional: Unix-Zeitstempel, zu dem der Bot das Meeting verlaesst

if [ -z "$ILIAS_LINK" ] || [ -z "$PASSCODE" ] || [ -z "$OUTPUT_MP3" ]; then
    echo "Usage: ./run_live_zoom.sh <ILIAS_LINK> <PASSCODE> <OUTPUT_MP3>"
    exit 1
fi

source /opt/KiAgentHSLU/venv/bin/activate
source /opt/KiAgentHSLU/.env

export DISPLAY=:99

# Starte Xvfb (Virtual Framebuffer) im Hintergrund
Xvfb :99 -screen 0 1280x1024x24 &
XVFB_PID=$!

# Starte PulseAudio Daemon
pulseaudio -D --exit-idle-time=-1
sleep 2

# Ohne Soundkarte (Server) gibt es kein Monitor-Device: virtuelle Senke anlegen
if ! pactl list short sources | grep -qi monitor; then
    pactl load-module module-null-sink sink_name=virt_out >/dev/null
    pactl set-default-sink virt_out
fi

# Finde das "Monitor" Device von PulseAudio (das nimmt auf was Lautsprecher abspielen)
MONITOR=$(pactl list short sources | grep -i monitor | awk '{print $2}' | head -n 1)

if [ -z "$MONITOR" ]; then
    echo "Kein PulseAudio Monitor gefunden!"
    kill $XVFB_PID
    pulseaudio -k
    exit 1
fi

echo "Start Recording von: $MONITOR"
# Starte ffmpeg im Hintergrund um den Sound mitzuschneiden
ffmpeg -y -f pulse -i "$MONITOR" -acodec libmp3lame "$OUTPUT_MP3" 2> /dev/null &
FFMPEG_PID=$!

# Starte den Python Bot
cd /opt/KiAgentHSLU
python live_zoom_bot.py "$ILIAS_LINK" "$PASSCODE" "$END_TS"
BOT_EXIT=$?

# Aufräumen
echo "Meeting beendet. Räume auf..."
kill -INT $FFMPEG_PID; wait $FFMPEG_PID 2>/dev/null   # sauber beenden, damit die MP3 vollstaendig ist
kill $XVFB_PID
pulseaudio -k

echo "Audio gespeichert in $OUTPUT_MP3"
exit $BOT_EXIT
