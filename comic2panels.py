#!/usr/bin/env python3
"""
[DE] comic2panels — Comics (CBZ/CBR/PDF/Ordner) in eine CBZ umbauen,
bei der jedes Panel eine eigene "Seite" ist.
[EN] comic2panels — turns comics (CBZ/CBR/PDF/folder) into a CBZ where
every panel becomes its own "page".

Voreingestellt auf / Preset for: PocketBook Era Color (1264 x 1680).

Beispiel / Example:
    python3 comic2panels.py "Batman 001.cbr" -o ~/Desktop/panels --preview
    python3 comic2panels.py ~/Comics/*.cbz -o ~/Desktop/panels
    python3 comic2panels.py manga.cbz --manga           # [DE] Lesereihenfolge rechts->links / [EN] right-to-left reading order
    python3 comic2panels.py x.cbz --include-page        # [DE] ganze Seite vor ihren Panels / [EN] full page before its panels
    python3 comic2panels.py x.cbz --rotate-wide         # [DE] breite Einzelpanels quer legen / [EN] rotate wide solo panels to landscape
    python3 comic2panels.py x.cbz --skip-start 2 --skip-end 3
        # [DE] erste 2 und letzte 3 Seiten unveraendert uebernehmen (kein Zerlegen)
        # [EN] keep the first 2 and last 3 pages unchanged (no splitting)

Batch:
    [DE] ein Stammverzeichnis rekursiv nach CBRs durchsuchen und alles verarbeiten
    (die Ordnerstruktur wird im Ziel gespiegelt, Vorhandenes wird uebersprungen):
    [EN] recursively scan a root directory for CBRs and process everything
    (the folder structure is mirrored into the target, existing output is skipped):
        python3 comic2panels.py ~/Comics --scan -o ~/Desktop/panels
        python3 comic2panels.py ~/Comics --scan --scan-ext cbr,cbz,pdf -o out

[DE] Seiten, auf denen kein oder nur ein Panel erkannt wird (Cover, Splash-Pages,
unklare Layouts), werden unveraendert uebernommen - da wird nichts zerschnitten
oder neu komprimiert.
[EN] Pages where zero or only one panel is detected (covers, splash pages,
unclear layouts) are copied through unchanged - nothing is cut or recompressed.

[DE] Erst mit --preview laufen lassen: im Ordner "<name>_preview" liegt zu jeder Seite
ein Bild mit den erkannten Panels und ihrer Reihenfolge. Passt das, den Lauf ohne
--preview wiederholen und die fertige CBZ auf den Reader kopieren.
[EN] Run with --preview first: the folder "<name>_preview" holds one image per
page showing the detected panels and their order. If it looks right, rerun
without --preview and copy the finished CBZ to your reader.

[DE] Metadaten (Autor, ISBN, Serie, Verlag, Schlagworte, Beschreibung) werden
uebernommen, wenn neben der Comicdatei eine metadata.opf liegt - genau so legt
Calibre seine Buecher ab. Sie landen dreifach in der neuen CBZ:
[EN] Metadata (author, ISBN, series, publisher, tags, description) is picked up
when a metadata.opf sits next to the comic file - that's how Calibre stores its
books. It ends up in the new CBZ in three places:
    ComicInfo.xml   [DE] fuer Comic-Reader / [EN] for comic readers
    ZIP-Kommentar   [DE] im ComicBookInfo-Format, das calibre selbst liest / [EN] as ComicBookInfo, which Calibre itself reads
    metadata.opf    [DE] unveraendert mitkopiert, damit nichts verlorengeht / [EN] copied through unchanged, so nothing gets lost
[DE] Ohne metadata.opf wird ersatzweise eine ComicInfo.xml aus dem Original benutzt.
[EN] Without a metadata.opf, an existing ComicInfo.xml from the original is used instead.
    --opf PFAD          [DE] metadata.opf explizit angeben / [EN] point to a metadata.opf explicitly
    --name-from-meta    [DE] Dateinamen aus Serie/Titel bilden / [EN] build the filename from series/title
    --no-metadata       [DE] abschalten / [EN] disable metadata handling

[DE] Nur umpacken statt zerlegen (CBR -> CBZ, Bilder unveraendert, Metadaten dabei):
[EN] Repack only, without splitting (CBR -> CBZ, images unchanged, metadata kept):
    python3 comic2panels.py ~/Comics/*.cbr --repack -o ~/Desktop/cbz

[DE] Stellschrauben, wenn die Erkennung danebenliegt:
[EN] Tuning knobs if detection gets it wrong:
    --gutter 0.015    [DE] nur breitere Zwischenraeume als Trennung werten (weniger Schnitte) / [EN] only count wider gaps as separators (fewer cuts)
    --gutter 0.004    [DE] auch enge Zwischenraeume trennen (mehr Schnitte) / [EN] also split on narrow gaps (more cuts)
    --min-area 0.03   [DE] kleine Fragmente verwerfen / [EN] discard small fragments
    --bridge 0.2      [DE] grosszuegiger gegenueber Figuren, die ueber den Rand ragen / [EN] more tolerant of art bleeding over a panel edge
    --tolerance 45    [DE] fuer graue/vergilbte Scans / [EN] for grey/yellowed scans

Voraussetzungen / Requirements:
    pip3 install opencv-python-headless numpy
    CBR/RAR: [DE] macOS bringt "bsdtar" mit, das reicht meistens. Sonst: brew install unar
             [EN] macOS ships "bsdtar", which is usually enough. Otherwise: brew install unar
    PDF (optional):  pip3 install pymupdf
"""
 
from __future__ import annotations
 
import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
 
import cv2
import numpy as np
 
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
COMIC_EXT = {".cbz", ".cbr", ".zip", ".rar", ".7z", ".pdf"}
 
 
# --------------------------------------------------------------------------
# Ein-/Auspacken
# --------------------------------------------------------------------------
 
