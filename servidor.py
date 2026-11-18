import html
import json
import logging
import re
import shutil
import webbrowser
import config
import extractor
import latex_api
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    import pymupdf
except Exception:
    pymupdf = None

logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("pymupdf").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parent


def source_root():
    r = config.root()
    if r is None:
        raise RuntimeError("Elige primero la carpeta de asignaturas")
    return r

PORT = 8000


def code_version():
    """Marca de la versión del código en disco (para avisar si el servidor está desactualizado)."""
    return max(int((ROOT / name).stat().st_mtime) for name in ("servidor.py", "latex_api.py", "config.py", "extractor.py", "limpieza.py"))


STARTED_CODE = code_version()
INVALID_NAME_CHARS = re.compile(r'[\\/:*?"<>|]')
PAGE_CACHE = {}


def get_page_count(pdf_path):
    try:
        stat = pdf_path.stat()
    except OSError:
        return None

    key = (str(pdf_path), stat.st_mtime, stat.st_size)
    if key in PAGE_CACHE:
        return PAGE_CACHE[key]

    pages = extractor.cached_pages(pdf_path)
    if pages is None and PdfReader is not None:
        try:
            pages = len(PdfReader(str(pdf_path)).pages)
        except Exception:
            pages = None
    if pages is None and pymupdf is not None:
        try:
            with extractor.PDF_LOCK, pymupdf.open(str(pdf_path)) as doc:
                pages = doc.page_count
        except Exception:
            pages = None

    PAGE_CACHE[key] = pages
    return pages


def extract_pdf_to_folder(pdf_path, force=False):
    output_dir, action = extractor.ensure(pdf_path, force=force)
    marker = extractor._read_marker(output_dir) or {}
    images = marker.get("images")
    if images is None:
        images = sum(1 for _ in (output_dir / "imagenes").glob("*")) if (output_dir / "imagenes").is_dir() else 0
    return {
        "folder": output_dir.relative_to(source_root()).as_posix(),
        "pages": marker.get("pages"),
        "images": images,
        "action": action,
    }


def ensure_extraction(pdf_path):
    try:
        return extractor.ensure(pdf_path)[0]
    except extractor.BlockedError:
        # Se muestra lo que quede (las vistas avisan si falta un archivo).
        out = extractor.output_dir(pdf_path)
        if out.is_dir():
            return out
        raise


def static_url(rel_path):
    return "/files/" + "/".join(quote(segment) for segment in rel_path.split("/"))


