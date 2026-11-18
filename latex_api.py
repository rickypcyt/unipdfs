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
\usepackage{iftex}
\ifXeTeX
  \usepackage{fontspec}          % Tectonic usa XeTeX: Unicode nativo (¿ ¡ º ñ salen bien)
\else
  \usepackage[utf8]{inputenc}
  \usepackage[T1]{fontenc}
  \usepackage{lmodern}
\fi
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


def published_path(tex):
    """Dónde se publica el PDF de un texto.tex generado a partir de un PDF: en el tema, junto al original.
    Ej.: Tema 3/Parte I_extraido/texto.tex  ->  Tema 3/Parte I VersionLatex.pdf  (None para otros .tex)."""
    import config
    folder = tex.parent
    if tex.name != "texto.tex" or not folder.name.endswith("_extraido"):
        return None
    return folder.parent / (folder.name[:-len("_extraido")] + config.LATEX_SUFFIX + ".pdf")


def publish_pdf(tex):
    """Copia el PDF compilado al tema con su nombre definitivo (solo si cambió). Devuelve su ruta relativa."""
    dest = published_path(tex)
    pdf = tex.with_suffix(".pdf")
    if dest is None or not pdf.is_file():
        return None
    try:
        if (not dest.exists() or dest.stat().st_size != pdf.stat().st_size
                or dest.stat().st_mtime_ns < pdf.stat().st_mtime_ns):
            shutil.copy2(pdf, dest)
    except OSError:
        return None
    return dest.relative_to(src()).as_posix()


def pdf_state(rel):
    """¿Ya hay un PDF compilado de este .tex y sigue al día? (así no se recompila al abrirlo)"""
    p = resolve(rel, {".tex", ".md"})
    if p.suffix.lower() != ".tex":
        return {"exists": False, "stale": False}
    pdf = p.with_suffix(".pdf")
    if not pdf.is_file():
        return {"exists": False, "stale": False}
    stale = pdf.stat().st_mtime_ns < p.stat().st_mtime_ns
    return {"exists": True, "stale": stale, "mtime": int(pdf.stat().st_mtime),
            "published": None if stale else publish_pdf(p)}


def regenerate_tex(rel):
    """Rehace texto.tex desde su texto.md con el estilo de apuntes. Guarda el anterior en anterior/."""
    p = resolve(rel, {".tex"})
    folder = p.parent
    md = folder / "texto.md"
    if p.name != "texto.tex" or not folder.name.endswith("_extraido") or not md.is_file():
        raise ValueError("Solo se puede regenerar un texto.tex que venga de una extracción (con su texto.md)")
    if p.exists():
        (folder / "anterior").mkdir(exist_ok=True)
        shutil.copy2(p, folder / "anterior" / "texto.tex")
    p.write_text(markdown_to_latex(md.read_text(encoding="utf-8"), folder), encoding="utf-8")
    return p.relative_to(src()).as_posix()


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
        "published": publish_pdf(p) if ok else None,
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
        urls = []

        def grab(m):
            url = m.group(0).rstrip(".,;:)")
            urls.append(url)
            return "\x01%d\x02" % (len(urls) - 1) + m.group(0)[len(url):]

        part = re.sub(r"https?://[^\s<>\"“”]+", grab, part)
        s = _esc(part)
        s = re.sub(r"[“\"]\s*([^“”\"]{1,120}?)\s*[”\"]", r"\\enquote{\1}", s)
        s = re.sub(r"\x01(\d+)\x02", lambda mm: "\\url{" + urls[int(mm.group(1))] + "}", s)
        s = re.sub(r"\*\*\*(.+?)\*\*\*", r"\\textbf{\\emph{\1}}", s)
        s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)
        s = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"\\emph{\1}", s)
        s = s.replace("→", r"$\rightarrow$")
        res.append(s)
    return "".join(res).replace("\x00", "*")