def natural_key(s: str):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]
 
 
def extract_archive(path: Path, dest: Path) -> None:
    """CBZ/CBR/ZIP/RAR/7z nach dest auspacken."""
    suffix = path.suffix.lower()
    if suffix in {".cbz", ".zip"}:
        try:
            with zipfile.ZipFile(path) as zf:
                zf.extractall(dest)
            return
        except zipfile.BadZipFile:
            pass  # manche .cbz sind in Wahrheit RARs
 
    for cmd in (
        ["bsdtar", "-xf", str(path), "-C", str(dest)],
        ["unar", "-q", "-f", "-o", str(dest), str(path)],
        ["7z", "x", "-y", f"-o{dest}", str(path)],
        ["7zz", "x", "-y", f"-o{dest}", str(path)],
        ["unrar", "x", "-y", str(path), str(dest) + "/"],
    ):
        if shutil.which(cmd[0]) is None:
            continue
        if subprocess.run(cmd, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0:
            return
 
    raise RuntimeError(
        f"Konnte {path.name} nicht entpacken. Fuer CBR/RAR bitte 'brew install unar' "
        f"installieren (oder die Datei vorher in eine CBZ umpacken)."
    )
 
 
def pdf_to_images(path: Path, dest: Path, dpi: int = 300) -> list[Path]:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("Fuer PDF-Eingabe bitte 'pip3 install pymupdf' ausfuehren.")
    out = []
    doc = fitz.open(path)
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi)
        p = dest / f"page{i:04d}.png"
        pix.save(p)
        out.append(p)
    return out
 
 
def collect_pages(src: Path, workdir: Path) -> list[Path]:
    if src.is_dir():
        files = [p for p in src.rglob("*") if p.suffix.lower() in IMAGE_EXT]
    elif src.suffix.lower() == ".pdf":
        files = pdf_to_images(src, workdir)
    else:
        extract_archive(src, workdir)
        files = [p for p in workdir.rglob("*") if p.suffix.lower() in IMAGE_EXT]
    files = [p for p in files if not p.name.startswith("._")]
    return sorted(files, key=lambda p: natural_key(p.relative_to(p.anchor)))
 
 
def imread_unicode(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)
 
 
# --------------------------------------------------------------------------
# Calibre-Metadaten
# --------------------------------------------------------------------------
 
def find_opf(src: Path) -> Path | None:
    """metadata.opf neben der Comicdatei suchen (Calibre legt sie im Buchordner ab).

    Nur verwenden, wenn im selben Ordner ausschliesslich diese eine Comicdatei
    liegt (Calibre: ein Ordner pro Buch). Liegen dort mehrere Comics - z.B. ein
    formlos befuellter Ordner statt einer Calibre-Bibliothek -, koennte die
    gefundene metadata.opf zu einem anderen Buch gehoeren und wuerde sonst
    faelschlich allen Comics im Ordner zugeordnet.
    """
    folder = src if src.is_dir() else src.parent
    if not src.is_dir():
        siblings = [p for p in folder.iterdir()
                    if p.is_file() and p.suffix.lower() in COMIC_EXT]
        if len(siblings) > 1:
            return None
    direct = folder / "metadata.opf"
    if direct.is_file():
        return direct
    opfs = sorted(folder.glob("*.opf"))
    return opfs[0] if opfs else None
 
 
# MARC-Rollencodes aus der OPF -> lesbare Rollen
ROLE_NAMES = {"aut": "Writer", "ill": "Artist", "art": "Artist", "drm": "Artist",
              "clr": "Colorist", "edt": "Editor", "trl": "Translator",
              "cov": "CoverArtist", "ctb": "Contributor"}
# ... und wie sie in ComicInfo.xml heissen
COMICINFO_ROLE = {"Artist": "Penciller", "Colorist": "Colorist", "Editor": "Editor",
                  "CoverArtist": "CoverArtist", "Letterer": "Letterer"}
LANG2 = {"deu": "de", "ger": "de", "eng": "en", "fra": "fr", "fre": "fr", "spa": "es",
         "ita": "it", "nld": "nl", "dut": "nl", "jpn": "ja", "por": "pt", "rus": "ru"}
 
 
def lang2(code: str | None) -> str:
    if not code:
        return ""
    code = code.strip().lower().replace("_", "-").split("-")[0]
    return LANG2.get(code, code[:2])
 
 
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()
 
 
def _strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()
 
 
def parse_opf(path: Path) -> dict:
    """Calibre-Metadaten aus einer metadata.opf lesen."""
    meta: dict = {"authors": [], "tags": [], "identifiers": {}}
    try:
        root = ET.parse(path).getroot()
    except Exception as e:  # noqa: BLE001
        print(f"  ! metadata.opf nicht lesbar: {e}")
        return meta
 
    for el in root.iter():
        name = _local(el.tag)
        val = (el.text or "").strip()
 
        if name == "meta":
            key = (el.get("name") or "").lower()
            content = el.get("content") or ""
            if key == "calibre:series":
                meta["series"] = content
            elif key == "calibre:series_index":
                meta["series_index"] = content
            elif key == "calibre:rating":
                meta["rating"] = content
            continue
 
        if not val:
            continue
        if name == "title":
            meta.setdefault("title", val)
        elif name == "creator":
            role = ""
            for k, v in el.attrib.items():
                if _local(k) == "role":
                    role = v.lower()
            if role in ("", "aut"):
                meta["authors"].append(val)
            else:
                meta.setdefault("contributors", []).append(
                    (ROLE_NAMES.get(role, role.title()), val))
        elif name == "publisher":
            meta.setdefault("publisher", val)
        elif name == "date":
            meta.setdefault("date", val)
        elif name == "language":
            meta.setdefault("language", val)
        elif name == "description":
            meta.setdefault("description", _strip_html(val))
        elif name == "subject":
            meta["tags"].append(val)
        elif name == "identifier":
            scheme = ""
            for k, v in el.attrib.items():
                if _local(k) == "scheme":
                    scheme = v.lower()
            if not scheme and val.lower().startswith("urn:"):
                parts = val.split(":")
                if len(parts) >= 3:
                    scheme, val = parts[1].lower(), parts[2]
            if scheme:
                meta["identifiers"][scheme] = val
 
    if "isbn" in meta["identifiers"]:
        meta["isbn"] = meta["identifiers"]["isbn"]
    return meta
 
 
