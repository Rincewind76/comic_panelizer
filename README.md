# comic2panels

Comics (CBZ/CBR/PDF/Ordner) in eine CBZ umbauen, bei der jedes Panel eine eigene "Seite" ist — voreingestellt auf den PocketBook Era Color (1264 × 1680).

Turns comics (CBZ/CBR/PDF/folder) into a CBZ where every panel becomes its own "page" — preset for the PocketBook Era Color (1264 × 1680).

**Sprache / Language:** [Deutsch](#deutsch) | [English](#english)

---

## Deutsch

### Was macht das Skript?

`comic2panels.py` erkennt automatisch die einzelnen Panels auf jeder Comicseite (über die Zwischenräume/"Gutter") und schreibt jedes Panel als eigene Bildseite in eine neue CBZ-Datei. Auf E-Readern wie dem PocketBook Era Color lässt sich ein Comic dadurch panelweise statt seitenweise lesen — die Schrift bleibt lesbar, ohne dass man zoomen muss.

Seiten, auf denen kein oder nur ein Panel erkannt wird (Cover, Splash-Pages, unklare Layouts), werden unverändert übernommen — da wird nichts zerschnitten oder neu komprimiert.

### Voraussetzungen

```bash
pip3 install opencv-python-headless numpy
```

- **CBR/RAR:** macOS bringt `bsdtar` mit, das reicht meistens. Sonst: `brew install unar`
- **PDF (optional):** `pip3 install pymupdf`

### Verwendung

```bash
python3 comic2panels.py "Batman 001.cbr" -o ~/Desktop/panels --preview
python3 comic2panels.py ~/Comics/*.cbz -o ~/Desktop/panels
python3 comic2panels.py manga.cbz --manga           # Lesereihenfolge rechts->links
python3 comic2panels.py x.cbz --include-page        # ganze Seite vor ihren Panels
python3 comic2panels.py x.cbz --rotate-wide         # breite Einzelpanels quer legen
```

**Batch:** ein Stammverzeichnis rekursiv nach CBRs durchsuchen und alles verarbeiten (die Ordnerstruktur wird im Ziel gespiegelt, Vorhandenes wird übersprungen):

```bash
python3 comic2panels.py ~/Comics --scan -o ~/Desktop/panels
python3 comic2panels.py ~/Comics --scan --scan-ext cbr,cbz,pdf -o out
```

**Erst mit `--preview` laufen lassen:** im Ordner `<name>_preview` liegt zu jeder Seite ein Bild mit den erkannten Panels und ihrer Reihenfolge. Passt das, den Lauf ohne `--preview` wiederholen und die fertige CBZ auf den Reader kopieren.

**Nur umpacken statt zerlegen** (CBR → CBZ, Bilder unverändert, Metadaten dabei):

```bash
python3 comic2panels.py ~/Comics/*.cbr --repack -o ~/Desktop/cbz
```

### Metadaten (Calibre)

Metadaten (Autor, ISBN, Serie, Verlag, Schlagworte, Beschreibung) werden übernommen, wenn neben der Comicdatei eine `metadata.opf` liegt — genau so legt Calibre seine Bücher ab. Sie landen dreifach in der neuen CBZ:

- `ComicInfo.xml` — für Comic-Reader
- ZIP-Kommentar — im ComicBookInfo-Format, das Calibre selbst liest
- `metadata.opf` — unverändert mitkopiert, damit nichts verlorengeht

Ohne `metadata.opf` wird ersatzweise eine `ComicInfo.xml` aus dem Original benutzt.

| Option | Bedeutung |
|---|---|
| `--opf PFAD` | `metadata.opf` explizit angeben |
| `--name-from-meta` | Dateinamen aus Serie/Titel bilden |
| `--no-metadata` | Metadaten-Übernahme abschalten |

### Stellschrauben, wenn die Erkennung danebenliegt

| Option | Bedeutung |
|---|---|
| `--gutter 0.02` | nur breitere Zwischenräume als Trennung werten (weniger Schnitte) |
| `--gutter 0.006` | auch enge Zwischenräume trennen (mehr Schnitte) |
| `--min-area 0.03` | kleine Fragmente verwerfen |
| `--bridge 0.2` | großzügiger gegenüber Figuren, die über den Rand ragen |
| `--tolerance 45` | für graue/vergilbte Scans |

### Alle Optionen

Vollständige Liste mit Beschreibung:

```bash
python3 comic2panels.py --help
```

---

## English

### What it does

`comic2panels.py` automatically detects the individual panels on each comic page (via the whitespace/"gutters" between them) and writes every panel out as its own image page in a new CBZ file. On e-readers like the PocketBook Era Color, this lets you read a comic panel by panel instead of page by page — text stays legible without needing to zoom.

Pages where zero or only one panel is detected (covers, splash pages, unclear layouts) are copied through unchanged — nothing gets cut or recompressed.

### Requirements

```bash
pip3 install opencv-python-headless numpy
```

- **CBR/RAR:** macOS ships `bsdtar`, which is usually enough. Otherwise: `brew install unar`
- **PDF (optional):** `pip3 install pymupdf`

### Usage

```bash
python3 comic2panels.py "Batman 001.cbr" -o ~/Desktop/panels --preview
python3 comic2panels.py ~/Comics/*.cbz -o ~/Desktop/panels
python3 comic2panels.py manga.cbz --manga           # right-to-left reading order
python3 comic2panels.py x.cbz --include-page        # full page before its panels
python3 comic2panels.py x.cbz --rotate-wide         # rotate wide solo panels to landscape
```

**Batch:** recursively scan a root directory for CBRs and process everything (the folder structure is mirrored into the target, existing output is skipped):

```bash
python3 comic2panels.py ~/Comics --scan -o ~/Desktop/panels
python3 comic2panels.py ~/Comics --scan --scan-ext cbr,cbz,pdf -o out
```

**Run with `--preview` first:** the folder `<name>_preview` holds one image per page showing the detected panels and their reading order. If it looks right, rerun without `--preview` and copy the finished CBZ to your reader.

**Repack only, without splitting** (CBR → CBZ, images unchanged, metadata kept):

```bash
python3 comic2panels.py ~/Comics/*.cbr --repack -o ~/Desktop/cbz
```

### Metadata (Calibre)

Metadata (author, ISBN, series, publisher, tags, description) is picked up when a `metadata.opf` sits next to the comic file — that's how Calibre stores its books. It ends up in the new CBZ in three places:

- `ComicInfo.xml` — for comic readers
- ZIP comment — as ComicBookInfo, which Calibre itself reads
- `metadata.opf` — copied through unchanged, so nothing gets lost

Without a `metadata.opf`, an existing `ComicInfo.xml` from the original is used instead.

| Option | Meaning |
|---|---|
| `--opf PATH` | point to a `metadata.opf` explicitly |
| `--name-from-meta` | build the filename from series/title |
| `--no-metadata` | disable metadata handling |

### Tuning knobs if detection gets it wrong

| Option | Meaning |
|---|---|
| `--gutter 0.02` | only count wider gaps as separators (fewer cuts) |
| `--gutter 0.006` | also split on narrow gaps (more cuts) |
| `--min-area 0.03` | discard small fragments |
| `--bridge 0.2` | more tolerant of art bleeding over a panel edge |
| `--tolerance 45` | for grey/yellowed scans |

### All options

Full list with descriptions:

```bash
python3 comic2panels.py --help
```

---

## Lizenz / License

**CC BY-NC 4.0** (Creative Commons Attribution-NonCommercial 4.0 International) — © Thomas Schoedl (Rincewind76). Siehe [LICENSE](LICENSE).

Freie Nutzung und Weitergabe erlaubt, solange der Urheber genannt wird — kommerzielle Nutzung ist nicht gestattet.

Free to use and share with attribution — commercial use is not permitted.