# Preámbulo "apuntes": tipografía cuidada, cabecera con la sección, cajas, listados con color y macros
# \diapo (referencia a la diapositiva en el margen) y \figura (imagen centrada con tamaño acotado).
PRO_PREAMBLE = r"""\documentclass[11pt,a4paper]{article}

% ---------------------------------------------------------------
%  Idioma y tipografía
% ---------------------------------------------------------------
\usepackage{iftex}
\ifXeTeX
  \usepackage{fontspec}          % Tectonic usa XeTeX: Unicode nativo (¿ ¡ º ñ salen bien)
\else
  \usepackage[utf8]{inputenc}
  \usepackage[T1]{fontenc}
  \usepackage{lmodern}
\fi
\usepackage[spanish,es-noshorthands,es-tabla]{babel}
\usepackage{microtype}
\emergencystretch=1.5em
\usepackage[spanish=spanish]{csquotes}

% ---------------------------------------------------------------
%  Página
% ---------------------------------------------------------------
\usepackage[margin=2.4cm,marginparwidth=1.9cm,marginparsep=3mm]{geometry}
\usepackage{parskip}
\usepackage{fancyhdr}
\setlength{\headheight}{14pt}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small %%HEADER%%}
\fancyhead[R]{\small\nouppercase{\leftmark}}
\fancyfoot[C]{\small\thepage}
\renewcommand{\headrulewidth}{0.4pt}

% ---------------------------------------------------------------
%  Paquetes
% ---------------------------------------------------------------
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage[dvipsnames]{xcolor}
\usepackage{booktabs,tabularx,array}
\usepackage{float}
\usepackage{enumitem}
\setlist{itemsep=2pt,topsep=4pt}
\usepackage{listings}
\usepackage[most]{tcolorbox}
\usepackage{hyperref}   % siempre de los últimos
\hypersetup{colorlinks=true,linkcolor=NavyBlue,urlcolor=NavyBlue}
\urlstyle{tt}
\sloppy

\usepackage{tocloft}
\setlength{\cftsecnumwidth}{2.4em}
\setlength{\cftsubsecindent}{2.4em}
\setlength{\cftsubsecnumwidth}{3.2em}
\setlength{\cftsubsubsecindent}{5.6em}
\setlength{\cftsubsubsecnumwidth}{4em}

\graphicspath{{imagenes/}}

% ---------------------------------------------------------------
%  Macros propias
% ---------------------------------------------------------------
% Referencia a la diapositiva original, en el margen
\newcommand{\diapo}[1]{\marginpar{\raggedright\footnotesize\color{gray}diap.~#1}}

% Imagen centrada con tamaño acotado
\newcommand{\figura}[2]{%
  \begin{center}
    \includegraphics[width=0.85\linewidth,height=0.42\textheight,keepaspectratio]{#1}
    \par\smallskip{\small\itshape #2}
  \end{center}}

% Cajas
\newtcolorbox{definicion}[1][Definición]{
  colback=NavyBlue!5, colframe=NavyBlue!70, fonttitle=\bfseries,
  title=#1, enhanced, breakable, boxrule=0.6pt, arc=2pt}
\newtcolorbox{nota}[1][Nota]{
  colback=Goldenrod!8, colframe=Goldenrod!80!black, fonttitle=\bfseries,
  title=#1, enhanced, breakable, boxrule=0.6pt, arc=2pt}
\newtcolorbox{ejercicio}[1][Ejercicio propuesto]{
  colback=ForestGreen!5, colframe=ForestGreen!70!black, fonttitle=\bfseries,
  title=#1, enhanced, breakable, boxrule=0.6pt, arc=2pt}

% ---------------------------------------------------------------
%  Listados de código
% ---------------------------------------------------------------
\lstset{
  basicstyle=\ttfamily\small,
  columns=fullflexible,
  keepspaces=true,
  breaklines=true,
  breakatwhitespace=false,
  postbreak=\mbox{\textcolor{gray}{$\hookrightarrow$}\space},
  frame=single,
  rulecolor=\color{gray!50},
  backgroundcolor=\color{gray!5},
  framesep=4pt,
  xleftmargin=6pt, xrightmargin=6pt,
  numberstyle=\tiny\color{gray},
  keywordstyle=\color{NavyBlue}\bfseries,
  stringstyle=\color{BrickRed},
  commentstyle=\color{ForestGreen}\itshape,
  showstringspaces=false,
  upquote=true,
  extendedchars=true,
  literate={á}{{\'a}}1 {é}{{\'e}}1 {í}{{\'i}}1 {ó}{{\'o}}1 {ú}{{\'u}}1
           {ñ}{{\~n}}1 {Á}{{\'A}}1 {É}{{\'E}}1 {Í}{{\'I}}1 {Ó}{{\'O}}1 {Ú}{{\'U}}1
           {Ñ}{{\~N}}1 {¿}{{?`}}1 {¡}{{!`}}1
}
\lstdefinelanguage{HTTP}{
  morekeywords={GET,POST,HEAD,PUT,DELETE,TRACE,OPTIONS},
  sensitive=true
}
\lstdefinelanguage{JSON}{
  morestring=[b]",
  literate=*{:}{{\textcolor{gray}{:}}}1 {,}{{\textcolor{gray}{,}}}1
}
\lstdefinelanguage{HTMLx}[]{HTML}{
  morekeywords={meta,http-equiv,content}
}

% ---------------------------------------------------------------
\title{\textbf{%%TITLE%%}}
\author{}
\date{}

% Numeración acorde con el temario (si los títulos de las diapositivas la traen)
%%NUMBERING%%

\begin{document}
\maketitle
\thispagestyle{empty}

\tableofcontents
\clearpage
"""

