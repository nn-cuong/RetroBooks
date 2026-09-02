#!/bin/sh
APP_DIR=/mnt/SDCARD/Apps/RetroRead
export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$APP_DIR:/usr/trimui/lib:/mnt/SDCARD/System/lib"
export PYSDL2_DLL_PATH="/usr/trimui/lib"
export SDL_NOMOUSE=1

cd $APP_DIR

PY=""
# 1. Bundled Python in App
if [ -x "$APP_DIR/python/bin/python3" ]; then
    PY="$APP_DIR/python/bin/python3"
fi

# 2. Fallback to System Python
if [ -z "$PY" ]; then
    for c in "/mnt/SDCARD/System/bin/python3" "/usr/bin/python3"; do
        if [ -x "$c" ]; then
            PY="$c"
            break
        fi
    done
fi

if [ -z "$PY" ]; then
    PY=$(command -v python3)
fi

"$PY" main.py > "$APP_DIR/crash.log" 2>&1
