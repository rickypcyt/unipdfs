"""Extracción automática de texto e imágenes de los PDF, sin repetir trabajo.

Cada carpeta `<pdf>_extraido/` guarda un `.fuente.json` con el tamaño, la fecha y el
hash SHA-1 del PDF del que salió. Con eso:
  * si el PDF no ha cambiado, no se vuelve a extraer;
  * si solo cambió la fecha (copiado, tocado) pero el contenido es el mismo, tampoco;
  * si el PDF se renombró, se renombra su carpeta en lugar de extraer de nuevo;
  * si el PDF cambió de verdad, se vuelve a extraer.
"""
import hashlib
import json
import shutil
import threading
import time
from pathlib import Path

try:
    import pymupdf
except Exception:
    pymupdf = None

import config
import limpieza

# Sube este número cuando cambie el formato de salida: las extracciones viejas se rehacen solas.
FORMAT = 2
MARKER = ".fuente.json"
SUFFIX = "_extraido"
SCAN_EVERY = 5  # segundos entre revisiones de la carpeta

# PyMuPDF no es seguro entre hilos: todas las operaciones con él pasan por este cerrojo.
PDF_LOCK = threading.RLock()

_status_lock = threading.Lock()
_status = {"running": False, "done": 0, "total": 0, "current": "", "errors": {}}
_wake = threading.Event()
_failed = {}  # ruta -> (tamaño, mtime) del intento fallido


def output_dir(pdf):
    return pdf.parent / (pdf.stem + SUFFIX)


def skipped(rel_parts):
    """Carpetas que no son temario: ocultas, internas o resultados de extracción."""
    return any(p.startswith((".", "_")) or p.endswith(SUFFIX) for p in rel_parts)


def iter_pdfs(base):
    for pdf in base.rglob("*.pdf"):
        if pdf.is_file() and not skipped(pdf.relative_to(base).parent.parts):
            yield pdf


def _read_marker(folder):
    try:
        return json.loads((folder / MARKER).read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_marker(folder, pdf, sha1, pages, images):
    st = pdf.stat()
    (folder / MARKER).write_text(json.dumps({
        "pdf": pdf.name, "size": st.st_size, "mtime_ns": st.st_mtime_ns,
        "sha1": sha1, "pages": pages, "images": images, "format": FORMAT,
    }, ensure_ascii=False), encoding="utf-8")


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_fresh(pdf):
    """Comprobación rápida (sin leer el PDF): ¿la extracción corresponde a este archivo?"""
    out = output_dir(pdf)
    m = _read_marker(out)
    if not m or m.get("format") != FORMAT or not (out / "texto.md").exists():
        return False
    try:
        st = pdf.stat()
    except OSError:
        return False
    return m.get("size") == st.st_size and m.get("mtime_ns") == st.st_mtime_ns


def cached_pages(pdf):
    m = _read_marker(output_dir(pdf)) if is_fresh(pdf) else None
    return m.get("pages") if m else None


def _extract(pdf, dest):
    """Extrae a una carpeta temporal y la coloca en `dest` de golpe (nunca queda a medias)."""
    if pymupdf is None:
        raise RuntimeError("PyMuPDF no está disponible en este Python")
    tmp = pdf.parent / ("." + dest.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    images_dir = tmp / "imagenes"
    images_dir.mkdir(parents=True)

    seen, count, by_page = set(), 0, {}
    doc = pymupdf.open(str(pdf))
    try:
        pages = limpieza.analyze(doc)
        # Imágenes decorativas: logos/franjas que salen en muchas páginas, o viñetas diminutas.
        uses = {}
        for page in doc:
            for info in page.get_images(full=True):
                uses.setdefault(info[0], set()).add(page.number)
        decorative = {x for x, ps in uses.items() if len(ps) >= max(3, 0.3 * len(doc))}
        for index in range(len(doc)):
            page = doc.load_page(index)
            number = index + 1
            for info in page.get_images(full=True):
                xref, width, height = info[0], info[2], info[3]
                if xref in seen or xref in decorative or min(width, height) < 48:
                    continue
                seen.add(xref)
                try:
                    image = doc.extract_image(xref)
                except Exception:
                    continue
                data = image.get("image")
                if not data:
                    continue
                count += 1
                ext = image.get("ext") or "png"
                name = f"img_{count:03d}_p{number}.{ext}"
                (images_dir / name).write_bytes(data)
                by_page.setdefault(number, []).append("imagenes/" + name)
    finally:
        doc.close()

    (tmp / "texto.txt").write_text(limpieza.to_text(pages), encoding="utf-8")
    (tmp / "texto.md").write_text(limpieza.to_markdown(pages, limpieza.pretty_title(pdf.stem), by_page),
                                  encoding="utf-8")
    return tmp, len(pages), count


def ensure(pdf, force=False):
    """Deja la extracción de `pdf` al día. Devuelve (carpeta, qué se hizo)."""
    pdf = Path(pdf)
    out = output_dir(pdf)
    with PDF_LOCK:
        if not force and is_fresh(pdf):
            return out, "al día"

        marker = _read_marker(out)
        # Solo se reutiliza una extracción que ya tenga el formato actual.
        has_text = (out / "texto.md").exists() and bool(marker) and marker.get("format") == FORMAT

        digest = _sha1(pdf)
        if not force and has_text and marker.get("sha1") == digest:
            _write_marker(out, pdf, digest, marker.get("pages"), marker.get("images"))
            return out, "mismo contenido"

        if not force and not out.exists():
            # ¿Se renombró el PDF? Busca una extracción huérfana con el mismo contenido.
            for cand in pdf.parent.glob("*" + SUFFIX):
                m = _read_marker(cand)
                if (cand.is_dir() and m and m.get("sha1") == digest and m.get("format") == FORMAT
                        and not (pdf.parent / m.get("pdf", "")).exists()):
                    cand.rename(out)
                    _write_marker(out, pdf, digest, m.get("pages"), m.get("images"))
                    return out, "renombrada"

        tmp, pages, images = _extract(pdf, out)
        _write_marker(tmp, pdf, digest, pages, images)
        if out.is_dir():
            shutil.rmtree(out)
        elif out.exists():
            out.unlink()
        tmp.rename(out)
        return out, "extraída"


def status():
    with _status_lock:
        return dict(_status, errors=dict(_status["errors"]))


def wake():
    _wake.set()


def _scan_once():
    base = config.root()
    if base is None:
        return
    pending = []
    for p in iter_pdfs(base):
        if is_fresh(p):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        # Un PDF que ya falló no se reintenta hasta que cambie.
        if _failed.get(str(p)) == (st.st_size, st.st_mtime_ns):
            continue
        pending.append(p)
    errors = {}
    with _status_lock:
        _status.update(running=bool(pending), done=0, total=len(pending), current="")
    for i, pdf in enumerate(pending):
        rel = pdf.relative_to(base).as_posix()
        with _status_lock:
            _status.update(current=rel, done=i)
        try:
            ensure(pdf)
        except Exception as exc:  # p. ej. PDF a medio copiar o protegido
            errors[rel] = str(exc)
            try:
                st = pdf.stat()
                _failed[str(pdf)] = (st.st_size, st.st_mtime_ns)
            except OSError:
                pass
    with _status_lock:
        _status.update(running=False, done=len(pending), current="",
                       errors={**_status["errors"], **errors} if not pending else errors)


def _loop():
    while True:
        try:
            _scan_once()
        except Exception:
            pass
        _wake.wait(SCAN_EVERY)
        _wake.clear()


def start():
    threading.Thread(target=_loop, name="extractor", daemon=True).start()
