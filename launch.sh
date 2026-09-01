#!/bin/sh
APP_DIR=/mnt/SDCARD/Apps/RetroRead
export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$APP_DIR:/usr/trimui/lib:/mnt/SDCARD/System/lib"
export PYSDL2_DLL_PATH="/usr/trimui/lib"
export SDL_NOMOUSE=1

cd $APP_DIR

PY=""
# 1. Try shared Python first (Fast boot from RAM)
for c in \
    "/mnt/SDCARD/.retrohub/python/bin/python3" \
    "/mnt/SDCARD/Apps/RetroHub/python/bin/python3" \
    "/mnt/SDCARD/System/bin/python3" \
    "/usr/bin/python3"
do
    if [ -x "$c" ]; then
        PY="$c"
        break
    fi
done

# 2. Fallback to bundled Python
if [ -z "$PY" ]; then
    if [ -x "$APP_DIR/python/bin/python3" ]; then
        PY="$APP_DIR/python/bin/python3"
    fi
fi

if [ -z "$PY" ]; then
    PY=$(command -v python3)
fi

"$PY" main.py > "$APP_DIR/crash.log" 2>&1
