"""Instala dependencias: PyMuPDF (pip) y el motor LaTeX Tectonic (binario oficial)."""
import io
import platform
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "0.17.0"
BASE = f"https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40{VERSION}/"
DEST = Path(__file__).resolve().parent / "_herramientas" / "tectonic"


def asset():
    system, machine = platform.system(), platform.machine().lower()
    if system == "Windows":
        return f"tectonic-{VERSION}-x86_64-pc-windows-msvc.zip", "tectonic.exe"
    if system == "Linux":
        return f"tectonic-{VERSION}-x86_64-unknown-linux-musl.tar.gz", "tectonic"
    if system == "Darwin":
        arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
        return f"tectonic-{VERSION}-{arch}-apple-darwin.tar.gz", "tectonic"
    return None, None


def main():
    print("==> Instalando PyMuPDF")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r",
                           str(Path(__file__).with_name("requirements.txt"))])

    name, exe = asset()
    if name is None:
        print("Sistema no soportado: instala Tectonic a mano (https://tectonic-typesetting.github.io)")
        return
    if (DEST / exe).exists():
        print("==> Tectonic ya instalado")
        return
    print("==> Descargando Tectonic", VERSION)
    DEST.mkdir(parents=True, exist_ok=True)
    data = urllib.request.urlopen(BASE + name).read()
    if name.endswith(".zip"):
        zipfile.ZipFile(io.BytesIO(data)).extractall(DEST)
    else:
        tarfile.open(fileobj=io.BytesIO(data)).extractall(DEST)
    path = DEST / exe
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    print("==> Listo:", path)


if __name__ == "__main__":
    main()