def parse_comicinfo(path: Path) -> dict:
    """Fallback: eine bereits vorhandene ComicInfo.xml aus dem Quellarchiv lesen."""
    meta: dict = {"authors": [], "tags": [], "identifiers": {}}
    try:
        root = ET.parse(path).getroot()
    except Exception:  # noqa: BLE001
        return meta
    got = {_local(el.tag): (el.text or "").strip() for el in root}
    if got.get("title"):
        meta["title"] = got["title"]
    if got.get("series"):
        meta["series"] = got["series"]
    if got.get("number"):
        meta["series_index"] = got["number"]
    if got.get("writer"):
        meta["authors"] = [a.strip() for a in got["writer"].split(",") if a.strip()]
    for role_field, role in (("penciller", "Artist"), ("colorist", "Colorist"),
                             ("editor", "Editor"), ("coverartist", "CoverArtist")):
        for person in (p.strip() for p in got.get(role_field, "").split(",")):
            if person:
                meta.setdefault("contributors", []).append((role, person))
    if got.get("publisher"):
        meta["publisher"] = got["publisher"]
    if got.get("year"):
        meta["date"] = "-".join(
            [got["year"].zfill(4), got.get("month", "1").zfill(2), got.get("day", "1").zfill(2)])
    if got.get("summary"):
        meta["description"] = got["summary"]
    if got.get("genre"):
        meta["tags"] = [t.strip() for t in got["genre"].split(",") if t.strip()]
    if got.get("languageiso"):
        meta["language"] = got["languageiso"]
    m = re.search(r"ISBN[:\s]*([\dXx-]{10,17})", got.get("notes", ""))
    if m:
        meta["isbn"] = m.group(1)
        meta["identifiers"]["isbn"] = m.group(1)
    return meta
 
 