_FOLD = {"→": "->", "←": "<-", "“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "--", "…": "...",
         "•": "*", " ": " ", "​": ""}
_KEEP_CODE = set("áéíóúñÁÉÍÓÚÑ¿¡")


def _safe_code(code):
    """Código apto para listings: se cambian los caracteres que no sabe dibujar (se conservan las tildes)."""
    import unicodedata
    out = []
    for ch in code:
        ch = _FOLD.get(ch, ch)
        for c in ch:
            if ord(c) < 128 or c in _KEEP_CODE or c == "\n":
                out.append(c)
            else:
                base = unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode()
                out.append(base or "?")
    return "".join(out)


def _guess_lang(code):
    """Lenguaje del listado, por el aspecto del código (HTTP, JSON, HTML o Java); None si no está claro."""
    text = code.strip()
    first = text.splitlines()[0] if text else ""
    if re.match(r"^(GET|POST|HEAD|PUT|DELETE|TRACE|OPTIONS)\s+\S+\s+HTTP/\d", first) or re.match(r"^HTTP/\d", first):
        return "HTTP"
    if text[:1] in "{[" and re.search(r'"\s*:', text):
        return "JSON"
    if re.match(r"^<\s*[!A-Za-z/]", text):
        return "HTMLx"
    if re.search(r"\b(System\.out|new\s+\w+\s*\(|public\s+(static\s+)?(class|void)|import\s+java|PrintWriter|Socket)\b", text):
        return "Java"
    return None


_HEAD = re.compile(r"^(#{1,6})\s+(.*)")
_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)")
_IMG = re.compile(r"^\s*!\[[^\]]*\]\(([^)\s]+)\)\s*$")
_PAGE = re.compile(r"^\s*<sub>\s*(.*?)\s*</sub>\s*$")
_NOTE = re.compile(r"^\*Nota:\s*(.*?)\*?\s*$")


def _find_dividers(lines):
    """Diapositivas "separador" (título + una sola frase corta): esa frase pasa a ser una sección."""
    heads, in_fence = [], False
    for i, ln in enumerate(lines):
        if ln.strip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and re.match(r"^#{1,2}\s+", ln):
            heads.append(i)
    dividers = {}
    for n, i in enumerate(heads):
        if not lines[i].startswith("## "):
            continue
        end = heads[n + 1] if n + 1 < len(heads) else len(lines)
        content = [(j, lines[j].strip()) for j in range(i + 1, end)
                   if lines[j].strip() and not _PAGE.match(lines[j]) and not lines[j].strip().startswith("<!--")
                   and not _NOTE.match(lines[j].strip())]
        if len(content) == 1:
            j, text = content[0]
            plain = not (_ITEM.match(lines[j]) or _IMG.match(lines[j]) or text.startswith("```"))
            if plain and len(text.split()) <= 8 and not text.endswith((".", ":")):
                dividers[i] = (j, text)
    return dividers


