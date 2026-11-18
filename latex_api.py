"""Utilidades para el taller LaTeX: compilar .tex, PDF -> Markdown, Markdown -> LaTeX."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import pymupdf
except Exception:
    pymupdf = None

ROOT = Path(__file__).resolve().parent


def src():
    import config
    r = config.root()
    if r is None:
        raise RuntimeError("Elige primero la carpeta de asignaturas")
    return r

_EXE = "tectonic.exe" if sys.platform == "win32" else "tectonic"
_LOCAL = ROOT / "_herramientas" / "tectonic" / _EXE
TECTONIC = _LOCAL if _LOCAL.exists() else Path(shutil.which("tectonic") or _LOCAL)
SKIP_DIRS = {"_herramientas", "_build"}

TEMPLATE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[spanish,es-noshorthands]{babel}
\usepackage{lmodern}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[margin=2.2cm]{geometry}
\usepackage{amsmath,amssymb,graphicx,hyperref,listings,xcolor}
\sloppy
\lstset{basicstyle=\ttfamily\small,breaklines=true,frame=single}

\title{Título}
\author{}
\date{}

\begin{document}
\maketitle

\section{Introducción}
Escribe aquí.

\end{document}
"""


def resolve(rel, suffixes):
    if not rel:
        raise ValueError("Falta la ruta")
    p = (src() / rel).resolve()
    p.relative_to(src())  # ValueError si se sale de la carpeta fuente
    if p.suffix.lower() not in suffixes:
        raise ValueError("Tipo de archivo no permitido")
    return p


def list_tex():
    out = []
    base = src()
    for f in base.rglob("*.tex"):
        rel = f.relative_to(base)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        out.append({
            "path": rel.as_posix(),
            "name": f.name,
            "folder": rel.parent.as_posix() if rel.parent != Path(".") else "",
            "modified": int(f.stat().st_mtime),
        })
    out.sort(key=lambda i: (i["folder"].lower(), i["name"].lower()))
    return out


def read_text(rel):
    p = resolve(rel, {".tex", ".md"})
    return p.read_text(encoding="utf-8", errors="replace")


def save_text(rel, content):
    p = resolve(rel, {".tex", ".md"})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    return p


def new_tex(rel):
    if not rel.lower().endswith(".tex"):
        rel += ".tex"
    p = resolve(rel, {".tex"})
    if p.exists():
        raise FileExistsError("Ya existe un archivo con ese nombre")
    save_text(rel, TEMPLATE)
    return p.relative_to(src()).as_posix()


def pdf_state(rel):
    """¿Ya hay un PDF compilado de este .tex y sigue al día? (así no se recompila al abrirlo)"""
    p = resolve(rel, {".tex", ".md"})
    if p.suffix.lower() != ".tex":
        return {"exists": False, "stale": False}
    pdf = p.with_suffix(".pdf")
    if not pdf.is_file():
        return {"exists": False, "stale": False}
    return {"exists": True, "stale": pdf.stat().st_mtime_ns < p.stat().st_mtime_ns, "mtime": int(pdf.stat().st_mtime)}


def compile_tex(rel):
    p = resolve(rel, {".tex"})
    if not TECTONIC.exists():
        return {"ok": False, "log": "No se encuentra Tectonic. Ejecuta: python setup.py"}
    try:
        r = subprocess.run(
            [str(TECTONIC), "-X", "compile", "--keep-logs",
             "--outdir", str(p.parent), p.name],
            cwd=str(p.parent), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "log": "Tiempo agotado (300 s). La primera compilación descarga paquetes; reintenta."}
    log = (r.stdout or "") + (r.stderr or "")
    pdf = p.with_suffix(".pdf")
    ok = r.returncode == 0 and pdf.exists()
    return {
        "ok": ok,
        "log": log,
        "pdf": pdf.relative_to(src()).as_posix() if ok else None,
        "mtime": int(pdf.stat().st_mtime) if ok else 0,
    }


# ---------- PDF -> Markdown ----------

def pdf_to_markdown(pdf_path):
    """Markdown limpio (sin pies repetidos, viñetas reconstruidas). Usa la misma limpieza que la extracción."""
    if pymupdf is None:
        raise RuntimeError("PyMuPDF no está disponible")
    import extractor
    import limpieza
    with extractor.PDF_LOCK:
        doc = pymupdf.open(str(pdf_path))
        try:
            pages = limpieza.analyze(doc)
        finally:
            doc.close()
    return limpieza.to_markdown(pages, limpieza.pretty_title(Path(pdf_path).stem))


# ---------- Markdown -> LaTeX ----------

