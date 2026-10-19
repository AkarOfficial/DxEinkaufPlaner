# -*- coding: utf-8 -*-
"""DxEinkaufsPlaner - lokale Einkaufs-, Rezept- und Preisverwaltung.
Python 3.10+ | CustomTkinter für abgerundete UI; Pillow für Bildfunktionen; Selenium für Gemini-Browserautomation.
"""

import os
import re
import threading
import sqlite3
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime
from pathlib import Path

# CustomTkinter liefert abgerundete Bedienelemente. Ohne das Paket bleibt
# die Anwendung mit den Tkinter-Fallbacks weiterhin startfähig.
try:
    import customtkinter as ctk
except ImportError:
    ctk = None

APP_NAME = "DxEinkaufsPlaner"
APP_VERSION = "1.0"
BASE_DIR = Path(__file__).resolve().parent

# Persistente Benutzerdaten liegen immer außerhalb des Installationsordners.
# Dadurch bleiben Daten bei Updates/Neuinstallation der EXE erhalten und
# benötigen keine Schreibrechte im Programmverzeichnis.
if sys.platform == "win32":
    _user_data_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
else:
    _user_data_root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
DATA_DIR = _user_data_root / "DxEinkaufsPlaner"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "DxEinkaufsPlaner.db"

# Einmalige Migration einer vorhandenen Datenbank aus dem alten Projektordner.
# Eine vorhandene Datenbank im neuen Speicherort hat immer Vorrang.
_legacy_db = BASE_DIR / "DxEinkaufsPlaner.db"
if not DB_PATH.exists() and _legacy_db.is_file():
    try:
        import shutil as _db_shutil
        _db_shutil.copy2(_legacy_db, DB_PATH)
        print(f"DxEinkaufsPlaner: Bestehende Datenbank nach {DB_PATH} übernommen.")
    except OSError as _migration_error:
        print(f"DxEinkaufsPlaner: Datenbankmigration fehlgeschlagen: {_migration_error}")
        # Sicherer Rückfall: bestehende Datenbank weiterverwenden, statt leer zu starten.
        DB_PATH = _legacy_db

CURRENCY = "€"

# Farben: Dx-Stil
BG = "#020201"
PANEL = "#10100f"
PANEL_ALT = "#181715"
FG = "#f4f2ee"
MUTED = "#8a8580"
ORANGE = "#ff7900"
GOLD = "#ffad18"
BORDER = "#29231a"
GREEN = "#4caf75"
RED = "#e15b64"


def money(value):
    try:
        return f"{float(value):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "0,00 €"


def parse_number(value, field="Zahl"):
    raw = str(value).strip().replace("€", "").replace(" ", "")
    if not raw:
        raise ValueError(f"Bitte einen Wert für {field} eingeben.")
    # Deutsche Eingaben wie 1.234,56 sowie 12,50 unterstützen.
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    number = float(raw)
    if number < 0:
        raise ValueError(f"{field} darf nicht negativ sein.")
    return number


def clean_receipt_product_name(name, known_products=()):
    """Bereinigt OCR-Namen und korrigiert nur klar erkennbare Artikelbezeichnungen.

    Wichtig: Bei Kassenbons sind Produktnamen oft stark abgekürzt. Eindeutige
    bekannte Wortfragmente werden deshalb vor dem Entfernen der Codes geprüft.
    Nicht eindeutig zuordenbare Namen werden nicht durch beliebige Wörter ersetzt.
    """
    name = re.sub(r"\s+", " ", name).strip()
    raw_fold = re.sub(r"[^a-zäöüß0-9]+", " ", name.casefold()).strip()

    # Konkrete, am vorliegenden Netto-Bon beobachtete OCR-Varianten. Diese
    # Korrekturen sind absichtlich eng gefasst, um falsche Treffer zu vermeiden.
    receipt_aliases = [
        (("mozzarella", "mozzarell", "moz zarella", "wozzarella", "woezarelle", "woezarella", "ozzarella"), "Mozzarella"),
        (("mozz mini", "mozz mini", "moz mini", "woz wiavhi", "woz wia", "mozzarella mini", "moz z min"), "Mozzarella Mini"),
        (("gouda jung", "gouda jung", "gouda jung hf", "gouda jung hf3"), "Gouda jung"),
        (("sonnenkern", "sonnenkero", "sonnenkorn"), "Sonnenkern"),
        (("der sahnige", "sahnige"), "Der Sahnige"),
        (("junger spinat", "junger spina", "junger spina t", "junger spina portio"), "Junger Spinat"),
        (("buttergemuese", "buttergemüse", "buttergeue", "buttergenuese", "butteroeuase", "butteroeese", "buttergeuese", "buttergeueese", "buttergemuese"), "Buttergemüse"),
        (("hirtenkaese leicht", "hirtenkaes leicht", "hirtenkaes", "wittenkaes leicht", "wittenkaes", "hirtenkaese", "hirtenkaes leicht"), "Hirtenkäse leicht"),
        (("linsenchips", "linsenchipsort", "linsenchips sort"), "Linsenchips"),
        (("knabbersnack salz", "knabbersnacksalz", "knabbersnack"), "Knabbersnack Salz"),
        (("americanstyle cookies", "american style cookies", "americanstyle cookies"), "Americanstyle Cookies"),
        (("mehrkornbrot", "mehrkornbrat", "mehrkornbrot500g", "kkkoerni mehrkornbrot"), "Mehrkornbrot"),
        (("vital fit", "vital flit", "vitalfit"), "Vital+Fit"),
        (("kartoffel rot pfanni", "kartoffeln rot pfanni", "kartoffel rot pfanni"), "Kartoffeln rot Pfanni"),
        (("paprika mix", "paprika mix 500g"), "Paprika Mix"),
        (("weisskraut kohl", "weißkraut kohl", "weisskraut", "weisskohl", "weißkohl"), "Weißkraut / Weißkohl"),
        (("schinkenwuerfel leicht", "schinkenwürfel leicht", "schinkenwuerfel"), "Schinkenwürfel leicht"),
        (("teewurst saeckchen fein", "teewurst-säckchen fein", "teewurst sackchen fein", "teewurst"), "Teewurst-Säckchen fein"),
        (("edelsalami", "edelsalami 150g"), "Edelsalami"),
        (("leberwurst", "leberwurst sort", "leberwurst sorte"), "Leberwurst"),
    ]
    for aliases, canonical in receipt_aliases:
        if any(alias in raw_fold for alias in aliases):
            return canonical

    # Unscharfe OCR-Korrektur für bekannte Lebensmittelbegriffe. Das hilft auch,
    # wenn Tesseract mehrere Buchstaben vertauscht/ersetzt (z. B. "Wittenkaes").
    # Es werden nur spezifische Begriffe mit einem ausreichend hohen Ähnlichkeitswert
    # korrigiert; kurze oder mehrdeutige Wörter bleiben unverändert.
    from difflib import SequenceMatcher
    compact_raw = re.sub(r"[^a-zäöüß0-9]", "", raw_fold)
    fuzzy_targets = [
        ("buttergemuese", "Buttergemüse", ("butter", "gemuese")),
        ("hirtenkaese", "Hirtenkäse leicht", ("hirten", "kaes", "wittenkaes")),
        ("mozzarella", "Mozzarella", ("mozz", "wozz", "woez", "ozzarella")),
        ("mozzarellamini", "Mozzarella Mini", ("mozz", "mini", "wiavhi", "wia")),
        ("mehrkornbrot", "Mehrkornbrot", ("mehrkorn", "kornbrot", "kornbrat")),
        ("jungerspinat", "Junger Spinat", ("spinat", "spina")),
        ("linsenchips", "Linsenchips", ("linsenchip",)),
        ("knabbersnacksalz", "Knabbersnack Salz", ("knabber", "snack")),
        ("americanstylecookies", "Americanstyle Cookies", ("american", "cookies")),
        ("kartoffelrotpfanni", "Kartoffeln rot Pfanni", ("kartoffel", "pfanni")),
        ("weisskrautkohl", "Weißkraut / Weißkohl", ("weisskraut", "weisskohl", "weissk")),
    ]
    fuzzy_ranked = []
    for target, canonical, hints in fuzzy_targets:
        # Vergleiche sowohl den gesamten kompakten Text als auch längere Fragmente,
        # damit Handelscodes und Gewichtsangaben die Ähnlichkeit nicht zerstören.
        score = SequenceMatcher(None, compact_raw, target).ratio()
        for hint in hints:
            if len(hint) >= 5 and hint in compact_raw:
                score = max(score, 0.82)
            elif len(hint) >= 5:
                # Toleriert einzelne OCR-Fehler innerhalb eines passenden Wortfragments.
                tokens = re.findall(r"[a-zäöüß]+", raw_fold)
                score = max(score, max((SequenceMatcher(None, token, hint).ratio() * 0.88 for token in tokens), default=0))
        fuzzy_ranked.append((score, canonical))
    fuzzy_ranked.sort(reverse=True)
    if fuzzy_ranked:
        best_score, best_canonical = fuzzy_ranked[0]
        second_score = fuzzy_ranked[1][0] if len(fuzzy_ranked) > 1 else 0.0
        if best_score >= 0.76 and best_score - second_score >= 0.035:
            return best_canonical

    name = name.strip()
    # Häufige Netto-/Handels-Kürzel am Anfang, keine eigentlichen Produktnamen.
    name = re.sub(r"(?i)^(?:(?:GL|BE|UL|VL|FF|CI|C1|MT|AL|FK|WL|M\.?I\.?|N\.?I\.?|SB|HER\.?|HER|KKAKÖRNI\.?)\s*\.?\s*)+", "", name)
    # OCR verwechselt bei diesem Bon regelmäßig Buchstaben und Nummern in Handelscodes.
    name = re.sub(r"(?i)\b(?:HF3|SHB|VLOG|YLOG|QS|Q5|BH|ULOG|G\.FL\.WU\.)\b", " ", name)
    # Maßeinheiten, Gewichte, Packungsgrößen und reine Ziffern aus dem Namen entfernen.
    name = re.sub(r"(?i)\b\d+(?:[,.]\d+)?\s*(?:kg|g|gr|ml|l|stk|stück|st)\b", " ", name)
    name = re.sub(r"(?i)\b\d+\s*[x×]\s*\d*\s*(?:g|gr)?\b", " ", name)
    name = re.sub(r"\b\d+(?:[,.]\d+)?\b", " ", name)
    # Steuerkennzeichen / OCR-Müll am Ende und isolierte Kurz-Codes entfernen.
    name = re.sub(r"(?i)(?:\s+|^)(?:B|8|VLOG|YLOG|VLOG|HF3|SHB|QS|Q5)+\s*$", "", name)
    name = re.sub(r"(?i)\b(?:VLOG|YLOG|HF3|SHB|QS|Q5|ULOG|BH|10ST)\b", " ", name)
    name = re.sub(r"[^A-Za-zÄÖÜäöüß+&/' -]", " ", name)
    name = re.sub(r"(?i)\b(?:portio|sort\.)\b", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" -./")

    # Häufige, eindeutig erkennbare Artikel auf dem gezeigten Bon sauber benennen.
    # Nur bei klaren Schlüsselwörtern anwenden; andere Namen bleiben möglichst erhalten.
    n = name.casefold()
    n = re.sub(r"\bgo\s+ug\b", "gouda", n)
    # Einige Bons verwenden schwer lesbare interne Artikelkürzel. Hier reichen
    # die noch erkennbaren Wortteile für eine saubere, kurze Bezeichnung.
    if "gou" in n or "gouda" in n:
        if "wa" in n or "am st" in n or "stueck" in n or "stück" in n:
            return "Gouda am Stück"
        if "jung" in n or "he" in n or "hf" in n or "s h" in n or "sba" in n or "oog" in n:
            return "Gouda jung"
        return "Gouda"
    if any(term in n for term in ("mozz", "wozz", "woez", "yozz", "ozzarella")):
        return "Mozzarella Mini" if any(term in n for term in ("mini", "wiavhi", "wia")) else "Mozzarella"
    if any(term in n for term in ("buttergem", "buttergenu", "buttergeue", "buttergemu")):
        return "Buttergemüse"
    if any(term in n for term in ("hirtenkaes", "hirtenkäs", "hirtenkae", "hirtenk")):
        return "Hirtenkäse leicht"
    if "paprika" in n:
        return "Paprika Mix"
    if "kornbrot" in n or "kornbrat" in n or "netirkorn" in n:
        return "Mehrkornbrot"
    if "vital" in n and ("fit" in n or "flit" in n):
        return "Vital+Fit"
    if "kartoffel" in n and ("pfanni" in n or "rot" in n):
        return "Kartoffeln rot Pfanni"
    if "schinken" in n and ("w" in n or "würfel" in n or "wuerfel" in n):
        return "Schinkenwürfel leicht"
    if "cookies" in n:
        return "Americanstyle Cookies"
    if "linsenchip" in n:
        return "Linsenchips"
    if "knabbersnack" in n:
        return "Knabbersnack Salz"
    if "spinat" in n:
        return "Junger Spinat"
    if "sahnige" in n:
        return "Der Sahnige"
    if "sonnenkern" in n:
        return "Sonnenkern"
    if "eier" in n:
        return "Eier"
    if "teewurst" in n:
        return "Teewurst-Säckchen fein"
    if "edelsalami" in n:
        return "Edelsalami"
    if "leberwurst" in n:
        return "Leberwurst"
    if "weisskraut" in n or "weißkraut" in n or "weisskohl" in n or "weißkohl" in n:
        return "Weißkraut / Weißkohl"
    if "wurst" in n or "brufil" in n or "brustfilet" in n:
        return "Hähnchenbrustfilet gebraten" if ("brufil" in n or "brustfilet" in n) else "Wurst"
    # Katalogabgleich als allgemeine zweite Ebene: Wenn der erkannte Name durch
    # OCR-Fehler verändert wurde, vergleichen wir ihn mit bereits bekannten
    # Produktnamen. Nur ein klarer Treffer wird automatisch übernommen; bei
    # Mehrdeutigkeit bleibt der bereinigte OCR-Text zur manuellen Prüfung stehen.
    if name and known_products:
        from difflib import SequenceMatcher

        def norm_product(value):
            value = value.casefold().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
            value = re.sub(r"[^a-z0-9+]+", " ", value)
            value = re.sub(r"\b(?:gl|be|ul|vl|ff|ci|c1|mt|al|fk|wl|sb|hf3|shb|vlog|ylog|qs|q5|bh|ulog)\b", " ", value)
            return re.sub(r"\s+", " ", value).strip()

        observed = norm_product(name)
        observed_tokens = set(observed.split())
        ranked = []
        for product in known_products:
            canonical = str(product).strip()
            target = norm_product(canonical)
            if not target:
                continue
            ratio = SequenceMatcher(None, observed, target).ratio()
            target_tokens = set(target.split())
            overlap = len(observed_tokens & target_tokens) / max(1, len(target_tokens))
            # Tokenähnlichkeit hilft bei zusätzlichen OCR-Resten; reine kurze
            # Teiltreffer reichen ausdrücklich nicht aus.
            score = max(ratio, overlap * 0.92)
            ranked.append((score, canonical))
        ranked.sort(reverse=True)
        if ranked:
            best_score, best_name = ranked[0]
            second_score = ranked[1][0] if len(ranked) > 1 else 0.0
            if best_score >= 0.84 and best_score - second_score >= 0.06:
                return best_name

    # Unklare OCR-Reste nicht mit Ziffern/Artikelcodes auffüllen.
    return name