def _date_parts(value: str | None):
    if not value:
        return None, None, None
    m = re.match(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", value)
    if not m:
        return None, None, None
    y, mo, d = m.groups()
    return int(y), int(mo) if mo else None, int(d) if d else None
 
 
def build_comicinfo(meta: dict, page_count: int, args) -> str:
    """ComicInfo.xml (ComicRack-Schema) - das lesen die meisten Comic-Reader."""
    y, mo, d = _date_parts(meta.get("date"))
    idx = meta.get("series_index", "")
    if idx.endswith(".0"):
        idx = idx[:-2]
 
    notes = ["erzeugt mit comic2panels (ein Panel pro Seite)"]
    if meta.get("isbn"):
        notes.append(f"ISBN: {meta['isbn']}")
    for k, v in sorted(meta.get("identifiers", {}).items()):
        if k not in ("isbn", "calibre", "uuid"):
            notes.append(f"{k.upper()}: {v}")
 
    by_role: dict[str, list[str]] = {}
    for role, person in meta.get("contributors", []):
        field = COMICINFO_ROLE.get(role)
        if field:
            by_role.setdefault(field, []).append(person)
 
    fields = [
        ("Title", meta.get("title")),
        ("Series", meta.get("series")),
        ("Number", idx or None),
        ("Writer", ", ".join(meta.get("authors", [])) or None),
        ("Penciller", ", ".join(by_role.get("Penciller", [])) or None),
        ("Colorist", ", ".join(by_role.get("Colorist", [])) or None),
        ("Letterer", ", ".join(by_role.get("Letterer", [])) or None),
        ("CoverArtist", ", ".join(by_role.get("CoverArtist", [])) or None),
        ("Editor", ", ".join(by_role.get("Editor", [])) or None),
        ("Publisher", meta.get("publisher")),
        ("Year", y), ("Month", mo), ("Day", d),
        ("Summary", meta.get("description")),
        ("Genre", ", ".join(meta.get("tags", [])) or None),
        ("LanguageISO", lang2(meta.get("language")) or None),
        ("PageCount", page_count),
        ("Notes", " | ".join(notes)),
        ("Web", meta.get("identifiers", {}).get("url")),
        ("BlackAndWhite", "Yes" if args.grayscale else None),
        ("Manga", "YesAndRightToLeft" if args.manga else None),
    ]
 
    lines = ['<?xml version="1.0" encoding="utf-8"?>',
             '<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">']
    for key, value in fields:
        if value in (None, ""):
            continue
        lines.append(f"  <{key}>{xml_escape(str(value))}</{key}>")
    lines.append("</ComicInfo>")
    return "\n".join(lines) + "\n"
 
 
def build_cbi_comment(meta: dict) -> bytes:
    """ComicBookInfo als ZIP-Kommentar - in diesem Format liest calibre die Daten."""
    y, mo, _ = _date_parts(meta.get("date"))
    credits = [{"person": a, "role": "Writer", "primary": i == 0}
               for i, a in enumerate(meta.get("authors", []))]
    for role, person in meta.get("contributors", []):
        credits.append({"person": person, "role": role, "primary": False})
 
    book = {"series": meta.get("series", ""),
            "title": meta.get("title", ""),
            "publisher": meta.get("publisher", ""),
            "credits": credits,
            "tags": meta.get("tags", []),
            "comments": meta.get("description", ""),
            "language": lang2(meta.get("language"))}
    idx = meta.get("series_index")
    if idx:
        try:
            f = float(idx)
            book["issue"] = int(f) if f.is_integer() else f
        except ValueError:
            pass
    if y:
        book["publicationYear"] = y
    if mo:
        book["publicationMonth"] = mo
 
    payload = {"appID": "comic2panels/1.0",
               "lastModified": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "ComicBookInfo/1.0": {k: v for k, v in book.items() if v not in ("", [], None)}}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")[:65500]
 
 
def safe_name(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", text).strip(" .") or "Comic"
 
 
def output_name(src: Path, meta: dict, args) -> str:
    suffix = "" if args.repack else " (Panels)"
    if args.name_from_meta and meta.get("title"):
        parts = []
        if meta.get("series") and meta["series"] not in meta["title"]:
            idx = (meta.get("series_index") or "").removesuffix(".0")
            parts.append(f"{meta['series']} {idx}".strip())
        parts.append(meta["title"])
        return safe_name(" - ".join(parts)) + suffix + ".cbz"
    return f"{src.stem}{suffix}.cbz"
 
 
# --------------------------------------------------------------------------
# Panel-Erkennung (rekursiver XY-Cut entlang der Gutter)
# --------------------------------------------------------------------------
 
def background_color(img: np.ndarray, tol: int = 28) -> tuple[np.ndarray, float]:
    """Farbe des Seitenhintergrunds schaetzen, mit Konfidenz (0..1).

    Normalfall: der Seitenrand. Bei randabfallenden Seiten (Zeichnung bis an die
    Kante) ist der Rand kein Hintergrund - dann wird zwischen Weiss und Schwarz
    nach Haeufigkeit im ganzen Bild entschieden (niedrige Konfidenz).
    """
    h, w = img.shape[:2]
    b = max(2, int(min(h, w) * 0.01))
    border = np.concatenate([
        img[:b].reshape(-1, 3), img[-b:].reshape(-1, 3),
        img[:, :b].reshape(-1, 3), img[:, -b:].reshape(-1, 3),
    ])
    cand = np.median(border, axis=0)
    close = (np.abs(border.astype(np.int16) - cand.astype(np.int16)).max(axis=1) <= tol)
    confidence = float(close.mean())
    if confidence >= 0.4:
        return cand, confidence

    small = cv2.resize(img, (0, 0), fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    flat = small.reshape(-1, 3).astype(np.int16)
    white = (np.abs(flat - 255).max(axis=1) <= tol).sum()
    black = (np.abs(flat).max(axis=1) <= tol).sum()
    total = flat.shape[0]
    if white >= black:
        return np.array([255.0, 255.0, 255.0]), white / total
    return np.array([0.0, 0.0, 0.0]), black / total
 
def fill_holes(mask: np.ndarray) -> np.ndarray:
    """Eingeschlossene Hintergrundflaechen (Sprechblasen, Textkaesten) als Inhalt werten.
 
    Nur kleine, lokal begrenzte Loecher werden gefuellt - ein durchgehendes Gutter-Kreuz
    zwischen randlosen Panels bleibt damit erhalten.
    """
    h, w = mask.shape
    bg = (mask == 0).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bg, 8)
    out = mask.copy()
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        touches_border = x == 0 or y == 0 or x + bw >= w or y + bh >= h
        if touches_border:
            continue
        if bw > 0.5 * w or bh > 0.5 * h:
            continue
        out[labels == i] = 1
    return out
 
 
def content_mask(img: np.ndarray, bg: np.ndarray, tol: int, fill: bool = True) -> np.ndarray:
    diff = np.abs(img.astype(np.int16) - bg.astype(np.int16)).max(axis=2)
    mask = (diff > tol).astype(np.uint8)
    return fill_holes(mask) if fill else mask
 
 
def bg_candidates(img: np.ndarray, tol: int) -> list[np.ndarray]:
    """Hintergrund-Kandidaten: Randfarbe, Weiss, Schwarz (ohne Dubletten).

    Ist die Randfarbe mit hoher Konfidenz erkannt (deutlicher, gleichmaessiger
    Seitenrand), wird nur sie verwendet. Sonst wuerden Weiss/Schwarz als
    Alternativen mitkonkurrieren und - da auf farbigen randlosen Seiten praktisch
    jedes Pixel von Schwarz abweicht - eine falsche Schwarz-Vermutung koennte
    trotz eindeutig erkanntem Seitenrand gewinnen (Score durch trivial hohe
    Fuellung eines einzigen Riesenpanels).
    """
    border, confidence = background_color(img, tol)
    if confidence >= 0.6:
        return [border]

    cands = [border, np.array([255.0, 255.0, 255.0]), np.array([0.0, 0.0, 0.0])]
    out: list[np.ndarray] = []
    for c in cands:
        if not any(np.abs(c - o).max() <= tol for o in out):
            out.append(c)
    return out
 
 
def _empty_runs(counts: np.ndarray, limit: float, min_len: int) -> list[tuple[int, int]]:
    """Zusammenhaengende 'leere' Abschnitte (Gutter) finden."""
    empty = counts <= limit
    runs, start = [], None
    for i, e in enumerate(empty):
        if e and start is None:
            start = i
        elif not e and start is not None:
            if i - start >= min_len:
                runs.append((start, i))
            start = None
    if start is not None and len(empty) - start >= min_len:
        runs.append((start, len(empty)))
    return runs
 
 
def _trim(mask: np.ndarray, box: tuple[int, int, int, int], noise: float):
    """Aussenraender einer Region wegschneiden."""
    x0, y0, x1, y1 = box
    sub = mask[y0:y1, x0:x1]
    if sub.size == 0:
        return None
    h, w = sub.shape
    rows = np.where(sub.sum(axis=1) > max(0.0, noise * w * 0.5))[0]
    cols = np.where(sub.sum(axis=0) > max(0.0, noise * h * 0.5))[0]
    if rows.size == 0 or cols.size == 0:
        return None
    return (x0 + int(cols[0]), y0 + int(rows[0]),
            x0 + int(cols[-1]) + 1, y0 + int(rows[-1]) + 1)
 
 
def _segments(sub: np.ndarray, axis: int, min_gutter: int, noise: float, kernel: int):
    """Schnittstellen entlang einer Achse suchen.
 
    Mit kernel > 1 wird die Maske vorher mit einem langen Kernel geoeffnet: dadurch
    verschwinden schmale Ueberlappungen (Figuren, die ueber den Panelrand ragen) und
    der Gutter bleibt als leere Zeile/Spalte erkennbar.
    """
    h, w = sub.shape
    work = sub
    if kernel > 1:
        shape = (kernel, 1) if axis == 0 else (1, kernel)
        work = cv2.morphologyEx(sub, cv2.MORPH_OPEN,
                                cv2.getStructuringElement(cv2.MORPH_RECT, shape))
    if axis == 0:
        counts = work.sum(axis=1)
        limit = max(1.0, noise * w)
    else:
        counts = work.sum(axis=0)
        limit = max(1.0, noise * h)
 
    runs = [r for r in _empty_runs(counts, limit, min_gutter)
            if r[0] > 0 and r[1] < len(counts)]
    if not runs:
        return None
    segs, prev = [], 0
    for s, e in runs:
        segs.append((prev, s))
        prev = e
    segs.append((prev, len(counts)))
    return [s for s in segs if s[1] - s[0] >= 4]
 
 
def split_region(mask, box, ctx, depth=0, axis=0):
    """Region rekursiv an Guttern zerlegen. axis 0 = horizontal schneiden (Zeilen)."""
    box = _trim(mask, box, ctx["noise"])
    if box is None:
        return []
    x0, y0, x1, y1 = box
    if depth >= ctx["max_depth"] or (x1 - x0) < 8 or (y1 - y0) < 8:
        return [box]
 
    sub = mask[y0:y1, x0:x1]
    # erst sauber (Gutter voellig leer), danach tolerant (ueberstehende Zeichnungen)
    for kern_x, kern_y in ((1, 1), (ctx["bridge_x"], ctx["bridge_y"])):
        for a in (axis, 1 - axis):
            kernel = kern_x if a == 0 else kern_y
            segs = _segments(sub, a, ctx["min_gutter"], ctx["noise"], kernel)
            if not segs or len(segs) < 2:
                continue
 
            children = []
            for c0, c1 in segs:
                child = ((x0, y0 + c0, x1, y0 + c1) if a == 0
                         else (x0 + c0, y0, x0 + c1, y1))
                t = _trim(mask, child, ctx["noise"])
                if t is None:
                    continue
                if (t[2] - t[0]) * (t[3] - t[1]) < ctx["min_area"] * ctx["page_area"]:
                    continue  # Seitenzahl, Credits, Staub
                children.append(t)
 
            if len(children) < 2:
                continue
            out = []
            for t in children:
                out.extend(split_region(mask, t, ctx, depth + 1, 1 - a))
            return out
 
    return [box]
 
 
def _merge_duplicates(boxes):
    """Boxen zusammenfassen, die sich fast vollstaendig ueberlappen."""
    out = []
    for b in boxes:
        merged = False
        for i, o in enumerate(out):
            ix = max(0, min(b[2], o[2]) - max(b[0], o[0]))
            iy = max(0, min(b[3], o[3]) - max(b[1], o[1]))
            inter = ix * iy
            smaller = min((b[2] - b[0]) * (b[3] - b[1]),
                          (o[2] - o[0]) * (o[3] - o[1]))
            if smaller > 0 and inter / smaller > 0.85:
                out[i] = (min(b[0], o[0]), min(b[1], o[1]),
                          max(b[2], o[2]), max(b[3], o[3]))
                merged = True
                break
        if not merged:
            out.append(b)
    return out
 
 
def order_panels(boxes, manga: bool):
    """Panels in Zeilen gruppieren und in Lesereihenfolge bringen.
 
    Liefert (boxes, solo): solo[i] ist True, wenn das Panel allein in seiner
    Zeile steht (kein Panel links oder rechts daneben).
    """
    if not boxes:
        return [], []
    boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
    rows, current = [], [boxes[0]]
    for b in boxes[1:]:
        ref = current[-1]
        overlap = min(b[3], ref[3]) - max(b[1], ref[1])
        if overlap > 0.4 * min(b[3] - b[1], ref[3] - ref[1]):
            current.append(b)
        else:
            rows.append(current)
            current = [b]
    rows.append(current)
    out, solo = [], []
    for row in rows:
        ordered = sorted(row, key=lambda b: -b[0] if manga else b[0])
        out.extend(ordered)
        solo.extend([len(row) == 1] * len(row))
    return out, solo
 
 
def _panels_for_bg(img, bg, args):
    h, w = img.shape[:2]
    mask = content_mask(img, bg, args.tolerance, fill=not args.no_fill)
    if args.denoise:      # Rasterpunkte / Scanstaub
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
 
    page_area = float(w * h)
    ctx = {
        "min_gutter": max(3, int(min(h, w) * args.gutter)),
        "noise": args.noise,
        "bridge_x": max(9, int(w * args.bridge)),
        "bridge_y": max(9, int(h * args.bridge)),
        "min_area": args.min_area,
        "page_area": page_area,
        "max_depth": args.max_depth,
    }
    boxes = split_region(mask, (0, 0, w, h), ctx)
    boxes = _merge_duplicates(boxes)
    boxes = [b for b in boxes
             if (b[2] - b[0]) * (b[3] - b[1]) >= args.min_area * page_area
             and (b[2] - b[0]) >= 0.05 * w and (b[3] - b[1]) >= 0.03 * h]
    if not boxes or len(boxes) > args.max_panels:
        boxes = [(0, 0, w, h)]
 
    # Bewertung: wie gut fuellen die gefundenen Kaesten den Inhalt aus?
    fills, weights = [], []
    for x0, y0, x1, y1 in boxes:
        a = (x1 - x0) * (y1 - y0)
        if a <= 0:
            continue
        fills.append(float(mask[y0:y1, x0:x1].sum()) / a)
        weights.append(a)
    fill = float(np.average(fills, weights=weights)) if fills else 0.0
    score = fill + 0.02 * min(len(boxes), 12)
    return boxes, score, fill
 
 
def detect_panels(img: np.ndarray, args) -> list[tuple[int, int, int, int]]:
    """Panels finden. Der Seitenhintergrund wird ueber mehrere Kandidaten
    ausprobiert (heller Rand, Weiss, Schwarz) und das plausibelste Ergebnis
    genommen - das faengt randabfallende Seiten und schwarze Gutter ab."""
    h, w = img.shape[:2]
    scale = min(1.0, args.detect_size / float(max(h, w)))
    small = (cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))),
                        interpolation=cv2.INTER_AREA) if scale < 1 else img)
    # leichtes Glaetten: JPEG-Artefakte und Papierkorn stoeren die Maske sonst
    small = cv2.GaussianBlur(small, (3, 3), 0)

    best, best_bg, best_score, best_fill = None, None, -1.0, 0.0
    for bg in bg_candidates(small, args.tolerance):
        boxes, score, fill = _panels_for_bg(small, bg, args)
        if score > best_score:
            best, best_bg, best_score, best_fill = boxes, bg, score, fill

    # Rueckfall fuer flaue Scans: kam nichts heraus, mit hoeherer Toleranz nachfassen
    if len(best) <= 1 and args.tolerance < 45:
        relaxed = argparse.Namespace(**{**vars(args), "tolerance": 45})
        for bg in bg_candidates(small, 45):
            boxes, score, fill = _panels_for_bg(small, bg, relaxed)
            if len(boxes) > 1 and score > best_score:
                best, best_bg, best_score, best_fill = boxes, bg, score, fill

    # Umrandete Panels sind durch ihre geschlossene Rahmenlinie praktisch
    # vollstaendig "gefuellt" (fill_holes schliesst das Rahmeninnere). Locker
    # verteilter Text auf randlosen Titel-/Coverseiten erreicht das nicht - so
    # eine Seite wird wie eine Splash-Page unveraendert uebernommen, statt an
    # zufaelligen Weissraeumen zwischen Textzeilen zerschnitten zu werden.
    if len(best) > 1 and best_fill < 0.75:
        bh, bw = small.shape[:2]
        best = [(0, 0, bw, bh)]

    inv = 1.0 / scale if scale < 1 else 1.0
    boxes = []
    for x0, y0, x1, y1 in best:
        boxes.append((max(0, int(x0 * inv)), max(0, int(y0 * inv)),
                      min(w, int(round(x1 * inv))), min(h, int(round(y1 * inv)))))
    ordered, solo = order_panels(boxes, args.manga)
    return ordered, solo, best_bg

 