_SERIES = re.compile(r"\s*\((?:[IVX]{1,6}|\d{1,2})\)\s*$|\s*\(continuaci[oó]n\)\s*$", re.I)
_INDEX_TITLE = re.compile(r"(?i)^(contenidos?|índice|indice|agenda|esquema)\b")
_SINTEXTO = re.compile(r"^\*\(diapositiva sin texto\)\*$")
_NUMBERED_HEAD = re.compile(r"^(\d+(?:\.\d+)+)\.?\s+(\S.*)$")
_INDEX_LINE = re.compile(r"^\s*(?:[-*]\s+)?\d+\.\d+")
_BOLD_LINE = re.compile(r"^\*\*([^*]+)\*\*\s*$")


def _page_numbers(body):
    nums = []
    for ln in body:
        m = _PAGE.match(ln)
        if m:
            nums += [int(x) for x in re.findall(r"\d+", m.group(1))]
    return nums


def _fmt_pages(nums):
    groups = []
    for n in sorted(set(nums)):
        if groups and n == groups[-1][-1] + 1:
            groups[-1].append(n)
        else:
            groups.append([n])
    return ", ".join(f"{g[0]}--{g[-1]}" if len(g) > 1 else str(g[0]) for g in groups)


def _split_slides(lines):
    """Separa el Markdown en bloques: cada `## título` abre una diapositiva (lo anterior es el bloque sin título)."""
    blocks, cur, in_fence = [{"head": None, "body": []}], None, False
    cur = blocks[0]
    for ln in lines:
        if ln.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and ln.startswith("## "):
            cur = {"head": ln[3:].strip(), "body": []}
            blocks.append(cur)
        else:
            cur["body"].append(ln)
    return blocks


def _prepare_slides(lines):
    """Limpia la estructura antes de convertir: quita diapositivas vacías e índices y une las series (I), (II)…"""
    kept = []
    for b in _split_slides(lines):
        b["body"] = [ln for ln in b["body"] if not _SINTEXTO.match(ln.strip())]
        head = b["head"]
        if head is not None:
            content = [ln for ln in b["body"] if ln.strip() and not _PAGE.match(ln) and not ln.strip().startswith("<!--")]
            index_like = sum(1 for ln in content if _INDEX_LINE.match(ln))
            # Índice: ya existe \tableofcontents
            if _INDEX_TITLE.match(head) or (len(content) >= 3 and index_like >= 0.7 * len(content)):
                continue
        kept.append(b)

    merged = []
    for b in kept:
        head = b["head"]
        b["raw"] = head or ""
        b["base"] = _SERIES.sub("", head).strip() if head else None
        b["pages"] = _page_numbers(b["body"])
        b["members"] = 1
        prev = merged[-1] if merged else None
        if (prev and head is not None and prev["head"] is not None and b["base"]
                and b["base"].lower() == prev["base"].lower()
                and (_SERIES.search(head) or head.lower() == prev["raw"].lower())):
            prev["pages"] += b["pages"]
            prev["body"] += b["body"]
            prev["members"] += 1
            continue
        merged.append(b)

    out = []
    for b in merged:
        if b["head"] is None:
            out += b["body"]
            continue
        out.append("## " + (b["base"] if b["members"] > 1 else b["raw"]))
        if b["pages"]:
            out.append(f"<sub>p. {_fmt_pages(b['pages'])}</sub>")
        out += [ln for ln in b["body"] if not _PAGE.match(ln)]
    return out