def build_preview_html(pdf_path, output_dir):
    """Página con el Markdown limpio de la extracción, renderizado y con sus imágenes."""
    try:
        md = (output_dir / "texto.md").read_text(encoding="utf-8")
    except OSError as exc:
        md = ("# No se puede abrir texto.md\n\nWindows no deja leer este archivo ("
              + (exc.strerror or str(exc)) + "). Suele ser **Windows Defender** marcándolo por error. "
              "Revisa *Seguridad de Windows → Protección contra virus → Historial de protección* "
              "o pulsa ↻ en la tarjeta para regenerarlo.\n")
    base_url = static_url(output_dir.relative_to(source_root()).as_posix()) + "/"
    md = md.replace("](imagenes/", "](" + base_url + "imagenes/")
    payload = json.dumps(md, ensure_ascii=False).replace("</", "<\\/")
    pdf_url = static_url(pdf_path.relative_to(source_root()).as_posix()) + "#page=1"
    title = html.escape(pdf_path.stem)
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; padding: 24px 16px 80px; background: #eef1f5; color: #1f2937;
         font: 16px/1.65 Georgia, 'Times New Roman', serif; }}
  .meta {{ max-width: 820px; margin: 0 auto 12px; color: #667085; font: 13px Inter, Segoe UI, Arial, sans-serif; }}
  .meta a {{ color: #155eef; }}
  article {{ max-width: 820px; margin: 0 auto; padding: 40px 48px; background: #fff;
            box-shadow: 0 4px 18px rgba(16,24,40,.10); border-radius: 4px; }}
  h1 {{ margin: 0 0 8px; font: 800 26px/1.25 Inter, Segoe UI, Arial, sans-serif; }}
  h2 {{ margin: 34px 0 2px; padding-top: 18px; border-top: 1px solid #eaecf0;
        font: 700 19px/1.3 Inter, Segoe UI, Arial, sans-serif; color: #101828; }}
  h1 + h2 {{ border-top: 0; }}
  sub {{ display: block; margin-bottom: 10px; color: #98a2b3; font: 12px Inter, Segoe UI, Arial, sans-serif; }}
  ul, ol {{ padding-left: 1.4em; }}
  li {{ margin: 3px 0; }}
  img {{ display: block; max-width: 100%; height: auto; margin: 14px auto; border: 1px solid #e5e7eb; border-radius: 4px; }}
  code {{ font-size: 14px; background: #f2f4f7; padding: 1px 4px; border-radius: 4px; }}
  em {{ color: #98a2b3; }}
  @media (max-width: 640px) {{ article {{ padding: 24px 18px; }} }}
</style></head><body>
<p class="meta"><a href="{html.escape(pdf_url, quote=True)}">Abrir PDF original</a> · texto limpio generado automáticamente</p>
<article id="doc"></article>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js"></script>
<script>
  const md = {payload};
  const doc = document.getElementById('doc');
  if (window.marked) doc.innerHTML = marked.parse(md);
  else {{ const pre = document.createElement('pre'); pre.style.whiteSpace = 'pre-wrap'; pre.textContent = md; doc.appendChild(pre); }}
</script>
</body></html>"""


def build_text_html(pdf_path, output_dir):
    """Página para leer texto.txt cómodamente (texto plano con buena tipografía)."""
    raw_url = static_url((output_dir / "texto.txt").relative_to(source_root()).as_posix())
    try:
        text = (output_dir / "texto.txt").read_text(encoding="utf-8")
    except OSError as exc:
        # Windows Defender a veces bloquea texto.txt (falso positivo con apuntes que citan código de ataques).
        md_url = "/api/preview?path=" + quote(pdf_path.relative_to(source_root()).as_posix())
        return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>Texto no disponible</title>
<style>body {{ margin: 0; padding: 40px 16px; background: #eef1f5; font: 15px/1.6 Inter, Segoe UI, Arial, sans-serif; color: #1f2937; }}
.box {{ max-width: 640px; margin: 0 auto; padding: 24px 28px; background: #fff; border-radius: 10px; box-shadow: 0 4px 18px rgba(16,24,40,.10); }}
a {{ color: #155eef; font-weight: 700; }} code {{ background: #f2f4f7; padding: 1px 5px; border-radius: 4px; }}</style></head>
<body><div class="box"><h2>No se puede abrir texto.txt</h2>
<p>Windows no deja leer este archivo ({html.escape(exc.strerror or str(exc))}). Suele pasar cuando
<b>Windows Defender</b> lo marca por error como sospechoso, por ejemplo en temas que citan código de ataques web.</p>
<p>El mismo contenido está en <a href="{html.escape(md_url, quote=True)}">la vista Markdown</a>.</p>
<p>Si quieres el .txt, revisa <i>Seguridad de Windows → Protección contra virus → Historial de protección</i>.</p>
</div></body></html>"""
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(pdf_path.stem)} · texto</title>
<style>
  body {{ margin: 0; padding: 24px 16px 80px; background: #eef1f5; color: #1f2937; }}
  .meta {{ max-width: 860px; margin: 0 auto 12px; color: #667085; font: 13px Inter, Segoe UI, Arial, sans-serif; }}
  .meta a {{ color: #155eef; }}
  pre {{ max-width: 860px; margin: 0 auto; padding: 32px 40px; background: #fff; border-radius: 4px;
        box-shadow: 0 4px 18px rgba(16,24,40,.10); white-space: pre-wrap; word-break: break-word;
        font: 14px/1.6 Consolas, "Cascadia Mono", monospace; }}
</style></head><body>
<p class="meta"><a href="{html.escape(raw_url, quote=True)}" download="texto.txt">Descargar texto.txt</a></p>
<pre>{html.escape(text)}</pre>
</body></html>"""


class Handler(SimpleHTTPRequestHandler):
    # Los archivos de texto se sirven como UTF-8 (si no, las tildes salen mal)
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".tex": "text/plain; charset=utf-8",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        # Sin caché: así cada cambio de la app se ve al recargar, sin Ctrl+F5.
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()

    def _html(self, page):
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _resolve_pdf(self, rel_path):
        if not rel_path:
            return None, "Falta la ruta del PDF"
        pdf = (source_root() / rel_path).resolve()
        try:
            pdf.relative_to(source_root())
        except ValueError:
            return None, "Ruta no válida"
        if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
            return None, "El archivo no existe o no es PDF"
        return pdf, None

    def translate_path(self, path):
        p = unquote(urlparse(path).path)
        if p.startswith("/files/"):
            base = config.root()
            target = (base / p[len("/files/"):]).resolve() if base else None
            if target is None or base not in target.parents and target != base:
                return str(ROOT / "__no_existe__")
            return str(target)
        return super().translate_path(path)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/version":
            self._json({"started": STARTED_CODE, "current": code_version()})
            return

        if path == "/api/signature":
            base = config.root()
            sig = []
            if base is not None:
                for p in base.rglob("*"):
                    if extractor.skipped(p.relative_to(base).parts):
                        continue
                    try:
                        if p.is_dir():
                            sig.append(f"d{p.relative_to(base)}")
                        elif p.suffix.lower() in (".pdf", ".tex", ".md"):
                            st = p.stat()
                            sig.append(f"{p.relative_to(base)}|{st.st_mtime_ns}|{st.st_size}")
                    except OSError:
                        pass
            self._json({"sig": str(base) + "|" + "|".join(sorted(sig))})
            return

        if path == "/api/files":
            base = config.root()
            if base is None:
                self._json({"configured": False, "root": "", "files": [], "subjects": []})
                return
            files, folders = [], []
            for item in base.rglob("*"):
                rel = item.relative_to(base)
                if extractor.skipped(rel.parts):
                    continue
                if item.is_dir():
                    folders.append(rel.as_posix())
                    continue
                kind = item.suffix.lower().lstrip(".")
                if kind not in ("pdf", "md", "tex"):
                    continue
                stat = item.stat()
                files.append({
                    "path": rel.as_posix(),
                    "name": item.name,
                    "kind": kind,
                    "folder": rel.parent.as_posix() if rel.parent != Path(".") else "",
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime),
                    "pages": get_page_count(item) if kind == "pdf" else None,
                    "generated": extractor.is_generated(item) if kind == "pdf" else False,
                    "extracted": extractor.is_fresh(item) if kind == "pdf" and not extractor.is_generated(item) else None,
                    "garbled": extractor.garbled_pages(item) if kind == "pdf" and not extractor.is_generated(item) else None,
                })
            files.sort(key=lambda item: (item["folder"].lower(), item["name"].lower()))
            subjects = sorted((f for f in folders if "/" not in f), key=str.lower)
            self._json({"configured": True, "root": str(base), "files": files,
                        "folders": folders, "subjects": subjects})
            return

        if path == "/api/view":
            query = parse_qs(urlparse(self.path).query)
            pdf, error = self._resolve_pdf(query.get("path", [""])[0].strip())
            if error:
                self._json({"ok": False, "error": error}, 404)
                return
            try:
                output_dir = ensure_extraction(pdf)
                self._html(build_text_html(pdf, output_dir))
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)
            return

        if path == "/api/stats":
            query = parse_qs(urlparse(self.path).query)
            pdf, error = self._resolve_pdf(query.get("path", [""])[0].strip())
            if error:
                self._json({"ok": False, "error": error}, 404)
                return
            try:
                self._json({"ok": True, **extractor.text_stats(pdf)})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)
            return

        if path == "/api/extract-status":
            self._json(extractor.status())
            return

        if path == "/api/extract":
            query = parse_qs(urlparse(self.path).query)
            rel_path = query.get("path", [""])[0].strip()
            pdf, error = self._resolve_pdf(rel_path)
            if error:
                self._json({"ok": False, "error": error}, 400 if "Falta" in error or "válida" in error else 404)
                return
            try:
                result = extract_pdf_to_folder(pdf, force=query.get("force", ["0"])[0] == "1")
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)
                return
            self._json({"ok": True, **result})
            return

        if path == "/api/preview":
            query = parse_qs(urlparse(self.path).query)
            rel_path = query.get("path", [""])[0].strip()
            pdf, error = self._resolve_pdf(rel_path)
            if error:
                self._json({"ok": False, "error": error}, 400 if "Falta" in error or "válida" in error else 404)
                return
            try:
                output_dir = ensure_extraction(pdf)
                preview = build_preview_html(pdf, output_dir)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)
                return
            body = preview.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith("/api/tex-") or path.startswith("/api/md-"):
            query = parse_qs(urlparse(self.path).query)
            rel = query.get("path", [""])[0].strip()
            try:
                if path == "/api/tex-files":
                    self._json({"files": latex_api.list_tex()})
                elif path == "/api/tex-read":
                    self._json({"ok": True, "content": latex_api.read_text(rel), "pdf": latex_api.pdf_state(rel)})
                else:
                    self.send_error(404)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            return

        if path in ("/", "/index.html"):
            self.path = "/index.html"
        super().do_GET()

    def _latex_post(self, path):
        try:
            data = self._read_json()
            rel = str(data.get("path", "")).strip()
            if path == "/api/tex-save":
                latex_api.save_text(rel, data.get("content", ""))
                self._json({"ok": True})
            elif path == "/api/tex-new":
                self._json({"ok": True, "path": latex_api.new_tex(rel)})
            elif path == "/api/tex-regen":
                self._json({"ok": True, "path": latex_api.regenerate_tex(rel)})
            elif path == "/api/tex-compile":
                if "content" in data:
                    latex_api.save_text(rel, data["content"])
                self._json(latex_api.compile_tex(rel))
            elif path == "/api/pdf-to-md":
                pdf, error = self._resolve_pdf(rel)
                if error:
                    self._json({"ok": False, "error": error}, 404)
                    return
                md = latex_api.pdf_to_markdown(pdf)
                md_path = pdf.with_suffix(".md")
                md_path.write_text(md, encoding="utf-8")
                self._json({"ok": True, "path": md_path.relative_to(source_root()).as_posix(), "content": md})
            elif path == "/api/md-to-tex":
                md_file = latex_api.resolve(rel, {".md"})
                tex = latex_api.markdown_to_latex(data.get("content") or md_file.read_text(encoding="utf-8"), md_file.parent)
                tex_path = md_file.with_name(md_file.stem + "_final.tex")
                tex_path.write_text(tex, encoding="utf-8")
                self._json({"ok": True, "path": tex_path.relative_to(source_root()).as_posix()})
            else:
                self.send_error(404)
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/pick-folder":
            try:
                chosen = config.pick_folder()
                if chosen:
                    config.set_root(chosen)
                    extractor.wake()
                self._json({"ok": True, "chosen": bool(chosen), "root": chosen})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)
            return
        if path == "/api/subject-new":
            try:
                name = INVALID_NAME_CHARS.sub("_", str(self._read_json().get("name", ""))).strip().strip(".")
                if not name:
                    raise ValueError("Nombre no válido")
                (source_root() / name).mkdir(parents=True, exist_ok=True)
                self._json({"ok": True, "name": name})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            return
        if path.startswith("/api/tex-") or path.startswith("/api/pdf-") or path.startswith("/api/md-"):
            self._latex_post(path)
            return
        if path != "/api/rename":
            self.send_error(404)
            return

        try:
            data = self._read_json()
            rel_path = str(data.get("path", "")).strip()
            new_name = str(data.get("newName", "")).strip()

            if not rel_path or not new_name:
                self._json({"ok": False, "error": "Faltan datos"}, 400)
                return

            source, error = self._resolve_pdf(rel_path)
            if error:
                self._json({"ok": False, "error": error}, 404)
                return

            if not new_name.lower().endswith(".pdf"):
                new_name += ".pdf"
            new_name = INVALID_NAME_CHARS.sub("_", Path(new_name).name).strip()
            if not new_name or new_name in (".", ".."):
                self._json({"ok": False, "error": "Nombre no válido"}, 400)
                return

            destination = source.with_name(new_name)
            if destination.exists():
                self._json({"ok": False, "error": "Ya existe un archivo con ese nombre"}, 409)
                return

            source.rename(destination)
            self._json({
                "ok": True,
                "path": destination.relative_to(source_root()).as_posix(),
                "name": destination.name,
            })
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, 500)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    extractor.start()
    url = f"http://localhost:{PORT}"
    print(f"Servidor listo en {url}")
    print("Presiona Ctrl+C para detenerlo.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
