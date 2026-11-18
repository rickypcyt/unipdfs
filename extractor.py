"""Extracción automática de texto e imágenes de los PDF, sin repetir trabajo.

Cada carpeta `<pdf>_extraido/` guarda un `.fuente.json` con el tamaño, la fecha y el
hash SHA-1 del PDF del que salió. Con eso:
  * si el PDF no ha cambiado, no se vuelve a extraer;
  * si solo cambió la fecha (copiado, tocado) pero el contenido es el mismo, tampoco;
  * si el PDF se renombró, se renombra su carpeta en lugar de extraer de nuevo;
  * si el PDF cambió de verdad, se vuelve a extraer.

Las extracciones ya hechas se dejan como están aunque cambie la versión del programa:
solo se rehacen si el PDF cambia o si se pide a mano con ↻ (entonces las versiones
anteriores de texto.md / texto.tex / texto.pdf se guardan en la subcarpeta `anterior/`).
"""
import hashlib
import json
import os
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

# Versión del formato con que se hizo cada extracción (solo informativa: no provoca re-extraer).
FORMAT = 4
MARKER = ".fuente.json"
OUTPUTS = ("texto.txt", "texto.md", "texto.tex")  # lo que se genera
REQUIRED = ("texto.txt", "texto.md")             # lo imprescindible para considerar hecha una extracción


class BlockedError(RuntimeError):
    """Los archivos extraídos desaparecen tras crearlos (antivirus u otro programa)."""
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


