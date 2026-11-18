"""Convierte el texto de un PDF (sobre todo diapositivas) en texto limpio y Markdown.

Problemas que resuelve:
  * texto justificado partido en una palabra por línea  -> reconstruye las filas por su altura
  * pies de página repetidos ("Asignatura - Tema 3", nº de página) -> se eliminan
  * diapositivas repetidas (índices "Contenidos") -> se omiten indicando cuál repiten
  * viñetas de Wingdings (Ø, §, ü...) y flechas (à) -> listas Markdown y "→"
  * numeración separada del texto ("1." / "Introducción") -> "1. Introducción"
"""
import re

# Viñetas de primer nivel (muchas vienen de Wingdings/Symbol mapeadas a letras latinas)
BULLET1 = set("Ø•▪■➢►✓✔§ü")
BULLET2 = set("–—-◦○·")
NUMBER_ONLY = re.compile(r"^\(?\d{1,2}(\.\d{1,2})*[.)]?$")
NUMBERED = re.compile(r"^(\d{1,2}(?:\.\d{1,2})*)[.)]\s+(.*)")


# Texto con la fuente rota: signos como ’ ‘ ´ % pegados dentro de las palabras ("TOk6k‘kGk").
_INNER = re.compile(r"[A-Za-zÀ-ÿ0-9][’‘´ˆ`ͻ][A-Za-zÀ-ÿ0-9’‘´]|[A-Za-zÀ-ÿ]%(?![0-9A-Fa-f]{2})[A-Za-zÀ-ÿ’‘´]")


_POSSESSIVE = re.compile(r"(?<=[A-Za-z])[’']s(?![A-Za-z])", re.I)  # "URL’s" es texto normal


def weird_count(line):
    return len(_INNER.findall(_POSSESSIVE.sub("", line)))


def is_garbled(line):
    n = weird_count(line)
    return n >= 2 or (n >= 1 and len(line.split()) <= 3)


