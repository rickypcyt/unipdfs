import html
import json
import logging
import re
import shutil
import webbrowser
import config
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

    pages = None
    if PdfReader is not None:
        try:
            pages = len(PdfReader(str(pdf_path)).pages)
        except Exception:
            pages = None

    PAGE_CACHE[key] = pages
    return pages


def extract_pdf_to_folder(pdf_path):
    if pymupdf is None:
        raise RuntimeError("PyMuPDF no está disponible en este Python")

    output_dir = pdf_path.parent / (pdf_path.stem + "_extraido")
    if output_dir.is_dir():
        shutil.rmtree(output_dir)
    elif output_dir.exists():
        output_dir.unlink()

    images_dir = output_dir / "imagenes"
    images_dir.mkdir(parents=True)

    text_parts = []
    seen_images = set()
    image_count = 0

    doc = pymupdf.open(str(pdf_path))
    try:
        for index in range(len(doc)):
            page = doc.load_page(index)
            page_number = index + 1
            text_parts.append(f"--- Página {page_number} ---\n{page.get_text('text')}\n")

            for image_info in page.get_images(full=True):
                xref = image_info[0]
                if xref in seen_images:
                    continue
                seen_images.add(xref)
                try:
                    image = doc.extract_image(xref)
                except Exception:
                    continue
                data = image.get("image")
                if not data:
                    continue
                image_count += 1
                extension = image.get("ext") or "png"
                (images_dir / f"img_{image_count:03d}_p{page_number}.{extension}").write_bytes(data)
    finally:
        doc.close()

    (output_dir / "texto.txt").write_text("\n".join(text_parts), encoding="utf-8")

    return {
        "folder": output_dir.relative_to(source_root()).as_posix(),
        "pages": len(text_parts),
        "images": image_count,
    }


def ensure_extraction(pdf_path):
    output_dir = pdf_path.parent / (pdf_path.stem + "_extraido")
    if not (output_dir / "texto.txt").exists():
        extract_pdf_to_folder(pdf_path)
    return output_dir


def static_url(rel_path):
    return "/files/" + "/".join(quote(segment) for segment in rel_path.split("/"))


def build_preview_html(pdf_path, output_dir):
    content = (output_dir / "texto.txt").read_text(encoding="utf-8")
    page_map = {}
    for match in re.finditer(r"--- Página (\d+) ---\n(.*?)(?=--- Página \d+ ---|\Z)", content, re.S):
        number = int(match.group(1))
        page_map[number] = {"number": number, "text": match.group(2).strip(), "images": []}

    images_dir = output_dir / "imagenes"
    if images_dir.is_dir():
        for image_path in sorted(images_dir.iterdir()):
            if not image_path.is_file():
                continue
            match = re.search(r"_p(\d+)\.[^.]+$", image_path.name)
            number = int(match.group(1)) if match else 1
            if number not in page_map:
                page_map[number] = {"number": number, "text": "", "images": []}
            page_map[number]["images"].append(image_path)

    pages = [page_map[key] for key in sorted(page_map)]

    css = """
    <style>
      body { margin: 0; padding: 24px 16px 60px; background: #eef1f5; }
      header { max-width: 820px; margin: 0 auto 8px; }
      h1 { margin: 0 0 6px; font-size: 24px; }
      .meta { margin: 0 0 24px; color: #667085; font-size: 14px; }
      .meta a { color: #155eef; }
      .page { max-width: 820px; margin: 28px auto; padding: 42px 48px; background: #fff; box-shadow: 0 4px 18px rgba(16,24,40,.10); font-family: Georgia, 'Times New Roman', serif; color: #1f2937; line-height: 1.65; }
      .page h2 { margin: 0 0 14px; color: #667085; font-size: 14px; font-family: Inter, Segoe UI, Arial, sans-serif; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; }
      .text { white-space: pre-wrap; word-break: break-word; }
      .images { margin-top: 18px; }
      .images img { display: block; max-width: 100%; height: auto; margin: 12px auto; border: 1px solid #e5e7eb; }
    </style>
    """

    body = []
    for page in pages:
        images = []
        for index, image_path in enumerate(page["images"], start=1):
            rel = (output_dir / "imagenes" / image_path.name).relative_to(source_root()).as_posix()
            src = static_url(rel)
            images.append(f'<img src="{html.escape(src, quote=True)}" alt="Imagen {index} de la página {page["number"]}">')
        body.append(
            f'<section class="page"><h2>Página {page["number"]}</h2>'
            f'<div class="text">{html.escape(page["text"])}</div>'
            f'<div class="images">{"".join(images)}</div></section>'
        )

    pdf_url = static_url(pdf_path.relative_to(source_root()).as_posix()) + "#page=1"
    return (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{html.escape(pdf_path.stem)}</title>{css}</head><body>'
        f'<header><h1>{html.escape(pdf_path.stem)}</h1>'
        f'<p class="meta">{len(pages)} páginas · {sum(len(page["images"]) for page in pages)} imágenes · '
        f'<a href="/">Volver al índice</a> · <a href="{html.escape(pdf_url, quote=True)}">Abrir PDF</a></p></header>'
        + "".join(body)
        + '</body></html>'
    )


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

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
        if path == "/api/files":
            base = config.root()
            if base is None:
                self._json({"configured": False, "root": "", "files": [], "subjects": []})
                return
            files = []
            for pdf in base.rglob("*.pdf"):
                if not pdf.is_file():
                    continue
                stat = pdf.stat()
                files.append({
                    "path": pdf.relative_to(source_root()).as_posix(),
                    "name": pdf.name,
                    "folder": pdf.parent.relative_to(base).as_posix() if pdf.parent != base else "",
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime),
                    "pages": get_page_count(pdf),
                })
            files.sort(key=lambda item: (item["folder"].lower(), item["name"].lower()))
            subjects = sorted((d.name for d in base.iterdir() if d.is_dir() and not d.name.startswith((".", "_"))), key=str.lower)
            self._json({"configured": True, "root": str(base), "files": files, "subjects": subjects})
            return

        if path == "/api/extract":
            query = parse_qs(urlparse(self.path).query)
            rel_path = query.get("path", [""])[0].strip()
            pdf, error = self._resolve_pdf(rel_path)
            if error:
                self._json({"ok": False, "error": error}, 400 if "Falta" in error or "válida" in error else 404)
                return
            try:
                result = extract_pdf_to_folder(pdf)
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
                    self._json({"ok": True, "content": latex_api.read_text(rel)})
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
                tex = latex_api.markdown_to_latex(data.get("content") or md_file.read_text(encoding="utf-8"))
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
