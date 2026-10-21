#!/bin/bash
# Double-click this file to start Novel to EPUB on macOS.
cd "$(dirname "$0")" || exit 1

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import tkinter" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Could not find Python 3 with Tkinter."
  echo "Fix: install Python from https://www.python.org/downloads/  (it includes Tkinter)"
  echo "  or, with Homebrew:  brew install python-tk@3.12"
  echo; read -n 1 -s -r -p "Press any key to close..."; exit 1
fi

if [ ! -d venv ]; then "$PY" -m venv venv || { read -n 1 -s -r -p "Failed. Press any key..."; exit 1; }; fi
source venv/bin/activate
if [ ! -f venv/.installed ] || [ requirements.txt -nt venv/.installed ]; then
  echo "Installing requirements (first run only)..."
  pip install -q -r requirements.txt && touch venv/.installed || { read -n 1 -s -r -p "Install failed. Press any key..."; exit 1; }
fi
python novel2epub_gui.py
