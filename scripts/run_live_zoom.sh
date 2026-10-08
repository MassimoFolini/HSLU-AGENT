#!/bin/bash
# Nimmt ein Zoom-Meeting als MP3 auf, ohne selbst Ton ins Meeting zu senden.
#
#   run_live_zoom.sh <ZOOM_LINK> <PASSCODE> <OUTPUT_MP3> [END_UNIX_TS]
#   run_live_zoom.sh --selftest        Prueft die Audio-Kette (Testton aufnehmen, Mikrofon muss stumm sein)
#
# Audio-Aufbau (alles virtuell, kein echtes Mikrofon/Lautsprecher):
#   hslu_rec  = Senke, in die der Browser spielt. Davon wird aufgenommen (nur Meeting-Ton, keine Systemklaenge).
#   hslu_mic  = stumme Senke. Ihr Monitor ist die "Mikrofon"-Quelle des Browsers: es kommt nie Ton ins Meeting.
BASE=/opt/KiAgentHSLU
cd "$BASE" || exit 1

export XDG_RUNTIME_DIR=/tmp/hslu-pulse-runtime
mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
export DISPLAY=:99
[ -f "$BASE/.env" ] && { set -a; . "$BASE/.env"; set +a; }
source "$BASE/venv/bin/activate"

XVFB_PID=""
if ! pgrep -f "Xvfb :99" > /dev/null; then
    Xvfb :99 -screen 0 1280x1024x24 > /dev/null 2>&1 &
    XVFB_PID=$!
    sleep 1
fi

pulseaudio --check 2>/dev/null || pulseaudio --start --exit-idle-time=-1 --log-target=file:/tmp/hslu-pulse.log
sleep 1
pactl list short sinks | grep -q hslu_rec || pactl load-module module-null-sink sink_name=hslu_rec sink_properties=device.description=HSLU_Rec > /dev/null
pactl list short sinks | grep -q hslu_mic || pactl load-module module-null-sink sink_name=hslu_mic sink_properties=device.description=HSLU_Silent_Mic > /dev/null
pactl set-default-sink hslu_rec
pactl set-default-source hslu_mic.monitor
export PULSE_SINK=hslu_rec
export PULSE_SOURCE=hslu_mic.monitor

mean_volume() {  # Mittlere Lautstaerke (dB) einer Datei, "-inf" bei absoluter Stille
    ffmpeg -hide_banner -i "$1" -af volumedetect -f null - 2>&1 | grep -o "mean_volume: [-0-9.inf]* dB" | head -1
}

if [ "$1" = "--selftest" ]; then
    T=/tmp/hslu_selftest
    rm -f $T.rec.mp3 $T.mic.mp3
    ffmpeg -y -loglevel error -f pulse -i hslu_rec.monitor -t 6 $T.rec.mp3 &
    REC=$!
    ffmpeg -y -loglevel error -f pulse -i hslu_mic.monitor -t 6 $T.mic.mp3 &
    MIC=$!
    sleep 1
    ffmpeg -y -loglevel error -f lavfi -i "sine=frequency=440:duration=4" -f pulse -device hslu_rec "selftest-tone"
    wait $REC $MIC
    echo "Aufnahme (Testton im Rec-Kanal): $(mean_volume $T.rec.mp3)   -> muss hoeher als -60 dB sein"
    echo "Mikrofon-Quelle (muss stumm sein): $(mean_volume $T.mic.mp3)   -> muss -inf oder < -80 dB sein"
    [ -n "$XVFB_PID" ] && kill $XVFB_PID
    exit 0
fi

ILIAS_LINK="$1"
PASSCODE="$2"
OUTPUT_MP3="$3"
END_TS="$4"   # optional: Unix-Zeitstempel, zu dem der Bot das Meeting verlaesst

if [ -z "$ILIAS_LINK" ] || [ -z "$OUTPUT_MP3" ]; then
    echo "Usage: $0 <ZOOM_LINK> <PASSCODE> <OUTPUT_MP3> [END_UNIX_TS]   |   $0 --selftest"
    exit 1
fi

mkdir -p "$(dirname "$OUTPUT_MP3")"
echo "Start Recording von: hslu_rec.monitor"
ffmpeg -y -loglevel error -f pulse -i hslu_rec.monitor -ac 1 -ar 32000 -acodec libmp3lame -b:a 64k "$OUTPUT_MP3" &
FFMPEG_PID=$!

python live_zoom_bot.py "$ILIAS_LINK" "$PASSCODE" "$END_TS"
BOT_EXIT=$?

echo "Meeting beendet. Raeume auf..."
kill -INT $FFMPEG_PID; wait $FFMPEG_PID 2>/dev/null   # sauber beenden, damit die MP3 vollstaendig ist
[ -n "$XVFB_PID" ] && kill $XVFB_PID

echo "Audio gespeichert in $OUTPUT_MP3"
exit $BOT_EXIT