def _clean(text):
    text = text.replace(" ", " ").replace("\t", " ")
    text = re.sub(r"(?<=\s)à(?=\s)", "→", text)  # flecha de Wingdings
    text = re.sub(r"^à(?=\s)", "→", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = re.sub(r"\s+([:;,.)”»])", r"\1", text)   # "servidor :" -> "servidor:"
    text = re.sub(r"([(“«])\s+", r"\1", text)       # "“ accesos" -> "“accesos"
    text = re.sub(r"(^|\s)(/+) (?=\w)", r"\1\2", text)  # "/ restart" -> "/restart"
    return text


_MONO_NAMES = ("courier", "consolas", "mono", "lucida console")


def _is_mono(span):
    return any(k in span["font"].lower() for k in _MONO_NAMES) or bool(span["flags"] & 8)


_BULLET_GLYPHS = set("Ø•▪■➢►✓✔§ü–—-◦○·")


def _is_bullet_span(span):
    """Trozo que solo es un símbolo de viñeta (a veces en fuente Wingdings/Symbol)."""
    t = span["text"].strip()
    font = span["font"].lower()
    return ("wingdings" in font or "symbol" in font) or (len(t) == 1 and t in _BULLET_GLYPHS)


def _is_bold(span):
    return bool(span["flags"] & 16) or "bold" in span["font"].lower()


def _rows(page):
    """Filas visuales de la página: une las 'líneas' del PDF que están a la misma altura."""
    rows = []
    data = page.get_text("dict")
    page_h = max(page.rect.height, 1)
    for bno, block in enumerate(data["blocks"]):
        if block.get("type") != 0:
            continue
        block_rows = []
        for line in block["lines"]:
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            x0, y0, x1, y1 = line["bbox"]
            yc, hgt = (y0 + y1) / 2, max(y1 - y0, 1)
            size = max(s["size"] for s in spans)
            bold = any(s["flags"] & 16 for s in spans)
            text = " ".join(s["text"] for s in spans)
            mono = any(_is_mono(s) for s in spans) and all(_is_mono(s) or _is_bullet_span(s) for s in spans)
            # En el código se descarta la viñeta que el PDF pone delante ("– Set-Cookie ...")
            raw = "".join(s["text"] for s in line["spans"] if not (mono and _is_bullet_span(s))).rstrip()
            bold_all = all(_is_bold(s) for s in spans)
            for row in block_rows:
                if abs(row["yc"] - yc) < 0.55 * min(hgt, row["h"]):
                    row["parts"].append((x0, text))
                    row["raws"].append((x0, raw))
                    row["x0"] = min(row["x0"], x0)
                    row["size"] = max(row["size"], size)
                    row["bold"] = row["bold"] or bold
                    row["mono"] = row["mono"] and mono
                    row["bold_all"] = row["bold_all"] and bold_all
                    break
            else:
                block_rows.append({"yc": yc, "h": hgt, "x0": x0, "size": size, "bold": bold, "mono": mono,
                                   "bold_all": bold_all, "rel_y": yc / page_h, "block": bno, "parts": [(x0, text)], "raws": [(x0, raw)]})
        for row in sorted(block_rows, key=lambda r: r["yc"]):
            row["raw"] = " ".join(t for _, t in sorted(row["raws"])).strip("\n")
            row["text"] = _clean(" ".join(t for _, t in sorted(row["parts"])))
            if row["text"]:
                rows.append(row)
    return rows


def _norm(text):
    return re.sub(r"\d+", "#", text.lower()).strip()


def analyze(doc):
    """Devuelve una lista de páginas estructuradas: título, elementos y duplicados."""
    raw = [_rows(page) for page in doc]
    n = len(raw)

    # Pies/cabeceras: filas que se repiten (ignorando números) en muchas páginas.
    counts = {}
    for rows in raw:
        for key in {_norm(r["text"]) for r in rows}:
            counts[key] = counts.get(key, 0) + 1
    limit = max(3, n * 0.4)
    repeated = {k for k, c in counts.items() if c >= limit and k not in ("#", "")}

    sizes = {}
    for rows in raw:
        for r in rows:
            sizes[round(r["size"])] = sizes.get(round(r["size"]), 0) + len(r["text"])
    body_size = max(sizes, key=sizes.get) if sizes else 12

    pages, seen = [], {}
    for index, rows in enumerate(raw):
        number = index + 1
        # Se quitan pies repetidos y el número de diapositiva (un número suelto en la franja inferior)
        rows = [r for r in rows
                if _norm(r["text"]) not in repeated and r["text"] != str(number)
                and not (re.fullmatch(r"\d{1,4}\.?", r["text"]) and r["rel_y"] > 0.85)]
        # Cualquier línea con signos raros dentro de las palabras indica fuente rota en esa página.
        garbled = [r for r in rows if weird_count(r["text"])]
        rows = [r for r in rows if r not in garbled]

        title = ""
        if rows:
            top = max(r["size"] for r in rows)
            if top >= body_size + 1.5 or len(rows) <= 3:
                title_rows = [r for r in rows if r["size"] >= top - 0.5]
                title = " ".join(r["text"] for r in title_rows)
                rows = [r for r in rows if r not in title_rows]

        items = _items(rows)
        # Diapositiva con imagen y muchas cajitas de 1-3 palabras: son etiquetas del diagrama, no texto corrido
        if (len(items) >= 6 and all(k in ("p", "h") for k, _, _ in items) and len(doc[index].get_images()) >= 1
                and sorted(len(t.split()) for _, _, t in items)[len(items) // 2] <= 3):
            items = [("labels", 0, " | ".join(t for _, _, t in items))]
        key = _norm(title + "|" + " ".join(t for _, _, t in items))
        # Solo se considera repetida si tiene texto propio (las de solo imagen suelen diferir).
        duplicate = seen.get(key) if items else None
        if duplicate is None and items:
            seen[key] = number
        pages.append({"number": number, "title": title, "items": items, "duplicate_of": duplicate,
                      "garbled": len(garbled)})
    return pages


def _items(rows):
    """Agrupa filas en elementos (tipo, nivel, texto): 'p' párrafo, 'ul' viñeta, 'ol' numerado."""
    items, pending_number, last_block, last_y, last_h = [], None, None, None, None
    numbered_x = [r["x0"] for r in rows if NUMBER_ONLY.match(r["text"]) or NUMBERED.match(r["text"])]
    base_x = min(numbered_x) if numbered_x else 0

    for r in rows:
        text = r["text"]
        first = text[0]

        # Código: filas en fuente monoespaciada y pegadas entre sí (se conservan sangrías y saltos).
        if r["mono"]:
            gap_now = (r["yc"] - last_y) if last_y is not None else None
            if (items and items[-1][0] == "code" and gap_now is not None
                    and 0 < gap_now <= 2.6 * max(r["h"], last_h or 0)):
                items[-1][2].append((r["x0"], r["raw"], max(0, round(gap_now / max(r["h"], 1)) - 1), r["size"]))
            else:
                items.append(["code", 0, [(r["x0"], r["raw"], 0, r["size"])], r["x0"]])
            pending_number = None
            last_block, last_y, last_h = r["block"], r["yc"], r["h"]
            continue

        # Línea corta toda en negrita = subtítulo (no se mezcla con el párrafo de debajo)
        if (r["bold_all"] and not NUMBER_ONLY.match(text) and not NUMBERED.match(text)
                and first not in BULLET1 and first not in BULLET2 and 1 <= len(text.split()) <= 10
                and not text.endswith((".", ",", ";", ":"))):
            items.append(["h", 0, text, r["x0"]])
            pending_number = None
            last_block, last_y, last_h = r["block"], r["yc"], r["h"]
            continue

        new_block = r["block"] != last_block
        gap = (r["yc"] - last_y) if last_y is not None else None
        line_h = max(r["h"], last_h or 0)
        big_gap = gap is not None and gap > 1.9 * line_h
        # Una viñeta que sigue en la fila de justo debajo (aunque el PDF la meta en otro bloque).
        close_below = gap is not None and 0 < gap <= 1.6 * line_h
        prev_open = bool(items) and items[-1][0] not in ("code", "h") and (
            items[-1][0] in ("ul", "ol") or not items[-1][2].endswith((".", ":", "?", "!")))

        if NUMBER_ONLY.match(text):
            pending_number = (text.rstrip(".)"), r["x0"])
            last_block, last_y, last_h = r["block"], r["yc"], r["h"]
            continue

        if pending_number:
            num, x0 = pending_number
            items.append(["ol", 1 if x0 - base_x > 8 else 0, f"{num}. {text}"])
            pending_number = None
        elif (m := NUMBERED.match(text)):
            items.append(["ol", 1 if r["x0"] - base_x > 8 else 0, f"{m.group(1)}. {m.group(2)}"])
        elif (first in BULLET1 or first in BULLET2) and len(text) > 1 and text[1] == " ":
            items.append(["ul", 0 if first in BULLET1 else 1, text[2:].strip(), r["x0"]])
        elif items and items[-1][0] not in ("code", "h") and ((not new_block and not big_gap) or (close_below and prev_open)):
            prev = items[-1]
            prev[2] = prev[2] + text if prev[2].endswith("-") else prev[2] + " " + text
        else:
            items.append(["p", 0, text])
        last_block, last_y, last_h = r["block"], r["yc"], r["h"]

    # Bloques de código: se convierte cada lista de líneas en texto, con la sangría relativa de cada una.
    for item in items:
        if item[0] != "code":
            continue
        lines = item[2]
        left = min(x for x, _, _, _ in lines)
        out_lines = []
        for x, raw, blank, size in lines:
            out_lines += [""] * min(blank, 2)
            char_w = max(size * 0.6, 1)
            out_lines.append(" " * round((x - left) / char_w) + raw.lstrip())
        item[2] = "\n".join(out_lines)

    # Nivel de las viñetas según su sangría real (más fiable que el símbolo usado).
    xs = sorted({round(i[3]) for i in items if i[0] == "ul"})
    columns = []
    for x in xs:
        if not columns or x - columns[-1] > 6:
            columns.append(x)
    if len(columns) > 1:
        for i in items:
            if i[0] == "ul":
                i[1] = max(k for k, c in enumerate(columns) if round(i[3]) >= c - 6)
    return [tuple(i[:3]) for i in items]


_SMALL_WORDS = {"de", "la", "el", "en", "y", "a", "los", "las", "del", "con", "por", "para", "un", "una"}
_DOC_WORDS = re.compile(r"(?i)^(tema|parte|unidad|bloque|práctica|practica|capítulo|capitulo|sesión|sesion)(\d+)?$")


def pretty_title(stem):
    """'2526_atw-tema1_PARTE II' -> 'ATW Tema 1 Parte II' (quita el prefijo de curso y separa tema/parte y números)."""
    s = re.sub(r"^\d{4}[_\s-]+", "", stem)
    out, prev = [], ""
    for token in (t for t in re.split(r"[_\-\s]+", s) if t):
        m = _DOC_WORDS.match(token)
        if m:
            out.append(m.group(1).capitalize())
            if m.group(2):
                out.append(m.group(2))
        elif re.fullmatch(r"[IVXivx]{1,5}", token) and prev.lower() in ("parte", "tema", "unidad", "bloque"):
            out.append(token.upper())
        elif token.isalpha() and token.islower() and len(token) <= 3 and token not in _SMALL_WORDS:
            out.append(token.upper())   # siglas (atw -> ATW)
        elif token.isupper() and len(token) > 4:
            out.append(token.capitalize())
        else:
            out.append(token)
        prev = out[-1]
    title = " ".join(out)
    return title[:1].upper() + title[1:]


# ---------- salidas ----------

def to_markdown(pages, title="", images=None):
    images = images or {}
    out = [f"# {title}", ""] if title else []
    for p in pages:
        n = p["number"]
        if p["duplicate_of"]:
            out += [f"<!-- p. {n}: repite la p. {p['duplicate_of']} -->", ""]
            continue
        flagged = p.get("garbled") or p.get("blocked")
        page_images = list(images.get(n, []))
        heading = p["title"] or (f"Diapositiva {n}" if flagged else "")
        if heading:
            out.append(f"## {heading}")
        out += [f"<sub>p. {n}</sub>", ""]
        prev_kind = None
        if p.get("garbled"):
            out += ["*Nota: parte del texto de esta diapositiva no se puede leer (la fuente del PDF está dañada); "
                    "se muestra la imagen de la página.*", ""]
        if p.get("blocked"):
            out += ["*Nota: un fragmento de código de esta diapositiva se omitió porque el antivirus lo detecta "
                    "como sospechoso; se muestra la imagen de la página.*", ""]
        if flagged and page_images:
            out += [f"![diapositiva {n}]({page_images.pop(0)})", ""]
        for kind, level, text in p["items"]:
            if kind == "code":
                if prev_kind in ("ul", "ol"):
                    out.append("")
                out += ["```", text, "```", ""]
                prev_kind = kind
                continue
            if kind == "h":
                if prev_kind in ("ul", "ol"):
                    out.append("")
                out += ["**" + text.replace("*", "\\*") + "**", ""]
                prev_kind = kind
                continue
            if kind == "labels":
                out += ["<!-- etiquetas del diagrama: " + text.replace("--", "—") + " -->", ""]
                prev_kind = kind
                continue
            text = text.replace("*", "\\*")
            if kind == "p":
                if prev_kind in ("ul", "ol"):
                    out.append("")
                out += [text, ""]
            else:
                indent = "  " * level if kind == "ul" else "   " * level
                out.append(f"{indent}{'- ' if kind == 'ul' else ''}{text}")
            prev_kind = kind
        if prev_kind in ("ul", "ol"):
            out.append("")
        for img in page_images:
            out += [f"![p. {n}]({img})", ""]
        if not p["items"] and not images.get(n) and not p.get("garbled") and not p.get("blocked"):
            out += ["*(diapositiva sin texto)*", ""]
    return "\n".join(out).strip() + "\n"


def to_text(pages):
    out = []
    for p in pages:
        n = p["number"]
        if p["duplicate_of"]:
            out += [f"=== p. {n} (repite la p. {p['duplicate_of']}) ===", ""]
            continue
        out.append(f"=== p. {n}" + (f" · {p['title']}" if p["title"] else "") + " ===")
        if p.get("blocked"):
            out.append(f"[fragmento omitido por el antivirus; ver imagenes/pagina_{n:03d}.png]")
        if p.get("garbled"):
            out.append(f"[texto ilegible en esta página: fuente dañada en el PDF; ver imagenes/pagina_{n:03d}.png]")
        for kind, level, text in p["items"]:
            if kind == "code":
                out += ["    " + ln for ln in text.splitlines()]
            elif kind == "labels":
                out.append("  [etiquetas del diagrama: " + text + "]")
            elif kind == "ul":
                out.append(("    ◦ " if level else "  • ") + text)
            elif kind == "ol":
                out.append(("      " if level else "  ") + text)
            else:
                out.append(text)
        out.append("")
    return "\n".join(out).strip() + "\n"