def _plan_headings(lines, dividers):
    """Para cada `## título`: qué comando LaTeX le toca y con qué texto (quita numeraciones propias como «1.5.1.»)."""
    heads, in_fence = [], False
    for i, ln in enumerate(lines):
        if ln.strip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and ln.startswith("## "):
            heads.append((i, ln[3:].strip()))
    cmds = ["section", "subsection", "subsubsection"]
    plan, numbering = {}, None
    numbered = [(i, _NUMBERED_HEAD.match(t)) for i, t in heads if _NUMBERED_HEAD.match(t)]
    if len(numbered) >= 3 and len(numbered) >= 0.25 * len(heads):
        const_prefix = len({m.group(1).split(".")[0] for _, m in numbered}) == 1
        last, last_section = None, None
        for i, text in heads:
            m = _NUMBERED_HEAD.match(text)
            if m:
                depth = len(m.group(1).split("."))
                level = max(0, min(depth - (2 if const_prefix else 1), 2))
                if level == 0:
                    if m.group(1) == last_section:      # el PDF repite «1.5. Servidores DNS» antes de cada subapartado
                        plan[i] = ("skip", m.group(2))
                        continue
                    last_section = m.group(1)
                text, last = m.group(2), level
            elif re.fullmatch(r"\d+(?:\.\d+)*\.?", text.strip()):
                plan[i] = ("skip", text)                # un título que es solo un número no dice nada
                continue
            else:
                level = 0 if last is None else min(last + 1, 2)
                if last is None and const_prefix:
                    plan[i] = ("section*", text)        # antes del primer apartado numerado: secciones sin número
                    continue
            plan[i] = (cmds[level], text)
        if const_prefix:
            first = next((m for _, m in numbered if len(m.group(1).split(".")) == 2), numbered[0][1])
            parts = first.group(1).split(".")
            numbering = (parts[0], int(parts[1]) if len(parts) > 1 else 1)
        return plan, numbering, "numbered"
    hier = len(dividers) >= 2
    seen_first = False
    for i, text in heads:
        if i in dividers:
            plan[i] = ("section", dividers[i][1])
        elif not hier or not seen_first:
            plan[i] = ("section", text)
        else:
            plan[i] = ("subsection", text)
        seen_first = True
    return plan, None, "hier" if hier else "flat"


def _grid(names):
    """Varias imágenes de una diapositiva: cuadrícula de 3 por fila."""
    out = [r"\begin{center}"]
    for k, name in enumerate(names):
        last = k == len(names) - 1
        end = "" if last else (r"\\[6pt]" if k % 3 == 2 else r"\hfill")
        out.append(r"\includegraphics[width=0.31\linewidth,height=0.22\textheight,keepaspectratio]{%s}%s" % (name, end))
    out.append(r"\end{center}")
    return out


