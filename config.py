"""Carpeta fuente elegida por el usuario (contiene las asignaturas; cada una, su temario)."""
import json
import subprocess
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parent / "config.json"

_PICKER = (
    "import tkinter as tk\n"
    "from tkinter import filedialog\n"
    "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
    "print(filedialog.askdirectory(title='Elige la carpeta que contiene tus asignaturas', mustexist=True))\n"
)


def root():
    """Devuelve la carpeta fuente o None si aún no se ha elegido / ya no existe."""
    try:
        p = Path(json.loads(CONFIG.read_text(encoding="utf-8")).get("root", ""))
    except Exception:
        return None
    return p.resolve() if p.is_dir() else None


def set_root(path):
    p = Path(path).resolve()
    if not p.is_dir():
        raise ValueError("La carpeta no existe")
    CONFIG.write_text(json.dumps({"root": str(p)}, ensure_ascii=False), encoding="utf-8")
    return p


def pick_folder():
    """Abre el selector de carpetas del sistema (Explorador en Windows). '' si se cancela."""
    r = subprocess.run([sys.executable, "-c", _PICKER], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("No se pudo abrir el selector de carpetas (¿falta tkinter?)")
    return r.stdout.strip()