def _write_marker(folder, pdf, sha1, pages, images, garbled=0):
    st = pdf.stat()
    (folder / MARKER).write_text(json.dumps({
        "pdf": pdf.name, "size": st.st_size, "mtime_ns": st.st_mtime_ns,
        "sha1": sha1, "pages": pages, "images": images, "garbled": garbled, "format": FORMAT,
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
    if not m or not all((out / name).exists() for name in REQUIRED):
        return False
    try:
        st = pdf.stat()
    except OSError:
        return False
    return m.get("size") == st.st_size and m.get("mtime_ns") == st.st_mtime_ns


def garbled_pages(pdf):
    m = _read_marker(output_dir(pdf)) if is_fresh(pdf) else None
    return (m or {}).get("garbled") or 0


def cached_pages(pdf):
    m = _read_marker(output_dir(pdf)) if is_fresh(pdf) else None
    return m.get("pages") if m else None


def _extract(pdf, dest):
    """Extrae a una carpeta temporal y la coloca en `dest` de golpe (nunca queda a medias)."""
    if pymupdf is None:
        raise RuntimeError("PyMuPDF no está disponible en este Python")
    tmp = pdf.parent / ("." + dest.name + f".{os.getpid()}.tmp")
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

    doc = pymupdf.open(str(pdf))
    try:
        def render_pages():
            for p in pages:
                name = f"pagina_{p['number']:03d}.png"
                if (p.get("garbled") or p.get("blocked")) and not p["duplicate_of"] and not (images_dir / name).exists():
                    doc[p["number"] - 1].get_pixmap(dpi=110).save(str(images_dir / name))
                    by_page.setdefault(p["number"], []).insert(0, "imagenes/" + name)

        title = limpieza.pretty_title(pdf.stem)
        render_pages()
        write_outputs(tmp, pages, title, by_page)
        bad = unreadable([tmp / n for n in OUTPUTS])
        if bad:
            # Un antivirus (Defender) bloquea algún fragmento, p. ej. un ejemplo de código de ataque.
            # Se localizan los fragmentos exactos, se sustituyen por un aviso y se muestra la imagen.
            redact_blocked(pages, tmp)
            render_pages()
            write_outputs(tmp, pages, title, by_page)
            bad = unreadable([tmp / n for n in OUTPUTS])
            if bad:
                raise BlockedError("El antivirus bloquea " + ", ".join(p.name for p in bad)
                                   + " incluso tras omitir los fragmentos sospechosos.")
    finally:
        doc.close()
    flagged = sum(1 for p in pages if p.get("garbled") or p.get("blocked"))
    return tmp, len(pages), count, flagged


PROBE_WAIT = 1.5  # segundos que se deja al antivirus para analizar los archivos recién escritos
BLOCKED_NOTE = "[fragmento omitido: el antivirus lo marca como sospechoso (es un ejemplo de código); ver la imagen de la página]"


def write_outputs(tmp, pages, title, by_page):
    md = limpieza.to_markdown(pages, title, by_page)
    (tmp / "texto.txt").write_text(limpieza.to_text(pages), encoding="utf-8")
    (tmp / "texto.md").write_text(md, encoding="utf-8")
    # Versión LaTeX lista para editar y compilar en el Taller (las imágenes van con ruta relativa).
    import latex_api
    (tmp / "texto.tex").write_text(latex_api.markdown_to_latex(md, tmp), encoding="utf-8")


def unreadable(paths, wait=PROBE_WAIT):
    """Archivos que no se pueden leer (Windows devuelve 'Invalid argument' si el antivirus los bloquea)."""
    time.sleep(wait)
    bad = []
    for p in paths:
        try:
            p.read_bytes()
        except OSError:
            bad.append(p)
    return bad


def _probe(texts, folder):
    """Índices de `texts` que el antivirus bloquea al escribirlos en un archivo."""
    probe_dir = folder / ".probe"
    shutil.rmtree(probe_dir, ignore_errors=True)
    probe_dir.mkdir()
    paths = []
    for i, text in enumerate(texts):
        path = probe_dir / f"{i:05d}.txt"
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    blocked = {int(p.stem) for p in unreadable(paths)}
    shutil.rmtree(probe_dir, ignore_errors=True)
    return blocked


def redact_blocked(pages, folder):
    candidates = [p for p in pages if not p["duplicate_of"] and (p["items"] or p["title"])]
    bad_pages = _probe([limpieza.to_text([p]) for p in candidates], folder)
    for index in sorted(bad_pages):
        page = candidates[index]
        parts = [page["title"]] + [text for _, _, text in page["items"]]
        hits = _probe(parts, folder)
        if not hits:  # solo bloquea la combinación: se omite todo el texto de la página
            hits = set(range(len(parts)))
        if 0 in hits and page["title"]:
            page["title"] = BLOCKED_NOTE
        page["items"] = [(kind, level, BLOCKED_NOTE if (i + 1) in hits else text)
                         for i, (kind, level, text) in enumerate(page["items"])]
        page["blocked"] = len(hits)


def fill_tex(out):
    """Extracciones antiguas sin texto.tex: se genera desde su texto.md (rápido, sin volver a extraer)."""
    tex, md = out / "texto.tex", out / "texto.md"
    if tex.exists() or not md.exists():
        return
    try:
        import latex_api
        tex.write_text(latex_api.markdown_to_latex(md.read_text(encoding="utf-8"), out), encoding="utf-8")
    except Exception:
        pass


def _keep_previous(out, tmp):
    """Al rehacer a mano una extracción se conservan las versiones anteriores editables."""
    old = [out / n for n in ("texto.md", "texto.tex", "texto.pdf") if (out / n).exists()]
    if not old:
        return
    (tmp / "anterior").mkdir(exist_ok=True)
    for f in old:
        try:
            shutil.copy2(f, tmp / "anterior" / f.name)
        except OSError:
            pass


def ensure(pdf, force=False):
    """Deja la extracción de `pdf` al día. Devuelve (carpeta, qué se hizo)."""
    pdf = Path(pdf)
    out = output_dir(pdf)
    with PDF_LOCK:
        if not force and is_fresh(pdf):
            fill_tex(out)
            return out, "al día"

        marker = _read_marker(out)
        digest = _sha1(pdf)
        same_content = bool(marker) and marker.get("sha1") == digest
        missing = [name for name in REQUIRED if not (out / name).exists()]
        if not force and same_content and not missing:
            _write_marker(out, pdf, digest, marker.get("pages"), marker.get("images"), marker.get("garbled", 0))
            fill_tex(out)
            return out, "mismo contenido"
        if not force and same_content and missing:
            # Ya se extrajo este mismo contenido y alguien ha borrado archivos (p. ej. Windows Defender
            # con un falso positivo). Re-extraer volvería a pasar lo mismo en bucle: se para aquí.
            raise BlockedError(
                "Windows (probablemente Defender) ha borrado " + ", ".join(missing)
                + ". Pulsa ↻ en la tarjeta para intentarlo de nuevo.")

        if not force and not out.exists():
            # ¿Se renombró el PDF? Busca una extracción huérfana con el mismo contenido.
            for cand in pdf.parent.glob("*" + SUFFIX):
                m = _read_marker(cand)
                if (cand.is_dir() and m and m.get("sha1") == digest
                        and not (pdf.parent / m.get("pdf", "")).exists()):
                    cand.rename(out)
                    _write_marker(out, pdf, digest, m.get("pages"), m.get("images"), m.get("garbled", 0))
                    fill_tex(out)
                    return out, "renombrada"

        tmp, pages, images, garbled = _extract(pdf, out)
        _write_marker(tmp, pdf, digest, pages, images, garbled)
        if out.is_dir():
            _keep_previous(out, tmp)
            shutil.rmtree(out)
        elif out.exists():
            out.unlink()
        tmp.rename(out)
        return out, "extraída"


MAX_WORKERS = 4  # PDF extraídos a la vez


def _job(path):
    """Trabajo de un proceso hijo: extrae un PDF. Devuelve (acción, error)."""
    try:
        return ensure(Path(path))[1], None
    except Exception as exc:
        return None, str(exc)


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

    def fail(pdf, rel, message):
        errors[rel] = message
        try:
            st = pdf.stat()
            _failed[str(pdf)] = (st.st_size, st.st_mtime_ns)
        except OSError:
            pass

    remaining = list(pending)
    workers = min(MAX_WORKERS, os.cpu_count() or 2, len(pending))
    if workers > 1:
        # Varios PDF a la vez, cada uno en su proceso (PyMuPDF no es seguro entre hilos).
        try:
            from concurrent.futures import ProcessPoolExecutor, as_completed
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_job, str(p)): p for p in pending}
                done = 0
                for future in as_completed(futures):
                    pdf = futures[future]
                    rel = pdf.relative_to(base).as_posix()
                    done += 1
                    remaining.remove(pdf)
                    try:
                        _, error = future.result()
                    except Exception as exc:
                        error = str(exc)
                    if error:
                        fail(pdf, rel, error)
                    with _status_lock:
                        nxt = remaining[0].relative_to(base).as_posix() if remaining else ""
                        _status.update(done=done, current=nxt)
        except Exception:
            pass  # sin procesos disponibles: lo que falte se hace uno a uno
    for i, pdf in enumerate(remaining):
        rel = pdf.relative_to(base).as_posix()
        with _status_lock:
            _status.update(current=rel, done=len(pending) - len(remaining) + i)
        try:
            ensure(pdf)
        except Exception as exc:  # p. ej. PDF a medio copiar o protegido
            fail(pdf, rel, str(exc))
    # Se conservan los fallos anteriores solo mientras el PDF siga existiendo y sin extraer.
    with _status_lock:
        previous = dict(_status["errors"])
    still = {}
    for rel, msg in previous.items():
        p = base / rel
        if p.is_file() and not is_fresh(p):
            still[rel] = msg
    with _status_lock:
        _status.update(running=False, done=len(pending), current="", errors={**still, **errors})


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