# --------------------------------------------------------------------------
# Ausgabe
# --------------------------------------------------------------------------
 
def fit_to_screen(crop: np.ndarray, args, bg, rotate: bool = False) -> np.ndarray:
    ch, cw = crop.shape[:2]
    tw, th = args.width, args.height
 
    if rotate:
        crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
        ch, cw = crop.shape[:2]
 
    scale = min(tw / cw, th / ch)
    scale = min(scale, args.max_upscale) if scale > 1 else scale
    nw, nh = max(1, int(round(cw * scale))), max(1, int(round(ch * scale)))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    resized = cv2.resize(crop, (nw, nh), interpolation=interp)
 
    if args.no_pad:
        return resized
    canvas = np.full((th, tw, 3), bg, dtype=np.uint8)
    y, x = (th - nh) // 2, (tw - nw) // 2
    canvas[y:y + nh, x:x + nw] = resized
    return canvas
 
 
def write_preview(img, boxes, path: Path):
    vis = img.copy()
    for i, (x0, y0, x1, y1) in enumerate(boxes, 1):
        cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 0, 255), 4)
        cv2.putText(vis, str(i), (x0 + 12, y0 + 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 255), 5)
    cv2.imwrite(str(path), vis, [cv2.IMWRITE_JPEG_QUALITY, 70])
 
 
