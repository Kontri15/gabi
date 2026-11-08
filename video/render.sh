#!/usr/bin/env bash
# Build the Tatry reel end to end.
#   ./render.sh <folder with IMG_7517.mov IMG_8052.mov IMG_7739.mov + the .mp4>
# Needs: ffmpeg (with zscale + libass), python3 with numpy scipy opencv-python-headless
#        pedalboard fonttools pillow
set -euo pipefail
SRC_DIR=${1:?usage: render.sh <source clips folder>}
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${WORK:-$HERE/build}
mkdir -p "$WORK/audio"

pick() { ls "$SRC_DIR"/*"$1"* | head -1; }

# 1) iPhone HLG (10-bit HDR) -> SDR BT.709 intermediates, 1080x1920
TM="zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
for n in 7517 8052 7739; do
  [ -f "$WORK/src_$n.mp4" ] || ffmpeg -v error -y -i "$(pick IMG_$n)" -map 0:v \
    -vf "$TM,scale=1080:1920:flags=lanczos,setsar=1" -c:v libx264 -preset veryfast -crf 12 "$WORK/src_$n.mp4"
  [ -f "$WORK/amb_$n.wav" ] || ffmpeg -v error -y -i "$(pick IMG_$n)" -map 0:a -ac 2 -ar 48000 "$WORK/amb_$n.wav"
done
[ -f "$WORK/src_d.mp4" ] || ffmpeg -v error -y -i "$(ls "$SRC_DIR"/*.mp4 | head -1)" -map 0:v \
  -vf "scale=-2:1920:flags=lanczos,crop=1080:1920,unsharp=5:5:0.6:5:5:0.0,setsar=1" \
  -c:v libx264 -preset veryfast -crf 12 "$WORK/src_d.mp4"

# 2) soundtrack (music + sound design + ambience), 3) picture, 4) titles
python3 "$HERE/build_audio.py" "$WORK" "$WORK/audio"
[ "${REUSE_PICTURE:-0}" = 1 ] && [ -f "$WORK/picture.mp4" ] || python3 "$HERE/build_video.py" "$WORK" "$WORK/picture.mp4"
HOOK=winter python3 "$HERE/make_captions.py" "$WORK/captions.ass"
HOOK=zima   python3 "$HERE/make_captions.py" "$WORK/captions_zima.ass"

# 5) final encodes: burn titles, loudness-normalise to -14 LUFS / -1.5 dBTP
final() {  # $1 = mix wav, $2 = output, $3 = captions file
  local J
  J=$(ffmpeg -hide_banner -nostats -i "$1" -af loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json -f null - 2>&1 | sed -n '/^{/,/^}/p')
  read -r MI MTP MLRA MTH OFF < <(python3 -c 'import json,sys; j=json.loads(sys.stdin.read()); print(j["input_i"],j["input_tp"],j["input_lra"],j["input_thresh"],j["target_offset"])' <<<"$J")
  ffmpeg -v error -y -i "$WORK/picture.mp4" -i "$1" \
    -vf "ass=$3:fontsdir=$HERE/fonts" \
    -af "loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=$MI:measured_TP=$MTP:measured_LRA=$MLRA:measured_thresh=$MTH:offset=$OFF:linear=true,aresample=48000" \
    -c:v libx264 -preset slow -crf 18 -maxrate 16M -bufsize 32M -profile:v high -level 4.2 -pix_fmt yuv420p -r 30 \
    -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
    -c:a aac -b:a 320k -ar 48000 -movflags +faststart -shortest "$2"
}
# main: "Winter is coming." hook; alt: Slovak "Zima prichádza." hook (A/B test)
final "$WORK/audio/mix_full.wav"    "$HERE/tatry_reel.mp4"               "$WORK/captions.ass"
final "$WORK/audio/mix_nomusic.wav" "$HERE/tatry_reel_bez_hudby.mp4"     "$WORK/captions.ass"
final "$WORK/audio/mix_full.wav"    "$HERE/tatry_reel_zima_prichadza.mp4" "$WORK/captions_zima.ass"

# cover frame for the Reel / TikTok
python3 "$HERE/make_captions.py" "$WORK/cover.ass" --cover
ffmpeg -v error -y -ss 7.6 -i "$WORK/picture.mp4" -frames:v 1 \
  -vf "ass=$WORK/cover.ass:fontsdir=$HERE/fonts" -q:v 2 "$HERE/tatry_reel_cover.jpg"
echo "done: $HERE/tatry_reel.mp4"
