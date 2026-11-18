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
UNI = ROOT / "University"
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
    p = (ROOT / rel).resolve()
    p.relative_to(UNI.resolve())  # ValueError si se sale de University/
    if p.suffix.lower() not in suffixes:
        raise ValueError("Tipo de archivo no permitido")
    return p


def list_tex():
    out = []
    for f in UNI.rglob("*.tex"):
        rel = f.relative_to(ROOT)
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
    return p.relative_to(ROOT).as_posix()


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
        "pdf": pdf.relative_to(ROOT).as_posix() if ok else None,
        "mtime": int(pdf.stat().st_mtime) if ok else 0,
    }


# ---------- PDF -> Markdown ----------

def pdf_to_markdown(pdf_path):
    if pymupdf is None:
        raise RuntimeError("PyMuPDF no está disponible")
    doc = pymupdf.open(str(pdf_path))
    try:
        sizes = {}
        for page in doc:
            for b in page.get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    for s in l["spans"]:
                        n = len(s["text"].strip())
                        if n:
                            k = round(s["size"])
                            sizes[k] = sizes.get(k, 0) + n
        body = max(sizes, key=sizes.get) if sizes else 11
        heads = sorted([k for k in sizes if k >= body + 2], reverse=True)[:3]

        out = []
        for i, page in enumerate(doc, 1):
            out.append(f"\n<!-- página {i} -->\n")
            for b in page.get_text("dict")["blocks"]:
                if b.get("type") != 0:
                    continue
                lines = []
                for l in b["lines"]:
                    text = ""
                    for s in l["spans"]:
                        t = s["text"]
                        if not t.strip():
                            text += t
                            continue
                        mono = "mono" in s["font"].lower() or "courier" in s["font"].lower()
                        bold = bool(s["flags"] & 16)
                        ital = bool(s["flags"] & 2)
                        if mono:
                            t = f"`{t.strip()}` "
                        elif bold and ital:
                            t = f"***{t.strip()}*** "
                        elif bold:
                            t = f"**{t.strip()}** "
                        elif ital:
                            t = f"*{t.strip()}* "
                        text += t
                    lines.append(text.strip())
                para = " ".join(x for x in lines if x)
                para = para.replace("** **", " ").replace("`  `", " ")
                if not para:
                    continue
                size = round(max(s["size"] for l in b["lines"] for s in l["spans"]))
                if size in heads and len(para) < 160:
                    level = heads.index(size) + 1
                    out.append("#" * level + " " + para.replace("**", "") + "\n")
                elif re.match(r"^[•●▪◦\-–]\s+", para):
                    out.append("- " + re.sub(r"^[•●▪◦\-–]\s+", "", para))
                else:
                    out.append(para + "\n")
        return "\n".join(out).strip() + "\n"
    finally:
        doc.close()


# ---------- Markdown -> LaTeX ----------

_ESC = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
        "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def _esc(t):
    return "".join(_ESC.get(c, c) for c in t)


def _inline(t):
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
        res.append(s)
    return "".join(res)


def markdown_to_latex(md):
    lines = md.splitlines()
    out, i, in_list = [], 0, None

    def close_list():
        nonlocal in_list
        if in_list:
            out.append(r"\end{%s}" % in_list)
            in_list = None

    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("```"):
            close_list()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            out += [r"\begin{lstlisting}", *code, r"\end{lstlisting}"]
        elif re.match(r"^\s*<!--.*-->\s*$", ln):
            close_list()
            out.append("%" + ln.strip()[4:-3])
        elif (m := re.match(r"^(#{1,4})\s+(.*)", ln)):
            close_list()
            cmd = ["section", "subsection", "subsubsection", "paragraph"][len(m.group(1)) - 1]
            out += ["", r"\%s{%s}" % (cmd, _inline(m.group(2).strip()))]
        elif (m := re.match(r"^\s*[-*+]\s+(.*)", ln)):
            if in_list != "itemize":
                close_list()
                out.append(r"\begin{itemize}")
                in_list = "itemize"
            out.append(r"  \item " + _inline(m.group(1)))
        elif (m := re.match(r"^\s*\d+[.)]\s+(.*)", ln)):
            if in_list != "enumerate":
                close_list()
                out.append(r"\begin{enumerate}")
                in_list = "enumerate"
            out.append(r"  \item " + _inline(m.group(1)))
        elif not ln.strip():
            close_list()
            out.append("")
        else:
            close_list()
            out.append(_inline(ln))
        i += 1
    close_list()
    body = "\n".join(out).strip()
    return TEMPLATE.split(r"\begin{document}")[0] + "\\begin{document}\n\\maketitle\n\n" + body + "\n\n\\end{document}\n"