def process_comic(src: Path, outdir: Path, args) -> Path | None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pages = collect_pages(src, tmp)
        if not pages:
            print(f"  ! keine Bilder in {src.name} gefunden")
            return None
 
        stage = tmp / "_out"
        stage.mkdir()
        prev_dir = outdir / f"{src.stem}_preview"
        if args.preview:
            prev_dir.mkdir(parents=True, exist_ok=True)
 
        n_pages = len(pages)
        n_panels = 0
        for pi, page in enumerate(pages, 1):
            if args.repack:      # nur umpacken: Bilder unveraendert uebernehmen
                dest = stage / page.name
                if dest.exists():
                    dest = stage / f"{pi:04d}_{page.name}"
                shutil.copy2(page, dest)
                continue

            # Erste/letzte N Seiten (Cover, Vor-/Nachwort, Werbung) unveraendert
            # uebernehmen - ohne Panel-Erkennung.
            if pi <= args.skip_start or pi > n_pages - args.skip_end:
                shutil.copy2(page, stage / f"{pi:04d}_01{page.suffix.lower()}")
                n_panels += 1
                print(f"  Seite {pi}/{n_pages}: uebersprungen (unveraendert)", end="\r")
                continue

            img = imread_unicode(page)
            if img is None:
                continue
            boxes, solo, page_bg = detect_panels(img, args)
            if args.preview:
                write_preview(img, boxes, prev_dir / f"page{pi:04d}.jpg")
 
            # Hoechstens ein Panel erkannt (Splash-Page, Cover, unklares
            # Layout): Seite unveraendert ins Archiv uebernehmen.
            if len(boxes) <= 1:
                shutil.copy2(page, stage / f"{pi:04d}_01{page.suffix.lower()}")
                n_panels += 1
                print(f"  Seite {pi}/{len(pages)}: unveraendert", end="\r")
                continue
 
            if args.pad_color == "white":
                bg = np.array([255, 255, 255], dtype=np.uint8)
            elif args.pad_color == "black":
                bg = np.array([0, 0, 0], dtype=np.uint8)
            else:
                bg = np.clip(page_bg, 0, 255).astype(np.uint8)
            h, w = img.shape[:2]
 
            if args.include_page:
                out = fit_to_screen(img, args, bg)
                cv2.imwrite(str(stage / f"{pi:04d}_00.jpg"), out,
                            [cv2.IMWRITE_JPEG_QUALITY, args.quality])
 
            for bi, (box, alone) in enumerate(zip(boxes, solo), 1):
                x0, y0, x1, y1 = box
                m = args.margin
                x0, y0 = max(0, x0 - m), max(0, y0 - m)
                x1, y1 = min(w, x1 + m), min(h, y1 + m)
                crop = img[y0:y1, x0:x1]
                if crop.size == 0:
                    continue
                if args.grayscale:
                    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                    crop = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
                # Drehen nur, wenn das Panel allein in seiner Zeile steht
                # (nichts daneben) und breiter als hoch ist.
                rotate = (args.rotate_wide and alone
                          and (x1 - x0) > (y1 - y0))
                out = fit_to_screen(crop, args, bg, rotate=rotate)
                cv2.imwrite(str(stage / f"{pi:04d}_{bi:02d}.jpg"), out,
                            [cv2.IMWRITE_JPEG_QUALITY, args.quality])
                n_panels += 1
 
            print(f"  Seite {pi}/{len(pages)}: {len(boxes)} Panels", end="\r")
 
        # Metadaten aus Calibre uebernehmen
        meta, opf_path = {}, None
        if not args.no_metadata:
            opf_path = Path(os.path.expanduser(args.opf)) if args.opf else find_opf(src)
            if opf_path and opf_path.is_file():
                meta = parse_opf(opf_path)
            else:
                opf_path = None
                found = [p for p in tmp.rglob("*.xml")
                         if p.name.lower() == "comicinfo.xml"]
                if found:      # Archiv bringt selbst schon Metadaten mit
                    meta = parse_comicinfo(found[0])
                    if meta.get("title"):
                        print("  (ComicInfo.xml aus dem Original uebernommen)")
 
        has_meta = bool(meta.get("title") or meta.get("series") or meta.get("authors"))
        outdir.mkdir(parents=True, exist_ok=True)
        target = outdir / output_name(src, meta if has_meta else {}, args)
        images = sorted(stage.iterdir(), key=lambda p: p.name)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as zf:
            for f in images:
                zf.write(f, f.name)
            if has_meta:
                zf.writestr("ComicInfo.xml",
                            build_comicinfo(meta, len(images), args))
                if opf_path:      # vollstaendige Calibre-Daten, verlustfrei
                    zf.write(opf_path, "metadata.opf")
                zf.comment = build_cbi_comment(meta)
 
        if args.repack:
            print(f"  {len(pages)} Seiten unveraendert -> {target.name}" + " " * 20)
        else:
            print(f"  {len(pages)} Seiten -> {n_panels} Panels -> {target.name}" + " " * 20)
        if has_meta:
            who = ", ".join(meta.get("authors", [])) or "?"
            extra = f", ISBN {meta['isbn']}" if meta.get("isbn") else ""
            print(f"  Metadaten uebernommen: {meta.get('title', '?')} / {who}{extra}")
        elif not args.no_metadata:
            print("  (keine metadata.opf gefunden - ohne Metadaten geschrieben)")
        return target
 
 