def markdown_to_latex(md, base_dir=None):
    """Markdown -> documento LaTeX con el estilo de apuntes. `base_dir` sirve para comprobar que las imágenes existen."""
    lines = md.splitlines()

    title = ""
    first = next((ln for ln in lines if ln.strip()), "")
    if (m := _HEAD.match(first)) and len(m.group(1)) == 1:
        title = m.group(2).strip()
        lines.remove(first)

    lines = _prepare_slides(lines)
    dividers = _find_dividers(lines)
    plan, numbering, mode = _plan_headings(lines, dividers)
    skip = {j for j, _ in dividers.values()} if mode == "hier" else set()
    sections = ["section", "subsection", "subsubsection", "paragraph", "subparagraph", "subparagraph"]
    child_offset = 1 if mode in ("hier", "numbered") else 0

    out, stack, i = [], [], 0          # stack: [(entorno, sangría)]
    box_open, pending_box, counter_set = False, None, False

    def close_lists(indent=-1):
        while stack and stack[-1][1] > indent:
            out.append("  " * (len(stack) - 1) + r"\end{%s}" % stack.pop()[0])

    def close_box():
        nonlocal box_open
        if box_open:
            out.append(r"\end{ejercicio}")
            box_open = False

    def heading(level, text, idx):
        nonlocal counter_set
        close_lists()
        close_box()
        if idx in plan:
            cmd, text = plan[idx]
            if cmd == "skip":
                return
        elif level == 1:
            cmd = "section"
        else:
            cmd = sections[min((level - 2) + child_offset, 5)]
        if cmd == "section" and numbering and not counter_set:
            out.append(r"\setcounter{section}{%d}" % (numbering[1] - 1))
            counter_set = True
        if cmd == "section*":
            title_tex = _inline(text.strip())
            out.extend(["", r"\section*{%s}" % title_tex, r"\addcontentsline{toc}{section}{%s}" % title_tex])
            return
        out.extend(["", r"\%s{%s}" % (cmd, _inline(text.strip()))])

    while i < len(lines):
        ln = lines[i]
        if i in skip:
            i += 1
            continue
        if ln.strip().startswith("```"):
            close_lists()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            body = _safe_code("\n".join(code))
            lang = _guess_lang(body)
            out += [r"\begin{lstlisting}" + (f"[language={lang}]" if lang else ""), body, r"\end{lstlisting}"]
        elif re.match(r"^\s*<!--.*-->\s*$", ln):
            close_lists()
            out.append("%" + ln.strip()[4:-3].replace("\n", " "))
        elif (m := _PAGE.match(ln)):
            close_lists()
            num = re.sub(r"^p\.\s*", "", m.group(1)).replace("-", "--").replace("–", "--")
            out.append(r"\diapo{%s}" % _esc(num))
            # El cuadro de ejercicio se abre después de la referencia (un \marginpar no cabe dentro de una caja).
            if pending_box:
                out.append(pending_box)
                box_open = True
                pending_box = None
        elif (m := _IMG.match(ln)):
            close_lists()
            # ¿Varias imágenes seguidas? (>=3 -> cuadrícula)
            names, j = [], i
            while j < len(lines):
                mm = _IMG.match(lines[j])
                if mm:
                    names.append(mm.group(1))
                elif lines[j].strip():
                    break
                j += 1
            usable = [n for n in names if not n.startswith(("http:", "https:")) and " " not in n
                      and (base_dir is None or (Path(base_dir) / n).exists())]
            short = [n[len("imagenes/"):] if n.startswith("imagenes/") else n for n in usable]
            if len(names) >= 3:
                out += _grid(short) if short else []
                i = j
                continue
            src = m.group(1)
            if src in usable:
                out.append(r"\figura{%s}{}" % (src[len("imagenes/"):] if src.startswith("imagenes/") else src))
            else:
                out.append("% imagen no incluida: " + src)
        elif (m := _HEAD.match(ln)):
            level, text = len(m.group(1)), m.group(2)
            heading(level, text, i)
            if re.match(r"(?i)^ejercicio", (plan.get(i) or (None, text))[1].strip()):
                pending_box = r"\begin{ejercicio}[%s]" % _inline((plan.get(i) or (None, text))[1].strip())
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
        elif (m := _NOTE.match(ln.strip())):
            close_lists()
            if m.group(1).lower().startswith(("parte del texto", "un fragmento")):
                # Avisos automáticos de la extracción (texto ilegible / omitido): una línea discreta, no una caja
                out.append(r"{\footnotesize\itshape\color{gray}" + _inline(m.group(1)) + r"}\par")
            else:
                out += [r"\begin{nota}[Aviso]", _inline(m.group(1)), r"\end{nota}"]
        elif (m := _BOLD_LINE.match(ln.strip())):
            close_lists()
            out.append(r"\paragraph{%s}" % _inline(m.group(1)))     # subtítulo dentro de la diapositiva
        else:
            close_lists()
            out.append(_inline(ln))
        i += 1
    close_lists()
    close_box()
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(out).strip())

    numbering_tex = (r"\renewcommand{\thesection}{%s.\arabic{section}}" % numbering[0]) if numbering else ""
    pre = (PRO_PREAMBLE.replace("%%HEADER%%", _esc((title or "Apuntes")[:70]))
                       .replace("%%TITLE%%", _inline(title) if title else "Apuntes")
                       .replace("%%NUMBERING%%", numbering_tex))
    return pre + "\n" + body + "\n\n\\end{document}\n"