_ESC = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
        "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def _esc(t):
    return "".join(_ESC.get(c, c) for c in t)


def _inline(t):
    t = t.replace("\\*", "\x00")  # asterisco escapado en Markdown = asterisco literal
    parts = re.split(r"(`[^`]+`)", t)
    res = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            res.append(r"\texttt{" + _esc(part[1:-1]) + "}")
            continue
        s = _esc(part)
        s = re.sub(r"\*\*\*(.+?)\*\*\*", r"\\textbf{\\emph{\1}}", s)
        s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)
        s = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"\\emph{\1}", s)
        s = s.replace("→", r"$\rightarrow$")
        res.append(s)
    return "".join(res).replace("\x00", "*")


_HEAD = re.compile(r"^(#{1,6})\s+(.*)")
_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)")
_IMG = re.compile(r"^\s*!\[[^\]]*\]\(([^)\s]+)\)\s*$")
_PAGE = re.compile(r"^\s*<sub>\s*(.*?)\s*</sub>\s*$")


def markdown_to_latex(md, base_dir=None):
    """Markdown -> documento LaTeX. `base_dir` sirve para comprobar que las imágenes existen."""
    lines = md.splitlines()

    # El primer "# Título" es el título del documento; el resto de niveles se reajusta
    # para que el encabezado más alto que quede sea \section.
    title = ""
    first = next((ln for ln in lines if ln.strip()), "")
    if (m := _HEAD.match(first)) and len(m.group(1)) == 1:
        title = m.group(2).strip()
        lines.remove(first)
    levels = [len(m.group(1)) for ln in lines if (m := _HEAD.match(ln))]
    shift = (min(levels) - 1) if levels else 0
    cmds = ["section", "subsection", "subsubsection", "paragraph", "subparagraph", "subparagraph"]

    out, stack, i = [], [], 0  # stack: [(entorno, sangría)]

    def close_lists(indent=-1):
        while stack and stack[-1][1] > indent:
            out.append("  " * (len(stack) - 1) + r"\end{%s}" % stack.pop()[0])

    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("```"):
            close_lists()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            out += [r"\begin{lstlisting}", *code, r"\end{lstlisting}"]
        elif re.match(r"^\s*<!--.*-->\s*$", ln):
            close_lists()
            out.append("%" + ln.strip()[4:-3])
        elif (m := _PAGE.match(ln)):
            close_lists()
            out.append(r"{\footnotesize\color{gray}" + _inline(m.group(1)).replace("p. ", "p.~") + r"}\par")
        elif (m := _IMG.match(ln)):
            close_lists()
            src = m.group(1)
            ok = not src.startswith(("http:", "https:")) and " " not in src and (
                base_dir is None or (Path(base_dir) / src).exists())
            if ok:
                out += [r"\begin{center}",
                        r"\includegraphics[width=0.85\linewidth,height=0.42\textheight,keepaspectratio]{%s}" % src,
                        r"\end{center}"]
            else:
                out.append("% imagen no incluida: " + src)
        elif (m := _HEAD.match(ln)):
            close_lists()
            level = max(len(m.group(1)) - shift, 1)
            out += ["", r"\%s*{%s}" % (cmds[level - 1], _inline(m.group(2).strip()))]
        elif (m := _ITEM.match(ln)):
            indent = len(m.group(1).replace("\t", "    "))
            env = "enumerate" if m.group(2)[0].isdigit() else "itemize"
            close_lists(indent)
            if stack and stack[-1][1] == indent and stack[-1][0] != env:
                out.append("  " * (len(stack) - 1) + r"\end{%s}" % stack.pop()[0])
            if not stack or stack[-1][1] < indent:
                out.append("  " * len(stack) + r"\begin{%s}" % env)
                stack.append((env, indent))
            # En listas numeradas se conserva el número original (2. no debe volver a ser 1.)
            label = "[{%s}] " % m.group(2) if env == "enumerate" else " "
            out.append("  " * len(stack) + r"\item" + label + _inline(m.group(3)))
        elif not ln.strip():
            if not (i + 1 < len(lines) and _ITEM.match(lines[i + 1]) and stack):
                close_lists()
            out.append("")
        else:
            close_lists()
            out.append(_inline(ln))
        i += 1
    close_lists()
    body = "\n".join(out).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    pre = TEMPLATE.split(r"\begin{document}")[0]
    if title:
        pre = pre.replace(r"\title{Título}", r"\title{%s}" % _inline(title))
    return pre + "\\begin{document}\n\\maketitle\n\n" + body + "\n\n\\end{document}\n"