def format_receipt_number(value):
    """Formatiert Mengen ohne unnötige Nachkommastellen."""
    number = float(value)
    return str(int(number)) if number.is_integer() else (f"{number:.3f}".rstrip("0").rstrip(".")).replace(".", ",")

def parse_gemini_receipt_response(text):
    """Parst Gemini-Artikelzeilen im Format Name | Menge | Einzelpreis | Zeilengesamtpreis."""
    rows = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip().strip("` ")
        if not line or line.startswith(("```", "#")):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 4:
            continue
        name, quantity_text, unit_price_text, total_price_text = parts
        if not name or name.casefold() in {"produktname", "lesbarer produktname", "artikel"}:
            continue
        try:
            quantity = parse_number(quantity_text, "Menge")
            unit_price = parse_number(unit_price_text, "Einzelpreis")
            total_price = parse_number(total_price_text, "Zeilengesamtpreis")
        except (ValueError, TypeError):
            continue
        if quantity <= 0 or unit_price < 0 or total_price < 0:
            continue
        rows.append({
            "name": name,
            "quantity": quantity,
            "unit_price": unit_price,
            "total_price": total_price,
        })
    return rows


class Database:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.init_schema()

    def init_schema(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
            unit TEXT NOT NULL DEFAULT 'Stück',
            price REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            store TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            portions REAL NOT NULL DEFAULT 1,
            notes TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS recipe_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            quantity REAL NOT NULL,
            UNIQUE(recipe_id, product_id)
        );
        CREATE TABLE IF NOT EXISTS saved_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            total REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS saved_list_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id INTEGER NOT NULL REFERENCES saved_lists(id) ON DELETE CASCADE,
            product_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            unit_price REAL NOT NULL,
            line_total REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS receipt_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS product_store_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            store TEXT NOT NULL,
            price REAL NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(product_id, store)
        );
        """)
        # Migration fuer bereits vorhandene Datenbanken.
        product_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(products)").fetchall()}
        if "store" not in product_columns:
            self.conn.execute("ALTER TABLE products ADD COLUMN store TEXT NOT NULL DEFAULT ''")
        for name in ["Obst & Gemüse", "Backwaren", "Milchprodukte", "Fleisch & Fisch", "Trockenprodukte", "Getränke", "Tiefkühl", "Haushalt", "Sonstiges"]:
            self.conn.execute("INSERT OR IGNORE INTO categories(name) VALUES (?)", (name,))
        self.conn.commit()

    def rows(self, sql, args=()):
        return self.conn.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        return self.conn.execute(sql, args).fetchone()

    def run(self, sql, args=()):
        cur = self.conn.execute(sql, args)
        self.conn.commit()
        return cur.lastrowid

    def close(self):
        self.conn.close()


class DxEinkaufsPlaner:
    def __init__(self, root):
        self.root = root
        self.db = Database()
        self.root.title(f"{APP_NAME}  |  Version {APP_VERSION}")
        self.root.geometry("1460x900")
        self.root.minsize(1120, 720)
        self.root.configure(bg=BG)
        self.script_dir = Path(__file__).resolve().parent
        self.logo_path = self.find_logo()
        print(f"{APP_NAME}: Skriptordner: {self.script_dir}")
        print(f"{APP_NAME}: Logo-Datei: {self.logo_path if self.logo_path else 'nicht gefunden'}")
        self.logo_image = None
        self.current_items = {}  # product_id -> {product, quantity}
        self.selected_product_id = None
        self.selected_recipe_id = None
        self.selected_category_id = None
        self.setup_style()
        self.build_ui()
        self.refresh_all()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def find_logo(self):
        """Sucht das Logo neben dem Skript und in PyInstallers Ressourcenordner."""
        search_dirs = [self.script_dir]
        # Bei PyInstaller liegen --add-data-Dateien je nach Version in _MEIPASS
        # (bei aktuellen onedir-Builds oft im Unterordner _internal).
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            search_dirs.append(Path(bundle_dir).resolve())
        exe_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None
        if exe_dir:
            search_dirs.append(exe_dir)

        names = [
            "DxEinkaufsPlaner.png",
            "DxEinkaufsPlaner_Logo.png",
            "logo.png",
            "Glänzendes Einkaufsplaner-Logo mit Warenkorb(1).png",
            "Glänzendes Einkaufsplaner-Logo mit Warenkorb.png",
        ]
        checked = set()
        for folder in search_dirs:
            if not folder or not folder.is_dir():
                continue
            for name in names:
                candidate = folder / name
                if candidate in checked:
                    continue
                checked.add(candidate)
                if candidate.is_file():
                    return candidate
            # Fallback auf ein eindeutig benanntes Einkaufsplaner-/Warenkorb-Logo.
            try:
                for candidate in sorted(folder.glob("*.png")):
                    normalized = candidate.name.casefold()
                    if "logo" in normalized and ("einkauf" in normalized or "warenkorb" in normalized):
                        return candidate
                    if "einkaufsplaner" in normalized and candidate.is_file():
                        return candidate
            except OSError:
                pass
        return None

    def load_logo_widget(self, parent):
        """Lädt das PNG über Pillow/ImageTk, kompatibel mit normalen Tkinter-Labels."""
        if not self.logo_path:
            print(f"{APP_NAME}: Kein Logo gefunden. Gesuchte Ordner: {self.script_dir}")
            tk.Label(parent, text="Dx", bg=parent.cget("bg"), fg=ORANGE,
                     font=("Segoe UI", 30, "bold")).pack(pady=(20, 12))
            return
        try:
            from PIL import Image, ImageTk
            with Image.open(self.logo_path) as source:
                image = source.convert("RGBA")
                image.thumbnail((168, 168), Image.Resampling.LANCZOS)
            # Wichtig: Ein CTkImage darf nicht an ein normales tk.Label übergeben
            # werden. PhotoImage ist mit tk.Label kompatibel und hält die Referenz.
            self.logo_image = ImageTk.PhotoImage(image)
            tk.Label(parent, image=self.logo_image, bg=parent.cget("bg"), bd=0,
                     highlightthickness=0).pack(pady=(12, 14))
            print(f"{APP_NAME}: Logo geladen: {self.logo_path}")
        except Exception as exc:
            print(f"{APP_NAME}: Logo konnte nicht geladen werden ({self.logo_path}): {exc}")
            tk.Label(parent, text="Dx", bg=parent.cget("bg"), fg=ORANGE,
                     font=("Segoe UI", 30, "bold")).pack(pady=(20, 12))

    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#20242a", foreground=MUTED,
                        padding=(22, 13), font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", ORANGE), ("active", "#30363d")],
                  foreground=[("selected", "#101214"), ("active", FG)])
        style.configure("Treeview", background=BG, fieldbackground=BG, foreground=FG,
                        rowheight=32, borderwidth=0, relief="flat", font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#15181b", foreground="#aeb4bc",
                        relief="flat", font=("Segoe UI", 9, "bold"), padding=(10, 9))
        style.map("Treeview", background=[("selected", "#3a2416")],
                  foreground=[("selected", "#ffffff")])
        style.configure("Vertical.TScrollbar", background=PANEL_ALT, troughcolor=BG,
                        bordercolor=BG, arrowcolor=MUTED, relief="flat", width=12)
        style.configure("Horizontal.TScrollbar", background=PANEL_ALT, troughcolor=BG,
                        bordercolor=BG, arrowcolor=MUTED, relief="flat", width=12)
        style.configure("TCombobox", fieldbackground=PANEL_ALT, background=PANEL_ALT,
                        foreground=FG, arrowcolor=ORANGE, padding=8)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL_ALT)],
                  foreground=[("readonly", FG)])
        style.configure("TEntry", fieldbackground=PANEL_ALT, foreground=FG, padding=8)
        style.configure("TSpinbox", fieldbackground=PANEL_ALT, foreground=FG, padding=8)

    def button(self, parent, text, command, primary=False, width=None):
        if ctk is not None:
            return ctk.CTkButton(
                parent, text=text, command=command,
                fg_color=ORANGE if primary else "#252a30",
                hover_color="#e66e00" if primary else "#343b43",
                text_color="#101214" if primary else FG,
                border_color=BORDER, border_width=0 if primary else 1,
                corner_radius=10, height=38,
                font=("Segoe UI", 10, "bold" if primary else "normal"),
                width=(width * 8 if width else 140),
            )
        return tk.Button(parent, text=text, command=command, bg=ORANGE if primary else PANEL_ALT,
                         fg="#111111" if primary else FG, activebackground=GOLD if primary else "#34383d",
                         activeforeground="#111111" if primary else FG, relief="flat", bd=0,
                         font=("Segoe UI", 10, "bold" if primary else "normal"), padx=14, pady=9,
                         cursor="hand2", width=width)

    def label(self, parent, text, size=10, color=FG, bold=False):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"))

    def entry(self, parent, variable=None, width=24):
        if ctk is not None:
            return ctk.CTkEntry(
                parent, textvariable=variable, width=max(90, width * 9), height=38,
                fg_color=PANEL_ALT, text_color=FG, border_color=BORDER,
                border_width=1, corner_radius=10,
                placeholder_text_color=MUTED, font=("Segoe UI", 10),
            )
        return tk.Entry(parent, textvariable=variable, width=width, bg=PANEL_ALT, fg=FG,
                        insertbackground=FG, relief="flat", highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=ORANGE, font=("Segoe UI", 10))

    def section(self, parent, title, subtitle=None):
        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x", pady=(0, 14))
        title_row = tk.Frame(head, bg=BG)
        title_row.pack(fill="x", anchor="w")
        tk.Frame(title_row, bg=ORANGE, width=4, height=25).pack(side="left", padx=(0, 10))
        self.label(title_row, title, 17, FG, True).pack(side="left", anchor="w")
        if subtitle:
            self.label(head, subtitle, 10, MUTED).pack(anchor="w", pady=(3, 0))
        return head

    def build_ui(self):
        # Schlankes App-Shell-Layout: Kopfzeile, linke Navigation und Inhaltsfläche.
        header = tk.Frame(self.root, bg=BG, height=68)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        brand = tk.Frame(header, bg=BG)
        brand.pack(side="left", fill="y", padx=(24, 0))
        tk.Label(brand, text="EINKAUFSPLANUNG", bg=BG, fg=FG,
                 font=("Segoe UI", 15, "bold")).pack(side="left", padx=(0, 12))
        tk.Frame(brand, bg=ORANGE, width=3, height=22).pack(side="left", padx=(0, 12))
        tk.Label(brand, text="Einfach planen. Preise im Blick behalten.", bg=BG, fg="#8a8580",
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Label(header, text="PLANEN  /  VERWALTEN  /  SPAREN", bg=BG, fg="#777067",
                 font=("Segoe UI", 8, "bold")).pack(side="right", padx=26)
        tk.Frame(self.root, bg=ORANGE, height=2).pack(fill="x", side="top")

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)
        self.sidebar = tk.Frame(body, bg=BG, width=204)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self.load_logo_widget(self.sidebar)
        tk.Frame(self.sidebar, bg="#332719", height=1).pack(fill="x", padx=18, pady=(0, 18))
        tk.Label(self.sidebar, text="ARBEITSBEREICH", bg=BG, fg="#777067",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=20, pady=(0, 12))

        self.content_area = tk.Frame(body, bg=BG)
        self.content_area.pack(side="left", fill="both", expand=True)
        self.home_tab = tk.Frame(self.content_area, bg=BG, padx=25, pady=24)
        self.shopping_tab = tk.Frame(self.content_area, bg=BG, padx=25, pady=24)
        self.recipes_tab = tk.Frame(self.content_area, bg=BG, padx=25, pady=24)
        self.catalog_tab = tk.Frame(self.content_area, bg=BG, padx=25, pady=24)
        self.pages = [self.home_tab, self.shopping_tab, self.recipes_tab, self.catalog_tab]
        for page in self.pages:
            page.place(relx=0, rely=0, relwidth=1, relheight=1)

        nav_items = [
            ("⌂", "Übersicht", 0),
            ("＋", "Einkaufszettel", 1),
            ("≡", "Rezepte", 2),
            ("▦", "Preiskatalog", 3),
        ]
        self.nav_buttons = {}
        for symbol, title, index in nav_items:
            if ctk is not None:
                btn = ctk.CTkButton(
                    self.sidebar, text=f"{symbol}    {title}", anchor="w", height=42,
                    corner_radius=9, border_width=0, font=("Segoe UI", 11),
                    fg_color="transparent", hover_color="#1a1d21", text_color="#aeb4bc",
                    command=lambda i=index: self.go_tab(i),
                )
            else:
                btn = tk.Button(
                    self.sidebar, text=f"{symbol}    {title}", anchor="w", height=2,
                    bg="#0e1012", fg="#aeb4bc", activebackground="#1a1d21",
                    activeforeground=FG, relief="flat", bd=0, padx=15,
                    font=("Segoe UI", 10), cursor="hand2", command=lambda i=index: self.go_tab(i),
                )
            btn.pack(fill="x", padx=11, pady=3)
            self.nav_buttons[index] = btn

        tk.Frame(self.sidebar, bg="#332719", height=1).pack(fill="x", padx=18, pady=(20, 14))
        tk.Label(self.sidebar, text="Dx  ·  VERSION 1.0", bg=BG, fg="#62594d",
                 font=("Segoe UI", 8)).pack(side="bottom", anchor="w", padx=20, pady=18)

        self.build_home()
        self.build_shopping()
        self.build_recipes()
        self.build_catalog()
        self.status_var = tk.StringVar(value="Bereit")
        status_bar = tk.Frame(self.root, bg=BG, height=27)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)
        tk.Label(status_bar, textvariable=self.status_var, anchor="w", bg=BG, fg="#777f88",
                 padx=20, font=("Segoe UI", 8)).pack(fill="both", expand=True)
        self.go_tab(0)

    def build_home(self):
        self.section(self.home_tab, "Dein Überblick", "Deine aktuelle Einkaufsliste und die wichtigsten Aktionen auf einen Blick.")
        cards = tk.Frame(self.home_tab, bg=BG)
        cards.pack(fill="x", pady=(2, 18))
        self.home_product_count = self.make_stat(cards, "PRODUKTE IM KATALOG", "0", 0)
        self.home_recipe_count = self.make_stat(cards, "GESPEICHERTE REZEPTE", "0", 1)
        self.home_list_count = self.make_stat(cards, "GESPEICHERTE LISTEN", "0", 2)
        self.home_total = self.make_stat(cards, "AKTUELLER EINKAUF", "0,00 €", 3)

        actionrow = tk.Frame(self.home_tab, bg=BG)
        actionrow.pack(fill="x", pady=(0, 16))
        self.button(actionrow, "+ Produkt hinzufügen", lambda: self.go_tab(3), True).pack(side="left", padx=(0, 8))
        self.button(actionrow, "Einkauf bearbeiten", lambda: self.go_tab(1)).pack(side="left", padx=8)
        self.button(actionrow, "Rezept auswählen", lambda: self.go_tab(2)).pack(side="left", padx=8)
        self.button(actionrow, "PNG exportieren", self.export_png, True).pack(side="right")

        self.section(self.home_tab, "Aktuelle Einkaufsliste", "Die Tabelle wird automatisch aktualisiert, sobald du Produkte hinzufügst oder Mengen änderst.")
        cols = ("name", "qty", "unit", "price", "total")
        self.home_tree = ttk.Treeview(self.home_tab, columns=cols, show="headings", height=12)
        for col, title, width, anchor in [("name", "Produkt", 440, "w"), ("qty", "Menge", 120, "e"), ("unit", "Einheit", 120, "w"), ("price", "Einzelpreis", 150, "e"), ("total", "Gesamtpreis", 160, "e")]:
            self.home_tree.heading(col, text=title)
            self.home_tree.column(col, width=width, anchor=anchor)
        self.home_tree.pack(fill="both", expand=True)
        bottom = tk.Frame(self.home_tab, bg=BG)
        bottom.pack(fill="x", pady=(12, 0))
        self.home_total_label = self.label(bottom, "Gesamtsumme: 0,00 €", 15, ORANGE, True)
        self.home_total_label.pack(side="left")
        self.button(bottom, "Einkaufsliste speichern", self.save_shopping_list).pack(side="right")

    def make_stat(self, parent, title, value, column):
        if ctk is not None:
            card = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=14, border_width=1, border_color=BORDER)
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 10, 0))
            card.configure(width=210, height=86)
            card.grid_propagate(False)
        else:
            card = tk.Frame(parent, bg=PANEL, padx=16, pady=14, highlightthickness=1, highlightbackground=BORDER)
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 10, 0))
        parent.grid_columnconfigure(column, weight=1)
        tk.Label(card, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(13, 0))
        var = tk.StringVar(value=value)
        tk.Label(card, textvariable=var, bg=PANEL, fg=ORANGE, font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=16, pady=(3, 8))
        return var

    def build_shopping(self):
        self.section(self.shopping_tab, "Einkaufszettel", "Produktnamen werden während der Eingabe vorgeschlagen. Preise stammen aus dem Preiskatalog.")
        top = tk.Frame(self.shopping_tab, bg=BG)
        top.pack(fill="x", pady=(0, 10))
        self.label(top, "Produkt suchen", color=GOLD, bold=True).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.search_var = tk.StringVar()
        self.search_entry = self.entry(top, self.search_var, 34)
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(5, 0))
        self.search_entry.bind("<KeyRelease>", self.on_search_change)
        self.search_entry.bind("<Down>", self.focus_suggestions)
        self.search_entry.bind("<Return>", self.add_from_search)
        self.label(top, "Menge", color=GOLD, bold=True).grid(row=0, column=1, sticky="w", padx=(0, 8))
        self.qty_var = tk.StringVar(value="1")
        self.entry(top, self.qty_var, 10).grid(row=1, column=1, sticky="w", padx=(0, 8), pady=(5, 0))
        self.button(top, "Hinzufügen", self.add_from_search, True).grid(row=1, column=2, padx=(0, 8), pady=(5, 0))
        self.button(top, "Manuelles Produkt", self.add_manual_product).grid(row=1, column=3, pady=(5, 0))
        top.grid_columnconfigure(0, weight=1)

        suggest_frame = tk.Frame(self.shopping_tab, bg=BG)
        suggest_frame.pack(fill="x", pady=(0, 10))
        self.suggest_list = tk.Listbox(suggest_frame, height=3, bg=PANEL, fg=FG, selectbackground="#65401f", selectforeground="white", relief="flat", highlightthickness=1, highlightbackground=BORDER, font=("Segoe UI", 10), activestyle="none")
        self.suggest_list.pack(fill="x")
        self.suggest_list.bind("<Double-Button-1>", self.select_suggestion)
        self.suggest_list.bind("<Return>", self.select_suggestion)

        # Die letzte Spalte enthält pro Produkt eine direkt anklickbare Löschaktion.
        cols = ("name", "qty", "unit", "price", "total", "delete")
        self.shopping_tree = ttk.Treeview(self.shopping_tab, columns=cols, show="headings", height=14, selectmode="browse")
        for col, title, width, anchor in [("name", "Produkt", 390, "w"), ("qty", "Menge", 90, "e"), ("unit", "Einheit", 100, "w"), ("price", "Einzelpreis", 125, "e"), ("total", "Gesamtpreis", 135, "e"), ("delete", "Aktion", 105, "center")]:
            self.shopping_tree.heading(col, text=title)
            self.shopping_tree.column(col, width=width, anchor=anchor, stretch=(col == "name"))
        self.shopping_tree.tag_configure("delete_action", foreground=ORANGE)
        self.shopping_tree.pack(fill="both", expand=True)
        self.shopping_tree.bind("<Double-Button-1>", self.on_shopping_tree_double_click)
        self.shopping_tree.bind("<Button-1>", self.on_shopping_tree_click)
        # Eintrag direkt über die Entf-Taste entfernen; die Auswahl bleibt eindeutig.
        self.shopping_tree.bind("<Delete>", self.remove_shopping_item)
        self.shopping_tree.bind("<BackSpace>", self.remove_shopping_item)

        bottom = tk.Frame(self.shopping_tab, bg=BG)
        bottom.pack(fill="x", pady=(12, 0))
        self.shopping_total_var = tk.StringVar(value="Gesamtsumme: 0,00 €")
        self.label(bottom, "Doppelklick auf die Menge eines Produkts, um sie zu ändern.", color=MUTED).pack(side="left")
        tk.Label(bottom, textvariable=self.shopping_total_var, bg=BG, fg=ORANGE, font=("Segoe UI", 15, "bold")).pack(side="right", padx=10)
        self.button(bottom, "Entfernen", self.remove_shopping_item).pack(side="right", padx=5)
        self.button(bottom, "Liste leeren", self.clear_shopping).pack(side="right", padx=5)
        self.button(bottom, "Liste speichern", self.save_shopping_list, True).pack(side="right", padx=5)
        self.button(bottom, "Gespeicherte Listen", self.load_shopping_list).pack(side="right", padx=5)

    def build_recipes(self):
        self.section(self.recipes_tab, "Rezeptverwaltung", "Rezepte und Zutaten bleiben in der lokalen Datenbank gespeichert.")
        main = tk.Frame(self.recipes_tab, bg=BG)
        main.pack(fill="both", expand=True)
        left = tk.Frame(main, bg=BG)
        left.pack(side="left", fill="y", padx=(0, 16))
        self.label(left, "Gespeicherte Rezepte", 11, GOLD, True).pack(anchor="w", pady=(0, 6))
        self.recipe_search_var = tk.StringVar()
        self.recipe_search_entry = self.entry(left, self.recipe_search_var, 28)
        self.recipe_search_entry.pack(fill="x", pady=(0, 8))
        self.recipe_search_entry.bind("<KeyRelease>", lambda _e: self.refresh_recipe_list())
        self.recipe_search_entry.bind("<Escape>", self.clear_recipe_search)
        self.recipe_search_entry.bind("<Return>", self.focus_first_recipe_result)
        self.recipe_list = tk.Listbox(left, width=32, bg=PANEL, fg=FG, selectbackground="#65401f", relief="flat", highlightthickness=1, highlightbackground=BORDER, font=("Segoe UI", 10), activestyle="none")
        self.recipe_list.pack(fill="y", expand=True)
        self.recipe_list.bind("<<ListboxSelect>>", self.on_recipe_select)
        leftbuttons = tk.Frame(left, bg=BG)
        leftbuttons.pack(fill="x", pady=8)
        self.button(leftbuttons, "+ Neu", self.new_recipe, True).pack(side="left", padx=(0, 5))
        self.button(leftbuttons, "Löschen", self.delete_recipe).pack(side="left")

        right = tk.Frame(main, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self.recipe_name_var = tk.StringVar()
        self.recipe_portions_var = tk.StringVar(value="1")
        self.label(right, "Rezeptname", color=GOLD, bold=True).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.entry(right, self.recipe_name_var, 35).grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(0, 12))
        self.label(right, "Portionen", color=GOLD, bold=True).grid(row=0, column=1, sticky="w", pady=(0, 5))
        self.entry(right, self.recipe_portions_var, 10).grid(row=1, column=1, sticky="w", pady=(0, 12))
        self.label(right, "Notizen / Zubereitung (optional)", color=GOLD, bold=True).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.recipe_notes = tk.Text(right, height=6, bg=PANEL_ALT, fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 10), wrap="word", highlightthickness=1, highlightbackground=BORDER)
        self.recipe_notes.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        self.label(right, "Zutat hinzufügen", color=GOLD, bold=True).grid(row=4, column=0, sticky="w", pady=(0, 5))
        self.ingredient_product_var = tk.StringVar()
        # Dieselbe Suchoberfläche wie im Einkaufszettel: Eingabefeld plus Vorschlagsliste.
        ingredient_search_frame = tk.Frame(right, bg=BG)
        ingredient_search_frame.grid(row=5, column=0, sticky="ew", padx=(0, 12), pady=(0, 12))
        self.ingredient_search_entry = self.entry(ingredient_search_frame, self.ingredient_product_var, 35)
        self.ingredient_search_entry.pack(fill="x")
        self.ingredient_search_entry.bind("<KeyRelease>", self.on_ingredient_search_change)
        self.ingredient_search_entry.bind("<Down>", self.focus_ingredient_suggestions)
        self.ingredient_search_entry.bind("<Return>", self.select_ingredient_suggestion)
        self.ingredient_suggest_list = tk.Listbox(ingredient_search_frame, height=3, bg=PANEL, fg=FG, selectbackground="#65401f", selectforeground="white", relief="flat", highlightthickness=1, highlightbackground=BORDER, font=("Segoe UI", 10), activestyle="none")
        # Vorschlagsliste nur bei einer aktiven Suche mit Treffern anzeigen.
        # So bleibt darunter kein leerer Bereich stehen.
        self.ingredient_suggest_list.bind("<Double-Button-1>", self.select_ingredient_suggestion)
        self.ingredient_suggest_list.bind("<Return>", self.select_ingredient_suggestion)
        self.label(right, "Menge", color=GOLD, bold=True).grid(row=4, column=1, sticky="w", pady=(0, 5))
        self.ingredient_qty_var = tk.StringVar(value="1")
        self.entry(right, self.ingredient_qty_var, 10).grid(row=5, column=1, sticky="w", pady=(0, 12))
        self.button(right, "Zutat hinzufügen", self.add_recipe_ingredient, True).grid(row=5, column=2, padx=(8, 0), pady=(0, 12))

        cols = ("product", "qty", "unit", "price", "total")
        self.recipe_tree = ttk.Treeview(right, columns=cols, show="headings", height=10)
        for col, title, width, anchor in [("product", "Zutat", 280, "w"), ("qty", "Menge", 100, "e"), ("unit", "Einheit", 100, "w"), ("price", "Einzelpreis", 130, "e"), ("total", "Kosten", 130, "e")]:
            self.recipe_tree.heading(col, text=title)
            self.recipe_tree.column(col, width=width, anchor=anchor)
        self.recipe_tree.grid(row=6, column=0, columnspan=3, sticky="nsew")
        self.recipe_tree.bind("<Delete>", self.remove_recipe_ingredient)
        self.recipe_tree.bind("<BackSpace>", self.remove_recipe_ingredient)
        right.grid_rowconfigure(6, weight=1)
        right.grid_columnconfigure(0, weight=1)
        controls = tk.Frame(right, bg=BG)
        controls.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.recipe_cost_var = tk.StringVar(value="Rezeptkosten: 0,00 €")
        tk.Label(controls, textvariable=self.recipe_cost_var, bg=BG, fg=ORANGE, font=("Segoe UI", 13, "bold")).pack(side="left")
        self.button(controls, "Zutat entfernen", self.remove_recipe_ingredient).pack(side="right", padx=5)
        self.button(controls, "Rezept speichern", self.save_recipe, True).pack(side="right", padx=5)
        self.button(controls, "Zum Einkaufszettel", self.add_recipe_to_shopping).pack(side="right", padx=5)
        self.recipe_ingredient_ids = {}

    def build_catalog(self):
        self.section(self.catalog_tab, "Preiskatalog", "Hier werden Produkte, Kategorien, Einheiten und aktuelle Preise zentral verwaltet.")
        main = tk.Frame(self.catalog_tab, bg=BG)
        main.pack(fill="both", expand=True)
        form = tk.Frame(main, bg=PANEL, padx=14, pady=14, highlightthickness=1, highlightbackground=BORDER)
        form.pack(side="left", fill="y", padx=(0, 16))
        self.label(form, "Produktname", color=GOLD, bold=True).pack(anchor="w", pady=(0, 5))
        self.product_name_var = tk.StringVar()
        self.product_name_entry = self.entry(form, self.product_name_var, 28)
        self.product_name_entry.pack(fill="x", pady=(0, 12))
        self.label(form, "Kategorie", color=GOLD, bold=True).pack(anchor="w", pady=(0, 5))
        self.product_category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(form, textvariable=self.product_category_var, state="readonly", width=26)
        self.category_combo.pack(fill="x", pady=(0, 12))
        self.label(form, "Einheit (z. B. Stück, kg, g, l)", color=GOLD, bold=True).pack(anchor="w", pady=(0, 5))
        self.product_unit_var = tk.StringVar(value="Stück")
        self.entry(form, self.product_unit_var, 28).pack(fill="x", pady=(0, 12))
        self.label(form, "Preis pro Einheit (€)", color=GOLD, bold=True).pack(anchor="w", pady=(0, 5))
        self.product_price_var = tk.StringVar(value="0,00")
        self.entry(form, self.product_price_var, 28).pack(fill="x", pady=(0, 14))
        self.button(form, "Produkt speichern", self.save_product, True).pack(fill="x", pady=3)
        self.button(form, "Formular leeren", self.clear_product_form).pack(fill="x", pady=3)
        self.button(form, "Produkt löschen", self.delete_product).pack(fill="x", pady=3)
        ttk.Separator(form, orient="horizontal").pack(fill="x", pady=12)
        self.button(form, "Kategorie hinzufügen", self.add_category).pack(fill="x", pady=3)
        self.button(form, "Google-Konto verbinden", self.connect_google_account).pack(fill="x", pady=3)
        self.button(form, "Kassenbon mit Gemini auslesen", self.import_receipt, True).pack(fill="x", pady=3)
        self.label(form, "Einmal im eigenen Edge-Profil bei Google anmelden. Selenium und Internetzugang werden benötigt.", 9, MUTED).pack(anchor="w", pady=(10, 0))

        right = tk.Frame(main, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        searchrow = tk.Frame(right, bg=BG)
        searchrow.pack(fill="x", pady=(0, 8))
        self.label(searchrow, "Suchen", color=GOLD, bold=True).pack(side="left", padx=(0, 8))
        self.catalog_search_var = tk.StringVar()
        search = self.entry(searchrow, self.catalog_search_var, 32)
        search.pack(side="left", fill="x", expand=True)
        search.bind("<KeyRelease>", lambda _e: self.refresh_catalog_tree())
        cols = ("name", "store", "category", "unit", "price", "comparison", "updated")
        self.catalog_tree = ttk.Treeview(right, columns=cols, show="headings", height=20, selectmode="extended")
        for col, title, width, anchor in [("name", "Produkt", 190, "w"), ("store", "Geschäft", 100, "w"), ("category", "Kategorie", 135, "w"), ("unit", "Einheit", 70, "w"), ("price", "Aktueller Preis", 100, "e"), ("comparison", "Preisvergleich je Geschäft", 230, "w"), ("updated", "Aktualisiert", 120, "w")]:
            self.catalog_tree.heading(col, text=title)
            self.catalog_tree.column(col, width=width, anchor=anchor)
        self.catalog_tree.pack(fill="both", expand=True)
        self.catalog_tree.bind("<<TreeviewSelect>>", self.on_product_select)
        self.catalog_tree.bind("<Double-Button-1>", self.on_product_select)

    # ---------- Refresh and shared helpers ----------
    def go_tab(self, index):
        if not hasattr(self, "pages") or index < 0 or index >= len(self.pages):
            return
        self.pages[index].tkraise()
        for nav_index, button in self.nav_buttons.items():
            active = nav_index == index
            if ctk is not None and isinstance(button, ctk.CTkButton):
                button.configure(
                    fg_color="#24170f" if active else "transparent",
                    text_color=ORANGE if active else "#aeb4bc",
                    border_width=1 if active else 0,
                    border_color="#4b2a14" if active else "#0e1012",
                    font=("Segoe UI", 11, "bold" if active else "normal"),
                )
            else:
                button.configure(
                    bg="#24170f" if active else "#0e1012",
                    fg=ORANGE if active else "#aeb4bc",
                    font=("Segoe UI", 10, "bold" if active else "normal"),
                )

    def refresh_all(self):
        self.refresh_categories()
        self.refresh_catalog_tree()
        self.refresh_product_choices()
        self.refresh_recipe_list()
        self.refresh_shopping_tree()
        self.refresh_home()

    def refresh_categories(self):
        cats = self.db.rows("SELECT id, name FROM categories ORDER BY name COLLATE NOCASE")
        self.categories_by_name = {r["name"]: r["id"] for r in cats}
        self.category_combo["values"] = [r["name"] for r in cats]
        if self.product_category_var.get() not in self.categories_by_name:
            self.product_category_var.set(cats[0]["name"] if cats else "")

    def refresh_product_choices(self):
        products = self.db.rows("SELECT id, name, unit, price FROM products ORDER BY name COLLATE NOCASE")
        self.products_by_display = {f"{p['name']} — {money(p['price'])}/{p['unit']}": p['id'] for p in products}
        self.all_ingredient_displays = list(self.products_by_display.keys())
        self.products_by_id = {p["id"]: p for p in products}
        if hasattr(self, "ingredient_suggest_list"):
            self.on_ingredient_search_change()

    def on_ingredient_search_change(self, _event=None):
        """Filtert Zutaten wie die Vorschlagsliste im Einkaufszettel."""
        term = self.ingredient_product_var.get().strip()
        self.ingredient_suggest_list.delete(0, "end")
        if not term:
            self.ingredient_suggest_list.pack_forget()
            return
        rows = self.db.rows(
            "SELECT id, name, unit, price FROM products WHERE name LIKE ? ORDER BY CASE WHEN name LIKE ? THEN 0 ELSE 1 END, name COLLATE NOCASE LIMIT 8",
            (f"%{term}%", f"{term}%")
        )
        for p in rows:
            self.ingredient_suggest_list.insert("end", f"{p['name']}  ·  {money(p['price'])}/{p['unit']}")
        if rows:
            if not self.ingredient_suggest_list.winfo_manager():
                self.ingredient_suggest_list.pack(fill="x", pady=(4, 0))
            self.ingredient_suggest_list.selection_clear(0, "end")
            self.ingredient_suggest_list.selection_set(0)
        else:
            self.ingredient_suggest_list.pack_forget()

    def focus_ingredient_suggestions(self, _event=None):
        if self.ingredient_suggest_list.size():
            self.ingredient_suggest_list.focus_set()
            self.ingredient_suggest_list.selection_clear(0, "end")
            self.ingredient_suggest_list.selection_set(0)
        return "break"

    def selected_ingredient_suggestion_product(self):
        sel = self.ingredient_suggest_list.curselection()
        if not sel:
            return None
        display = self.ingredient_suggest_list.get(sel[0])
        name = display.split("  ·  ", 1)[0]
        return self.db.one("SELECT * FROM products WHERE name=? COLLATE NOCASE", (name,))

    def select_ingredient_suggestion(self, _event=None):
        product = self.selected_ingredient_suggestion_product()
        if product:
            display = next((d for d, pid in self.products_by_display.items() if pid == product["id"]), product["name"])
            self.ingredient_product_var.set(display)
            self.ingredient_suggest_list.delete(0, "end")
            self.ingredient_search_entry.focus_set()
        return "break"

    def refresh_catalog_tree(self):
        if not hasattr(self, "catalog_tree"):
            return
        for item in self.catalog_tree.get_children():
            self.catalog_tree.delete(item)
        term = self.catalog_search_var.get().strip() if hasattr(self, "catalog_search_var") else ""
        rows = self.db.rows("""SELECT p.*, c.name AS category FROM products p LEFT JOIN categories c ON c.id=p.category_id
                               WHERE p.name LIKE ? OR COALESCE(c.name,'') LIKE ? ORDER BY p.name COLLATE NOCASE""", (f"%{term}%", f"%{term}%"))
        for p in rows:
            price_rows = self.db.rows("SELECT store, price FROM product_store_prices WHERE product_id=? ORDER BY price ASC, store COLLATE NOCASE", (p["id"],))
            comparison = " | ".join(f"{r['store']}: {money(r['price'])}" for r in price_rows)
            self.catalog_tree.insert("", "end", iid=str(p["id"]), values=(p["name"], p["store"] or "—", p["category"] or "Ohne Kategorie", p["unit"], money(p["price"]), comparison or "Noch keine Vergleichspreise", p["updated_at"]))

    def refresh_recipe_list(self, select_id=None):
        if not hasattr(self, "recipe_list"):
            return
        self.recipe_list.delete(0, "end")
        self.recipe_ids = []
        term = self.recipe_search_var.get().strip().casefold() if hasattr(self, "recipe_search_var") else ""
        rows = self.db.rows("SELECT id, name FROM recipes ORDER BY name COLLATE NOCASE")
        for r in rows:
            if term and term not in r["name"].casefold():
                continue
            self.recipe_list.insert("end", r["name"])
            self.recipe_ids.append(r["id"])
        if select_id in self.recipe_ids:
            index = self.recipe_ids.index(select_id)
            self.recipe_list.selection_clear(0, "end")
            self.recipe_list.selection_set(index)
            self.recipe_list.activate(index)
            self.load_recipe(select_id)

    def clear_recipe_search(self, _event=None):
        self.recipe_search_var.set("")
        self.refresh_recipe_list()
        self.recipe_search_entry.focus_set()
        return "break"

    def focus_first_recipe_result(self, _event=None):
        if self.recipe_ids:
            self.recipe_list.selection_clear(0, "end")
            self.recipe_list.selection_set(0)
            self.recipe_list.activate(0)
            self.load_recipe(self.recipe_ids[0])
        return "break"

    def refresh_shopping_tree(self):
        if not hasattr(self, "shopping_tree"):
            return
        for tree in (self.shopping_tree, self.home_tree):
            for item in tree.get_children():
                tree.delete(item)
        total = 0.0
        for pid, data in sorted(self.current_items.items(), key=lambda kv: kv[1]["product"]["name"].lower()):
            p = data["product"]
            qty = data["quantity"]
            line = qty * float(p["price"])
            total += line
            values = (p["name"], self.format_qty(qty), p["unit"], money(p["price"]), money(line))
            self.shopping_tree.insert("", "end", iid=str(pid), values=values + ("✕ Löschen",), tags=("delete_action",))
            self.home_tree.insert("", "end", iid=str(pid), values=values)
        self.shopping_total_var.set(f"Gesamtsumme: {money(total)}")
        self.home_total_label.config(text=f"Gesamtsumme: {money(total)}")
        self.home_total.set(money(total))
        self.refresh_home_stats()

    def refresh_home_stats(self):
        self.home_product_count.set(str(self.db.one("SELECT COUNT(*) n FROM products")["n"]))
        self.home_recipe_count.set(str(self.db.one("SELECT COUNT(*) n FROM recipes")["n"]))
        self.home_list_count.set(str(self.db.one("SELECT COUNT(*) n FROM saved_lists")["n"]))

    def refresh_home(self):
        self.refresh_shopping_tree()

    @staticmethod
    def format_qty(qty):
        return str(int(qty)) if float(qty).is_integer() else str(qty).replace(".", ",")

    def status(self, text):
        self.status_var.set(text)

    # ---------- Shopping list ----------
    def on_search_change(self, _event=None):
        term = self.search_var.get().strip()
        self.suggest_list.delete(0, "end")
        if not term:
            return
        rows = self.db.rows("SELECT id, name, unit, price FROM products WHERE name LIKE ? ORDER BY CASE WHEN name LIKE ? THEN 0 ELSE 1 END, name COLLATE NOCASE LIMIT 8", (f"%{term}%", f"{term}%"))
        for p in rows:
            self.suggest_list.insert("end", f"{p['name']}  ·  {money(p['price'])}/{p['unit']}")
        if rows:
            self.suggest_list.selection_clear(0, "end")
            self.suggest_list.selection_set(0)

    def focus_suggestions(self, _event=None):
        if self.suggest_list.size():
            self.suggest_list.focus_set()
            self.suggest_list.selection_clear(0, "end")
            self.suggest_list.selection_set(0)
        return "break"

    def selected_suggestion_product(self):
        sel = self.suggest_list.curselection()
        if not sel:
            return None
        display = self.suggest_list.get(sel[0])
        name = display.split("  ·  ", 1)[0]
        return self.db.one("SELECT * FROM products WHERE name=? COLLATE NOCASE", (name,))

    def select_suggestion(self, _event=None):
        p = self.selected_suggestion_product()
        if p:
            self.search_var.set(p["name"])
            self.suggest_list.delete(0, "end")
            self.add_product_to_shopping(p["id"], self.qty_var.get())
        return "break"

    def add_from_search(self, _event=None):
        p = self.selected_suggestion_product()
        if p is None:
            name = self.search_var.get().strip()
            if name:
                p = self.db.one("SELECT * FROM products WHERE name=? COLLATE NOCASE", (name,))
        if not p:
            if self.search_var.get().strip():
                messagebox.showinfo("Produkt nicht gefunden", "Wähle einen Vorschlag aus oder füge das Produkt zuerst im Preiskatalog hinzu.")
            return "break"
        self.add_product_to_shopping(p["id"], self.qty_var.get())
        self.search_var.set("")
        self.suggest_list.delete(0, "end")
        self.search_entry.focus_set()
        return "break"

    def add_product_to_shopping(self, product_id, qty_value):
        try:
            qty = parse_number(qty_value, "Menge")
            if qty <= 0:
                raise ValueError("Die Menge muss größer als 0 sein.")
        except ValueError as e:
            messagebox.showerror("Ungültige Menge", str(e))
            return
        p = self.db.one("SELECT * FROM products WHERE id=?", (product_id,))
        if not p:
            return
        if product_id in self.current_items:
            self.current_items[product_id]["quantity"] += qty
        else:
            self.current_items[product_id] = {"product": dict(p), "quantity": qty}
        self.refresh_shopping_tree()
        # Für das nächste Produkt ist die Standardmenge wieder 1.
        self.qty_var.set("1")
        self.status(f"{p['name']} hinzugefügt.")

    def add_manual_product(self):
        name = simpledialog.askstring("Manuelles Produkt", "Produktname:", parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        p = self.db.one("SELECT * FROM products WHERE name=? COLLATE NOCASE", (name,))
        if p:
            self.add_product_to_shopping(p["id"], self.qty_var.get())
            return
        messagebox.showinfo("Produkt noch nicht im Katalog", "Das Produkt muss zuerst mit Kategorie, Einheit und Preis im Preiskatalog angelegt werden.")
        self.product_name_var.set(name)
        self.go_tab(3)

    def on_shopping_tree_click(self, event):
        """Entfernt gezielt den angeklickten Eintrag über dessen Löschspalte."""
        row_id = self.shopping_tree.identify_row(event.y)
        column = self.shopping_tree.identify_column(event.x)
        if row_id and column == "#6":
            self.shopping_tree.selection_set(row_id)
            self.remove_shopping_item()
            return "break"
        return None

    def on_shopping_tree_double_click(self, event):
        """Doppelklick auf die Mengen-Spalte öffnet die Mengenbearbeitung."""
        if self.shopping_tree.identify_column(event.x) == "#2":
            self.shopping_tree.identify_row(event.y)
            return self.edit_shopping_quantity(event)
        return None

    def edit_shopping_quantity(self, _event=None):
        sel = self.shopping_tree.selection()
        if not sel:
            return
        pid = int(sel[0])
        current = self.current_items[pid]["quantity"]
        value = simpledialog.askstring("Menge ändern", "Neue Menge:", initialvalue=self.format_qty(current), parent=self.root)
        if value is None:
            return
        try:
            qty = parse_number(value, "Menge")
            if qty <= 0:
                raise ValueError("Die Menge muss größer als 0 sein.")
            self.current_items[pid]["quantity"] = qty
            self.refresh_shopping_tree()
        except ValueError as e:
            messagebox.showerror("Ungültige Menge", str(e))

    def remove_shopping_item(self, _event=None):
        sel = self.shopping_tree.selection()
        if not sel:
            messagebox.showinfo("Auswahl fehlt", "Bitte zuerst ein Produkt in der Einkaufsliste markieren.")
            return "break" if _event is not None else None

        # Auch temporäre Einträge aus gespeicherten Listen haben eine ID im aktuellen Warenkorb.
        product_id = int(sel[0])
        removed = self.current_items.pop(product_id, None)
        self.refresh_shopping_tree()
        self.shopping_tree.focus_set()
        if removed:
            self.status(f"{removed['product']['name']} von der Einkaufsliste entfernt.")
        return "break" if _event is not None else None

    def clear_shopping(self):
        if self.current_items and not messagebox.askyesno("Liste leeren", "Möchtest du die aktuelle Einkaufsliste wirklich leeren?"):
            return
        self.current_items.clear()
        self.refresh_shopping_tree()

    def add_recipe_to_shopping(self):
        sel = self.recipe_list.curselection()
        if not sel:
            messagebox.showinfo("Rezept auswählen", "Wähle links ein Rezept aus.")
            return
        recipe_id = self.recipe_ids[sel[0]]
        items = self.db.rows("SELECT p.*, ri.quantity FROM recipe_items ri JOIN products p ON p.id=ri.product_id WHERE ri.recipe_id=?", (recipe_id,))
        if not items:
            messagebox.showinfo("Keine Zutaten", "Dieses Rezept enthält noch keine Zutaten.")
            return
        for p in items:
            pid = p["id"]
            qty = float(p["quantity"])
            if pid in self.current_items:
                self.current_items[pid]["quantity"] += qty
            else:
                self.current_items[pid] = {"product": dict(p), "quantity": qty}
        self.refresh_shopping_tree()
        self.go_tab(1)
        self.status(f"Rezept „{self.db.one('SELECT name FROM recipes WHERE id=?', (recipe_id,))['name']}“ zur Einkaufsliste hinzugefügt.")

    def save_shopping_list(self):
        if not self.current_items:
            messagebox.showinfo("Leere Liste", "Die Einkaufsliste enthält keine Produkte.")
            return
        name = simpledialog.askstring("Einkaufsliste speichern", "Name der Einkaufsliste:", initialvalue=f"Einkauf {datetime.now().strftime('%d.%m.%Y')}", parent=self.root)
        if not name or not name.strip():
            return
        total = sum(d["quantity"] * float(d["product"]["price"]) for d in self.current_items.values())
        list_id = self.db.run("INSERT INTO saved_lists(name, created_at, total) VALUES (?, ?, ?)", (name.strip(), datetime.now().strftime("%Y-%m-%d %H:%M"), total))
        for data in self.current_items.values():
            p = data["product"]
            qty = data["quantity"]
            line = qty * float(p["price"])
            self.db.run("INSERT INTO saved_list_items(list_id, product_name, quantity, unit, unit_price, line_total) VALUES (?, ?, ?, ?, ?, ?)", (list_id, p["name"], qty, p["unit"], float(p["price"]), line))
        self.refresh_home_stats()
        self.status(f"Einkaufsliste „{name.strip()}“ gespeichert.")
        messagebox.showinfo("Gespeichert", f"Die Einkaufsliste wurde gespeichert. Gesamt: {money(total)}")

    def load_shopping_list(self):
        lists = self.db.rows("SELECT * FROM saved_lists ORDER BY id DESC")
        if not lists:
            messagebox.showinfo("Keine gespeicherten Listen", "Du hast noch keine Einkaufsliste gespeichert.")
            return
        win = tk.Toplevel(self.root)
        win.title("Gespeicherte Einkaufslisten")
        win.configure(bg=BG)
        win.geometry("680x440")
        tk.Label(win, text="Gespeicherte Einkaufslisten", bg=BG, fg=GOLD, font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=16, pady=14)
        tree = ttk.Treeview(win, columns=("name", "date", "total"), show="headings", height=12)
        for c, t, w in [("name", "Name", 300), ("date", "Gespeichert am", 180), ("total", "Gesamtsumme", 130)]:
            tree.heading(c, text=t); tree.column(c, width=w)
        tree.pack(fill="both", expand=True, padx=16)
        for r in lists:
            tree.insert("", "end", iid=str(r["id"]), values=(r["name"], r["created_at"], money(r["total"])))
        btns = tk.Frame(win, bg=BG); btns.pack(fill="x", padx=16, pady=12)
        def load():
            selection = tree.selection()
            if not selection: return
            list_id = int(selection[0])
            if self.current_items and not messagebox.askyesno("Liste laden", "Die aktuelle Liste wird ersetzt. Fortfahren?", parent=win): return
            self.current_items.clear()
            saved = self.db.rows("SELECT * FROM saved_list_items WHERE list_id=?", (list_id,))
            for item in saved:
                # Beim Laden wird ein vorhandenes Produkt mit aktuellem Katalogpreis verwendet.
                p = self.db.one("SELECT * FROM products WHERE name=? COLLATE NOCASE", (item["product_name"],))
                if p:
                    self.current_items[p["id"]] = {"product": dict(p), "quantity": float(item["quantity"])}
                else:
                    # Produkt wurde aus dem Katalog entfernt: als temporärer Eintrag erhalten.
                    fake_id = -item["id"]
                    self.current_items[fake_id] = {"product": {"id": fake_id, "name": item["product_name"], "unit": item["unit"], "price": item["unit_price"]}, "quantity": float(item["quantity"])}
            self.refresh_shopping_tree(); self.go_tab(1); win.destroy()
            self.status("Gespeicherte Einkaufsliste geladen.")
        def delete_saved():
            selection = tree.selection()
            if not selection: return
            if messagebox.askyesno("Gespeicherte Liste löschen", "Diese gespeicherte Liste löschen?", parent=win):
                self.db.run("DELETE FROM saved_lists WHERE id=?", (int(selection[0]),))
                tree.delete(selection[0]); self.refresh_home_stats()
        self.button(btns, "Laden", load, True).pack(side="left")
        self.button(btns, "Löschen", delete_saved).pack(side="left", padx=8)
        self.button(btns, "Schließen", win.destroy).pack(side="right")

    def export_png(self):
        if not self.current_items:
            messagebox.showinfo("Nichts zu exportieren", "Die aktuelle Einkaufsliste ist leer.")
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Einkaufsliste als PNG speichern", defaultextension=".png", filetypes=[("PNG-Bild", "*.png")], initialfile=f"Einkaufsliste_{datetime.now().strftime('%Y-%m-%d')}.png")
        if not path:
            return
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            messagebox.showerror("Pillow fehlt", "Für den PNG-Export installiere bitte Pillow mit: python -m pip install Pillow")
            return
        rows = sorted(self.current_items.values(), key=lambda d: d["product"]["name"].lower())
        width = 1200
        margin = 55
        row_h = 48
        height = 250 + len(rows) * row_h + 95
        image = Image.new("RGB", (width, height), "#111214")
        draw = ImageDraw.Draw(image)
        try:
            font_path = "C:/Windows/Fonts/segoeui.ttf"
            bold_path = "C:/Windows/Fonts/segoeuib.ttf"
            font = ImageFont.truetype(font_path, 24)
            small = ImageFont.truetype(font_path, 19)
            bold = ImageFont.truetype(bold_path, 34)
            headfont = ImageFont.truetype(bold_path, 20)
        except OSError:
            font = ImageFont.load_default(); small = font; bold = font; headfont = font
        draw.rectangle((0, 0, width, 12), fill=ORANGE)
        draw.text((margin, 36), "Dx", fill=ORANGE, font=bold)
        draw.text((115, 39), "EinkaufsPlaner", fill="#f2f2f2", font=bold)
        draw.text((margin, 105), "EINKAUFSLISTE", fill="#d6a84f", font=headfont)
        draw.text((margin, 140), datetime.now().strftime("Erstellt am %d.%m.%Y um %H:%M"), fill="#a7abb1", font=small)
        y = 200
        draw.rounded_rectangle((margin, y, width-margin, y+42), radius=7, fill="#24272b")
        draw.text((margin+14, y+8), "PRODUKT", fill="#d6a84f", font=headfont)
        draw.text((690, y+8), "MENGE", fill="#d6a84f", font=headfont)
        draw.text((830, y+8), "EINZELPREIS", fill="#d6a84f", font=headfont)
        draw.text((1010, y+8), "GESAMT", fill="#d6a84f", font=headfont)
        y += 52
        total = 0.0
        for idx, data in enumerate(rows):
            p = data["product"]; qty = float(data["quantity"]); price = float(p["price"]); line = qty * price; total += line
            if idx % 2 == 0:
                draw.rounded_rectangle((margin, y, width-margin, y+row_h-3), radius=5, fill="#1b1d20")
            name = p["name"]
            if draw.textlength(name, font=font) > 520:
                while name and draw.textlength(name + "…", font=font) > 520: name = name[:-1]
                name += "…"
            draw.text((margin+14, y+9), name, fill="#f2f2f2", font=font)
            draw.text((690, y+10), f"{self.format_qty(qty)} {p['unit']}", fill="#f2f2f2", font=small)
            draw.text((830, y+10), money(price), fill="#f2f2f2", font=small)
            draw.text((1010, y+10), money(line), fill="#f2f2f2", font=small)
            y += row_h
        y += 18
        draw.line((margin, y, width-margin, y), fill=ORANGE, width=3)
        draw.text((margin, y+18), "GESAMTSUMME", fill="#f2f2f2", font=headfont)
        draw.text((900, y+13), money(total), fill=ORANGE, font=bold)
        draw.text((margin, height-35), "DxEinkaufsPlaner · Lokale Einkaufsliste", fill="#777d85", font=small)
        image.save(path, "PNG")
        self.status(f"PNG exportiert: {path}")
        messagebox.showinfo("Export abgeschlossen", f"Die Einkaufsliste wurde als PNG gespeichert:\n{path}")

    # ---------- Catalog ----------
    def clear_product_form(self):
        self.selected_product_id = None
        self.product_name_var.set("")
        self.product_unit_var.set("Stück")
        self.product_price_var.set("0,00")
        self.refresh_categories()
        self.catalog_tree.selection_remove(self.catalog_tree.selection())

    def on_product_select(self, _event=None):
        sel = self.catalog_tree.selection()
        if not sel:
            return
        pid = int(sel[0])
        p = self.db.one("SELECT p.*, c.name category FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE p.id=?", (pid,))
        if not p:
            return
        self.selected_product_id = pid
        self.product_name_var.set(p["name"])
        self.product_category_var.set(p["category"] or "")
        self.product_unit_var.set(p["unit"])
        self.product_price_var.set(str(p["price"]).replace(".", ","))

    def save_product(self):
        name = self.product_name_var.get().strip()
        unit = self.product_unit_var.get().strip() or "Stück"
        if not name:
            messagebox.showerror("Produktname fehlt", "Bitte einen Produktnamen eingeben.")
            return
        try:
            price = parse_number(self.product_price_var.get(), "Preis")
        except ValueError as e:
            messagebox.showerror("Ungültiger Preis", str(e)); return
        category_id = self.categories_by_name.get(self.product_category_var.get())
        existing = self.db.one("SELECT id FROM products WHERE name=? COLLATE NOCASE", (name,))
        try:
            if self.selected_product_id:
                # Umbenennen möglich; Konflikte mit anderem Produkt werden von SQLite abgefangen.
                self.db.run("UPDATE products SET name=?, category_id=?, unit=?, price=?, updated_at=? WHERE id=?", (name, category_id, unit, price, datetime.now().strftime("%Y-%m-%d %H:%M"), self.selected_product_id))
                pid = self.selected_product_id
            elif existing:
                # Produkt existiert bereits: aktuellen Preis und Angaben aktualisieren.
                pid = existing["id"]
                self.db.run("UPDATE products SET category_id=?, unit=?, price=?, updated_at=? WHERE id=?", (category_id, unit, price, datetime.now().strftime("%Y-%m-%d %H:%M"), pid))
            else:
                pid = self.db.run("INSERT INTO products(name, category_id, unit, price, updated_at) VALUES (?, ?, ?, ?, ?)", (name, category_id, unit, price, datetime.now().strftime("%Y-%m-%d %H:%M")))
        except sqlite3.IntegrityError:
            messagebox.showerror("Produktname bereits vorhanden", "Ein anderes Produkt besitzt bereits diesen Namen.")
            return
        self.refresh_all()
        # Bereits offene Einkaufsposten auf den neuen Preis aktualisieren.
        if pid in self.current_items:
            self.current_items[pid]["product"] = dict(self.db.one("SELECT * FROM products WHERE id=?", (pid,)))
            self.refresh_shopping_tree()
        self.status(f"Produkt „{name}“ gespeichert.")
        messagebox.showinfo("Gespeichert", f"Produkt „{name}“ wurde gespeichert bzw. aktualisiert.")
        # Formular nach dem Speichern zurücksetzen, damit direkt das nächste
        # Produkt eingetragen werden kann. Die Einheit startet bei „Stück“.
        self.clear_product_form()
        self.product_name_entry.focus_set()

    def delete_product(self):
        # Treeview im Extended-Modus erlaubt Windows-Mehrfachauswahl:
        # Strg+Klick für einzelne zusätzliche Produkte, Umschalt+Klick für Bereiche.
        selected = self.catalog_tree.selection()
        product_ids = [int(item_id) for item_id in selected]

        # Rückfall, falls ein Produkt im Formular ausgewählt wurde, aber keine
        # Tabellenzeile mehr markiert ist.
        if not product_ids and self.selected_product_id:
            product_ids = [int(self.selected_product_id)]

        if not product_ids:
            messagebox.showinfo(
                "Produkte auswählen",
                "Bitte wähle ein oder mehrere Produkte im Preiskatalog aus.\n\n"
                "Strg + linker Mausklick: einzelne Produkte auswählen\n"
                "Umschalt + linker Mausklick: zusammenhängenden Bereich auswählen"
            )
            return

        placeholders = ",".join("?" for _ in product_ids)
        products = self.db.rows(
            f"SELECT id, name FROM products WHERE id IN ({placeholders}) ORDER BY name COLLATE NOCASE",
            tuple(product_ids),
        )
        if not products:
            return

        names = [row["name"] for row in products]
        preview = "\n".join(f"• {name}" for name in names[:10])
        if len(names) > 10:
            preview += f"\n… und {len(names) - 10} weitere Produkte"
        if not messagebox.askyesno(
            "Produkte löschen",
            f"Möchtest du {len(products)} Produkt(e) wirklich löschen?\n\n{preview}\n\n"
            "Produkte, die in Rezepten verwendet werden, können nicht gelöscht werden.",
        ):
            return

        # In Rezepten verwendete Produkte überspringen; andere ausgewählte
        # Produkte können trotzdem gelöscht werden.
        recipe_rows = self.db.rows(
            f"SELECT DISTINCT product_id FROM recipe_items WHERE product_id IN ({placeholders})",
            tuple(product_ids),
        )
        blocked_ids = {int(row["product_id"]) for row in recipe_rows}
        deleted_ids = []
        for product in products:
            pid = int(product["id"])
            if pid in blocked_ids:
                continue
            self.db.run("DELETE FROM products WHERE id=?", (pid,))
            self.current_items.pop(pid, None)
            deleted_ids.append(pid)

        self.clear_product_form()
        self.refresh_all()

        blocked_names = [row["name"] for row in products if int(row["id"]) in blocked_ids]
        if blocked_names:
            blocked_preview = "\n".join(f"• {name}" for name in blocked_names[:10])
            if len(blocked_names) > 10:
                blocked_preview += f"\n… und {len(blocked_names) - 10} weitere"
            if deleted_ids:
                messagebox.showwarning(
                    "Teilweise gelöscht",
                    f"{len(deleted_ids)} Produkt(e) wurden gelöscht.\n\n"
                    "Diese Produkte konnten nicht gelöscht werden, weil sie in Rezepten verwendet werden:\n"
                    f"{blocked_preview}",
                )
            else:
                messagebox.showwarning(
                    "Produkte werden verwendet",
                    "Keines der ausgewählten Produkte konnte gelöscht werden, weil es in Rezepten verwendet wird:\n\n"
                    f"{blocked_preview}\n\nEntferne die Zutaten zuerst aus den betroffenen Rezepten.",
                )
        else:
            self.status(f"{len(deleted_ids)} Produkt(e) gelöscht.")

    def add_category(self):
        name = simpledialog.askstring("Kategorie hinzufügen", "Name der neuen Kategorie:", parent=self.root)
        if not name or not name.strip(): return
        try:
            self.db.run("INSERT INTO categories(name) VALUES (?)", (name.strip(),))
        except sqlite3.IntegrityError:
            messagebox.showinfo("Kategorie vorhanden", "Diese Kategorie existiert bereits."); return
        self.refresh_categories(); self.product_category_var.set(name.strip())

    # ---------- Recipes ----------
    def new_recipe(self):
        self.selected_recipe_id = None
        self.recipe_list.selection_clear(0, "end")
        self.recipe_name_var.set("")
        self.recipe_portions_var.set("1")
        self.recipe_notes.delete("1.0", "end")
        self.recipe_ingredient_ids = {}
        self.refresh_recipe_tree()
        self.recipe_cost_var.set("Rezeptkosten: 0,00 €")

    def on_recipe_select(self, _event=None):
        sel = self.recipe_list.curselection()
        if sel:
            self.load_recipe(self.recipe_ids[sel[0]])

    def load_recipe(self, recipe_id):
        r = self.db.one("SELECT * FROM recipes WHERE id=?", (recipe_id,))
        if not r: return
        self.selected_recipe_id = recipe_id
        self.recipe_name_var.set(r["name"])
        self.recipe_portions_var.set(str(r["portions"]).replace(".", ","))
        self.recipe_notes.delete("1.0", "end"); self.recipe_notes.insert("1.0", r["notes"])
        self.refresh_recipe_tree()

    def refresh_recipe_tree(self):
        for item in self.recipe_tree.get_children(): self.recipe_tree.delete(item)
        self.recipe_ingredient_ids = {}
        total = 0.0
        if self.selected_recipe_id:
            rows = self.db.rows("SELECT ri.id, ri.quantity, p.id product_id, p.name, p.unit, p.price FROM recipe_items ri JOIN products p ON p.id=ri.product_id WHERE ri.recipe_id=? ORDER BY p.name COLLATE NOCASE", (self.selected_recipe_id,))
            for r in rows:
                line = float(r["quantity"]) * float(r["price"]); total += line
                iid = self.recipe_tree.insert("", "end", values=(r["name"], self.format_qty(r["quantity"]), r["unit"], money(r["price"]), money(line)))
                self.recipe_ingredient_ids[iid] = r["id"]
        self.recipe_cost_var.set(f"Rezeptkosten: {money(total)}")

    def save_recipe(self):
        name = self.recipe_name_var.get().strip()
        if not name:
            messagebox.showerror("Rezeptname fehlt", "Bitte einen Rezeptnamen eingeben."); return
        try:
            portions = parse_number(self.recipe_portions_var.get(), "Portionen")
            if portions <= 0: raise ValueError("Die Portionszahl muss größer als 0 sein.")
        except ValueError as e:
            messagebox.showerror("Ungültige Portionen", str(e)); return
        notes = self.recipe_notes.get("1.0", "end").strip()
        try:
            if self.selected_recipe_id:
                self.db.run("UPDATE recipes SET name=?, portions=?, notes=? WHERE id=?", (name, portions, notes, self.selected_recipe_id))
                rid = self.selected_recipe_id
            else:
                rid = self.db.run("INSERT INTO recipes(name, portions, notes) VALUES (?, ?, ?)", (name, portions, notes))
                self.selected_recipe_id = rid
        except sqlite3.IntegrityError:
            messagebox.showerror("Rezeptname bereits vorhanden", "Ein anderes Rezept hat bereits diesen Namen."); return
        self.refresh_recipe_list(select_id=rid); self.refresh_home_stats()
        self.status(f"Rezept „{name}“ gespeichert.")
        messagebox.showinfo("Rezept gespeichert", f"Rezept „{name}“ wurde gespeichert.")

    def delete_recipe(self):
        sel = self.recipe_list.curselection()
        if not sel:
            messagebox.showinfo("Rezept auswählen", "Bitte wähle ein Rezept aus."); return
        rid = self.recipe_ids[sel[0]]
        name = self.db.one("SELECT name FROM recipes WHERE id=?", (rid,))["name"]
        if messagebox.askyesno("Rezept löschen", f"Rezept „{name}“ wirklich löschen?"):
            self.db.run("DELETE FROM recipes WHERE id=?", (rid,))
            self.new_recipe(); self.refresh_recipe_list(); self.refresh_home_stats()

    def add_recipe_ingredient(self):
        if not self.selected_recipe_id:
            messagebox.showinfo("Rezept zuerst speichern", "Erstelle ein neues Rezept und speichere es zuerst, bevor du Zutaten hinzufügst."); return
        display = self.ingredient_product_var.get()
        pid = self.products_by_display.get(display)
        if not pid:
            messagebox.showinfo("Produkt auswählen", "Bitte wähle eine Zutat aus dem Preiskatalog aus."); return
        try:
            qty = parse_number(self.ingredient_qty_var.get(), "Zutatenmenge")
            if qty <= 0: raise ValueError("Die Zutatenmenge muss größer als 0 sein.")
        except ValueError as e:
            messagebox.showerror("Ungültige Menge", str(e)); return
        existing = self.db.one("SELECT id, quantity FROM recipe_items WHERE recipe_id=? AND product_id=?", (self.selected_recipe_id, pid))
        if existing:
            self.db.run("UPDATE recipe_items SET quantity=? WHERE id=?", (float(existing["quantity"]) + qty, existing["id"]))
        else:
            self.db.run("INSERT INTO recipe_items(recipe_id, product_id, quantity) VALUES (?, ?, ?)", (self.selected_recipe_id, pid, qty))
        self.refresh_recipe_tree(); self.status("Zutat zum Rezept hinzugefügt.")

    def remove_recipe_ingredient(self, _event=None):
        sel = self.recipe_tree.selection()
        if not sel:
            messagebox.showinfo("Zutat auswählen", "Bitte markiere zuerst die Zutat, die du entfernen möchtest.")
            return "break" if _event is not None else None
        item_id = self.recipe_ingredient_ids.get(sel[0])
        if item_id:
            row = self.db.one("SELECT p.name FROM recipe_items ri JOIN products p ON p.id=ri.product_id WHERE ri.id=?", (item_id,))
            self.db.run("DELETE FROM recipe_items WHERE id=?", (item_id,))
            self.refresh_recipe_tree()
            self.recipe_tree.focus_set()
            if row:
                self.status(f"Zutat {row['name']} aus dem Rezept entfernt.")
        return "break" if _event is not None else None

    # ---------- Google-/Gemini-Browserprofil ----------
    def _gemini_edge_paths(self):
        """Liefert Edge-Programmdatei und dauerhaftes, app-eigenes Benutzerprofil."""
        import shutil
        env = os.environ
        local_app_data = Path(env.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        candidates = [
            Path(env.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
            Path(env.get("PROGRAMFILES", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe",
            local_app_data / "Microsoft/Edge/Application/msedge.exe",
        ]
        edge_binary = next((candidate for candidate in candidates if candidate.is_file()), None)
        if edge_binary is None:
            found = shutil.which("msedge")
            if found:
                edge_binary = Path(found)
        if edge_binary is None:
            raise RuntimeError("Microsoft Edge wurde nicht gefunden. Bitte Edge installieren oder den Installationspfad prüfen.")
        profile = local_app_data / "DxEinkaufsPlaner" / "EdgeGeminiProfile"
        profile.mkdir(parents=True, exist_ok=True)
        return edge_binary, profile

    def connect_google_account(self):
        """Öffnet Gemini in einem persistenten Edge-Profil für die manuelle Anmeldung."""
        try:
            import subprocess
            edge_binary, profile = self._gemini_edge_paths()
            command = [
                str(edge_binary), "--remote-debugging-port=9222",
                f"--user-data-dir={profile}", "--profile-directory=Default",
                "--no-first-run", "--no-default-browser-check", "--start-maximized",
                "https://gemini.google.com/app",
            ]
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            messagebox.showinfo(
                "Google-Konto verbinden",
                "Edge wurde mit dem eigenen DxEinkaufsPlaner-Profil geöffnet.\n\n"
                "Melde dich dort manuell bei deinem Google-Konto an und prüfe, ob Gemini erreichbar ist. "
                "Lass dieses Edge-Profil danach normal schließen oder geöffnet; beim nächsten Bonimport wird dasselbe Profil verwendet.\n\n"
                "Hinweis: Google kann automatisierte Browsersteuerung weiterhin blockieren.",
                parent=self.root,
            )
            self.status("Google-Konto: Anmeldung im DxEinkaufsPlaner-Edge-Profil durchführen.")
        except Exception as exc:
            messagebox.showerror("Google-Konto verbinden fehlgeschlagen", str(exc), parent=self.root)

    # ---------- Receipt import via Gemini in a visible browser ----------
    def import_receipt(self):
        """Öffnet Gemini und führt den Bonimport über manuelles Kopieren/Einfügen aus."""
        import subprocess
        import shutil
        import threading

        prompt = (
            "Wenn du diesen Kassenbon auslesen sollst und alle Produkte samt Einzelpreis auflisten sollst, würdest du es hinbekommen? "
            "Wenn ja, mach es. Achte darauf, dass du unnötige Abkürzungen und Bezeichnungen entschlüsselst und lesbare Produkte auflistest."
            "Bitte lies das angehängte Bonbild vollständig von oben nach unten. Gib ausschließlich die Artikel in Bon-Reihenfolge aus, "
            "keine Einleitung, keine Markdown-Tabelle und keine Gesamtsumme. Verwende pro Artikel eine Zeile im Format: "
            "LESBARER PRODUKTNAME | MENGE | EINZELPREIS_EURO | ZEILENGESAMTPREIS_EURO. Preise mit genau zwei Nachkommastellen "
            "und Dezimalkomma. Bei Menge 1 sind Einzelpreis und Zeilengesamtpreis gleich. Verwende ausschließlich sichtbare Bonangaben; "
            "rate keine unleserlichen Preise oder Produktdetails. Lass Mehrwertsteuer, Summe, Zahlung, Rückgeld und sonstige Nicht-Artikel weg."
        )

        # Öffne ausschließlich Gemini. Es wird kein Bon-Dateidialog angezeigt und kein Bild
        # automatisch hochgeladen; der Benutzer lädt das Bild selbst in Gemini hoch.
        try:
            edge_binary, profile = self._gemini_edge_paths()
            import urllib.request
            try:
                with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1.0) as response:
                    edge_ready = response.status == 200
            except Exception:
                edge_ready = False

            if edge_ready:
                # Die bereits angemeldete Edge-Sitzung weiterverwenden und Gemini öffnen.
                try:
                    from selenium import webdriver
                    options = webdriver.EdgeOptions()
                    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
                    driver = webdriver.Edge(options=options)
                    driver.switch_to.new_window("tab")
                    driver.get("https://gemini.google.com/app")
                    self._gemini_driver = driver
                except Exception:
                    # Der Debugger kann erreichbar sein, obwohl Selenium nicht anhängen kann.
                    # In dem Fall Edge mit dem gleichen persistenten Profil aufrufen.
                    subprocess.Popen([
                        str(edge_binary), "--remote-debugging-port=9222",
                        f"--user-data-dir={profile}", "--profile-directory=Default",
                        "--no-first-run", "--no-default-browser-check", "--start-maximized",
                        "https://gemini.google.com/app",
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen([
                    str(edge_binary), "--remote-debugging-port=9222",
                    f"--user-data-dir={profile}", "--profile-directory=Default",
                    "--no-first-run", "--no-default-browser-check", "--start-maximized",
                    "https://gemini.google.com/app",
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            messagebox.showerror("Gemini konnte nicht geöffnet werden", str(exc), parent=self.root)
            return

        # Einheitliche Dx-Optik für beide manuellen Gemini-Dialoge.
        def style_dialog(win, title, geometry, minsize):
            win.title(title)
            win.configure(bg=BG)
            win.geometry(geometry)
            win.minsize(*minsize)
            win.transient(self.root)
            win.option_add("*Font", ("Segoe UI", 10))
            win.lift()
            win.attributes("-topmost", True)
            win.after(500, lambda: win.attributes("-topmost", False))

        def make_dialog_header(parent, title, subtitle):
            header = tk.Frame(parent, bg=BG)
            header.pack(fill="x", padx=22, pady=(20, 14))
            tk.Frame(header, bg=ORANGE, height=3).pack(fill="x", pady=(0, 14))
            tk.Label(header, text=title, bg=BG, fg=GOLD,
                     font=("Segoe UI", 16, "bold"), anchor="w").pack(fill="x")
            tk.Label(header, text=subtitle, bg=BG, fg=MUTED,
                     font=("Segoe UI", 9), anchor="w", justify="left",
                     wraplength=740).pack(fill="x", pady=(5, 0))

        def make_text_area(parent, *, wrap="word", height=16, font=("Segoe UI", 10)):
            outer = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER,
                             highlightthickness=1, bd=0)
            outer.pack(fill="both", expand=True, padx=22, pady=(0, 14))
            text_frame = tk.Frame(outer, bg=PANEL)
            text_frame.pack(fill="both", expand=True, padx=2, pady=2)
            text = tk.Text(
                text_frame, wrap=wrap, height=height, font=font,
                bg=PANEL_ALT, fg=FG, insertbackground=ORANGE,
                selectbackground=ORANGE, selectforeground="#111111",
                relief="flat", bd=0, padx=12, pady=10,
                undo=True, highlightthickness=0,
            )
            ybar = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
            text.configure(yscrollcommand=ybar.set)
            text.pack(side="left", fill="both", expand=True)
            ybar.pack(side="right", fill="y")
            return text

        def make_action_button(parent, text, command, primary=False):
            return tk.Button(
                parent, text=text, command=command,
                bg=ORANGE if primary else PANEL_ALT,
                fg="#111111" if primary else FG,
                activebackground=GOLD if primary else "#34383d",
                activeforeground="#111111" if primary else FG,
                relief="flat", bd=0, padx=18, pady=10,
                font=("Segoe UI", 10, "bold" if primary else "normal"),
                cursor="hand2", highlightthickness=0,
            )

        prompt_win = tk.Toplevel(self.root)
        style_dialog(prompt_win, "Gemini · Prompt kopieren", "780x500", (620, 400))
        make_dialog_header(
            prompt_win, "Prompt für Gemini",
            "Füge diesen Text in Gemini ein und lade dein Kassenbon-Foto in Gemini hoch."
        )
        prompt_box = make_text_area(prompt_win, wrap="word", height=16, font=("Segoe UI", 10))
        prompt_box.insert("1.0", prompt)
        prompt_box.configure(state="disabled")

        def show_response_dialog():
            response_win = tk.Toplevel(self.root)
            style_dialog(response_win, "Gemini · Antwort übernehmen", "800x540", (620, 400))
            make_dialog_header(
                response_win, "Gemini-Antwort übernehmen",
                "Kopiere die Antwort aus Gemini, füge sie unten ein und bestätige die Artikel zur Prüfung."
            )
            response_box = make_text_area(
                response_win, wrap="none", height=18, font=("Consolas", 10)
            )
            response_box.focus_set()
            response_win.transient(self.root)
            response_win.grab_set()

            def confirm_response():
                response_text = response_box.get("1.0", "end-1c").strip()
                if not response_text:
                    messagebox.showwarning("Antwort fehlt", "Bitte füge zuerst die Gemini-Antwort ein.", parent=response_win)
                    return
                rows = parse_gemini_receipt_response(response_text)
                if not rows:
                    messagebox.showerror(
                        "Antwort nicht erkannt",
                        "Die Antwort enthält keine gültigen Artikelzeilen im Format NAME | MENGE | EINZELPREIS | ZEILENGESAMTPREIS.\n"
                        "Bitte prüfe die Antwort und füge sie erneut ein.", parent=response_win
                    )
                    return
                try:
                    response_win.grab_release()
                except tk.TclError:
                    pass
                response_win.destroy()
                try:
                    prompt_win.destroy()
                except tk.TclError:
                    pass
                self.status(f"Gemini hat {len(rows)} Artikelzeile(n) erkannt; bitte Ergebnisse prüfen.")
                ReceiptReview(self, "", "", gemini_rows=rows)

            def cancel_response():
                try:
                    response_win.grab_release()
                except tk.TclError:
                    pass
                response_win.destroy()

            buttons = tk.Frame(response_win, bg=BG)
            buttons.pack(fill="x", padx=22, pady=(0, 20))
            make_action_button(buttons, "Bestätigen", confirm_response, primary=True).pack(side="right", padx=(8, 0))
            make_action_button(buttons, "Abbrechen", cancel_response).pack(side="right")
            response_win.protocol("WM_DELETE_WINDOW", cancel_response)

        def copy_prompt():
            try:
                prompt_win.clipboard_clear()
                prompt_win.clipboard_append(prompt)
                prompt_win.update()
            except tk.TclError as exc:
                messagebox.showerror("Kopieren fehlgeschlagen", f"Der Text konnte nicht kopiert werden:\n{exc}", parent=prompt_win)
                return
            try:
                prompt_win.destroy()
            except tk.TclError:
                pass
            show_response_dialog()

        buttons = tk.Frame(prompt_win, bg=BG)
        buttons.pack(fill="x", padx=22, pady=(0, 20))
        make_action_button(buttons, "Text kopieren", copy_prompt, primary=True).pack(side="right", padx=(8, 0))
        make_action_button(buttons, "Schließen", prompt_win.destroy).pack(side="right")
        prompt_win.protocol("WM_DELETE_WINDOW", prompt_win.destroy)

    def on_close(self):
        try:
            self.db.close()
        finally:
            self.root.destroy()


class ReceiptReview:
    """Prüffenster für Bonartikel aus Gemini oder vorhandenen OCR-Texten."""
    def __init__(self, app, filename, text, gemini_rows=None):
        self.app = app
        self.filename = filename
        self.gemini_rows = gemini_rows
        self.root = tk.Toplevel(app.root)
        self.root.title("Kassenbon prüfen")
        self.root.geometry("1360x740")
        self.root.minsize(1120, 620)
        self.root.configure(bg=BG)
        tk.Label(self.root, text="Kassenbon-Erkennung prüfen", bg=BG, fg=GOLD, font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=18, pady=(16, 4))
        tk.Label(self.root, text="Kontrolliere Produktname, Menge und Preise. Der Katalog übernimmt weiterhin den Einzelpreis pro Produkt.", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", padx=18, pady=(0, 8))
        self.store_name = self.detect_store(text) if text else ""
        store_bar = tk.Frame(self.root, bg=BG)
        store_bar.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(store_bar, text="Geschäft für diesen Kassenbon", bg=BG, fg=GOLD, font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 12))
        self.store_entry = tk.Entry(store_bar, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 11))
        self.store_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.store_entry.insert(0, self.store_name)
        tk.Label(store_bar, text="Wird beim Übernehmen allen ausgewählten Produkten zugeordnet.", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(12, 0))
        body = tk.Frame(self.root, bg=BG); body.pack(fill="both", expand=True, padx=18)
        self.tree = ttk.Treeview(body, columns=("use", "name", "quantity", "price", "total", "store", "category", "unit"), show="headings", height=16)
        columns = [("use", "Übernehmen", 85), ("name", "Erkannter Produktname", 330), ("quantity", "Menge", 75), ("price", "Einzelpreis (€)", 105), ("total", "Zeilensumme (€)", 115), ("store", "Geschäft", 125), ("category", "Kategorie", 180), ("unit", "Einheit", 85)]
        for c, title, width in columns:
            self.tree.heading(c, text=title)
            self.tree.column(c, width=width, anchor="w" if c in ("name", "store", "category", "unit") else "center")
        self.tree.pack(fill="both", expand=True)
        self.row_data = {}
        self.categories = [r["name"] for r in app.db.rows("SELECT name FROM categories ORDER BY name")]
        self.catalog_product_names = [r["name"] for r in app.db.rows("SELECT name FROM products ORDER BY name COLLATE NOCASE")]
        self.default_category = next((c for c in self.categories if c.casefold() == "sonstiges"), "Sonstiges")
        if gemini_rows is not None:
            self.parse_gemini_rows(gemini_rows)
        else:
            self.parse_lines(text)
        controls = tk.Frame(self.root, bg=BG); controls.pack(fill="x", padx=18, pady=14)
        app.button(controls, "Ausgewählte Zeile bearbeiten", self.edit_row).pack(side="left")
        app.button(controls, "Ausgewählte Zeile entfernen", self.remove_row).pack(side="left", padx=8)
        app.button(controls, "Geprüfte Produkte übernehmen", self.commit, True).pack(side="right")
        app.button(controls, "Abbrechen", self.root.destroy).pack(side="right", padx=8)
        self.root.transient(app.root); self.root.grab_set()

    def parse_gemini_rows(self, rows):
        """Übernimmt validierte Gemini-Artikel unverändert und in Bon-Reihenfolge."""
        for row in rows:
            name = str(row["name"]).strip()
            quantity = float(row["quantity"])
            price = float(row["unit_price"])
            total = float(row["total_price"])
            if not name or quantity <= 0:
                continue
            category = self.suggest_category(name)
            iid = self.tree.insert(
                "", "end",
                values=("Ja", name, format_receipt_number(quantity), f"{price:.2f}".replace(".", ","),
                        f"{total:.2f}".replace(".", ","), self.store_name, category, "Stück")
            )
            self.row_data[iid] = True

    @staticmethod
    def detect_store(text):
        """Erkennt nur klar sichtbare Ladenbezeichnungen; sonst bleibt das Feld leer."""
        normalized = re.sub(r"\s+", " ", text).casefold()
        if "netto" in normalized and ("marken-discount" in normalized or "netto-online" in normalized or "bonkopie" in normalized):
            return "Netto"
        if re.search(r"\baldi\b", normalized):
            return "Aldi"
        if re.search(r"\blidl\b", normalized):
            return "Lidl"
        if re.search(r"\brewe\b", normalized):
            return "REWE"
        if re.search(r"\bedeka\b", normalized):
            return "EDEKA"
        return ""

    def suggest_category(self, name):
        """Schlägt nur bei einem erkennbaren Treffer eine vorhandene Kategorie vor."""
        n = name.casefold()
        rules = [
            (("spinat", "paprika", "weißkraut", "weisskraut", "kohl", "kartoffel", "gemüse", "gemuese", "buttergemuese", "buttergemüse", "buttergenuese", "salat", "zwiebel"), ("gemüse", "gemuese", "obst")),
            (("brot", "brötchen", "toast", "mehrkorn", "knäckebrot", "backware", "kuchen"), ("back", "brot")),
            (("gouda", "käse", "kaese", "kaes", "hirtenkaes", "mozzarella", "mozzarel", "milch", "butter", "joghurt", "sahne", "quark", "eier"), ("milch", "molkerei", "käse", "kaese", "eier")),
            (("chips", "knabber", "cookies", "keks", "snack", "linsenchips"), ("snack", "süß", "suess", "süßwaren", "suesswaren")),
            (("schinken", "wurst", "salami", "leberwurst", "teewurst", "fleisch"), ("fleisch", "wurst", "aufschnitt")),
        ]
        for product_terms, category_terms in rules:
            if any(term in n for term in product_terms):
                for category in self.categories:
                    if any(term in category.casefold() for term in category_terms):
                        return category
        return self.default_category

    def parse_lines(self, text):
        """Liest Bonzeilen und ordnet Mehrfachkauf-Rechnungen bonweit zu.

        Manche Händler drucken die Mengenrechnung oberhalb des Artikels (Netto auf
        dem hier verwendeten Bon), andere darunter. Die Richtung wird einmal anhand
        der ersten Artikelzeilen bestimmt. Eine Rechnung wird danach ausschließlich
        innerhalb des Abschnitts zwischen zwei Produktzeilen gesucht; sie darf niemals
        auf ein weiter entferntes Produkt übertragen werden.
        """
        seen = set()
        ignored_prefix = re.compile(
            r"(?i)^(summe|gesamt|mwst|ust|bar|ec|visa|gegeben|rückgeld|ruckgeld|wechselgeld|kartenzahlung|terminal|ta-nr|eur|kontaktlos|pan|girocard)\b"
        )
        # OCR liest die Bon-Summe gelegentlich als Fantasiewort (z. B. "SUWAE").
        # Diese Erkennung wird nur für typische Zahlungs-/Fußzeilen angewendet.
        from difflib import SequenceMatcher
        def looks_like_footer(line):
            compact = re.sub(r"[^a-zäöüß]", "", line.casefold())
            words = re.findall(r"[A-Za-zÄÖÜäöüß]+", line.casefold())
            if any(term in compact for term in ("kartenzahlung", "kontaktlos", "girocard", "terminalid", "bonkopie", "ta-nr")):
                return True
            if words and any(SequenceMatcher(None, words[0], word).ratio() >= 0.76
                             for word in ("summe", "gesamt", "kartenzahlung", "gegeben", "rückgeld")):
                return True
            # Wiederholte Endsumme/Bezahlbetrag ist kein Artikel, auch wenn der
            # Text davor von OCR stark beschädigt wurde.
            if re.search(r"(?i)\b(?:eur|pan|karte|zahlung)\b", line) and price_pattern.search(line):
                return True
            return False
        price_pattern = re.compile(r"(?<!\d)(\d{1,4}[,.]\d{2})(?!\d)")
        lines = [re.sub(r"\s+", " ", line).strip(" \t|:;-") for line in text.splitlines()]

        def product_candidate(line):
            if not line or ignored_prefix.search(line) or looks_like_footer(line):
                return None
            if re.search(r"(?i)(?:EUR\s*/\s*kg|€/kg|\d[,.]\d{2}\s*(?:EUR)?\s*/\s*kg)", line):
                return None
            matches = list(price_pattern.finditer(line))
            if not matches:
                return None
            match = matches[-1]
            name = (line[:match.start()] + line[match.end():]).strip(" \t-:*")
            # Bei seitlich gedruckten Rechnungen kann die OCR Menge/Einzelpreis
            # und Produkt in eine Zeile schreiben. Diese Rechenangabe gehört nicht
            # zum Produktnamen.
            name = re.sub(r"(?i)(?<!\d)\d{1,2}\s*[x×]\s*\d{1,4}[,.]\d{2}", " ", name)
            name = re.sub(r"(?i)(?<!\d)\d{1,2}\s*[x×](?!\w)", " ", name)
            name = re.sub(r"(?i)\s+[B8]$", "", name).strip()
            name = re.sub(r"(?i)\b(EUR|EURO)\b", "", name).strip()
            name = re.sub(r"\s+", " ", name)
            if len(re.findall(r"[A-Za-zÄÖÜäöüß]", name)) < 4:
                return None
            if not re.search(r"[A-Za-zÄÖÜäöüß]{2,}", name):
                return None
            name = re.sub(r"^\d{3,5}\s+(?=[A-Za-zÄÖÜäöüß])", "", name)
            name = re.sub(r"^[^A-Za-zÄÖÜäöüß]+", "", name).strip()
            name = clean_receipt_product_name(name, getattr(self, "catalog_product_names", ()))
            if len(re.findall(r"[A-Za-zÄÖÜäöüß]", name)) < 3:
                return None
            if re.fullmatch(r"(?i)(?:artikel|produkt|ware|st|stk|stück|sonstiges)", name):
                return None
            try:
                price = float(match.group(1).replace(",", "."))
            except ValueError:
                return None
            return {"name": name, "printed_price": price, "match": match}

        candidates = {}
        product_indices = []
        for i, line in enumerate(lines):
            candidate = product_candidate(line)
            if candidate:
                candidates[i] = candidate
                product_indices.append(i)

        def parse_calculation_line(line):
            """Liest eine explizite Mehrfachkauf-Rechnung aus einer OCR-Zeile."""
            if not line:
                return None
            qm = re.search(
                r"(?i)(?<!\d)(\d{1,2})\s*[x×]\s*(\d{1,4}[,.]\d{2})(?!\d)", line
            )
            if qm:
                qty = int(qm.group(1))
                unit = float(qm.group(2).replace(",", "."))
                if 2 <= qty <= 99 and 0 < unit < 1000:
                    return qty, unit
            return None

        def calculation_in_segment(segment):
            """Findet nur eine explizite Mengenrechnung innerhalb eines Produktabschnitts."""
            if not segment:
                return None
            for j, line in enumerate(segment):
                inline = parse_calculation_line(line)
                if inline:
                    return inline
                qm = re.fullmatch(r"(?i)\s*(\d{1,2})\s*[x×]\s*[B8]?\s*", line or "")
                if not qm:
                    continue
                qty = int(qm.group(1))
                if not 2 <= qty <= 99:
                    continue
                # OCR-Reihenfolge kann die reine Preiszeile direkt vor oder nach
                # der Mengenzeile liefern. Suche nur im unmittelbaren Nachbarbereich.
                for k in (j + 1, j - 1, j + 2, j - 2):
                    if k < 0 or k >= len(segment):
                        continue
                    price_line = segment[k]
                    pm = re.fullmatch(
                        r"(?i)\s*(?:EUR\s*)?(\d{1,4}[,.]\d{2})\s*[B8]?\s*", price_line or ""
                    )
                    if pm:
                        unit = float(pm.group(1).replace(",", "."))
                        if 0 < unit < 1000:
                            return qty, unit
            return None

        # Sammle jede explizite Mehrfachkauf-Rechnung. Erst wenn eine Rechnung
        # anhand der gedruckten Zeilensumme einem Produkt eindeutig zugeordnet
        # werden kann, wird daraus die Bon-Richtung abgeleitet. Der erste Artikel
        # allein sagt nichts über die Druckrichtung aus.
        calculations = []
        for i, line in enumerate(lines):
            inline = parse_calculation_line(line)
            if inline:
                calculations.append((i, i, inline[0], inline[1]))
                continue
            qm = re.fullmatch(r"(?i)\s*(\d{1,2})\s*[x×]\s*[B8]?\s*", line or "")
            if not qm:
                continue
            qty = int(qm.group(1))
            if not 2 <= qty <= 99:
                continue
            for j in (i + 1, i - 1, i + 2, i - 2):
                if j < 0 or j >= len(lines):
                    continue
                pm = re.fullmatch(r"(?i)\s*(?:EUR\s*)?(\d{1,4}[,.]\d{2})\s*[B8]?\s*", lines[j] or "")
                if pm:
                    unit = float(pm.group(1).replace(",", "."))
                    if 0 < unit < 1000:
                        calculations.append((min(i, j), max(i, j), qty, unit))
                        break

        direction = None
        # Gehe in Bon-Reihenfolge durch die Mehrfachkauf-Rechnungen. Eine passende
        # Produkt-Zeilensumme (Menge * Einzelpreis) ist das stärkste Signal dafür,
        # ob die Rechnung oberhalb oder unterhalb des Produkts steht. OCR-Toleranz
        # ist bewusst klein; bei Mehrdeutigkeit wird nicht geraten.
        for calc_start, calc_end, qty, unit in sorted(calculations, key=lambda x: x[0]):
            total = qty * unit
            before = [(idx, candidates[idx]) for idx in product_indices if idx < calc_start]
            after = [(idx, candidates[idx]) for idx in product_indices if idx > calc_end]
            before_match = next(((idx, c) for idx, c in reversed(before)
                                 if abs(c["printed_price"] - total) <= 0.03), None)
            after_match = next(((idx, c) for idx, c in after
                                if abs(c["printed_price"] - total) <= 0.03), None)
            if before_match and not after_match:
                direction = "below"
                break
            if after_match and not before_match:
                direction = "above"
                break
            # Wenn der Bon vor dem ersten Produkt bereits eine Mengenrechnung zeigt,
            # ist die Zuordnung oberhalb eindeutig, selbst wenn OCR die Summe falsch liest.
            if not before and after:
                direction = "above"
                break

        # Wenn die Richtung nicht sicher ermittelt werden kann, keine Mengenrechnung
        # auf andere Produkte übertragen. Gedruckte Produktpreise bleiben unangetastet.
        for pos, index in enumerate(product_indices):
            candidate = candidates[index]
            name = candidate["name"]
            price = candidate["printed_price"]
            previous_index = product_indices[pos - 1] if pos > 0 else -1
            next_index = product_indices[pos + 1] if pos + 1 < len(product_indices) else len(lines)

            calculation = None
            # Rechnung auf derselben OCR-Zeile wie das Produkt (seitlich gedruckt oder
            # von Tesseract zu einer Zeile zusammengeführt) hat Vorrang, wenn die
            # Zeile eine explizite Menge x Einzelpreis enthält.
            inline = parse_calculation_line(lines[index])
            if inline:
                calculation = inline
            elif direction == "above":
                calculation = calculation_in_segment(lines[previous_index + 1:index])
            elif direction == "below":
                calculation = calculation_in_segment(lines[index + 1:next_index])

            if calculation:
                qty, unit_price = calculation
                # Nur eine ausdrücklich gedruckte Rechnung verwenden. Keine Summe
                # durch Menge teilen und niemals eine Rechnung von einem anderen
                # Produktabschnitt übernehmen.
                price = unit_price

            key = (re.sub(r"[^a-z0-9äöüß]", "", name.casefold()), round(price, 2), self.store_name.casefold())
            if key in seen:
                continue
            seen.add(key)
            category = self.suggest_category(name)
            iid = self.tree.insert(
                "", "end",
                values=("Ja", name, "1", f"{price:.2f}".replace(".", ","), f"{price:.2f}".replace(".", ","), self.store_name, category, "Stück")
            )
            self.row_data[iid] = True

    def edit_row(self):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        values = list(self.tree.item(iid, "values"))
        fields = [
            (1, "Produktname"), (2, "Menge"), (3, "Einzelpreis in Euro"),
            (4, "Zeilengesamtpreis in Euro"), (5, "Geschäft (leer lassen, wenn unbekannt)"),
            (6, "Kategorie"), (7, "Einheit"),
        ]
        for index, title in fields:
            value = simpledialog.askstring("Bonzeile bearbeiten", title + ":", initialvalue=values[index], parent=self.root)
            if value is None:
                return
            values[index] = value.strip()
        try:
            quantity = parse_number(values[2], "Menge")
            price = parse_number(values[3], "Einzelpreis")
            total = parse_number(values[4], "Zeilengesamtpreis")
            if quantity <= 0:
                raise ValueError("Die Menge muss größer als 0 sein.")
            if not values[1]:
                raise ValueError("Der Produktname darf nicht leer sein.")
            values[2] = format_receipt_number(quantity)
            values[3] = f"{price:.2f}".replace(".", ",")
            values[4] = f"{total:.2f}".replace(".", ",")
        except ValueError as e:
            messagebox.showerror("Ungültige Daten", str(e), parent=self.root)
            return
        self.tree.item(iid, values=values)

    def remove_row(self):
        sel = self.tree.selection()
        if sel:
            self.tree.delete(sel[0]); self.row_data.pop(sel[0], None)

    def commit(self):
        imported = 0
        errors = []
        for iid in self.tree.get_children():
            use, name, quantity_text, price_text, total_text, store, category, unit = self.tree.item(iid, "values")
            if str(use).strip().lower() not in ("ja", "yes", "1", "x", "✓"):
                continue
            name = name.strip(); unit = unit.strip() or "Stück"
            if not name: continue
            try:
                price = parse_number(price_text, "Einzelpreis")
                quantity = parse_number(quantity_text, "Menge")
                total_price = parse_number(total_text, "Zeilengesamtpreis")
                if quantity <= 0:
                    raise ValueError("Die Menge muss größer als 0 sein.")
            except ValueError as exc:
                errors.append(f"{name}: ungültige Bonwerte ({exc})")
                continue
            cat = self.app.db.one("SELECT id FROM categories WHERE name=? COLLATE NOCASE", (category.strip(),))
            if not cat:
                try:
                    cid = self.app.db.run("INSERT INTO categories(name) VALUES (?)", (category.strip() or "Sonstiges",))
                except sqlite3.IntegrityError:
                    cid = self.app.db.one("SELECT id FROM categories WHERE name=? COLLATE NOCASE", (category.strip(),))["id"]
            else:
                cid = cat["id"]
            # Ein im Kopf eingetragenes Geschäft gilt für alle übernommenen Bonartikel.
            # Bleibt das Feld leer, wird der ggf. pro Zeile vorhandene Geschäftsname verwendet.
            entered_store = self.store_entry.get().strip()
            store = (entered_store or str(store or "")).strip()
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            existing = self.app.db.one("SELECT id FROM products WHERE name=? COLLATE NOCASE", (name,))
            if existing:
                pid = existing["id"]
                # Der aktuelle Katalog zeigt den zuletzt importierten Preis; die Tabelle
                # product_store_prices bewahrt zusätzlich getrennte Preise je Geschäft.
                self.app.db.run("UPDATE products SET category_id=?, unit=?, price=?, store=?, updated_at=? WHERE id=?", (cid, unit, price, store, now, pid))
            else:
                pid = self.app.db.run("INSERT INTO products(name, category_id, unit, price, updated_at, store) VALUES (?, ?, ?, ?, ?, ?)", (name, cid, unit, price, now, store))
            if store:
                self.app.db.run("INSERT INTO product_store_prices(product_id, store, price, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(product_id, store) DO UPDATE SET price=excluded.price, updated_at=excluded.updated_at", (pid, store, price, now))
            if pid in self.app.current_items:
                self.app.current_items[pid]["product"] = dict(self.app.db.one("SELECT * FROM products WHERE id=?", (pid,)))
            imported += 1
        self.app.db.run("INSERT INTO receipt_imports(filename, imported_at) VALUES (?, ?)", (os.path.basename(self.filename), datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.app.refresh_all()
        self.app.status(f"Kassenbon verarbeitet: {imported} Produkt(e) übernommen.")
        msg = f"{imported} Produkt(e) wurden übernommen. Bei bereits vorhandenen Produkten wurde der Katalogpreis aktualisiert."
        if errors: msg += "\n\nNicht übernommen:\n" + "\n".join(errors)
        messagebox.showinfo("Kassenbon verarbeitet", msg, parent=self.root)
        self.root.destroy()


def main():
    root = tk.Tk()
    app = DxEinkaufsPlaner(root)
    root.mainloop()


if __name__ == "__main__":
    main()
