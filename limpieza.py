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


def _clean(text):
    text = text.replace(" ", " ").replace("\t", " ")
    text = re.sub(r"(?<=\s)à(?=\s)", "→", text)  # flecha de Wingdings
    text = re.sub(r"^à(?=\s)", "→", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = re.sub(r"\s+([:;,.)”»])", r"\1", text)   # "servidor :" -> "servidor:"
    text = re.sub(r"([(“«])\s+", r"\1", text)       # "“ accesos" -> "“accesos"
    text = re.sub(r"(^|\s)(/+) (?=\w)", r"\1\2", text)  # "/ restart" -> "/restart"
    return text


def _rows(page):
    """Filas visuales de la página: une las 'líneas' del PDF que están a la misma altura."""
    rows = []
    data = page.get_text("dict")
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
            for row in block_rows:
                if abs(row["yc"] - yc) < 0.55 * min(hgt, row["h"]):
                    row["parts"].append((x0, text))
                    row["x0"] = min(row["x0"], x0)
                    row["size"] = max(row["size"], size)
                    row["bold"] = row["bold"] or bold
                    break
            else:
                block_rows.append({"yc": yc, "h": hgt, "x0": x0, "size": size, "bold": bold,
                                   "block": bno, "parts": [(x0, text)]})
        for row in sorted(block_rows, key=lambda r: r["yc"]):
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
        rows = [r for r in rows
                if _norm(r["text"]) not in repeated and r["text"] != str(number)]

        title = ""
        if rows:
            top = max(r["size"] for r in rows)
            if top >= body_size + 1.5 or len(rows) <= 3:
                title_rows = [r for r in rows if r["size"] >= top - 0.5]
                title = " ".join(r["text"] for r in title_rows)
                rows = [r for r in rows if r not in title_rows]

        items = _items(rows)
        key = _norm(title + "|" + " ".join(t for _, _, t in items))
        # Solo se considera repetida si tiene texto propio (las de solo imagen suelen diferir).
        duplicate = seen.get(key) if items else None
        if duplicate is None and items:
            seen[key] = number
        pages.append({"number": number, "title": title, "items": items, "duplicate_of": duplicate})
    return pages


def _items(rows):
    """Agrupa filas en elementos (tipo, nivel, texto): 'p' párrafo, 'ul' viñeta, 'ol' numerado."""
    items, pending_number, last_block, last_y, last_h = [], None, None, None, None
    numbered_x = [r["x0"] for r in rows if NUMBER_ONLY.match(r["text"]) or NUMBERED.match(r["text"])]
    base_x = min(numbered_x) if numbered_x else 0

    for r in rows:
        text = r["text"]
        first = text[0]
        new_block = r["block"] != last_block
        gap = (r["yc"] - last_y) if last_y is not None else None
        line_h = max(r["h"], last_h or 0)
        big_gap = gap is not None and gap > 1.9 * line_h
        # Una viñeta que sigue en la fila de justo debajo (aunque el PDF la meta en otro bloque).
        close_below = gap is not None and 0 < gap <= 1.6 * line_h
        prev_open = bool(items) and (items[-1][0] in ("ul", "ol") or not items[-1][2].endswith((".", ":", "?", "!")))

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
        elif items and ((not new_block and not big_gap) or (close_below and prev_open)):
            prev = items[-1]
            prev[2] = prev[2] + text if prev[2].endswith("-") else prev[2] + " " + text
        else:
            items.append(["p", 0, text])
        last_block, last_y, last_h = r["block"], r["yc"], r["h"]

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


def pretty_title(stem):
    """'2526_ATW_Tema3_Parte I' -> 'ATW Tema3 Parte I' (quita el prefijo de curso y los guiones bajos)."""
    title = re.sub(r"[_]+", " ", stem)
    title = re.sub(r"^\d{4}\s+", "", title)
    return re.sub(r"\s{2,}", " ", title).strip()


# ---------- salidas ----------

def to_markdown(pages, title="", images=None):
    images = images or {}
    out = [f"# {title}", ""] if title else []
    for p in pages:
        n = p["number"]
        if p["duplicate_of"]:
            out += [f"<!-- p. {n}: repite la p. {p['duplicate_of']} -->", ""]
            continue
        if p["title"]:
            out.append(f"## {p['title']}")
        out += [f"<sub>p. {n}</sub>", ""]
        prev_kind = None
        for kind, level, text in p["items"]:
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
        for img in images.get(n, []):
            out += [f"![p. {n}]({img})", ""]
        if not p["items"] and not images.get(n):
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
        for kind, level, text in p["items"]:
            if kind == "ul":
                out.append(("    ◦ " if level else "  • ") + text)
            elif kind == "ol":
                out.append(("      " if level else "  ") + text)
            else:
                out.append(text)
        out.append("")
    return "\n".join(out).strip() + "\n"
