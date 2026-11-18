#!/usr/bin/env sh
cd "$(dirname "$0")"
[ -x _herramientas/tectonic/tectonic ] || python3 setup.py
python3 servidor.py
