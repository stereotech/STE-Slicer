#!/usr/bin/env bash
Xvfb :1 -screen 0 1280x800x16 &
export DISPLAY=:1.0
python3 steslicer_app.py --headless