def main():
    ap = argparse.ArgumentParser(
        description="[DE] Comics panelweise aufbereiten (Standard: PocketBook Era Color). "
                     "[EN] Split comics into one page per panel (default: PocketBook Era Color).")
    ap.add_argument("inputs", nargs="+", help="CBZ/CBR/PDF/Ordner")
    ap.add_argument("-o", "--out", default="panels", help="Zielordner")
    ap.add_argument("--width", type=int, default=1264, help="Displaybreite (Standard 1264)")
    ap.add_argument("--height", type=int, default=1680, help="Displayhoehe (Standard 1680)")
    ap.add_argument("--manga", action="store_true", help="Lesereihenfolge rechts nach links")
    ap.add_argument("--repack", action="store_true",
                    help="nicht in Panels zerlegen, nur CBR -> CBZ umpacken "
                         "(Bilder bleiben unveraendert, Metadaten kommen mit)")
    ap.add_argument("--preview", action="store_true",
                    help="Kontrollbilder mit eingezeichneten Panels schreiben")
    ap.add_argument("--include-page", action="store_true",
                    help="vor den Panels jeweils die ganze Seite einfuegen")
    ap.add_argument("--skip-start", type=int, default=0, metavar="N",
                    help="die ersten N Seiten unveraendert uebernehmen "
                         "(keine Panel-Erkennung, z.B. fuer Cover/Vorworte)")
    ap.add_argument("--skip-end", type=int, default=0, metavar="N",
                    help="die letzten N Seiten unveraendert uebernehmen "
                         "(keine Panel-Erkennung, z.B. fuer Anhang/Werbung)")
    ap.add_argument("--grayscale", action="store_true", help="in Graustufen ausgeben")
    ap.add_argument("--opf", default=None,
                    help="metadata.opf explizit angeben (sonst wird neben der "
                         "Comicdatei danach gesucht)")
    ap.add_argument("--no-metadata", action="store_true",
                    help="keine Calibre-Metadaten uebernehmen")
    ap.add_argument("--name-from-meta", action="store_true",
                    help="Dateiname aus Serie/Titel der Metadaten bilden")
    ap.add_argument("--rotate-wide", action="store_true",
                    help="Panels, die allein in ihrer Zeile stehen und breiter "
                         "als hoch sind, um 90 Grad drehen")
    ap.add_argument("--scan", action="store_true",
                    help="inputs als Stammverzeichnisse behandeln: alle Unterordner "
                         "rekursiv nach Comics durchsuchen und als Batch verarbeiten; "
                         "die Ordnerstruktur wird im Zielordner gespiegelt")
    ap.add_argument("--scan-ext", default="cbr",
                    help="Dateiendungen fuer --scan, kommagetrennt (Standard: cbr; "
                         "z.B. cbr,cbz,pdf)")
    ap.add_argument("--force", action="store_true",
                    help="im Batch auch Comics verarbeiten, deren Ziel-CBZ schon existiert")
    ap.add_argument("--no-pad", action="store_true",
                    help="nicht auf Displaygroesse auffuellen (nur skalieren)")
    ap.add_argument("--margin", type=int, default=6, help="Rand um jedes Panel in Pixel")
    ap.add_argument("--pad-color", choices=["auto", "white", "black"], default="white",
                    help="Farbe der Raender, wenn ein Panel nicht das ganze Display fuellt")
    ap.add_argument("--quality", type=int, default=88, help="JPEG-Qualitaet")
    ap.add_argument("--max-upscale", type=float, default=2.5)
    ap.add_argument("--tolerance", type=int, default=28,
                    help="Farbabstand zum Hintergrund, ab dem ein Pixel als Inhalt gilt")
    ap.add_argument("--gutter", type=float, default=0.008,
                    help="Mindestbreite eines Gutters als Anteil der Seite")
    ap.add_argument("--noise", type=float, default=0.006,
                    help="erlaubter Stoeranteil in einer 'leeren' Zeile/Spalte")
    ap.add_argument("--min-area", type=float, default=0.012,
                    help="kleinste Panelflaeche als Anteil der Seite")
    ap.add_argument("--max-panels", type=int, default=24,
                    help="mehr Panels pro Seite gelten als Fehlerkennung")
    ap.add_argument("--bridge", type=float, default=0.12,
                    help="wie breit ueber den Gutter ragende Zeichnungen ignoriert werden "
                         "(Anteil der Seitenbreite/-hoehe)")
    ap.add_argument("--no-fill", action="store_true",
                    help="Sprechblasen nicht als Panelinhalt behandeln")
    ap.add_argument("--detect-size", type=int, default=1400,
                    help="Bildgroesse fuer die Erkennung (kleiner = schneller)")
    ap.add_argument("--max-depth", type=int, default=8,
                    help="maximale Verschachtelungstiefe der Schnitte")
    ap.add_argument("--denoise", action="store_true",
                    help="Rasterpunkte/Scanstaub vor der Erkennung glaetten")
    args = ap.parse_args()
 
    outdir = Path(os.path.expanduser(args.out))
 
    # Arbeitsliste aufbauen: (Quelldatei, Zielordner)
    jobs: list[tuple[Path, Path]] = []
    if args.scan:
        exts = {"." + e.strip().lstrip(".").lower()
                for e in args.scan_ext.split(",") if e.strip()}
        for pattern in args.inputs:
            root = Path(os.path.expanduser(pattern))
            if not root.is_dir():
                print(f"! kein Verzeichnis (bei --scan erwartet): {root}")
                continue
            found = sorted((p for p in root.rglob("*")
                            if p.is_file() and p.suffix.lower() in exts),
                           key=lambda p: natural_key(str(p)))
            print(f"# {root}: {len(found)} Datei(en) gefunden")
            for f in found:
                # Ordnerstruktur unterhalb des Stammverzeichnisses spiegeln
                jobs.append((f, outdir / f.parent.relative_to(root)))
    else:
        for pattern in args.inputs:
            src = Path(os.path.expanduser(pattern))
            if not src.exists():
                print(f"! nicht gefunden: {src}")
                continue
            jobs.append((src, outdir))
 
    made, skipped, failed = [], 0, 0
    for i, (src, dest) in enumerate(jobs, 1):
        # Schon verarbeitet? (nur pruefbar, wenn der Name nicht aus Metadaten kommt)
        if not args.force and not args.name_from_meta:
            probe = dest / output_name(src, {}, args)
            if probe.exists():
                print(f"= [{i}/{len(jobs)}] uebersprungen (existiert): {probe.name}")
                skipped += 1
                continue
        print(f"* [{i}/{len(jobs)}] {src.name}")
        try:
            r = process_comic(src, dest, args)
            if r:
                made.append(r)
            else:
                failed += 1
        except KeyboardInterrupt:
            print("\nAbgebrochen.")
            break
        except Exception as e:  # noqa: BLE001
            print(f"  ! Fehler: {e}")
            failed += 1
 
    summary = f"\nFertig: {len(made)} Datei(en) in {outdir}"
    if skipped:
        summary += f", {skipped} uebersprungen"
    if failed:
        summary += f", {failed} fehlgeschlagen"
    print(summary)
    return 0 if (made or skipped) else 1
 
 
if __name__ == "__main__":
    sys.exit(main())
 