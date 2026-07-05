from __future__ import annotations

"""
Mighty DOOM Admin server.

This module intentionally contains the Flask routes and the HTML rendering code in
one place because the project is deployed as a tiny private admin tool. The public
repository around it is structured like a normal Python package, while the runtime
file stays self-contained enough to make updates and local debugging simple.

Design goals:
- never modify the original game server code;
- write directly to the local SQLite database only after creating safety backups;
- keep external game changes auditable through SQLite triggers;
- keep all UI labels translatable between German and English;
- keep the mobile API stable for the optional Android companion app.
"""

import argparse
import base64
import datetime as dt
import html
import json
import os
import random
import re
import secrets
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

import bcrypt
from flask import Flask, Response, abort, flash, g, make_response, redirect, request, send_file, url_for

APP_TITLE = "Mighty DOOM Admin"
APP_VERSION = "v17.1 inbox-image-null-fix"
WRITE_TABLES = {
    "users",
    "user_settings",
    "user_stats",
    "tutorial_sequences",
    "items",
    "cosmetics",
    "inventory_slots",
    "currencies",
    "energies",
    "talents",
    "chapter_progress",
    "attempts",
    "battle_passes",
    "missions",
    "store_quotas",
    "admin_event_schedule",
    "admin_event_progress",
    "admin_inbox_messages",
    "admin_inbox_message_state",
}

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

_ENERGY_AUTOFILL_THREAD: threading.Thread | None = None
_ENERGY_AUTOFILL_STOP = threading.Event()
_ENERGY_AUTOFILL_LOCK = threading.Lock()




# ---------------------------------------------------------------------------
# UI language and theme configuration
# ---------------------------------------------------------------------------
SUPPORTED_LANGUAGES = {"de": "Deutsch", "en": "English"}
SUPPORTED_THEMES = {
    "ops": "Ops Dashboard",
    "hellforge": "Hellforge Dashboard",
}
DEFAULT_LANGUAGE = "de"
DEFAULT_THEME = "ops"

TRANSLATIONS_DE_EN = {
    "Mighty DOOM Admin": "Mighty DOOM Admin",
    "Dashboard": "Dashboard",
    "User": "Users",
    "Users": "Users",
    "Backups": "Backups",
    "Katalog": "Catalog",
    "Resource-Katalog": "Resource catalog",
    "Energy Auto-Fill": "Energy Auto-Fill",
    "Änderungen": "Changes",
    "DB-Audit": "DB Audit",
    "Tools": "Tools",
    "Tables": "Tables",
    "Tabellen": "Tables",
    "Sprache": "Language",
    "Design": "Design",
    "Öffnen": "Open",
    "Suchen": "Search",
    "Suche": "Search",
    "Speichern": "Save",
    "Zurückspielen": "Restore",
    "Rückgängig": "Undo",
    "Rückgängig machen": "Undo",
    "Änderung rückgängig machen": "Undo change",
    "bereits rückgängig": "already undone",
    "Backup jetzt erstellen": "Create backup now",
    "Datenbank-Backups": "Database backups",
    "Backup-Dateien": "Backup files",
    "Backup-Log": "Backup log",
    "Änderungsprotokoll": "Change log",
    "Änderungsprotokoll ansehen": "View change log",
    "Letzte Änderungen": "Recent changes",
    "Reparatur-Tools": "Repair tools",
    "Schnell-Reparatur": "Quick repair",
    "Validierung": "Validation",
    "Keine typischen Start-Probleme gefunden.": "No typical startup problems found.",
    "Status": "Status",
    "aktiv": "active",
    "deaktiviert": "disabled",
    "aus": "off",
    "Wieder aktivieren": "Re-enable",
    "Deaktivieren": "Disable",
    "Jetzt sofort setzen": "Set now",
    "Jetzt setzen": "Set now",
    "Ausschalten": "Turn off",
    "Einschalten": "Turn on",
    "Aktuell": "Current",
    "Ziel": "Target",
    "Intervall": "Interval",
    "Letzter Check": "Last check",
    "Letzte Änderung": "Last change",
    "Aktion": "Action",
    "Aktionen": "Actions",
    "Tabelle": "Table",
    "Name": "Name",
    "Größe": "Size",
    "Zeit": "Time",
    "Grund": "Reason",
    "Datei": "File",
    "Download": "Download",
    "Beschreibung": "Description",
    "Kategorie": "Category",
    "Bezeichnung": "Label",
    "Quelle": "Source",
    "Kompatible Slots": "Compatible slots",
    "Währungen": "Currencies",
    "Währung": "Currency",
    "Energie": "Energy",
    "Talente": "Talents",
    "Stats": "Stats",
    "Rohdaten": "Raw data",
    "Ausgerüstete Slots": "Equipped slots",
    "Inventar-Items": "Inventory items",
    "Chapter Progress": "Chapter progress",
    "Doppelte UUIDs": "Duplicate UUIDs",
    "Kaputte Inventory Slots": "Broken inventory slots",
    "Verdächtige Current Attempts": "Suspicious current attempts",
    "Alle": "All",
    "Alle Änderungen für diesen User anzeigen": "Show all changes for this user",
    "Nur Ansicht": "Read-only",
    "Nicht gefunden": "Not found",
    "User nicht gefunden.": "User not found.",
    "game-data geladen": "game-data loaded",
    "game-data fehlt": "game-data missing",
    "Primärwaffe": "Primary weapon",
    "Sekundärwaffe": "Secondary weapon",
    "Stiefel": "Boots",
    "Handschuhe": "Gloves",
    "Helm": "Helmet",
    "Torso": "Torso",
    "Waffe": "Weapon",
    "Ausrüstung": "Equipment",
    "Kosmetik": "Cosmetic",
    "Ressource": "Resource",
    "verfügbar": "available",
    "bedingt": "conditional",
    "intern": "internal",
    "leer": "empty",
    "nicht equippen": "do not equip",
    "unbekanntes Item": "unknown item",
    "Unbekannt": "Unknown",
    "Keine Zuordnung in game-data.json gefunden.": "No mapping found in game-data.json.",
    "Schneller Überblick über User, Items, Backups, DB-Audit, Auto-Fill und Progress-Transfer.": "Quick overview of users, items, backups, DB audit, auto-fill and progress transfer.",
    "Schnellaktionen": "Quick actions",
    "Neueste User": "Latest users",
    "User suchen": "Search user",
    "Current Attempts": "Current attempts",
    "Verdächtig": "Suspicious",
    "Game-/DB-Änderungen": "Game/DB changes",
    "Reparatur-Tools": "Repair tools",
    "Progress übertragen": "Transfer progress",
    "Progress-Transfer": "Progress transfer",
    "Von User": "From user",
    "Zu User": "To user",
    "Quell-User": "Source user",
    "Ziel-User": "Target user",
    "Übertragung starten": "Start transfer",
    "Vorschau aktualisieren": "Update preview",
    "Ziel vorher bereinigen": "Clear target first",
    "Core-Fortschritt": "Core progress",
    "Spieltabellen": "Game progress tables",
    "Inventar und Ausrüstung": "Inventory and equipment",
    "Attempts übernehmen": "Copy attempts",
    "Sicherheitsbackup": "Safety backup",
    "Fortschritt übertragen": "Transfer progress",
    "Sicherer Progress-Transfer": "Safe progress transfer",
    "Progress sicher übertragen": "Safely transfer progress",
    "Transfer starten": "Start transfer",
    "Quelle und Ziel auswählen": "Select source and target",
    "Automatische Sicherheitsprüfung": "Automatic safety check",
    "Instabile Menü-/Saison-Daten werden automatisch zurückgesetzt.": "Unstable menu/season data is reset automatically.",
    "Keine erweiterten Optionen nötig.": "No advanced options required.",
    "Kopiert stabilen Fortschritt, Inventar, Ausrüstung, Währungen, Energie, Stats, Talente, Settings, Tutorial und Chapter-Fortschritt.": "Copies stable progress, inventory, equipment, currencies, energy, stats, talents, settings, tutorial and chapter progress.",
    "Events": "Events",
    "Event-Admin": "Event admin",
    "Event-Katalog": "Event catalog",
    "Event-Schedule": "Event schedule",
    "Event aktivieren": "Activate event",
    "Event bearbeiten": "Edit event",
    "Event exportieren": "Export events",
    "Event Definition ID": "Event definition ID",
    "Event-Art": "Event type",
    "Startzeit": "Start time",
    "Endzeit": "End time",
    "Für alle User": "For all users",
    "Nur bestimmte User": "Only selected users",
    "User-IDs": "User IDs",
    "Stage-Rewards": "Stage rewards",
    "Standard-Testrewards setzen": "Set default test rewards",
    "Rewards aus Eventdefinition übernehmen": "Import rewards from event definition",
    "Additional Event Modifiers": "Additional event modifiers",
    "Event-Progress": "Event progress",
    "Event für alle User aktivieren": "Enable event for all users",
    "Event für User zuweisen": "Assign event to user",
    "Event-Progress zurücksetzen": "Reset event progress",
    "geplant": "planned",
    "abgelaufen": "expired",
    "global": "global",
    "user-spezifisch": "user-specific",
    "Nachrichten": "Inbox",
    "Inbox": "Inbox",
    "Nachrichtenübersicht": "Inbox messages",
    "Nachricht erstellen": "Create message",
    "Nachricht bearbeiten": "Edit message",
    "Nachricht löschen": "Delete message",
    "Komplett löschen": "Delete completely",
    "Zielgruppe": "Target audience",
    "Alle User": "All users",
    "bestimmter User": "specific user",
    "Veröffentlicht ab": "Published from",
    "Läuft ab": "Expires",
    "Hat Rewards": "Has rewards",
    "gelesen": "read",
    "geclaimt": "claimed",
    "gelöscht": "deleted",
    "Rewards": "Rewards",
    "Nachrichtentext": "Message text",
    "Display Type": "Display type",
    "Image ID": "Image ID",
    "Status zurücksetzen": "Reset state",
    "Status für alle User zurücksetzen": "Reset state for all users",
    "Status für User zurücksetzen": "Reset state for user",
    "unread": "unread",
    "read": "read",
    "claimed": "claimed",
    "archiviert": "archived",
}




# ---------------------------------------------------------------------------
# Translation helpers
# ---------------------------------------------------------------------------
def current_language() -> str:
    lang = request.args.get("lang") or request.cookies.get("mda_lang") or DEFAULT_LANGUAGE
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def current_theme() -> str:
    theme = request.args.get("theme") or request.cookies.get("mda_theme") or DEFAULT_THEME
    return theme if theme in SUPPORTED_THEMES else DEFAULT_THEME


def tt(de: str, en: str | None = None) -> str:
    if current_language() == "en":
        return en if en is not None else TRANSLATIONS_DE_EN.get(de, de)
    return de


def translate_html(text: str) -> str:
    if current_language() != "en":
        return text
    for de, en in sorted(TRANSLATIONS_DE_EN.items(), key=lambda kv: len(kv[0]), reverse=True):
        text = text.replace(de, en)
    return text



# ---------------------------------------------------------------------------
# Dashboard CSS generation
# ---------------------------------------------------------------------------
def app_shell_css(theme: str) -> str:
    accent = "#7c3aed" if theme == "ops" else "#f97316"
    accent2 = "#22d3ee" if theme == "ops" else "#ef4444"
    return f"""
:root {{ color-scheme: dark; --bg:#070b16; --panel:#111827; --panel2:#0b1220; --panel3:#172033; --text:#eef2ff; --muted:#9aa4b8; --line:rgba(148,163,184,.22); --accent:{accent}; --accent2:{accent2}; --bad:#fb7185; --good:#34d399; --warn:#fbbf24; --shadow:0 24px 70px rgba(0,0,0,.35); --radius:22px; }}
* {{ box-sizing:border-box; }}
html {{ min-height:100%; }}
body {{ margin:0; min-height:100%; font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif; background:var(--bg); color:var(--text); overflow-x:hidden; }}
body.theme-ops {{ background: radial-gradient(circle at top left, rgba(124,58,237,.28), transparent 34rem), radial-gradient(circle at top right, rgba(34,211,238,.20), transparent 38rem), linear-gradient(135deg,#070b16 0%,#111827 55%,#08111f 100%); }}
body.theme-hellforge {{ background: radial-gradient(circle at 10% 0%, rgba(249,115,22,.28), transparent 34rem), radial-gradient(circle at 98% 8%, rgba(239,68,68,.20), transparent 34rem), linear-gradient(135deg,#09070a 0%,#17100d 55%,#1b1210 100%); }}
a {{ color:#b9ccff; text-decoration:none; }}
a:hover {{ color:white; text-decoration:none; }}
.app-bg {{ position:fixed; inset:0; pointer-events:none; opacity:.75; }}
.app-bg:before {{ content:""; position:absolute; inset:28px; border-radius:44px; background:linear-gradient(135deg, rgba(255,255,255,.05), rgba(255,255,255,0)); border:1px solid rgba(255,255,255,.08); transform:rotate(-1.8deg); }}
.app-layout {{ position:relative; display:grid; grid-template-columns:92px minmax(0,1fr); min-height:100vh; padding:24px; gap:18px; }}
.sidebar {{ position:sticky; top:24px; align-self:start; height:calc(100vh - 48px); border:1px solid var(--line); border-radius:28px; background:rgba(8,13,26,.78); backdrop-filter: blur(18px); box-shadow:var(--shadow); display:flex; flex-direction:column; align-items:center; padding:18px 12px; gap:14px; }}
.logo {{ width:48px; height:48px; display:grid; place-items:center; border-radius:18px; background:linear-gradient(135deg,var(--accent),var(--accent2)); color:white; font-weight:900; letter-spacing:-.05em; box-shadow:0 12px 28px rgba(0,0,0,.32); }}
.side-nav {{ display:flex; flex-direction:column; gap:10px; width:100%; align-items:center; margin-top:8px; }}
.side-link {{ width:54px; height:54px; display:grid; place-items:center; border-radius:18px; color:var(--muted); background:transparent; font-size:22px; border:1px solid transparent; }}
.side-link:hover,.side-link.active {{ color:white; background:rgba(255,255,255,.08); border-color:var(--line); }}
.side-spacer {{ flex:1; }}
.content-shell {{ min-width:0; border:1px solid var(--line); border-radius:28px; background:rgba(12,18,34,.80); backdrop-filter: blur(18px); box-shadow:var(--shadow); overflow:hidden; }}
.topbar {{ min-height:88px; display:flex; align-items:center; justify-content:space-between; gap:18px; padding:20px 26px; background:rgba(15,23,42,.62); border-bottom:1px solid var(--line); }}
.title-wrap h1 {{ margin:0; font-size:28px; letter-spacing:-.03em; }}
.title-wrap .subtitle {{ margin-top:4px; color:var(--muted); font-size:13px; overflow-wrap:anywhere; }}
.quick-actions {{ display:flex; align-items:center; justify-content:flex-end; gap:10px; flex-wrap:wrap; }}
.ui-form {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; padding:6px; border:1px solid var(--line); background:rgba(255,255,255,.04); border-radius:18px; }}
main {{ padding:26px; max-width:1660px; margin:0 auto; width:100%; }}
.page-tabs {{ display:flex; gap:10px; flex-wrap:wrap; margin:0 0 22px; }}
.page-tabs a {{ display:inline-flex; align-items:center; gap:8px; border:1px solid var(--line); background:rgba(255,255,255,.06); color:var(--text); padding:11px 14px; border-radius:15px; white-space:nowrap; }}
.page-tabs a:hover,.page-tabs a.active {{ background:linear-gradient(135deg, rgba(124,58,237,.8), rgba(34,211,238,.35)); border-color:rgba(255,255,255,.24); }}
body.theme-hellforge .page-tabs a:hover, body.theme-hellforge .page-tabs a.active {{ background:linear-gradient(135deg, rgba(249,115,22,.85), rgba(239,68,68,.35)); }}
.card {{ background:rgba(18,27,46,.82); border:1px solid var(--line); border-radius:var(--radius); padding:18px; margin:0 0 18px 0; box-shadow:0 16px 42px rgba(0,0,0,.20); overflow-x:auto; }}
.card h1,.card h2,.card h3 {{ margin-top:0; letter-spacing:-.02em; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(285px,1fr)); gap:18px; }}
.dashboard-grid {{ display:grid; grid-template-columns:1.15fr .85fr; gap:18px; }}
.stat-grid {{ display:grid; grid-template-columns:repeat(4,minmax(160px,1fr)); gap:14px; margin-bottom:18px; }}
.stat-card {{ position:relative; overflow:hidden; border:1px solid var(--line); border-radius:22px; padding:18px; background:linear-gradient(145deg, rgba(255,255,255,.08), rgba(255,255,255,.03)); min-height:130px; }}
.stat-card:after {{ content:""; position:absolute; right:-34px; bottom:-34px; width:110px; height:110px; border-radius:999px; background:radial-gradient(circle, var(--accent), transparent 68%); opacity:.28; }}
.stat-label {{ color:var(--muted); font-size:13px; }}
.stat-value {{ font-size:34px; font-weight:850; letter-spacing:-.05em; margin:8px 0 2px; }}
.stat-hint {{ color:var(--muted); font-size:12px; }}
.hero-card {{ min-height:260px; background:linear-gradient(135deg, rgba(124,58,237,.26), rgba(34,211,238,.10)), rgba(18,27,46,.82); }}
body.theme-hellforge .hero-card {{ background:linear-gradient(135deg, rgba(249,115,22,.28), rgba(239,68,68,.12)), rgba(18,20,25,.86); }}
.sparkline {{ height:160px; border:1px solid var(--line); border-radius:18px; background:linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.01)); padding:12px; }}
table {{ width:100%; border-collapse:separate; border-spacing:0; font-size:14px; min-width:680px; }}
th,td {{ border-bottom:1px solid var(--line); padding:10px 10px; vertical-align:top; text-align:left; }}
th {{ color:var(--muted); font-weight:650; }}
tr:hover td {{ background:rgba(255,255,255,.025); }}
input,select,textarea,button {{ font:inherit; }}
input,textarea,select {{ width:100%; background:#0b1220; color:var(--text); border:1px solid var(--line); border-radius:12px; padding:10px 11px; outline:none; }}
.ui-form select {{ width:auto; min-width:120px; padding:8px 10px; }}
textarea {{ min-height:78px; font-family:ui-monospace,SFMono-Regular,Consolas,monospace; }}
button,.btn {{ display:inline-flex; align-items:center; justify-content:center; gap:7px; border:0; background:linear-gradient(135deg,var(--accent),var(--accent2)); color:white; padding:10px 13px; border-radius:13px; cursor:pointer; box-shadow:0 10px 24px rgba(0,0,0,.22); font-weight:650; }}
button.danger {{ background:linear-gradient(135deg,#e11d48,#7f1d1d); }}
button.secondary,.btn.secondary {{ background:rgba(255,255,255,.08); color:var(--text); border:1px solid var(--line); box-shadow:none; }}
label {{ display:block; color:var(--muted); margin:10px 0 5px; }}
form.inline {{ display:inline; }}
.actions {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
.actions form {{ margin:0; }}
.flash {{ background:rgba(16,185,129,.16); border:1px solid rgba(16,185,129,.55); color:white; padding:12px 14px; border-radius:15px; margin-bottom:14px; }}
.bad {{ color:var(--bad); }} .good {{ color:var(--good); }} .warn {{ color:var(--warn); }} .muted {{ color:var(--muted); }}
code {{ background:rgba(4,10,22,.80); border:1px solid rgba(255,255,255,.06); padding:2px 6px; border-radius:7px; }}
.small {{ font-size:12px; }}
.pill {{ display:inline-flex; align-items:center; border:1px solid var(--line); border-radius:999px; padding:3px 8px; margin:1px 2px 1px 0; background:rgba(4,10,22,.56); }}
select.compact {{ min-width:180px; }}
td .muted.small {{ line-height:1.35; display:inline-block; }}
.nowrap {{ white-space:nowrap; }}
pre {{ white-space:pre-wrap; background:#0b1220; padding:12px; border-radius:12px; overflow:auto; }}
.audit-card-list {{ display:grid; gap:12px; }}
.audit-card {{ border:1px solid var(--line); border-radius:18px; padding:14px; background:rgba(255,255,255,.04); overflow-wrap:anywhere; }}
.audit-card-head {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; align-items:baseline; }}
.audit-card details pre {{ white-space:pre-wrap; max-height:260px; overflow:auto; }}
@media (max-width: 1100px) {{ .dashboard-grid,.stat-grid {{ grid-template-columns:1fr 1fr; }} .app-layout {{ grid-template-columns:1fr; padding:14px; }} .sidebar {{ position:relative; top:0; height:auto; flex-direction:row; overflow-x:auto; justify-content:flex-start; }} .side-nav {{ flex-direction:row; width:auto; margin-top:0; }} .side-spacer {{ display:none; }} }}
@media (max-width: 760px) {{ .content-shell {{ border-radius:22px; }} .topbar {{ align-items:flex-start; flex-direction:column; padding:18px; }} main {{ padding:16px; }} .title-wrap h1 {{ font-size:24px; }} .stat-grid,.dashboard-grid {{ grid-template-columns:1fr; }} .card {{ padding:14px; border-radius:18px; }} .page-tabs {{ overflow-x:auto; flex-wrap:nowrap; padding-bottom:4px; }} .audit-card .actions {{ display:block; }} .audit-card .actions form,.audit-card .actions button {{ width:100%; }} }}
"""


# ---------------------------------------------------------------------------
# Generic formatting helpers
# ---------------------------------------------------------------------------
def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def h(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


_RESOURCE_CATALOG_CACHE: dict[str, Any] | None = None
_RESOURCE_CATALOG_MTIME: float | None = None
_RESOURCE_CATALOG_PATH: str | None = None

SECTION_LABELS = {
    "resources": "Ressource",
    "currencies": "Währung",
    "weapons": "Waffe",
    "equipment": "Ausrüstung",
    "launchers": "Launcher",
    "ultimates": "Ultimate",
    "slayers": "Slayer",
    "entitlements": "Entitlement",
    "cosmetics": "Kosmetik",
    "energies": "Energie",
}

RESOURCE_CATEGORY_LABELS = {
    1: "Währung/Material",
    2: "Waffe",
    3: "Ausrüstung",
    4: "Launcher",
    5: "Energie",
    6: "Ultimate",
    7: "Slayer",
    8: "Entitlement",
    9: "Kosmetik",
}

SLOT_NAME_OVERRIDES = {
    "slot_primary_weapon": "Primärwaffe",
    "slot_secondary_weapon": "Sekundärwaffe",
    "slot_boots": "Stiefel",
    "slot_gloves": "Handschuhe",
    "slot_helmet": "Helm",
    "slot_torso": "Torso",
    "slot_launcher": "Launcher",
    "slot_ultimate": "Ultimate",
    "slot_slayer": "Slayer",
}

WORD_OVERRIDES = {
    "uac": "UAC",
    "bfg": "BFG",
    "xp": "XP",
    "doom": "DOOM",
    "doomicorn": "Doomicorn",
    "unmaykr": "Unmaykr",
    "gauss": "Gauss",
    "slayer": "Slayer",
    "t60": "T-60",
    "s01": "S01", "s02": "S02", "s03": "S03", "s04": "S04", "s05": "S05",
    "s06": "S06", "s07": "S07", "s08": "S08", "s09": "S09", "s10": "S10",
    "s11": "S11", "s12": "S12", "s13": "S13", "s14": "S14", "s15": "S15",
}

EQUIPPABLE_SECTIONS = ("weapons", "equipment", "launchers", "ultimates", "slayers")
CATALOG_SECTIONS = ("currencies", "weapons", "equipment", "launchers", "ultimates", "slayers", "entitlements", "cosmetics", "energies")


def game_data_path() -> Path:
    """Return the configured game-data.json path.

    The real game-data.json can be large and may contain proprietary game data,
    so this GitHub-ready package does not commit it by default. Place your local
    copy in ./data/game-data.json or pass --game-data /path/to/game-data.json.
    """
    configured = app.config.get("GAME_DATA_PATH") or os.environ.get("MIGHTYDOOM_GAME_DATA")
    if configured:
        return Path(configured).resolve()
    return (Path.cwd() / "data" / "game-data.json").resolve()


def clean_tag(tag: str) -> str:
    return (tag or "").replace("UNUSED - ", "").replace("UNUSED_", "")


def humanize_tag(tag: str) -> str:
    tag = clean_tag(tag)
    if tag.startswith("cosmetic_"):
        tag = tag[len("cosmetic_"):]
    tag = tag.replace("cheat-disk", "cheatdisk")
    tag = re.sub(r"([a-z])([A-Z])", r"\1_\2", tag)
    tag = tag.replace("-", "_")
    words = [w for w in tag.split("_") if w]
    if not words:
        return "Unbenannt"
    out: list[str] = []
    for w in words:
        key = w.lower()
        out.append(WORD_OVERRIDES.get(key, w[:1].upper() + w[1:]))
    return " ".join(out)


def item_name_from_tag(tag: str, section: str) -> str:
    tag = clean_tag(tag)
    parts = [p for p in re.sub(r"([a-z])([A-Z])", r"\1_\2", tag).replace("-", "_").split("_") if p]
    if section == "equipment" and parts:
        slot_word = parts[0].lower()
        rest = "_".join(parts[1:])
        slot_names = {
            "chest": "Chest",
            "helmet": "Helmet",
            "boots": "Boots",
            "gauntlets": "Gauntlets",
        }
        if slot_word in slot_names and rest:
            return f"{humanize_tag(rest)} {slot_names[slot_word]}"
    if section == "cosmetics":
        return f"{humanize_tag(tag)} Skin"
    if tag == "mini_slayer_default":
        return "Mini Slayer"
    return humanize_tag(tag)


def _availability_label(value: Any) -> str:
    labels = {1: "intern", 2: "bedingt", 3: "verfügbar", 5: "unused/deaktiviert"}
    try:
        return labels.get(int(value), str(value))
    except Exception:
        return str(value or "")


def _build_empty_catalog(path: Path, error: str | None = None) -> dict[str, Any]:
    return {
        "path": str(path),
        "loaded": False,
        "error": error,
        "resources_by_id": {},
        "resources_list": [],
        "slots_by_id": {},
        "slots_by_type": {},
        "talents_by_id": {},
        "stats_by_id": {},
        "event_definitions": [],
        "event_definitions_by_key": {},
    }


def _build_resource_description(entry: dict[str, Any], info: dict[str, Any], catalog: dict[str, Any]) -> str:
    parts: list[str] = []
    tag = info.get("tag") or entry.get("tag") or ""
    category = info.get("category_label") or info.get("section_label") or "Ressource"
    parts.append(f"{category}: {tag}")
    slot_text = info.get("compatible_slot_text")
    if slot_text:
        parts.append(f"kompatibel mit {slot_text}")
    if entry.get("token") is not None:
        token = resource_info(entry.get("token"), catalog)
        parts.append(f"Upgrade-Token: {token['name']} (RID {token['id']})")
    if entry.get("compatible_resource") is not None:
        target = resource_info(entry.get("compatible_resource"), catalog)
        parts.append(f"Skin/Zusatz für {target['name']} (RID {target['id']})")
    if entry.get("availability") is not None:
        parts.append(f"Availability: {_availability_label(entry.get('availability'))}")
    return "; ".join(parts) + "."


def _load_resource_catalog() -> dict[str, Any]:
    path = game_data_path()
    if not path.exists():
        return _build_empty_catalog(path, f"game-data.json nicht gefunden: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _build_empty_catalog(path, f"game-data.json konnte nicht gelesen werden: {exc}")

    catalog = _build_empty_catalog(path)
    catalog["loaded"] = True
    catalog["raw"] = data

    for slot in data.get("inventory", {}).get("slots", []):
        try:
            slot_id = int(slot["id"])
            slot_type = int(slot.get("type"))
        except Exception:
            continue
        tag = slot.get("tag", "")
        label = SLOT_NAME_OVERRIDES.get(tag, humanize_tag(tag.replace("slot_", "")))
        slot_info = {
            "id": slot_id,
            "type": slot_type,
            "tag": tag,
            "label": label,
            "attribute_set": slot.get("attribute_set"),
        }
        catalog["slots_by_id"][slot_id] = slot_info
        catalog["slots_by_type"].setdefault(slot_type, []).append(slot_info)

    resources: dict[int, dict[str, Any]] = {}

    def put_resource(rid: int, values: dict[str, Any]) -> None:
        current = resources.get(rid, {"id": rid})
        current.update(values)
        resources[rid] = current

    for entry in data.get("resources", []):
        try:
            rid = int(entry["id"])
        except Exception:
            continue
        cat_id = entry.get("category")
        put_resource(rid, {
            "id": rid,
            "tag": entry.get("tag", ""),
            "name": item_name_from_tag(entry.get("tag", ""), "resources"),
            "section": "resources",
            "section_label": "Ressource",
            "category_id": cat_id,
            "category_label": RESOURCE_CATEGORY_LABELS.get(cat_id, f"Kategorie {cat_id}"),
            "value": entry.get("value"),
            "equippable": False,
            "cosmetic": False,
        })

    # Currencies/energies enrich the raw resource list.
    for section in ("currencies", "energies", "entitlements"):
        for entry in data.get(section, []):
            try:
                rid = int(entry["id"])
            except Exception:
                continue
            base = resources.get(rid, {})
            put_resource(rid, {
                "id": rid,
                "tag": entry.get("tag", base.get("tag", "")),
                "name": item_name_from_tag(entry.get("tag", base.get("tag", "")), section),
                "section": section,
                "section_label": SECTION_LABELS.get(section, section),
                "category_label": SECTION_LABELS.get(section, section),
                "availability": entry.get("availability"),
                "value": entry.get("value", base.get("value")),
                "equippable": False,
                "cosmetic": False,
            })

    # Equippable items contain the slot type; inventory_slots stores the slot id.
    for section in EQUIPPABLE_SECTIONS:
        for entry in data.get(section, []):
            try:
                rid = int(entry["id"])
            except Exception:
                continue
            slot_type = entry.get("slot")
            compatible_slots: list[dict[str, Any]] = []
            if slot_type is not None:
                try:
                    compatible_slots = list(catalog["slots_by_type"].get(int(slot_type), []))
                except Exception:
                    compatible_slots = []
            compatible_slot_ids = [s["id"] for s in compatible_slots]
            compatible_slot_text = ", ".join(f"Slot {s['id']} · {s['label']}" for s in compatible_slots)
            slot_label = compatible_slots[0]["label"] if compatible_slots else ""
            category_label = slot_label or SECTION_LABELS.get(section, section)
            put_resource(rid, {
                "id": rid,
                "tag": entry.get("tag", ""),
                "name": item_name_from_tag(entry.get("tag", ""), section),
                "section": section,
                "section_label": SECTION_LABELS.get(section, section),
                "category_label": category_label,
                "availability": entry.get("availability"),
                "value": entry.get("value"),
                "slot_type": slot_type,
                "slot_label": slot_label,
                "compatible_slot_ids": compatible_slot_ids,
                "compatible_slot_text": compatible_slot_text,
                "token": entry.get("token"),
                "equippable": True,
                "cosmetic": False,
            })

    for entry in data.get("cosmetics", []):
        try:
            rid = int(entry["id"])
        except Exception:
            continue
        compatible = entry.get("compatible_resource")
        target = resource_info(compatible, {**catalog, "resources_by_id": resources}) if compatible is not None else None
        target_text = f" für {target['name']}" if target else ""
        put_resource(rid, {
            "id": rid,
            "tag": entry.get("tag", ""),
            "name": item_name_from_tag(entry.get("tag", ""), "cosmetics"),
            "section": "cosmetics",
            "section_label": "Kosmetik",
            "category_label": "Kosmetik" + target_text,
            "availability": entry.get("availability"),
            "value": entry.get("value"),
            "target": entry.get("target"),
            "compatible_resource": compatible,
            "purchase_hint": entry.get("purchase_hint"),
            "equippable": False,
            "cosmetic": True,
        })

    catalog["resources_by_id"] = resources
    # Add descriptions after every resource is known.
    for rid, info in resources.items():
        info["description"] = _build_resource_description(info, info, catalog)

    catalog["resources_list"] = sorted(resources.values(), key=lambda x: (str(x.get("section_label", "")), str(x.get("category_label", "")), str(x.get("name", "")), int(x.get("id", 0))))

    for talent in data.get("talents", {}).get("talents", []):
        try:
            tid = int(talent["id"])
        except Exception:
            continue
        catalog["talents_by_id"][tid] = {
            "id": tid,
            "tag": talent.get("tag", ""),
            "name": humanize_tag(talent.get("tag", "")),
            "description": f"Talent: {talent.get('tag', '')}",
        }

    for stat in data.get("stats", []):
        try:
            sid = int(stat["id"])
        except Exception:
            continue
        catalog["stats_by_id"][sid] = {
            "id": sid,
            "tag": stat.get("tag", ""),
            "name": humanize_tag(stat.get("tag", "")),
            "description": f"Stat: {stat.get('tag', '')}; Kategorie {stat.get('category')}; Source {stat.get('update_source')}",
        }

    return catalog


def get_catalog() -> dict[str, Any]:
    global _RESOURCE_CATALOG_CACHE, _RESOURCE_CATALOG_MTIME, _RESOURCE_CATALOG_PATH
    path = game_data_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    path_text = str(path)
    if _RESOURCE_CATALOG_CACHE is None or _RESOURCE_CATALOG_MTIME != mtime or _RESOURCE_CATALOG_PATH != path_text:
        _RESOURCE_CATALOG_CACHE = _load_resource_catalog()
        _RESOURCE_CATALOG_MTIME = mtime
        _RESOURCE_CATALOG_PATH = path_text
    return _RESOURCE_CATALOG_CACHE




# ---------------------------------------------------------------------------
# Event catalog and admin event schedule helpers
# ---------------------------------------------------------------------------
EVENT_TYPE_LABELS = {
    1: "GameMode",
    2: "StoreOffer",
    3: "BattlePass",
}


def _to_int_or_none(value: Any) -> int | None:
    """Return an integer when a value is safely integer-like."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _safe_json_loads(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _normalize_stage_rewards(value: Any) -> list[dict[str, Any]]:
    """Normalize reward rows to the stage/resources/loot_rolls shape used by the client."""
    raw = value if isinstance(value, list) else []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        stage = _to_int_or_none(item.get("stage"))
        if stage is None:
            continue
        resources = item.get("resources") if isinstance(item.get("resources"), list) else []
        normalized_resources = []
        for res in resources:
            if not isinstance(res, dict):
                continue
            rid = _to_int_or_none(res.get("rid"))
            amount = _to_int_or_none(res.get("amount"))
            if rid is None or amount is None:
                continue
            normalized_resources.append({"rid": rid, "amount": amount})
        loot_rolls = item.get("loot_rolls") if isinstance(item.get("loot_rolls"), list) else []
        row = {"stage": stage, "resources": normalized_resources, "loot_rolls": loot_rolls}
        if isinstance(item.get("vip_resources"), list):
            row["vip_resources"] = item["vip_resources"]
        out.append(row)
    return sorted(out, key=lambda x: int(x.get("stage") or 0))


def _event_stage_count(entry: dict[str, Any]) -> int | None:
    for key in ("stage_rewards", "stage_scalars", "stages"):
        value = entry.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, int):
            return value
    info = entry.get("chapter_progression_info")
    if isinstance(info, list) and info:
        # Event chapters often contain one progression block per chapter and a separate
        # stage_scalars array per stage. When only progression data is present, this is
        # still useful as a rough count for the admin catalog.
        return len(info)
    return None


def _infer_event_type(path: str, entry: dict[str, Any]) -> int | None:
    explicit = _to_int_or_none(entry.get("event_type"))
    if explicit in EVENT_TYPE_LABELS:
        return explicit
    hay = f"{path} {entry.get('tag', '')}".lower()
    if "store_offer" in hay or "storeoffer" in hay:
        return 2
    if "battle_pass" in hay or "battlepass" in hay:
        return 3
    if "game_mode" in hay or "gamemode" in hay:
        return 1
    if any(k in entry for k in ("allowed_attempts", "stage_scalars", "chapter_progression_info", "event_modifiers")):
        return 1
    return None


def _event_title(entry: dict[str, Any], tag: str) -> str:
    for key in ("title", "name", "title_key", "name_key", "display_name", "loc_key"):
        value = entry.get(key)
        if value not in (None, ""):
            return str(value)
    return humanize_tag(tag) if tag else "Unbenanntes Event"


def _event_description(entry: dict[str, Any]) -> str:
    for key in ("description", "description_key", "desc_key", "subtitle", "body_key"):
        value = entry.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _event_definition_id(entry: dict[str, Any]) -> str | None:
    for key in ("event_definition_id", "definition_id", "id"):
        value = entry.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _default_event_args(entry: dict[str, Any], event_type: int) -> dict[str, Any]:
    """Build editable args_json for admin-created scheduled events."""
    if isinstance(entry.get("args"), dict):
        return entry["args"]
    if event_type == 1:
        return {
            "additional_event_modifiers": list(entry.get("event_modifiers") or []),
            "stage_rewards": _normalize_stage_rewards(entry.get("stage_rewards")),
        }
    return {}


def build_event_catalog_from_game_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Find event definitions even when game-data.json stores them in different places.

    The official data layout changed over time. This scanner first picks up known
    Mighty DOOM keys and then recursively scans dictionaries/lists whose path or
    fields look like event definitions. Results are de-duplicated by event type,
    definition id and tag.
    """
    found: dict[str, dict[str, Any]] = {}

    def add(entry: dict[str, Any], path: str, forced_type: int | None = None) -> None:
        event_type = forced_type or _infer_event_type(path, entry)
        if event_type not in EVENT_TYPE_LABELS:
            return
        definition_id = _event_definition_id(entry)
        tag = str(entry.get("tag") or entry.get("name") or "")
        if not definition_id and not tag:
            return
        key = f"{event_type}:{definition_id or ''}:{tag}"
        if key in found:
            return
        args = _default_event_args(entry, event_type)
        found[key] = {
            "catalog_key": key,
            "event_definition_id": definition_id or tag,
            "event_type": event_type,
            "event_type_label": EVENT_TYPE_LABELS[event_type],
            "tag": tag,
            "title": _event_title(entry, tag),
            "description": _event_description(entry),
            "stage_count": _event_stage_count(entry),
            "source_path": path,
            "default_args_json": args,
            "raw": entry,
        }

    events = data.get("events") if isinstance(data.get("events"), dict) else {}
    for entry in events.get("game_mode_event_definitions", []) if isinstance(events.get("game_mode_event_definitions"), list) else []:
        if isinstance(entry, dict):
            add(entry, "events.game_mode_event_definitions", 1)
    for entry in events.get("store_offer_events", []) if isinstance(events.get("store_offer_events"), list) else []:
        if isinstance(entry, dict):
            add(entry, "events.store_offer_events", 2)
    for entry in data.get("story_battle_passes", []) if isinstance(data.get("story_battle_passes"), list) else []:
        if isinstance(entry, dict):
            add(entry, "story_battle_passes", 3)
    bp_definition_id = events.get("battle_pass_event_definition_id")
    if bp_definition_id is not None:
        add({"event_definition_id": bp_definition_id, "tag": "battle_pass_event", "title": "Battle Pass Event"}, "events.battle_pass_event_definition_id", 3)

    def walk(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            if ("event" in path.lower() or "event_type" in obj or "event_definition_id" in obj) and ("id" in obj or "event_definition_id" in obj) and ("tag" in obj or "event_type" in obj):
                add(obj, path)
            for key, value in obj.items():
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(obj, list):
            for idx, value in enumerate(obj):
                walk(value, f"{path}[{idx}]")

    walk(data, "")
    return sorted(found.values(), key=lambda e: (e["event_type"], str(e.get("tag") or ""), str(e.get("event_definition_id") or "")))


def event_catalog() -> list[dict[str, Any]]:
    catalog = get_catalog()
    if not catalog.get("loaded"):
        return []
    cached = catalog.get("event_definitions")
    if cached:
        return cached
    raw = catalog.get("raw") or {}
    events = build_event_catalog_from_game_data(raw if isinstance(raw, dict) else {})
    catalog["event_definitions"] = events
    catalog["event_definitions_by_key"] = {str(e["catalog_key"]): e for e in events}
    return events


def event_definition_by_key(catalog_key: str) -> dict[str, Any] | None:
    for event in event_catalog():
        if str(event.get("catalog_key")) == str(catalog_key):
            return event
    return None


def event_definition_by_schedule_row(schedule: sqlite3.Row | dict[str, Any]) -> dict[str, Any] | None:
    definition_id = str(schedule["event_definition_id"])
    event_type = _to_int_or_none(schedule["event_type"])
    tag = str(schedule["tag"] or "")
    for event in event_catalog():
        if event_type is not None and _to_int_or_none(event.get("event_type")) != event_type:
            continue
        if str(event.get("event_definition_id")) == definition_id or (tag and event.get("tag") == tag):
            return event
    return None


def event_catalog_options(selected_key: str | None = None, only_type: int | None = None) -> str:
    groups: dict[str, list[dict[str, Any]]] = {}
    for event in event_catalog():
        if only_type is not None and int(event.get("event_type") or 0) != only_type:
            continue
        groups.setdefault(str(event.get("event_type_label") or "Event"), []).append(event)
    parts: list[str] = []
    for group, events in sorted(groups.items()):
        opts = []
        for event in events:
            key = str(event.get("catalog_key"))
            label = f"{event.get('event_definition_id')} · {event.get('title')} · {event.get('tag')}"
            opts.append(f'<option value="{h(key)}" {"selected" if key == selected_key else ""}>{h(label)}</option>')
        parts.append(f'<optgroup label="{h(group)}">{"".join(opts)}</optgroup>')
    return "".join(parts)


def _parse_datetime_to_iso(value: str | None, fallback: dt.datetime | None = None) -> str:
    if not value:
        value_dt = fallback or dt.datetime.now(dt.timezone.utc)
        return value_dt.replace(microsecond=0).isoformat()
    text = value.strip()
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        parsed = fallback or dt.datetime.now(dt.timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()


def _iso_to_unix_seconds(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return int(parsed.timestamp())
    except Exception:
        try:
            return int(value)
        except Exception:
            return None


def _iso_for_datetime_input(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")
    except Exception:
        return str(value)[:16]



def is_valid_uuid(value: Any) -> bool:
    """Return True when value is a syntactically valid UUID string."""
    if value in (None, ""):
        return False
    try:
        parsed = uuid.UUID(str(value))
        return str(parsed) == str(value).strip().lower()
    except Exception:
        return False


def new_scheduled_event_uuid() -> str:
    """Create a new stable scheduled_event_id for the game server."""
    return str(uuid.uuid4())


def valid_or_new_uuid(value: Any) -> str:
    """Keep an incoming UUID only when it is valid, otherwise create a new one."""
    return str(value).strip().lower() if is_valid_uuid(value) else new_scheduled_event_uuid()


def _event_progress_where_for_schedule(schedule: sqlite3.Row | dict[str, Any]) -> tuple[str, list[Any]]:
    """Build the SQL filter that matches progress for one schedule row.

    Progress is intentionally joined through scheduled_event_id, not through the
    internal admin_event_schedule.id. For user-specific schedules we also filter
    by user_id so progress from other users sharing the same event UUID does not
    appear on the wrong detail page.
    """
    scheduled_event_id = schedule["scheduled_event_id"]
    user_id = schedule["user_id"]
    if user_id is None:
        return "scheduled_event_id=?", [scheduled_event_id]
    return "scheduled_event_id=? AND user_id=?", [scheduled_event_id, user_id]


def reset_event_progress_defaults(con: sqlite3.Connection, scheduled_event_id: str, user_id: int | None = None, reset_all: bool = False) -> int:
    """Reset event progress to the default empty state expected by the client.

    The game server writes progress using (scheduled_event_id, user_id). The admin
    UI therefore resets progress by the same pair and never by the internal admin
    schedule row id.
    """
    now = now_iso()
    if reset_all:
        return con.execute(
            """
            UPDATE admin_event_progress
            SET attempts=0, highest_stage=0, best_completion_time_milliseconds=0, run_json=NULL, updated_at=?
            WHERE scheduled_event_id=?
            """,
            [now, scheduled_event_id],
        ).rowcount
    if user_id is None:
        return 0
    updated = con.execute(
        """
        UPDATE admin_event_progress
        SET attempts=0, highest_stage=0, best_completion_time_milliseconds=0, run_json=NULL, updated_at=?
        WHERE scheduled_event_id=? AND user_id=?
        """,
        [now, scheduled_event_id, user_id],
    ).rowcount
    if updated:
        return updated
    con.execute(
        """
        INSERT INTO admin_event_progress(
            scheduled_event_id, user_id, attempts, highest_stage, best_completion_time_milliseconds, run_json, updated_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        [scheduled_event_id, user_id, 0, 0, 0, None, now],
    )
    return 1


def migrate_event_schedule_uuid_ids(con: sqlite3.Connection) -> dict[str, Any]:
    """Repair legacy scheduled_event_id values and move matching progress rows.

    Older admin builds generated values like ``admin-1-8-...``. The game server
    now expects a real UUID and stores progress under exactly that UUID. This
    migration fixes schedule rows and migrates matching progress when the mapping
    is unambiguous. Progress that cannot be mapped safely is left untouched and
    can still be displayed as unassigned progress in the UI.
    """
    schedule_rows = con.execute("SELECT * FROM admin_event_schedule ORDER BY id").fetchall()
    progress_rows = con.execute("SELECT * FROM admin_event_progress ORDER BY id").fetchall()
    now = now_iso()
    updated_schedules = 0
    migrated_progress = 0
    ambiguous_progress = 0

    # Keep UUIDs stable within one legacy scheduled_event_id when it was clearly
    # one shared event. If the same legacy id is used by multiple user-specific
    # rows, progress is mapped by user_id below.
    old_to_rows: dict[str, list[sqlite3.Row]] = {}
    row_id_to_uuid: dict[str, str] = {}
    user_specific_map: dict[tuple[str, int], str] = {}
    global_map: dict[str, str] = {}
    single_map: dict[str, str] = {}

    for sched in schedule_rows:
        sid = str(sched["scheduled_event_id"] or "")
        if is_valid_uuid(sid):
            row_id_to_uuid[str(sched["id"])] = sid
        else:
            old_to_rows.setdefault(sid, []).append(sched)

    for old_sid, scheds in old_to_rows.items():
        if len(scheds) == 1:
            single_map[old_sid] = new_scheduled_event_uuid()
        for sched in scheds:
            new_uuid = single_map.get(old_sid) or new_scheduled_event_uuid()
            row_id_to_uuid[str(sched["id"])] = new_uuid
            if sched["user_id"] is None:
                global_map[old_sid] = new_uuid
            else:
                try:
                    user_specific_map[(old_sid, int(sched["user_id"]))] = new_uuid
                except Exception:
                    pass
            con.execute(
                "UPDATE admin_event_schedule SET scheduled_event_id=?, updated_at=? WHERE id=?",
                [new_uuid, now, sched["id"]],
            )
            updated_schedules += 1

    # Progress sometimes used the legacy scheduled_event_id and sometimes a
    # numeric admin_event_schedule.id. Handle both where it is safe.
    for pr in progress_rows:
        old_sid = str(pr["scheduled_event_id"] or "")
        if is_valid_uuid(old_sid):
            continue
        target_uuid = None
        user_id = int(pr["user_id"])
        if (old_sid, user_id) in user_specific_map:
            target_uuid = user_specific_map[(old_sid, user_id)]
        elif old_sid in single_map:
            target_uuid = single_map[old_sid]
        elif old_sid in global_map:
            target_uuid = global_map[old_sid]
        elif old_sid in row_id_to_uuid:
            target_uuid = row_id_to_uuid[old_sid]
        if target_uuid:
            # Merge into an existing correct row if the game server already wrote
            # one, otherwise simply move the legacy row.
            existing = con.execute(
                "SELECT id FROM admin_event_progress WHERE scheduled_event_id=? AND user_id=?",
                [target_uuid, user_id],
            ).fetchone()
            if existing:
                con.execute("DELETE FROM admin_event_progress WHERE id=?", [pr["id"]])
            else:
                con.execute(
                    "UPDATE admin_event_progress SET scheduled_event_id=?, updated_at=? WHERE id=?",
                    [target_uuid, now, pr["id"]],
                )
            migrated_progress += 1
        else:
            ambiguous_progress += 1

    return {
        "updated_schedules": updated_schedules,
        "migrated_progress": migrated_progress,
        "unassigned_progress": ambiguous_progress,
    }


def unassigned_event_progress_rows(con: sqlite3.Connection, limit: int = 100) -> list[sqlite3.Row]:
    """Return progress rows that do not currently match any schedule UUID."""
    return con.execute(
        """
        SELECT p.*
        FROM admin_event_progress p
        LEFT JOIN admin_event_schedule s ON s.scheduled_event_id=p.scheduled_event_id
        WHERE s.id IS NULL
        ORDER BY p.updated_at DESC, p.id DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()

def _admin_events_export_path() -> Path:
    configured = app.config.get("ADMIN_EVENTS_EXPORT_PATH") or os.environ.get("MIGHTYDOOM_ADMIN_EVENTS_EXPORT")
    if configured:
        return Path(configured).resolve()
    return (Path.cwd() / "data" / "admin-events.json").resolve()


def default_test_stage_rewards() -> list[dict[str, Any]]:
    return [
        {"stage": 5, "resources": [{"rid": 1, "amount": 2500}], "loot_rolls": []},
        {"stage": 10, "resources": [{"rid": 1, "amount": 5000}], "loot_rolls": []},
        {"stage": 15, "resources": [{"rid": 1, "amount": 7500}], "loot_rolls": []},
        {"stage": 20, "resources": [{"rid": 1, "amount": 10000}], "loot_rolls": []},
    ]


def _args_from_editor_form(form: Any) -> dict[str, Any]:
    args = _safe_json_loads(form.get("args_json"), {})
    if not isinstance(args, dict):
        args = {}
    modifiers_text = str(form.get("additional_event_modifiers") or "").strip()
    modifiers: list[int] = []
    if modifiers_text:
        for part in re.split(r"[,\s]+", modifiers_text):
            num = _to_int_or_none(part)
            if num is not None:
                modifiers.append(num)
    args["additional_event_modifiers"] = modifiers
    rewards: list[dict[str, Any]] = []
    for stage, rid, amount in zip(form.getlist("reward_stage"), form.getlist("reward_rid"), form.getlist("reward_amount")):
        stage_i = _to_int_or_none(stage)
        rid_i = _to_int_or_none(rid)
        amount_i = _to_int_or_none(amount)
        if stage_i is None or rid_i is None or amount_i is None:
            continue
        rewards.append({"stage": stage_i, "resources": [{"rid": rid_i, "amount": amount_i}], "loot_rolls": []})
    args["stage_rewards"] = _normalize_stage_rewards(rewards)
    return args


def _stage_rewards_editor_html(args: dict[str, Any]) -> str:
    rewards = _normalize_stage_rewards(args.get("stage_rewards"))
    while len(rewards) < 4:
        rewards.append({"stage": "", "resources": [{"rid": 1, "amount": ""}], "loot_rolls": []})
    rows_html = []
    for item in rewards[:20]:
        res = item.get("resources", [{}])[0] if isinstance(item.get("resources"), list) and item.get("resources") else {}
        rows_html.append(f"""
<tr>
  <td><input name="reward_stage" type="number" min="1" value="{h(item.get('stage', ''))}"></td>
  <td><select name="reward_rid">{simple_key_options('currencies', 'rid', selected=res.get('rid', 1))}</select></td>
  <td><input name="reward_amount" type="number" min="0" value="{h(res.get('amount', ''))}"></td>
  <td><span class="muted small">prepared: loot_rolls []</span></td>
</tr>""")
    return f"""
<table>
<thead><tr><th>Stage</th><th>Ressourcen/RID</th><th>Amount</th><th>Loot Rolls</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table>"""


def _event_schedule_badges(item: sqlite3.Row | dict[str, Any]) -> str:
    now_ts = int(dt.datetime.now(dt.timezone.utc).timestamp())
    start_ts = _iso_to_unix_seconds(item["start_time"])
    end_ts = _iso_to_unix_seconds(item["end_time"])
    badges = []
    badges.append('<span class="pill good">aktiv</span>' if int(item["is_active"] or 0) else '<span class="pill muted">inaktiv</span>')
    badges.append('<span class="pill">global</span>' if item["user_id"] is None else '<span class="pill warn">user-spezifisch</span>')
    if end_ts is not None and end_ts < now_ts:
        badges.append('<span class="pill bad">abgelaufen</span>')
    elif start_ts is not None and start_ts > now_ts:
        badges.append('<span class="pill warn">geplant</span>')
    else:
        badges.append('<span class="pill good">läuft</span>')
    return " ".join(badges)


def _event_schedule_rows(limit: int = 500) -> list[sqlite3.Row]:
    return rows(
        """
        SELECT s.*,
          (SELECT COUNT(DISTINCT p.user_id)
             FROM admin_event_progress p
             WHERE p.scheduled_event_id=s.scheduled_event_id
               AND (s.user_id IS NULL OR p.user_id=s.user_id)) AS progress_count,
          (SELECT COUNT(DISTINCT p.user_id)
             FROM admin_event_progress p
             WHERE p.scheduled_event_id=s.scheduled_event_id
               AND (s.user_id IS NULL OR p.user_id=s.user_id)
               AND COALESCE(p.best_completion_time_milliseconds,0) > 0) AS completed_count,
          (SELECT COALESCE(MAX(p.highest_stage), 0)
             FROM admin_event_progress p
             WHERE p.scheduled_event_id=s.scheduled_event_id
               AND (s.user_id IS NULL OR p.user_id=s.user_id)) AS max_highest_stage
        FROM admin_event_schedule s
        ORDER BY s.is_active DESC, s.start_time DESC, s.id DESC
        LIMIT ?
        """,
        [limit],
    )


def export_admin_events_json(con: sqlite3.Connection) -> Path:
    """Write data/admin-events.json for the optional Node.js game server integration."""
    schedule_rows = con.execute("SELECT * FROM admin_event_schedule WHERE is_active=1 ORDER BY start_time, id").fetchall()
    progress_rows = con.execute("SELECT * FROM admin_event_progress ORDER BY updated_at DESC, id DESC").fetchall()
    scheduled_events = []
    for r in schedule_rows:
        args_obj = _safe_json_loads(r["args_json"], {})
        args_compact = json.dumps(args_obj, ensure_ascii=False, separators=(",", ":"))
        scheduled_events.append({
            "admin_schedule_id": r["id"],
            "id": r["scheduled_event_id"],
            "scheduled_event_id": r["scheduled_event_id"],
            "event_definition_id": _to_int_or_none(r["event_definition_id"]) if _to_int_or_none(r["event_definition_id"]) is not None else r["event_definition_id"],
            "event_type": int(r["event_type"] or 1),
            "tag": r["tag"],
            "title": r["title"],
            "user_id": r["user_id"],
            "start_time": _iso_to_unix_seconds(r["start_time"]),
            "end_time": _iso_to_unix_seconds(r["end_time"]),
            "availability": int(r["availability"] or 1),
            "min_api_version": r["min_api_version"],
            "max_api_version": r["max_api_version"],
            "stop_time": _iso_to_unix_seconds(r["stop_time"]),
            "args": base64.b64encode(args_compact.encode("utf-8")).decode("ascii"),
            "args_json": args_obj,
        })
    payload = {
        "schema": "mightydoom-admin-events/v1",
        "generated_at": now_iso(),
        "source": APP_TITLE,
        "scheduled_events": scheduled_events,
        "progress": [_rows_to_plain_dict(p) for p in progress_rows],
    }
    path = _admin_events_export_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _rows_to_plain_dict(row_value: sqlite3.Row) -> dict[str, Any]:
    return {k: row_value[k] for k in row_value.keys()}


def create_event_schedule_from_payload(con: sqlite3.Connection, payload: dict[str, Any]) -> int:
    """Create one or more admin_event_schedule rows and return the first row id."""
    catalog_key = str(payload.get("catalog_key") or "")
    event = event_definition_by_key(catalog_key)
    if event is None:
        raise ValueError("Event-Definition nicht gefunden.")
    start_iso = _parse_datetime_to_iso(payload.get("start_time"), dt.datetime.now(dt.timezone.utc))
    end_iso = _parse_datetime_to_iso(payload.get("end_time"), dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7))
    availability = int(payload.get("availability") or 1)
    args = payload.get("args_json") if isinstance(payload.get("args_json"), dict) else event.get("default_args_json") or {}
    if payload.get("use_test_rewards"):
        args = dict(args)
        args["stage_rewards"] = default_test_stage_rewards()
    user_ids: list[int | None] = [None]
    if payload.get("scope") == "users":
        user_ids = []
        for part in re.split(r"[,;\s]+", str(payload.get("user_ids") or "")):
            user_id = _to_int_or_none(part)
            if user_id is not None:
                user_ids.append(user_id)
        if not user_ids:
            raise ValueError("Für user-spezifische Events muss mindestens eine User-ID angegeben werden.")
    scheduled_event_id = valid_or_new_uuid(payload.get("scheduled_event_id"))
    created_ids: list[int] = []
    for user_id in user_ids:
        con.execute(
            """
            INSERT INTO admin_event_schedule(
                scheduled_event_id, event_definition_id, event_type, tag, title, user_id,
                start_time, end_time, availability, min_api_version, max_api_version, stop_time,
                args_json, is_active, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                scheduled_event_id,
                str(event.get("event_definition_id")),
                int(event.get("event_type") or 1),
                event.get("tag"),
                event.get("title"),
                user_id,
                start_iso,
                end_iso,
                availability,
                payload.get("min_api_version") or None,
                payload.get("max_api_version") or None,
                _parse_datetime_to_iso(payload.get("stop_time"), None) if payload.get("stop_time") else None,
                json.dumps(args, ensure_ascii=False, separators=(",", ":")),
                1 if str(payload.get("is_active", "1")) != "0" else 0,
                now_iso(),
                now_iso(),
            ],
        )
        created_ids.append(int(con.execute("SELECT last_insert_rowid()").fetchone()[0]))
        if user_id is not None:
            reset_event_progress_defaults(con, scheduled_event_id, int(user_id), reset_all=False)
    return created_ids[0]


def resource_info(rid: Any, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    catalog = catalog or get_catalog()
    try:
        key = int(rid)
    except Exception:
        return {"id": rid, "name": "", "tag": "", "category_label": "", "description": ""}
    found = catalog.get("resources_by_id", {}).get(key)
    if found:
        return found
    return {
        "id": key,
        "name": f"RID {key}",
        "tag": "",
        "category_label": "Unbekannt",
        "section_label": "Unbekannt",
        "description": "Keine Zuordnung in game-data.json gefunden.",
        "compatible_slot_ids": [],
        "compatible_slot_text": "",
        "equippable": False,
        "cosmetic": False,
    }


def lookup_info(kind: str, ident: Any) -> dict[str, Any]:
    catalog = get_catalog()
    try:
        key = int(ident)
    except Exception:
        return {"id": ident, "name": "", "tag": ""}
    maps = {
        "resource": catalog.get("resources_by_id", {}),
        "talent": catalog.get("talents_by_id", {}),
        "stat": catalog.get("stats_by_id", {}),
    }
    found = maps.get(kind, {}).get(key)
    if found:
        return found
    return {"id": key, "name": f"{kind} {key}", "tag": ""}


def resource_label(rid: Any, compact: bool = False) -> str:
    info = resource_info(rid)
    if compact:
        return f"{info['name']} (RID {info['id']})"
    extra = []
    if info.get("category_label"):
        extra.append(str(info["category_label"]))
    if info.get("tag"):
        extra.append(str(info["tag"]))
    suffix = " · ".join(extra)
    return f"{info['name']} (RID {info['id']})" + (f" · {suffix}" if suffix else "")


def slot_label(slot_id: Any) -> str:
    try:
        sid = int(slot_id)
    except Exception:
        return str(slot_id or "")
    slot = get_catalog().get("slots_by_id", {}).get(sid)
    if slot:
        return f"Slot {sid} · {slot['label']}"
    return f"Slot {sid}"


def compatible_slot_ids_for_rid(rid: Any) -> list[int]:
    info = resource_info(rid)
    return [int(x) for x in info.get("compatible_slot_ids", [])]


def option_selected(value: Any, selected: Any) -> str:
    return " selected" if str(value) == str(selected) else ""


def grouped_resource_options(only_equippable: bool = False, only_cosmetics: bool = False, selected: Any = None, include_blank: bool = False) -> str:
    catalog = get_catalog()
    resources = catalog.get("resources_list", [])
    groups: dict[str, list[dict[str, Any]]] = {}
    for info in resources:
        if only_equippable and not info.get("equippable"):
            continue
        if only_cosmetics and not info.get("cosmetic"):
            continue
        if not only_cosmetics and info.get("cosmetic") and only_equippable:
            continue
        group = str(info.get("category_label") or info.get("section_label") or "Sonstiges")
        groups.setdefault(group, []).append(info)
    out: list[str] = []
    if include_blank:
        out.append(f'<option value=""{option_selected("", selected)}>— leer / NULL —</option>')
    for group in sorted(groups):
        out.append(f'<optgroup label="{h(group)}">')
        for info in sorted(groups[group], key=lambda x: (str(x.get("name", "")), int(x.get("id", 0)))):
            label = f"{info.get('name')} — RID {info.get('id')}"
            if info.get("compatible_slot_text"):
                label += f" — {info.get('compatible_slot_text')}"
            if info.get("availability") == 5 or str(info.get("tag", "")).startswith("UNUSED"):
                label += " — UNUSED"
            out.append(f'<option value="{h(info.get("id"))}"{option_selected(info.get("id"), selected)}>{h(label)}</option>')
        out.append('</optgroup>')
    if not out:
        out.append('<option value="">game-data.json nicht geladen</option>')
    return "".join(out)


def slot_options(selected: Any = None, include_blank: bool = False, compatible_ids: list[int] | None = None) -> str:
    catalog = get_catalog()
    out: list[str] = []
    if include_blank:
        out.append(f'<option value=""{option_selected("", selected)}>— nicht equippen / leer —</option>')
    allowed = set(int(x) for x in compatible_ids) if compatible_ids else None
    for sid, slot in sorted(catalog.get("slots_by_id", {}).items()):
        if allowed is not None and sid not in allowed:
            continue
        out.append(f'<option value="{sid}"{option_selected(sid, selected)}>{h(slot_label(sid))}</option>')
    if not out or (include_blank and len(out) == 1):
        out.append('<option value="">keine Slots aus game-data.json</option>')
    return "".join(out)


def item_instance_label(item: sqlite3.Row | dict[str, Any] | None, include_id: bool = True) -> str:
    if not item:
        return "unbekanntes Item"
    info = resource_info(item["rid"])
    parts = []
    if include_id:
        parts.append(f"#{item['id']}")
    parts.append(str(info.get("name") or f"RID {item['rid']}"))
    if item["tier"] is not None:
        parts.append(f"T{item['tier']}")
    if item["level"] is not None:
        parts.append(f"L{item['level']}")
    return " · ".join(parts)


def render_item_id_json(value: Any, items_by_id: dict[int, sqlite3.Row]) -> str:
    try:
        parsed = json.loads(value if value not in (None, "") else "[]")
        if not isinstance(parsed, list):
            return f'<span class="bad">kein Array:</span> <code>{h(value)}</code>'
    except Exception as exc:
        return f'<span class="bad">ungültiges JSON:</span> {h(exc)} <code>{h(value)}</code>'
    if not parsed:
        return '<span class="muted">leer</span>'
    lines = []
    for raw_id in parsed:
        try:
            iid = int(raw_id)
        except Exception:
            lines.append(f'<span class="bad">{h(raw_id)} ist keine Item-ID</span>')
            continue
        item = items_by_id.get(iid)
        if item:
            info = resource_info(item["rid"])
            lines.append(f'<span class="pill">{h(item_instance_label(item))}</span><br><span class="muted small">RID {h(item["rid"])} · {h(info.get("category_label"))}</span>')
        else:
            lines.append(f'<span class="bad">Item #{iid} fehlt/fremd</span>')
    return "<br>".join(lines)


def simple_key_label(table: str, key_field: str, value: Any) -> str:
    if table in {"currencies", "energies"} and key_field == "rid":
        return resource_label(value, compact=True)
    if table == "talents" and key_field == "talent_id":
        info = lookup_info("talent", value)
        return f"{info['name']} ({info['tag']})" if info.get("tag") else info["name"]
    if table == "user_stats" and key_field == "stat_id":
        info = lookup_info("stat", value)
        return f"{info['name']} ({info['tag']})" if info.get("tag") else info["name"]
    return ""


def simple_key_options(table: str, key_field: str, selected: Any = None) -> str:
    catalog = get_catalog()
    if table == "currencies" and key_field == "rid":
        infos = [x for x in catalog.get("resources_list", []) if x.get("section") == "currencies" or x.get("category_id") == 1]
    elif table == "energies" and key_field == "rid":
        infos = [x for x in catalog.get("resources_list", []) if x.get("section") == "energies" or x.get("id") == 28]
    elif table == "talents" and key_field == "talent_id":
        infos = list(catalog.get("talents_by_id", {}).values())
    elif table == "user_stats" and key_field == "stat_id":
        infos = list(catalog.get("stats_by_id", {}).values())
    else:
        infos = []
    out = []
    for info in sorted(infos, key=lambda x: (str(x.get("name", "")), int(x.get("id", 0)))):
        label = f"{info.get('name')} — {key_field} {info.get('id')}"
        if info.get("tag"):
            label += f" — {info.get('tag')}"
        out.append(f'<option value="{h(info.get("id"))}"{option_selected(info.get("id"), selected)}>{h(label)}</option>')
    return "".join(out)


def catalog_status_html() -> str:
    catalog = get_catalog()
    if catalog.get("loaded"):
        return f'<span class="pill good">game-data geladen</span> <span class="muted small">{h(catalog.get("path"))}</span>'
    return f'<span class="pill bad">game-data fehlt</span> <span class="muted small">{h(catalog.get("error"))}</span>'


def parse_int(value: str | None, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    return int(value)


def parse_nullable_int(value: str | None) -> int | None:
    if value is None or value.strip() == "" or value.strip().lower() == "null":
        return None
    return int(value)


def parse_json_text(value: str | None, default: str = "[]") -> str:
    if value is None or value.strip() == "":
        value = default
    parsed = json.loads(value)
    return json.dumps(parsed, separators=(",", ":"))



# ---------------------------------------------------------------------------
# Database, backup and audit helpers
# ---------------------------------------------------------------------------
def db_path() -> Path:
    return Path(app.config["DB_PATH"]).resolve()


def backup_dir() -> Path:
    source = db_path()
    return Path(app.config.get("BACKUP_DIR") or source.parent / "admin_backups").resolve()


def file_size_text(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return "?"


def make_backup(reason: str = "write") -> Path | None:
    if not app.config.get("AUTO_BACKUP", True):
        return None
    source = db_path()
    out_dir = backup_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_reason = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in reason)[:60] or "backup"
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"{source.stem}.{stamp}.{safe_reason}.sqlite3"
    shutil.copy2(source, target)
    try:
        con = getattr(g, "db", None)
        if con is not None:
            con.execute(
                """
                INSERT INTO admin_db_backups(created_at, reason, path, size_bytes)
                VALUES(?,?,?,?)
                """,
                [now_iso(), reason, str(target), target.stat().st_size],
            )
            con.commit()
    except Exception:
        pass
    return target


def audit(action: str, user_id: int | None = None, table_name: str | None = None, details: dict[str, Any] | str | None = None) -> None:
    if isinstance(details, str):
        detail_text = details
    else:
        detail_text = json.dumps(details or {}, ensure_ascii=False, separators=(",", ":"))
    g.db.execute(
        """
        INSERT INTO admin_change_log(created_at, action, table_name, user_id, details)
        VALUES(?,?,?,?,?)
        """,
        [now_iso(), action, table_name, user_id, detail_text],
    )


def qident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def audit_user_expr(table: str, cols: list[str], prefix: str) -> str:
    if table == "users" and "id" in cols:
        return f"{prefix}.id"
    if table == "user_settings" and "id" in cols:
        return f"{prefix}.id"
    if "user_id" in cols:
        return f"{prefix}.user_id"
    return "NULL"


def json_object_expr(cols: list[str], prefix: str) -> str:
    parts: list[str] = []
    for col in cols:
        parts.append(sql_literal(col))
        parts.append(f"{prefix}.{qident(col)}")
    return "json_object(" + ",".join(parts) + ")"



# ---------------------------------------------------------------------------
# SQLite trigger based audit logging
# ---------------------------------------------------------------------------
def ensure_audit_control(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_audit_control (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            enabled INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            note TEXT
        )
        """
    )
    con.execute(
        """
        INSERT INTO admin_audit_control(id, enabled, updated_at, note)
        VALUES(1, 0, CURRENT_TIMESTAMP, 'External DB-Audit: aus bis explizit aktiviert')
        ON CONFLICT(id) DO NOTHING
        """
    )


def get_external_audit_enabled(con: sqlite3.Connection) -> bool:
    ensure_audit_control(con)
    r = con.execute("SELECT enabled FROM admin_audit_control WHERE id=1").fetchone()
    return bool(r and int(r[0] or 0) == 1)


def set_external_audit_enabled(con: sqlite3.Connection, enabled: bool, note: str = "") -> None:
    ensure_audit_control(con)
    con.execute(
        """
        UPDATE admin_audit_control
        SET enabled=?, updated_at=CURRENT_TIMESTAMP, note=?
        WHERE id=1
        """,
        [1 if enabled else 0, note],
    )


def audit_trigger_names_for_table(table: str) -> list[str]:
    safe_table = table.replace('"', '')
    return [
        'admin_audit_' + safe_table + '_ai',
        'admin_audit_' + safe_table + '_au',
        'admin_audit_' + safe_table + '_ad',
    ]


def audit_trigger_status(con: sqlite3.Connection) -> dict[str, Any]:
    ensure_audit_control(con)
    existing = {
        r["name"]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'admin_audit_%'"
        )
    }
    expected: list[str] = []
    table_status: list[dict[str, Any]] = []
    for table in sorted(WRITE_TABLES):
        info = list(con.execute(f"PRAGMA table_info({qident(table)})"))
        if not info:
            table_status.append({"table": table, "exists": False, "installed": 0, "expected": 0, "missing": []})
            continue
        names = audit_trigger_names_for_table(table)
        expected.extend(names)
        installed = [n for n in names if n in existing]
        missing = [n for n in names if n not in existing]
        table_status.append({"table": table, "exists": True, "installed": len(installed), "expected": len(names), "missing": missing})
    return {
        "enabled": get_external_audit_enabled(con),
        "installed": len([n for n in expected if n in existing]),
        "expected": len(expected),
        "missing": [n for n in expected if n not in existing],
        "extra": sorted([n for n in existing if n not in expected]),
        "tables": table_status,
    }


def drop_audit_triggers_for_all(con: sqlite3.Connection) -> int:
    names = [
        r["name"]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'admin_audit_%'"
        )
    ]
    for name in names:
        con.execute(f"DROP TRIGGER IF EXISTS {qident(name)}")
    return len(names)


def install_audit_triggers_for_all(con: sqlite3.Connection, recreate: bool = True) -> int:
    """Install SQLite triggers that also catch writes made by the game server.

    The triggers live inside the SQLite database, so they fire for every client that
    writes to the watched tables, including the original game server. The global
    switch in admin_audit_control lets the Admin UI pause logging during rollback.
    """
    ensure_audit_control(con)
    if recreate:
        drop_audit_triggers_for_all(con)
    installed = 0
    for table in sorted(WRITE_TABLES):
        info = list(con.execute(f"PRAGMA table_info({qident(table)})"))
        if not info:
            continue
        cols = [r[1] for r in info]
        new_user = audit_user_expr(table, cols, "NEW")
        old_user = audit_user_expr(table, cols, "OLD")
        new_json = json_object_expr(cols, "NEW")
        old_json = json_object_expr(cols, "OLD")
        safe_table = table.replace('"', '')
        when_enabled = "COALESCE((SELECT enabled FROM admin_audit_control WHERE id=1), 0) = 1"
        con.execute(
            f"""
            CREATE TRIGGER {qident('admin_audit_' + safe_table + '_ai')}
            AFTER INSERT ON {qident(table)}
            WHEN {when_enabled}
            BEGIN
              INSERT INTO admin_change_log(created_at, action, table_name, user_id, details)
              VALUES(strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'db-insert', {sql_literal(table)}, {new_user}, json_object('new', {new_json}));
            END
            """
        )
        con.execute(
            f"""
            CREATE TRIGGER {qident('admin_audit_' + safe_table + '_au')}
            AFTER UPDATE ON {qident(table)}
            WHEN {when_enabled}
            BEGIN
              INSERT INTO admin_change_log(created_at, action, table_name, user_id, details)
              VALUES(strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'db-update', {sql_literal(table)}, {new_user}, json_object('old', {old_json}, 'new', {new_json}));
            END
            """
        )
        con.execute(
            f"""
            CREATE TRIGGER {qident('admin_audit_' + safe_table + '_ad')}
            AFTER DELETE ON {qident(table)}
            WHEN {when_enabled}
            BEGIN
              INSERT INTO admin_change_log(created_at, action, table_name, user_id, details)
              VALUES(strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'db-delete', {sql_literal(table)}, {old_user}, json_object('old', {old_json}));
            END
            """
        )
        installed += 3
    return installed


PRIMARY_KEY_FALLBACKS = {
    "users": ["id"],
    "items": ["id"],
    "inventory_slots": ["user_id", "slot_id"],
    "attempts": ["id"],
    "currencies": ["user_id", "rid"],
    "energies": ["user_id", "rid"],
    "talents": ["user_id", "talent_id"],
    "user_stats": ["user_id", "stat_id"],
    "chapter_progress": ["user_id", "chapter_id"],
    "battle_passes": ["user_id", "battle_pass_id"],
    "missions": ["user_id", "mission_id"],
    "tutorial_sequences": ["user_id", "sequence_id"],
    "store_quotas": ["user_id", "quota_id"],
    "user_settings": ["id"],
}


def table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [r["name"] for r in con.execute(f"PRAGMA table_info({qident(table)})")]


def table_primary_keys(con: sqlite3.Connection, table: str) -> list[str]:
    info = list(con.execute(f"PRAGMA table_info({qident(table)})"))
    pk = [(int(r["pk"]), r["name"]) for r in info if int(r["pk"] or 0) > 0]
    if pk:
        return [name for _, name in sorted(pk)]
    cols = {r["name"] for r in info}
    fallback = [c for c in PRIMARY_KEY_FALLBACKS.get(table, []) if c in cols]
    if fallback:
        return fallback
    if "id" in cols:
        return ["id"]
    return []


def parse_change_details(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def compact_change_summary(table: str, action: str, details: dict[str, Any]) -> str:
    old = details.get("old") if isinstance(details.get("old"), dict) else {}
    new = details.get("new") if isinstance(details.get("new"), dict) else {}
    if action == "db-update" and old and new:
        changed = []
        for key in sorted(set(old) | set(new)):
            if old.get(key) != new.get(key):
                changed.append(f"{key}: {old.get(key)!r} → {new.get(key)!r}")
        return "; ".join(changed[:10]) + ("; …" if len(changed) > 10 else "")
    if action == "audit-rollback":
        rid = details.get("rolled_back_change_id")
        result = details.get("result") or "Rollback ausgeführt"
        return f"Änderung #{rid} rückgängig gemacht: {result}" if rid else str(result)
    row_data = new or old
    important = ["id", "user_id", "rid", "item_id", "slot_id", "attempt_id", "amount", "level", "tier", "state", "current_attempt_id"]
    parts = [f"{k}={row_data.get(k)!r}" for k in important if k in row_data]
    return "; ".join(parts) or json.dumps(row_data, ensure_ascii=False)[:240]


def rolled_back_change_ids(con: sqlite3.Connection) -> set[int]:
    ids: set[int] = set()
    try:
        rs = con.execute("SELECT details FROM admin_change_log WHERE action='audit-rollback'").fetchall()
    except Exception:
        return ids
    for r in rs:
        details = parse_change_details(r["details"] if isinstance(r, sqlite3.Row) else r[0])
        try:
            value = details.get("rolled_back_change_id")
            if value is not None:
                ids.add(int(value))
        except Exception:
            pass
    return ids


def rollback_action_html(change_id: Any, already_rolled_back: bool, label: str = "Änderung rückgängig machen") -> str:
    if already_rolled_back:
        return "<span class='good small'>bereits rückgängig</span>"
    return f"""
<form class="inline" method="post" action="{url_for('external_audit_rollback')}" onsubmit="return confirm('Änderung #{h(change_id)} wirklich rückgängig machen? Vorher wird automatisch ein Backup erstellt.');">
  <input type="hidden" name="change_id" value="{h(change_id)}">
  <button class="danger">{h(label)}</button>
</form>
"""


def _where_clause_for_keys(keys: list[str], data: dict[str, Any]) -> tuple[str, list[Any]]:
    if not keys:
        raise ValueError("Keine Schlüsselspalten gefunden; Rollback wäre unsicher.")
    missing = [k for k in keys if k not in data]
    if missing:
        raise ValueError("Schlüsselspalten fehlen im Audit-Log: " + ", ".join(missing))
    return " AND ".join(f"{qident(k)} IS ?" for k in keys), [data.get(k) for k in keys]



# ---------------------------------------------------------------------------
# Single-change rollback support
# ---------------------------------------------------------------------------
def rollback_audit_change(con: sqlite3.Connection, change_id: int) -> str:
    change = con.execute("SELECT * FROM admin_change_log WHERE id=?", [change_id]).fetchone()
    if change is None:
        raise ValueError("Änderung nicht gefunden.")
    action = change["action"]
    table = change["table_name"]
    if action not in {"db-insert", "db-update", "db-delete"}:
        raise ValueError("Diese Änderung stammt nicht aus dem SQLite-DB-Audit und kann nicht automatisch zurückgerollt werden.")
    if change_id in rolled_back_change_ids(con):
        raise ValueError("Diese Änderung wurde bereits rückgängig gemacht.")
    if table not in WRITE_TABLES:
        raise ValueError("Diese Tabelle ist für automatischen Rollback nicht freigegeben.")
    cols = table_columns(con, table)
    if not cols:
        raise ValueError("Tabelle existiert nicht mehr: " + table)
    keys = table_primary_keys(con, table)
    details = parse_change_details(change["details"])
    old = details.get("old") if isinstance(details.get("old"), dict) else None
    new = details.get("new") if isinstance(details.get("new"), dict) else None

    was_enabled = get_external_audit_enabled(con)
    set_external_audit_enabled(con, False, f"paused for rollback change #{change_id}")
    try:
        if action == "db-insert":
            if not new:
                raise ValueError("Audit-Eintrag enthält keinen new-Zustand.")
            where, params = _where_clause_for_keys(keys, new)
            deleted = con.execute(f"DELETE FROM {qident(table)} WHERE {where}", params).rowcount
            result = f"Rollback von Insert: {deleted} Zeile(n) gelöscht."
        elif action == "db-delete":
            if not old:
                raise ValueError("Audit-Eintrag enthält keinen old-Zustand.")
            use_cols = [c for c in cols if c in old]
            placeholders = ",".join("?" for _ in use_cols)
            con.execute(
                f"INSERT OR REPLACE INTO {qident(table)} ({','.join(qident(c) for c in use_cols)}) VALUES ({placeholders})",
                [old.get(c) for c in use_cols],
            )
            result = "Rollback von Delete: alte Zeile wieder eingefügt/ersetzt."
        else:
            if not old or not new:
                raise ValueError("Audit-Eintrag enthält keinen old/new-Zustand.")
            use_cols = [c for c in cols if c in old]
            where, params = _where_clause_for_keys(keys, new)
            assignments = ", ".join(f"{qident(c)}=?" for c in use_cols)
            updated = con.execute(
                f"UPDATE {qident(table)} SET {assignments} WHERE {where}",
                [old.get(c) for c in use_cols] + params,
            ).rowcount
            if updated == 0:
                placeholders = ",".join("?" for _ in use_cols)
                con.execute(
                    f"INSERT OR REPLACE INTO {qident(table)} ({','.join(qident(c) for c in use_cols)}) VALUES ({placeholders})",
                    [old.get(c) for c in use_cols],
                )
                result = "Rollback von Update: Zeile war nicht mehr vorhanden und wurde aus old-Zustand wieder eingefügt."
            else:
                result = f"Rollback von Update: {updated} Zeile(n) auf old-Zustand zurückgesetzt."

        con.execute(
            """
            INSERT INTO admin_change_log(created_at, action, table_name, user_id, details)
            VALUES(?,?,?,?,?)
            """,
            [
                now_iso(),
                "audit-rollback",
                table,
                change["user_id"],
                json.dumps({"rolled_back_change_id": change_id, "original_action": action, "result": result}, ensure_ascii=False, separators=(",", ":")),
            ],
        )
    finally:
        set_external_audit_enabled(con, was_enabled, "restored after rollback")
    return result


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(db_path())
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    return con



# ---------------------------------------------------------------------------
# Flask request lifecycle and authentication
# ---------------------------------------------------------------------------
@app.before_request
def before_request() -> None:
    g.db = connect()
    ensure_admin_tables(g.db)


@app.teardown_request
def teardown_request(_exc: Exception | None) -> None:
    con = getattr(g, "db", None)
    if con is not None:
        try:
            con.close()
        except Exception:
            pass


def ensure_admin_tables(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_user_flags (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            disabled INTEGER NOT NULL DEFAULT 0,
            password_hash_backup TEXT,
            note TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_change_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            action TEXT NOT NULL,
            table_name TEXT,
            user_id INTEGER,
            details TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_db_backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            reason TEXT NOT NULL,
            path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_energy_autofill (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            rid INTEGER NOT NULL DEFAULT 28,
            target_amount INTEGER NOT NULL DEFAULT 20,
            interval_seconds INTEGER NOT NULL DEFAULT 120,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_checked_at TEXT,
            last_changed_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            note TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_event_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scheduled_event_id TEXT NOT NULL,
            event_definition_id TEXT NOT NULL,
            event_type INTEGER NOT NULL DEFAULT 1,
            tag TEXT,
            title TEXT,
            user_id INTEGER,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            availability INTEGER NOT NULL DEFAULT 1,
            min_api_version TEXT,
            max_api_version TEXT,
            stop_time TEXT,
            args_json TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_admin_event_schedule_lookup ON admin_event_schedule(is_active, event_type, event_definition_id, user_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_admin_event_schedule_time ON admin_event_schedule(start_time, end_time)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_admin_event_schedule_uuid_user ON admin_event_schedule(scheduled_event_id, user_id)")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_event_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scheduled_event_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            highest_stage INTEGER NOT NULL DEFAULT 0,
            best_completion_time_milliseconds INTEGER NOT NULL DEFAULT 0,
            run_json TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(scheduled_event_id, user_id)
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_admin_event_progress_uuid_user ON admin_event_progress(scheduled_event_id, user_id)")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_inbox_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NULL,
            display_type INTEGER NOT NULL DEFAULT 1,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            published INTEGER NULL,
            expires INTEGER NULL,
            resources_json TEXT NOT NULL DEFAULT '[]',
            image_id TEXT NULL,
            conditions_json TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_admin_inbox_messages_active_time ON admin_inbox_messages(is_active, published, expires)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_admin_inbox_messages_target ON admin_inbox_messages(user_id, is_active)")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_inbox_message_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            state INTEGER NOT NULL DEFAULT 1,
            claimed_at INTEGER NULL,
            read_at INTEGER NULL,
            deleted_at INTEGER NULL,
            updated_at INTEGER NOT NULL,
            UNIQUE(message_id, user_id)
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_admin_inbox_state_message ON admin_inbox_message_state(message_id, user_id, state)")
    ensure_audit_control(con)
    con.commit()


def check_auth() -> bool:
    username = app.config["ADMIN_USER"]
    password = app.config["ADMIN_PASSWORD"]
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(auth[6:]).decode("utf-8")
        got_user, got_password = raw.split(":", 1)
    except Exception:
        return False
    return secrets.compare_digest(got_user, username) and secrets.compare_digest(got_password, password)


@app.before_request
def basic_auth() -> Response | None:
    if request.path.startswith("/static/"):
        return None
    # Mobile App / local WebView sends CORS preflight requests before Basic Auth.
    if request.method == "OPTIONS" and request.path.startswith("/api/mobile/"):
        return Response("", 204)
    if check_auth():
        return None
    return Response(
        "Authentication required",
        401,
        {"WWW-Authenticate": 'Basic realm="Mighty DOOM Admin"'},
    )


@app.after_request
def add_mobile_api_cors_headers(resp: Response) -> Response:
    # Needed so the Android APK can run its UI from file:///android_asset/index.html
    # and still call the local/remote Admin API with Basic Auth.
    if request.path.startswith("/api/mobile/"):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Max-Age"] = "86400"
    return resp


def rows(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return list(g.db.execute(sql, tuple(params)))


def row(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return g.db.execute(sql, tuple(params)).fetchone()


def execute(sql: str, params: Iterable[Any] = ()) -> None:
    make_backup("write")
    g.db.execute(sql, tuple(params))
    g.db.commit()


def _connect_worker_db() -> sqlite3.Connection:
    con = sqlite3.connect(db_path())
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    ensure_admin_tables(con)
    return con


def _parse_iso_utc(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None



# ---------------------------------------------------------------------------
# Energy Auto-Fill background worker
# ---------------------------------------------------------------------------
def apply_energy_autofill_once(con: sqlite3.Connection, cfg: sqlite3.Row | dict[str, Any], source: str = "manual") -> bool:
    """Set one user's energy resource to the configured target when needed.

    Returns True when the energies table was changed. Frequent auto-fill writes do
    not create backups, otherwise a 2-minute lock would create backup spam.
    Every actual correction is still written to admin_change_log.
    """
    user_id = int(cfg["user_id"])
    rid = int(cfg["rid"])
    target = int(cfg["target_amount"])
    checked_at = now_iso()
    energy = con.execute("SELECT * FROM energies WHERE user_id=? AND rid=?", [user_id, rid]).fetchone()
    changed = False
    old_amount = None if energy is None else energy["amount"]
    if energy is None:
        con.execute(
            "INSERT INTO energies(user_id, rid, amount, last_regen_at) VALUES(?,?,?,?)",
            [user_id, rid, target, checked_at],
        )
        changed = True
    elif int(energy["amount"]) != target:
        con.execute(
            "UPDATE energies SET amount=?, last_regen_at=? WHERE user_id=? AND rid=?",
            [target, checked_at, user_id, rid],
        )
        changed = True

    if changed:
        con.execute(
            "UPDATE admin_energy_autofill SET last_checked_at=?, last_changed_at=? WHERE user_id=?",
            [checked_at, checked_at, user_id],
        )
        con.execute(
            """
            INSERT INTO admin_change_log(created_at, action, table_name, user_id, details)
            VALUES(?,?,?,?,?)
            """,
            [
                checked_at,
                "energy-autofill-set",
                "energies",
                user_id,
                json.dumps({"rid": rid, "old_amount": old_amount, "new_amount": target, "source": source}, ensure_ascii=False, separators=(",", ":")),
            ],
        )
    else:
        con.execute(
            "UPDATE admin_energy_autofill SET last_checked_at=? WHERE user_id=?",
            [checked_at, user_id],
        )
    con.commit()
    return changed


def run_due_energy_autofill(con: sqlite3.Connection) -> tuple[int, int]:
    now = dt.datetime.now(dt.timezone.utc)
    checked = 0
    changed = 0
    configs = list(con.execute("SELECT * FROM admin_energy_autofill WHERE enabled=1 ORDER BY user_id"))
    for cfg in configs:
        last = _parse_iso_utc(cfg["last_checked_at"])
        interval = max(30, int(cfg["interval_seconds"] or 120))
        if last is not None and (now - last).total_seconds() < interval:
            continue
        checked += 1
        if apply_energy_autofill_once(con, cfg, source="worker"):
            changed += 1
    return checked, changed


def energy_autofill_worker() -> None:
    while not _ENERGY_AUTOFILL_STOP.is_set():
        con: sqlite3.Connection | None = None
        try:
            con = _connect_worker_db()
            run_due_energy_autofill(con)
        except Exception as exc:
            print(f"[Energy Auto-Fill] Fehler: {exc}")
        finally:
            if con is not None:
                con.close()
        _ENERGY_AUTOFILL_STOP.wait(10)


def start_energy_autofill_worker() -> None:
    global _ENERGY_AUTOFILL_THREAD
    with _ENERGY_AUTOFILL_LOCK:
        if _ENERGY_AUTOFILL_THREAD is not None and _ENERGY_AUTOFILL_THREAD.is_alive():
            return
        _ENERGY_AUTOFILL_STOP.clear()
        _ENERGY_AUTOFILL_THREAD = threading.Thread(target=energy_autofill_worker, name="energy-autofill", daemon=True)
        _ENERGY_AUTOFILL_THREAD.start()


def energy_autofill_rows() -> list[sqlite3.Row]:
    return rows(
        """
        SELECT f.*, u.uuid, e.amount AS current_amount, e.last_regen_at
        FROM admin_energy_autofill f
        LEFT JOIN users u ON u.id = f.user_id
        LEFT JOIN energies e ON e.user_id = f.user_id AND e.rid = f.rid
        ORDER BY f.enabled DESC, f.user_id
        """
    )


def render_energy_autofill_card(user_id: int) -> str:
    cfg = row(
        """
        SELECT f.*, e.amount AS current_amount, e.last_regen_at
        FROM admin_energy_autofill f
        LEFT JOIN energies e ON e.user_id = f.user_id AND e.rid = f.rid
        WHERE f.user_id=?
        """,
        [user_id],
    )
    enabled = bool(cfg and cfg["enabled"])
    current = cfg["current_amount"] if cfg else row("SELECT amount FROM energies WHERE user_id=? AND rid=28", [user_id])
    current_text = current["amount"] if isinstance(current, sqlite3.Row) else (cfg["current_amount"] if cfg else "-")
    target = cfg["target_amount"] if cfg else 20
    interval = cfg["interval_seconds"] if cfg else 120
    rid = cfg["rid"] if cfg else 28
    last_checked = cfg["last_checked_at"] if cfg else ""
    last_changed = cfg["last_changed_at"] if cfg else ""
    status = '<span class="good">aktiv</span>' if enabled else '<span class="muted">aus</span>'
    return f"""
<div class="card">
<h2>Energy Auto-Fill</h2>
<p>Status: {status}<br>Aktuell: <b>{h(current_text)}</b> · Ziel: <b>{h(target)}</b> · Intervall: <b>{h(interval)} Sekunden</b></p>
<p class="muted small">Setzt die Energie für diesen User automatisch wieder auf den Zielwert. Standard: RID 28 / Energy alle 120 Sekunden auf 20. Diese Auto-Korrektur erzeugt keine Backup-Datei bei jedem Tick, wird aber bei echten Änderungen im Änderungsprotokoll erfasst.</p>
<form method="post" action="{url_for('energy_autofill_save')}">
<input type="hidden" name="user_id" value="{user_id}">
<label>Energy-RID</label><select name="rid">{simple_key_options('energies', 'rid', selected=rid)}</select>
<label>Zielwert</label><input name="target_amount" type="number" min="0" value="{h(target)}">
<label>Prüfintervall in Sekunden</label><input name="interval_seconds" type="number" min="60" value="{h(interval)}">
<label>Aktiv</label><select name="enabled"><option value="1" {'selected' if enabled else ''}>aktiv</option><option value="0" {'selected' if not enabled else ''}>aus</option></select>
<p><button>Speichern</button> <button class="secondary" name="run_now" value="1">Jetzt sofort setzen</button></p>
</form>
<p class="muted small">Letzter Check: {h(last_checked or '-')} · Letzte Änderung: {h(last_changed or '-')}</p>
</div>
"""



# ---------------------------------------------------------------------------
# User progress transfer helpers
# ---------------------------------------------------------------------------
# These tables are user-scoped in the Mighty DOOM private server database. The
# transfer tool copies only rows belonging to the selected source user and writes
# them to the selected target user. It never copies account identity fields such
# as UUIDs, tokens, e-mail addresses or passwords.
PROGRESS_CORE_EXCLUDED_USER_COLUMNS = {
    "id",
    "uuid",
    "email",
    "mail",
    "username",
    "user_name",
    "display_name",
    "name",
    "password",
    "password_hash",
    "password_salt",
    "token",
    "auth_token",
    "access_token",
    "refresh_token",
    "device_id",
    "platform_id",
    "external_id",
    "created_at",
    "updated_at",
    "deleted_at",
}

# Stable rows that can be copied to another user without confusing the
# client startup flow. Seasonal/menu state and active run data are deliberately
# not copied because those rows caused restart loops during real-device tests.
PROGRESS_GAME_TABLES = [
    "tutorial_sequences",
    "chapter_progress",
    "user_settings",
    "user_stats",
    "talents",
    "currencies",
    "energies",
]

PROGRESS_INVENTORY_TABLES = ["items", "cosmetics", "inventory_slots"]

# Volatile tables are reset on the target user after the transfer. They will be
# recreated by the game/server as needed. Copying them can leave a migrated user
# stuck in tutorial, event, store or battle-pass startup loops.
PROGRESS_VOLATILE_TABLES = ["attempts", "battle_passes", "missions", "store_quotas"]

PROGRESS_TRANSFER_LABELS = {
    "core": "Core-Fortschritt",
    "game": "Stabiler Fortschritt",
    "inventory": "Inventar und Ausrüstung",
}


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    """Return True when a table exists in the connected SQLite database."""
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        [table],
    ).fetchone() is not None


def user_scope_column(table: str, cols: list[str]) -> str | None:
    """Return the column that identifies the owning user for a table.

    Most game tables use ``user_id``. A few tables, notably ``users`` and the
    private server's ``user_settings`` table, use ``id`` as the user key.
    """
    if table in {"users", "user_settings"} and "id" in cols:
        return "id"
    if "user_id" in cols:
        return "user_id"
    return None


def progress_transfer_table_count(con: sqlite3.Connection, table: str, user_id: int) -> int:
    """Count rows that would be copied for one table and one user."""
    if not table_exists(con, table):
        return 0
    cols = table_columns(con, table)
    user_col = user_scope_column(table, cols)
    if user_col is None:
        return 0
    return int(con.execute(f"SELECT COUNT(*) AS c FROM {qident(table)} WHERE {qident(user_col)}=?", [user_id]).fetchone()["c"] or 0)


def progress_transfer_user_options(selected: int | None = None) -> str:
    """Render compact user options for the transfer form."""
    users = rows(
        """
        SELECT id, uuid, level, chapter_progression,
               (SELECT amount FROM energies e WHERE e.user_id=users.id AND e.rid=28 LIMIT 1) AS energy,
               (SELECT COUNT(*) FROM items i WHERE i.user_id=users.id) AS item_count
        FROM users
        ORDER BY id
        """
    )
    options = ['<option value="">User wählen</option>']
    for u in users:
        label = f"#{u['id']} · Level {u['level']} · Chapter {u['chapter_progression']} · Items {u['item_count']} · {u['uuid']}"
        options.append(f'<option value="{h(u["id"])}" {"selected" if selected == int(u["id"]) else ""}>{h(label)}</option>')
    return "".join(options)


def progress_transfer_selected_sections(form: Any | None = None) -> set[str]:
    """Return the fixed safe transfer profile.

    Older builds exposed many checkboxes and allowed attempts/seasonal state to
    be copied. In practice that created broken migrated users. The transfer is
    now intentionally simple: choose source user, choose target user, run.
    """
    return {"core", "game", "inventory"}


def progress_transfer_tables_for_sections(sections: set[str] | None = None) -> list[str]:
    """Return the stable tables copied by the safe transfer profile."""
    return [*PROGRESS_GAME_TABLES, *PROGRESS_INVENTORY_TABLES]


def progress_transfer_preview(source_user_id: int | None, target_user_id: int | None, sections: set[str] | None = None) -> str:
    """Render a clear preview for the fixed safe progress transfer.

    The operator should not have to understand internal tables. The preview
    therefore explains what is copied, what is reset, and which health checks
    will be enforced after the write transaction.
    """
    if not source_user_id or not target_user_id:
        return '<p class="muted">Quelle und Ziel auswählen, um eine Vorschau zu sehen.</p>'
    if source_user_id == target_user_id:
        return '<p class="bad">Quelle und Ziel dürfen nicht derselbe User sein.</p>'
    source = row("SELECT id, uuid, level, chapter_progression, current_attempt_id FROM users WHERE id=?", [source_user_id])
    target = row("SELECT id, uuid, level, chapter_progression, current_attempt_id FROM users WHERE id=?", [target_user_id])
    if source is None or target is None:
        return '<p class="bad">Quell- oder Ziel-User wurde nicht gefunden.</p>'

    copied_rows = []
    copied_rows.append(
        f"<tr><td>users</td><td>Progress-Felder</td><td>Level {h(target['level'])} → {h(source['level'])}, Chapter {h(target['chapter_progression'])} → {h(source['chapter_progression'])}</td></tr>"
    )
    for table in progress_transfer_tables_for_sections():
        if not table_exists(g.db, table):
            copied_rows.append(f"<tr><td>{h(table)}</td><td>fehlt</td><td>Tabelle existiert in dieser Datenbank nicht und wird übersprungen.</td></tr>")
            continue
        source_count = progress_transfer_table_count(g.db, table, source_user_id)
        target_count = progress_transfer_table_count(g.db, table, target_user_id)
        copied_rows.append(
            f"<tr><td>{h(table)}</td><td>{h(source_count)} Quelle</td><td>Ziel wird sicher ersetzt; vorhandene Ziel-Zeilen: {h(target_count)}</td></tr>"
        )

    reset_rows = []
    if table_exists(g.db, "attempts"):
        reset_rows.append(f"<tr><td>attempts</td><td>{h(progress_transfer_table_count(g.db, 'attempts', target_user_id))}</td><td>Wird gelöscht; aktive Runs werden nicht kopiert.</td></tr>")
    for table in ["battle_passes", "missions", "store_quotas"]:
        if table_exists(g.db, table):
            reset_rows.append(f"<tr><td>{h(table)}</td><td>{h(progress_transfer_table_count(g.db, table, target_user_id))}</td><td>Wird zurückgesetzt, damit der Client keine alten Saison-/Store-Aktionen ausführt.</td></tr>")

    return f"""
<p class="muted small">Quelle: <b>#{h(source_user_id)}</b> <code>{h(source['uuid'])}</code><br>Ziel: <b>#{h(target_user_id)}</b> <code>{h(target['uuid'])}</code></p>
<p><span class="pill good">Keine erweiterten Optionen nötig.</span> <span class="pill">Automatische Sicherheitsprüfung</span></p>
<h3>Wird kopiert</h3>
<table><thead><tr><th>Bereich</th><th>Umfang</th><th>Hinweis</th></tr></thead><tbody>{''.join(copied_rows)}</tbody></table>
<h3>Wird absichtlich zurückgesetzt</h3>
<table><thead><tr><th>Bereich</th><th>Ziel-Zeilen</th><th>Warum?</th></tr></thead><tbody>{''.join(reset_rows) or '<tr><td>-</td><td>0</td><td>Keine instabilen Ziel-Zeilen gefunden.</td></tr>'}</tbody></table>
<p class="warn">UUID, Login-/Token-Felder, Passwortfelder und Account-Identität bleiben beim Ziel-User erhalten. <code>current_attempt_id</code> wird immer auf <code>NULL</code> gesetzt.</p>
"""


def _json_remap_item_ids(value: Any, item_id_map: dict[int, int]) -> str:
    """Remap JSON item instance id arrays used by attempts.weapon_ids/gear_ids."""
    try:
        parsed = json.loads(value if value not in (None, "") else "[]")
    except Exception:
        parsed = []
    if not isinstance(parsed, list):
        parsed = []
    remapped: list[Any] = []
    for entry in parsed:
        try:
            old_id = int(entry)
        except Exception:
            remapped.append(entry)
            continue
        remapped.append(item_id_map.get(old_id, old_id))
    return json.dumps(remapped, separators=(",", ":"))


def _copy_user_row_progress(con: sqlite3.Connection, source_user_id: int, target_user_id: int, include_attempt_state: bool) -> int:
    """Copy progress-like columns from users while preserving account identity."""
    if not table_exists(con, "users"):
        return 0
    cols = table_columns(con, "users")
    source = con.execute("SELECT * FROM users WHERE id=?", [source_user_id]).fetchone()
    if source is None:
        raise ValueError(f"Source user #{source_user_id} not found.")
    target = con.execute("SELECT * FROM users WHERE id=?", [target_user_id]).fetchone()
    if target is None:
        raise ValueError(f"Target user #{target_user_id} not found.")

    excluded = set(PROGRESS_CORE_EXCLUDED_USER_COLUMNS)
    if not include_attempt_state:
        excluded.update({"current_attempt_id", "attempt_count"})
    update_cols = [c for c in cols if c not in excluded]
    if not update_cols:
        return 0
    assignments = ", ".join(f"{qident(c)}=?" for c in update_cols)
    values = [source[c] for c in update_cols]
    con.execute(f"UPDATE users SET {assignments} WHERE id=?", values + [target_user_id])
    return len(update_cols)


def _delete_target_progress_rows(con: sqlite3.Connection, target_user_id: int, tables: list[str]) -> dict[str, int]:
    """Delete target rows in dependency-safe order before a replacement copy."""
    delete_order = ["attempts", "inventory_slots", "cosmetics", "items"] + [t for t in tables if t not in {"attempts", "inventory_slots", "cosmetics", "items"}]
    deleted: dict[str, int] = {}
    for table in delete_order:
        if table not in tables or not table_exists(con, table):
            continue
        cols = table_columns(con, table)
        user_col = user_scope_column(table, cols)
        if user_col is None:
            continue
        cur = con.execute(f"DELETE FROM {qident(table)} WHERE {qident(user_col)}=?", [target_user_id])
        deleted[table] = cur.rowcount if cur.rowcount is not None else 0
    return deleted


def _clear_target_volatile_state(con: sqlite3.Connection, target_user_id: int) -> dict[str, int]:
    """Reset target-only state that must not survive a progress migration.

    These rows are connected to the active menu/session/event flow. Copying or
    keeping them caused the game client to enter restart loops after a migration.
    The game/server recreates the needed seasonal/menu rows when the user logs in.
    """
    deleted: dict[str, int] = {}
    if table_exists(con, "users") and "current_attempt_id" in table_columns(con, "users"):
        con.execute("UPDATE users SET current_attempt_id=NULL WHERE id=?", [target_user_id])
        deleted["users.current_attempt_id"] = 1

    for table in PROGRESS_VOLATILE_TABLES:
        if not table_exists(con, table):
            continue
        cols = table_columns(con, table)
        user_col = user_scope_column(table, cols)
        if user_col is None:
            continue
        cur = con.execute(f"DELETE FROM {qident(table)} WHERE {qident(user_col)}=?", [target_user_id])
        deleted[table] = cur.rowcount if cur.rowcount is not None else 0
    return deleted


def _normalize_target_progress_rows(con: sqlite3.Connection, target_user_id: int) -> dict[str, int]:
    """Normalize known problematic values after copying.

    The private server expects empty challenge ids to be stored as NULL. Some
    copied or hand-edited rows may contain an empty string instead, which can
    later break game requests. This routine is schema-aware and only touches
    tables/columns that exist.
    """
    fixed: dict[str, int] = {}
    for table in ["chapter_progress", "attempts", "missions", "store_quotas"]:
        if not table_exists(con, table):
            continue
        cols = table_columns(con, table)
        user_col = user_scope_column(table, cols)
        if user_col is None or "challenge_id" not in cols:
            continue
        cur = con.execute(
            f"UPDATE {qident(table)} SET challenge_id=NULL WHERE {qident(user_col)}=? AND challenge_id=''",
            [target_user_id],
        )
        fixed[table + ".challenge_id"] = cur.rowcount if cur.rowcount is not None else 0
    return fixed


def validate_progress_transfer_result(con: sqlite3.Connection, target_user_id: int) -> dict[str, Any]:
    """Run safety checks that are known to affect client startup.

    This is not a full game simulation, but it catches the broken states that
    caused the migrated user to restart in the menu: active attempts, stale
    volatile rows, empty challenge ids and equipment slots pointing at missing
    target items. Critical failures abort the transfer transaction.
    """
    checks: list[dict[str, Any]] = []
    critical_errors: list[str] = []

    def add_check(name: str, ok: bool, details: str, critical: bool = True) -> None:
        checks.append({"name": name, "ok": ok, "details": details})
        if critical and not ok:
            critical_errors.append(f"{name}: {details}")

    user = con.execute("SELECT id, current_attempt_id, level, chapter_progression FROM users WHERE id=?", [target_user_id]).fetchone()
    if user is None:
        raise ValueError(f"Target user #{target_user_id} disappeared during transfer.")
    add_check("target user exists", True, f"level={user['level']}, chapter={user['chapter_progression']}")
    add_check("current_attempt_id cleared", user["current_attempt_id"] is None, f"current_attempt_id={user['current_attempt_id']}")

    if table_exists(con, "attempts"):
        attempt_count = int(con.execute("SELECT COUNT(*) AS c FROM attempts WHERE user_id=?", [target_user_id]).fetchone()["c"] or 0)
        add_check("no copied attempts", attempt_count == 0, f"attempt rows={attempt_count}")

    for table in ["battle_passes", "missions", "store_quotas"]:
        if table_exists(con, table):
            cols = table_columns(con, table)
            user_col = user_scope_column(table, cols)
            if user_col:
                count = int(con.execute(f"SELECT COUNT(*) AS c FROM {qident(table)} WHERE {qident(user_col)}=?", [target_user_id]).fetchone()["c"] or 0)
                add_check(f"{table} reset", count == 0, f"rows={count}")

    # Make sure equipped slots never point at item instances owned by another
    # user or at deleted/non-existent item ids.
    if table_exists(con, "inventory_slots") and table_exists(con, "items"):
        slot_cols = table_columns(con, "inventory_slots")
        if "user_id" in slot_cols and "item_id" in slot_cols:
            orphan_count = int(con.execute(
                """
                SELECT COUNT(*) AS c
                FROM inventory_slots s
                LEFT JOIN items i ON i.id = s.item_id AND i.user_id = s.user_id
                WHERE s.user_id=? AND s.item_id IS NOT NULL AND i.id IS NULL
                """,
                [target_user_id],
            ).fetchone()["c"] or 0)
            add_check("equipped slots valid", orphan_count == 0, f"orphan slots={orphan_count}")

    # Empty challenge ids should have been normalized to NULL.
    for table in ["chapter_progress", "attempts", "missions", "store_quotas"]:
        if not table_exists(con, table):
            continue
        cols = table_columns(con, table)
        user_col = user_scope_column(table, cols)
        if user_col and "challenge_id" in cols:
            empty_count = int(con.execute(
                f"SELECT COUNT(*) AS c FROM {qident(table)} WHERE {qident(user_col)}=? AND challenge_id=''",
                [target_user_id],
            ).fetchone()["c"] or 0)
            add_check(f"{table}.challenge_id normalized", empty_count == 0, f"empty strings={empty_count}")

    if critical_errors:
        raise ValueError("Post-transfer safety check failed: " + "; ".join(critical_errors))
    return {"status": "ok", "checks": checks}


def _insert_copied_row(
    con: sqlite3.Connection,
    table: str,
    source_row: sqlite3.Row,
    target_user_id: int,
    item_id_map: dict[int, int],
    keep_id: bool = False,
) -> int | None:
    """Insert a copied row and return the new integer id where available."""
    cols = table_columns(con, table)
    pk_cols = set(table_primary_keys(con, table))
    user_col = user_scope_column(table, cols)
    insert_cols: list[str] = []
    values: list[Any] = []
    for col in cols:
        # Let SQLite allocate new item/attempt/autoincrement ids. For
        # user_settings, id is the user key and must be written as target id.
        if col == "id" and not keep_id and table not in {"user_settings"}:
            continue
        value = source_row[col]
        if col == user_col:
            value = target_user_id
        elif col == "item_id" and value is not None:
            try:
                value = item_id_map.get(int(value), value)
            except Exception:
                pass
        elif table == "attempts" and col in {"weapon_ids", "gear_ids"}:
            value = _json_remap_item_ids(value, item_id_map)
        insert_cols.append(col)
        values.append(value)
    placeholders = ",".join("?" for _ in insert_cols)
    sql = f"INSERT INTO {qident(table)} ({', '.join(qident(c) for c in insert_cols)}) VALUES ({placeholders})"
    cur = con.execute(sql, values)
    if "id" in cols and "id" not in insert_cols:
        return int(cur.lastrowid) if cur.lastrowid else None
    if "id" in cols and "id" in insert_cols:
        try:
            return int(values[insert_cols.index("id")])
        except Exception:
            return None
    return None


def perform_progress_transfer(
    con: sqlite3.Connection,
    source_user_id: int,
    target_user_id: int,
    sections: set[str] | None = None,
    clear_target: bool = True,
) -> dict[str, Any]:
    """Safely copy playable progress from one user to another.

    This is the production-safe profile used by the UI. It intentionally does
    not copy active attempts, battle pass state, missions or store quotas. Those
    tables are volatile session/menu/season state and were proven to break the
    client after a migration. Instead, the target user receives stable progress
    and inventory data, while volatile state is reset and then validated.
    """
    if source_user_id == target_user_id:
        raise ValueError("Source and target user must be different.")
    if con.execute("SELECT 1 FROM users WHERE id=?", [source_user_id]).fetchone() is None:
        raise ValueError(f"Source user #{source_user_id} not found.")
    if con.execute("SELECT 1 FROM users WHERE id=?", [target_user_id]).fetchone() is None:
        raise ValueError(f"Target user #{target_user_id} not found.")

    safe_sections = progress_transfer_selected_sections()
    tables = progress_transfer_tables_for_sections(safe_sections)
    copied: dict[str, int] = {}
    item_id_map: dict[int, int] = {}

    # Start from a clean target state for the rows that are safe to replace.
    # This avoids unique-key conflicts and prevents old target data from mixing
    # with copied source progress.
    deleted = _delete_target_progress_rows(con, target_user_id, tables)

    # Always clear volatile startup/session state. Do this both before and after
    # copying user columns so current_attempt_id can never leak through.
    volatile_deleted_before = _clear_target_volatile_state(con, target_user_id)

    copied["users.columns"] = _copy_user_row_progress(con, source_user_id, target_user_id, include_attempt_state=False)

    # Copy stable progress tables. The order keeps user_settings/stats/talents
    # independent from inventory item remapping.
    for table in PROGRESS_GAME_TABLES:
        if table not in tables or not table_exists(con, table):
            continue
        cols = table_columns(con, table)
        user_col = user_scope_column(table, cols)
        if user_col is None:
            continue
        source_rows = list(con.execute(f"SELECT * FROM {qident(table)} WHERE {qident(user_col)}=?", [source_user_id]))
        for src in source_rows:
            _insert_copied_row(con, table, src, target_user_id, item_id_map)
        copied[table] = len(source_rows)

    # Copy items first so inventory_slots/cosmetics can be remapped to the new
    # target item instance ids. items.id is an instance id, not a resource id.
    if "items" in tables and table_exists(con, "items"):
        source_items = list(con.execute("SELECT * FROM items WHERE user_id=? ORDER BY id", [source_user_id]))
        for src in source_items:
            new_id = _insert_copied_row(con, "items", src, target_user_id, item_id_map)
            if new_id is not None:
                item_id_map[int(src["id"])] = new_id
        copied["items"] = len(source_items)

    for table in ("cosmetics", "inventory_slots"):
        if table not in tables or not table_exists(con, table):
            continue
        cols = table_columns(con, table)
        user_col = user_scope_column(table, cols)
        if user_col is None:
            continue
        source_rows = list(con.execute(f"SELECT * FROM {qident(table)} WHERE {qident(user_col)}=?", [source_user_id]))
        for src in source_rows:
            _insert_copied_row(con, table, src, target_user_id, item_id_map)
        copied[table] = len(source_rows)

    normalized = _normalize_target_progress_rows(con, target_user_id)
    volatile_deleted_after = _clear_target_volatile_state(con, target_user_id)
    validation = validate_progress_transfer_result(con, target_user_id)

    return {
        "source_user_id": source_user_id,
        "target_user_id": target_user_id,
        "profile": "safe-playable-progress",
        "sections": sorted(safe_sections),
        "deleted": deleted,
        "volatile_deleted_before": volatile_deleted_before,
        "volatile_deleted_after": volatile_deleted_after,
        "normalized": normalized,
        "copied": copied,
        "item_id_map_size": len(item_id_map),
        "validation": validation,
    }




# ---------------------------------------------------------------------------
# HTML rendering helpers
# ---------------------------------------------------------------------------
def render_page(title: str, body: str) -> str:
    messages = "".join(
        f'<div class="flash">{h(m)}</div>' for m in get_flashed_messages_safe()
    )
    lang = current_language()
    theme = current_theme()
    title_text = tt(title, TRANSLATIONS_DE_EN.get(title, title))
    subtitle = f"DB: {h(db_path())} · {APP_VERSION}"
    path = request.path
    nav = [
        ("dashboard", "⬡", tt("Dashboard", "Dashboard"), url_for("dashboard")),
        ("users", "☷", tt("User", "Users"), url_for("index")),
        ("backups", "▣", tt("Backups", "Backups"), url_for("backups")),
        ("catalog", "◇", tt("Katalog", "Catalog"), url_for("catalog_view")),
        ("events", "◈", tt("Events", "Events"), url_for("events_view")),
        ("inbox", "✉", tt("Nachrichten", "Inbox"), url_for("inbox_view")),
        ("energy", "⚡", tt("Energy Auto-Fill", "Energy Auto-Fill"), url_for("energy_autofill")),
        ("transfer", "⇄", tt("Progress-Transfer", "Progress transfer"), url_for("progress_transfer")),
        ("changes", "↶", tt("Änderungen", "Changes"), url_for("change_log")),
        ("audit", "◉", tt("DB-Audit", "DB Audit"), url_for("external_audit")),
        ("tools", "⚙", tt("Tools", "Tools"), url_for("tools")),
        ("tables", "≡", tt("Tables", "Tables"), url_for("tables")),
    ]
    def active_for(key: str, href: str) -> str:
        if path == href or (href != "/" and path.startswith(href + "/")):
            return " active"
        if key == "users" and path.startswith("/user/"):
            return " active"
        return ""
    side_links = "".join(
        f'<a class="side-link{active_for(key, href)}" href="{href}" title="{h(label)}"><span>{icon}</span></a>'
        for key, icon, label, href in nav
    )
    tab_links = "".join(
        f'<a class="{active_for(key, href).strip()}" href="{href}"><span>{icon}</span>{h(label)}</a>'
        for key, icon, label, href in nav
    )
    lang_options = "".join(
        f'<option value="{h(k)}" {"selected" if k == lang else ""}>{h(v)}</option>'
        for k, v in SUPPORTED_LANGUAGES.items()
    )
    theme_options = "".join(
        f'<option value="{h(k)}" {"selected" if k == theme else ""}>{h(v)}</option>'
        for k, v in SUPPORTED_THEMES.items()
    )
    translated_body = translate_html(body)
    translated_messages = translate_html(messages)
    return f"""<!doctype html>
<html lang="{h(lang)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{h(title_text)} - {APP_TITLE}</title>
<style>{app_shell_css(theme)}</style>
</head>
<body class="theme-{h(theme)}">
<div class="app-bg"></div>
<div class="app-layout">
  <aside class="sidebar">
    <a class="logo" href="{url_for('dashboard')}" title="{APP_TITLE}">MD</a>
    <nav class="side-nav">{side_links}</nav>
    <div class="side-spacer"></div>
    <a class="side-link" href="{url_for('backups')}" title="{h(tt('Backup jetzt erstellen', 'Create backup now'))}">⤓</a>
  </aside>
  <section class="content-shell">
    <header class="topbar">
      <div class="title-wrap">
        <h1>{h(title_text)}</h1>
        <div class="subtitle">{subtitle}</div>
      </div>
      <div class="quick-actions">
        <form class="ui-form" method="post" action="{url_for('ui_preferences')}">
          <input type="hidden" name="next" value="{h(request.full_path if request.query_string else request.path)}">
          <label class="small" style="margin:0">{h(tt('Sprache','Language'))}</label>
          <select name="lang">{lang_options}</select>
          <label class="small" style="margin:0">{h(tt('Design','Design'))}</label>
          <select name="theme">{theme_options}</select>
          <button class="secondary">OK</button>
        </form>
      </div>
    </header>
    <main>
      <nav class="page-tabs">{tab_links}</nav>
      {translated_messages}
      {translated_body}
    </main>
  </section>
</div>
</body>
</html>"""


def get_flashed_messages_safe() -> list[str]:
    from flask import get_flashed_messages

    return list(get_flashed_messages())


@app.post("/ui/preferences")
def ui_preferences():
    lang = request.form.get("lang", DEFAULT_LANGUAGE)
    theme = request.form.get("theme", DEFAULT_THEME)
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE
    if theme not in SUPPORTED_THEMES:
        theme = DEFAULT_THEME
    next_url = request.form.get("next") or request.referrer or url_for("dashboard")
    if not str(next_url).startswith("/"):
        next_url = url_for("dashboard")
    resp = make_response(redirect(next_url))
    resp.set_cookie("mda_lang", lang, max_age=60 * 60 * 24 * 365, samesite="Lax")
    resp.set_cookie("mda_theme", theme, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return resp



def _scalar_int(sql: str, params: list[Any] | None = None) -> int:
    try:
        r = row(sql, params or [])
        if r is None:
            return 0
        return int(r[0] or 0)
    except Exception:
        return 0


def _mini_sparkline_svg(values: list[int]) -> str:
    if not values:
        values = [0, 1, 0]
    w, hgt, pad = 620, 150, 14
    mn, mx = min(values), max(values)
    if mx == mn:
        mx = mn + 1
    pts = []
    for i, v in enumerate(values):
        x = pad + (w - pad * 2) * i / max(1, len(values) - 1)
        y = hgt - pad - ((v - mn) / (mx - mn)) * (hgt - pad * 2)
        pts.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(pts)
    return (
        f'<svg viewBox="0 0 {w} {hgt}" width="100%" height="150" role="img" aria-label="activity sparkline">'
        '<defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="var(--accent)"/><stop offset="1" stop-color="var(--accent2)"/></linearGradient></defs>'
        f'<path d="M{pts[0]} L{poly} L{w-pad},{hgt-pad} L{pad},{hgt-pad} Z" fill="url(#g)" opacity=".18"/>'
        f'<polyline points="{poly}" fill="none" stroke="url(#g)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    )


@app.get("/")
@app.get("/dashboard")
def dashboard() -> str:
    user_count = _scalar_int("SELECT COUNT(*) AS c FROM users")
    disabled_count = _scalar_int("SELECT COUNT(*) AS c FROM admin_user_flags WHERE disabled=1")
    item_count = _scalar_int("SELECT COUNT(*) AS c FROM items")
    backup_count = _scalar_int("SELECT COUNT(*) AS c FROM admin_db_backups")
    db_change_count = _scalar_int("SELECT COUNT(*) AS c FROM admin_change_log WHERE action LIKE 'db-%'")
    active_autofill = _scalar_int("SELECT COUNT(*) AS c FROM admin_energy_autofill WHERE enabled=1")
    current_attempts = _scalar_int("SELECT COUNT(*) AS c FROM users WHERE current_attempt_id IS NOT NULL")
    suspicious_attempts = _scalar_int("""
        SELECT COUNT(*) AS c
        FROM users u
        LEFT JOIN attempts a ON a.user_id = u.id AND a.attempt_id = u.current_attempt_id
        WHERE u.current_attempt_id IS NOT NULL
          AND (a.id IS NULL OR a.state <> 0 OR a.ended_at IS NOT NULL OR a.challenge_id = '')
    """)
    recent_users = rows("""
        SELECT u.id, u.uuid, u.level, u.chapter_progression, u.current_attempt_id,
               COALESCE(f.disabled, 0) AS disabled,
               (SELECT amount FROM energies e WHERE e.user_id=u.id AND e.rid=28 LIMIT 1) AS energy,
               (SELECT COUNT(*) FROM items i WHERE i.user_id=u.id) AS item_count
        FROM users u
        LEFT JOIN admin_user_flags f ON f.user_id = u.id
        ORDER BY u.id DESC LIMIT 8
    """)
    user_cards = []
    for u in recent_users:
        status = '<span class="bad">deaktiviert</span>' if u["disabled"] else '<span class="good">aktiv</span>'
        user_cards.append(f"""
<tr><td><a href="{url_for('user_detail', user_id=u['id'])}">#{h(u['id'])}</a><br><span class="muted small"><code>{h(u['uuid'])}</code></span></td><td>{h(u['level'])}</td><td>{h(u['chapter_progression'])}</td><td>{h(u['energy'])}</td><td>{h(u['item_count'])}</td><td>{status}</td></tr>
""")
    recent_changes = rows("SELECT * FROM admin_change_log ORDER BY id DESC LIMIT 8")
    change_rows = "".join(
        f"<tr><td>{h(c['created_at'])}</td><td>{h(c['action'])}</td><td>{h(c['table_name'])}</td><td>{h(compact_change_summary(c['table_name'] or '', c['action'] or '', parse_change_details(c['details'])))}</td></tr>"
        for c in recent_changes
    )
    spark_values = [user_count, max(0, item_count // 10), db_change_count, backup_count, active_autofill, current_attempts, suspicious_attempts + 1]
    body = f"""
<div class="stat-grid">
  <div class="stat-card"><div class="stat-label">{tt('User','Users')}</div><div class="stat-value">{h(user_count)}</div><div class="stat-hint">{h(disabled_count)} {tt('deaktiviert','disabled')}</div></div>
  <div class="stat-card"><div class="stat-label">Items</div><div class="stat-value">{h(item_count)}</div><div class="stat-hint">Inventory + equipped</div></div>
  <div class="stat-card"><div class="stat-label">{tt('DB-Audit','DB Audit')}</div><div class="stat-value">{h(db_change_count)}</div><div class="stat-hint">Game-/DB-Änderungen</div></div>
  <div class="stat-card"><div class="stat-label">Energy Auto-Fill</div><div class="stat-value">{h(active_autofill)}</div><div class="stat-hint">{tt('aktiv','active')}</div></div>
</div>
<div class="dashboard-grid">
  <div class="card hero-card">
    <h2>{tt('Admin Dashboard','Admin Dashboard')}</h2>
    <p class="muted">{tt('Schneller Überblick über User, Items, Backups, DB-Audit, Auto-Fill und Progress-Transfer.','Quick overview of users, items, backups, DB audit, auto-fill and progress transfer.')}</p>
    <div class="sparkline">{_mini_sparkline_svg(spark_values)}</div>
  </div>
  <div class="card">
    <h2>{tt('Schnellaktionen','Quick actions')}</h2>
    <div class="actions">
      <a class="btn" href="{url_for('backups')}">{tt('Backups','Backups')}</a>
      <a class="btn secondary" href="{url_for('external_audit')}">{tt('DB-Audit','DB Audit')}</a>
      <a class="btn secondary" href="{url_for('energy_autofill')}">Energy Auto-Fill</a>
      <a class="btn secondary" href="{url_for('progress_transfer')}">{tt('Progress-Transfer','Progress transfer')}</a> <a class="btn secondary" href="{url_for('events_view')}">{tt('Events','Events')}</a> <a class="btn secondary" href="{url_for('inbox_view')}">{tt('Nachrichten','Inbox')}</a>
      <a class="btn secondary" href="{url_for('tools')}">{tt('Tools','Tools')}</a>
    </div>
    <hr style="border:0;border-top:1px solid var(--line);margin:18px 0">
    <p><span class="pill">{tt('Current Attempts','Current attempts')}: {h(current_attempts)}</span> <span class="pill {'bad' if suspicious_attempts else 'good'}">Verdächtig: {h(suspicious_attempts)}</span> <span class="pill">{tt('Backups','Backups')}: {h(backup_count)}</span></p>
    <form method="get" action="{url_for('index')}"><label>{tt('User suchen','Search user')}</label><input name="q" placeholder="ID oder UUID"><p><button>{tt('Suchen','Search')}</button></p></form>
  </div>
</div>
<div class="grid">
  <div class="card"><h2>{tt('Neueste User','Latest users')}</h2><table><thead><tr><th>User</th><th>Level</th><th>Chapter</th><th>Energy</th><th>Items</th><th>Status</th></tr></thead><tbody>{''.join(user_cards)}</tbody></table></div>
  <div class="card"><h2>{tt('Letzte Änderungen','Recent changes')}</h2><table><thead><tr><th>Zeit</th><th>Aktion</th><th>Tabelle</th><th>Details</th></tr></thead><tbody>{change_rows}</tbody></table></div>
</div>
"""
    return render_page("Dashboard", body)


@app.get("/users")
def index() -> str:
    q = request.args.get("q", "").strip()
    params: list[Any] = []
    where = ""
    if q:
        where = "WHERE CAST(u.id AS TEXT) LIKE ? OR u.uuid LIKE ?"
        params = [f"%{q}%", f"%{q}%"]
    users = rows(
        f"""
        SELECT
          u.id, u.uuid, u.level, u.chapter_progression, u.current_attempt_id,
          u.attempt_count, u.created_at,
          COALESCE(f.disabled, 0) AS disabled,
          (SELECT COUNT(*) FROM items i WHERE i.user_id = u.id) AS item_count,
          (SELECT COUNT(*) FROM currencies c WHERE c.user_id = u.id) AS currency_count,
          (SELECT COUNT(*) FROM attempts a WHERE a.user_id = u.id) AS attempt_rows,
          a.state AS current_attempt_state,
          a.ended_at AS current_attempt_ended_at
        FROM users u
        LEFT JOIN admin_user_flags f ON f.user_id = u.id
        LEFT JOIN attempts a ON a.user_id = u.id AND a.attempt_id = u.current_attempt_id
        {where}
        ORDER BY u.id
        """,
        params,
    )
    trs = []
    for u in users:
        status = '<span class="good">aktiv</span>'
        if u["disabled"]:
            status = '<span class="bad">deaktiviert</span>'
        attempt = "-"
        if u["current_attempt_id"] is not None:
            css = "good" if u["current_attempt_state"] == 0 and u["current_attempt_ended_at"] is None else "warn"
            attempt = f'<span class="{css}">#{h(u["current_attempt_id"])} state={h(u["current_attempt_state"])} ended={h(u["current_attempt_ended_at"])}</span>'
        trs.append(
            f"""<tr>
<td><a href="{url_for('user_detail', user_id=u['id'])}">{u['id']}</a></td>
<td><code>{h(u['uuid'])}</code></td>
<td>{h(u['level'])}</td>
<td>{h(u['chapter_progression'])}</td>
<td>{attempt}</td>
<td>{h(u['item_count'])}</td>
<td>{h(u['currency_count'])}</td>
<td>{h(u['attempt_rows'])}</td>
<td>{status}</td>
<td>{h(u['created_at'])}</td>
</tr>"""
        )
    body = f"""
<div class="card">
  <h1>User</h1>
  <p><a class="btn secondary" href="{url_for('backups')}">Backup erstellen</a> <a class="btn secondary" href="{url_for('progress_transfer')}">Progress übertragen</a> <a class="btn secondary" href="{url_for('change_log')}">Änderungsprotokoll ansehen</a> <a class="btn secondary" href="{url_for('tools')}">Reparatur-Tools</a></p>
  <form method="get">
    <label>Suche nach ID oder UUID</label>
    <input name="q" value="{h(q)}" placeholder="z. B. 6 oder UUID">
  </form>
</div>
<div class="card">
<table>
<thead><tr><th>ID</th><th>UUID</th><th>Level</th><th>Chapter</th><th>Current Attempt</th><th>Items</th><th>Currencies</th><th>Attempts</th><th>Status</th><th>Created</th></tr></thead>
<tbody>{''.join(trs)}</tbody>
</table>
</div>
"""
    return render_page("Users", body)


@app.get("/progress-transfer")
def progress_transfer() -> str:
    source_user_id = parse_nullable_int(request.args.get("source_user_id"))
    target_user_id = parse_nullable_int(request.args.get("target_user_id"))
    preview = progress_transfer_preview(source_user_id, target_user_id)
    can_run = bool(source_user_id and target_user_id and source_user_id != target_user_id)
    body = f"""
<div class="card hero-card">
  <h1>Sicherer Progress-Transfer</h1>
  <p class="muted">Kopiert stabilen Fortschritt, Inventar, Ausrüstung, Währungen, Energie, Stats, Talente, Settings, Tutorial und Chapter-Fortschritt. Instabile Menü-/Saison-Daten werden automatisch zurückgesetzt.</p>
  <p><span class="pill good">Keine erweiterten Optionen nötig.</span> <span class="pill">Automatische Sicherheitsprüfung</span></p>
</div>
<div class="grid">
  <div class="card">
    <h2>Quelle und Ziel auswählen</h2>
    <form method="get" action="{url_for('progress_transfer')}">
      <label>Von User</label>
      <select name="source_user_id">{progress_transfer_user_options(source_user_id)}</select>
      <label>Zu User</label>
      <select name="target_user_id">{progress_transfer_user_options(target_user_id)}</select>
      <p><button class="secondary">Vorschau aktualisieren</button></p>
    </form>
    <form method="post" action="{url_for('progress_transfer_run')}">
      <input type="hidden" name="source_user_id" value="{h(source_user_id or '')}">
      <input type="hidden" name="target_user_id" value="{h(target_user_id or '')}">
      <p><button class="danger" {'disabled' if not can_run else ''}>Transfer starten</button></p>
    </form>
  </div>
  <div class="card">
    <h2>Vorschau</h2>
    {preview}
  </div>
</div>
<div class="card">
  <h2>Was der sichere Transfer macht</h2>
  <ul>
    <li>Vor der Übertragung wird automatisch ein Sicherheitsbackup erstellt.</li>
    <li>Der Ziel-User behält seine UUID, Login-/Token-Felder, Passwörter und Account-Identität.</li>
    <li>Inventar wird als neue Ziel-Item-Instanzen kopiert; ausgerüstete Slots werden auf diese neuen Item-IDs umgebogen.</li>
    <li>Aktive Runs, Attempts, Battle-Pass, Missions und Store-Quotas werden auf dem Ziel-User bewusst gelöscht, damit das Game beim Login saubere Menü-Daten neu erzeugt.</li>
    <li><code>current_attempt_id</code> wird immer auf <code>NULL</code> gesetzt.</li>
    <li>Nach dem Transfer prüft das Tool automatisch, ob der Ziel-User keine kaputten Attempts, keine verwaisten Equip-Slots und keine leeren <code>challenge_id</code>-Strings mehr hat.</li>
  </ul>
</div>
"""
    return render_page("Progress-Transfer", body)


@app.post("/progress-transfer/run")
def progress_transfer_run():
    source_user_id = parse_nullable_int(request.form.get("source_user_id"))
    target_user_id = parse_nullable_int(request.form.get("target_user_id"))
    if not source_user_id or not target_user_id:
        flash("Quelle und Ziel müssen ausgewählt sein.")
        return redirect(url_for("progress_transfer"))
    if source_user_id == target_user_id:
        flash("Quelle und Ziel dürfen nicht derselbe User sein.")
        return redirect(url_for("progress_transfer", source_user_id=source_user_id, target_user_id=target_user_id))
    make_backup(f"safe-progress-transfer-{source_user_id}-to-{target_user_id}")
    try:
        result = perform_progress_transfer(g.db, source_user_id, target_user_id)
        audit("safe-progress-transfer", target_user_id, "users", result)
        g.db.commit()
        flash(f"Progress von User #{source_user_id} auf User #{target_user_id} übertragen und geprüft.")
        return redirect(url_for("user_detail", user_id=target_user_id))
    except Exception as exc:
        g.db.rollback()
        flash(f"Progress-Transfer abgebrochen: {exc}")
        return redirect(url_for("progress_transfer", source_user_id=source_user_id, target_user_id=target_user_id))


@app.get("/user/<int:user_id>")
def user_detail(user_id: int) -> str:
    u = row(
        """
        SELECT u.*, COALESCE(f.disabled, 0) AS disabled, f.note AS admin_note
        FROM users u
        LEFT JOIN admin_user_flags f ON f.user_id = u.id
        WHERE u.id = ?
        """,
        [user_id],
    )
    if u is None:
        return render_page("Nicht gefunden", "<div class='card bad'>User nicht gefunden.</div>")
    validation = validate_user(user_id)
    body = f"""
<h1>User {user_id}</h1>
<div class="card">{catalog_status_html()}</div>
<div class="grid">
  <div class="card">
    <h2>Core</h2>
    <p>Status: {'<span class="bad">deaktiviert</span>' if u['disabled'] else '<span class="good">aktiv</span>'}</p>
    <form method="post" action="{url_for('update_user_core')}">
      <input type="hidden" name="user_id" value="{user_id}">
      <label>UUID</label><input name="uuid" value="{h(u['uuid'])}">
      <label>Level</label><input name="level" type="number" min="1" value="{h(u['level'])}">
      <label>Chapter Progression</label><input name="chapter_progression" type="number" min="0" value="{h(u['chapter_progression'])}">
      <label>Current Attempt ID</label><input name="current_attempt_id" type="number" value="{h(u['current_attempt_id'])}">
      <label>Attempt Count</label><input name="attempt_count" type="number" min="0" value="{h(u['attempt_count'])}">
      <label>Admin-Notiz</label><textarea name="note">{h(u['admin_note'])}</textarea>
      <p><button>Speichern</button></p>
    </form>
    <form method="post" action="{url_for('toggle_disable')}">
      <input type="hidden" name="user_id" value="{user_id}">
      <button class="{'secondary' if u['disabled'] else 'danger'}" name="disabled" value="{'0' if u['disabled'] else '1'}">{'Wieder aktivieren' if u['disabled'] else 'Deaktivieren'}</button>
    </form>
  </div>
  <div class="card">
    <h2>Validierung</h2>
    {render_validation(validation)}
  </div>
  {render_energy_autofill_card(user_id)}
  <div class="card">
    <h2>Schnell-Reparatur</h2>
    <p class="muted small">Diese Buttons sind genau für die Fehler gedacht, die wir beim Troubleshooting gesehen haben. Vor jeder Änderung wird automatisch ein Backup erstellt.</p>
    <form method="post" action="{url_for('repair_empty_challenges')}">
      <input type="hidden" name="user_id" value="{user_id}">
      <button class="secondary">challenge_id='' → NULL</button>
    </form>
    <form method="post" action="{url_for('repair_clear_current_attempt')}">
      <input type="hidden" name="user_id" value="{user_id}">
      <button class="secondary">Current Attempt leeren</button>
    </form>
    <form method="post" action="{url_for('repair_attempt_from_equipped')}">
      <input type="hidden" name="user_id" value="{user_id}">
      <label>Chapter für neuen offenen Attempt</label><input name="chapter_id" type="number" value="666">
      <button>Neuen Attempt aus ausgerüsteten Items bauen</button>
    </form>
    <p><a class="btn secondary" href="{url_for('progress_transfer', source_user_id=user_id)}">Progress von diesem User übertragen</a></p>
    <form method="post" action="{url_for('backup_create')}">
      <input type="hidden" name="reason" value="manual-user-{user_id}">
      <button class="secondary">Jetzt DB-Backup erstellen</button>
    </form>
  </div>
</div>
{render_recent_changes(user_id)}
{render_attempts(user_id)}
<div class="grid">
  {render_key_value_table(user_id, 'currencies', ['rid','amount'], 'rid', 'Währungen')}
  {render_key_value_table(user_id, 'energies', ['rid','amount','last_regen_at'], 'rid', 'Energie')}
  {render_key_value_table(user_id, 'talents', ['talent_id','level'], 'talent_id', 'Talente')}
  {render_key_value_table(user_id, 'user_stats', ['stat_id','value'], 'stat_id', 'Stats')}
  {render_settings(user_id)}
</div>
{render_inventory(user_id)}
{render_chapter_progress(user_id)}
"""
    return render_page(f"User {user_id}", body)


def render_validation(problems: list[tuple[str, str]]) -> str:
    if not problems:
        return '<p class="good">Keine typischen Start-Probleme gefunden.</p>'
    lis = "".join(f'<li class="{h(level)}">{h(msg)}</li>' for level, msg in problems)
    return f"<ul>{lis}</ul>"


def render_recent_changes(user_id: int) -> str:
    changes = rows(
        """
        SELECT *
        FROM admin_change_log
        WHERE user_id = ? OR user_id IS NULL
        ORDER BY id DESC
        LIMIT 20
        """,
        [user_id],
    )
    trs = "".join(
        f"<tr><td>{h(c['created_at'])}</td><td>{h(c['action'])}</td><td>{h(c['table_name'])}</td><td><code>{h(c['details'])}</code></td></tr>"
        for c in changes
    )
    return f"""
<div class="card">
<h2>Letzte Änderungen</h2>
<table><thead><tr><th>Zeit</th><th>Aktion</th><th>Tabelle</th><th>Details</th></tr></thead><tbody>{trs}</tbody></table>
<p><a href="{url_for('change_log', user_id=user_id)}">Alle Änderungen für diesen User anzeigen</a></p>
</div>
"""


def validate_json_array(value: Any, name: str, problems: list[tuple[str, str]]) -> list[Any]:
    try:
        parsed = json.loads(value if value not in (None, "") else "[]")
        if not isinstance(parsed, list):
            problems.append(("bad", f"{name} ist kein JSON-Array."))
            return []
        return parsed
    except Exception as exc:
        problems.append(("bad", f"{name} ist kein gültiges JSON: {exc}"))
        return []


def validate_user(user_id: int) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    u = row("SELECT * FROM users WHERE id=?", [user_id])
    if u is None:
        return [("bad", "User existiert nicht.")]
    dupes = rows("SELECT id FROM users WHERE uuid = ? AND id <> ?", [u["uuid"], user_id])
    if dupes:
        problems.append(("bad", f"UUID ist doppelt vorhanden bei User(s): {', '.join(str(x['id']) for x in dupes)}"))
    if u["current_attempt_id"] is not None:
        a = row("SELECT * FROM attempts WHERE user_id=? AND attempt_id=?", [user_id, u["current_attempt_id"]])
        if a is None:
            problems.append(("bad", f"current_attempt_id {u['current_attempt_id']} zeigt auf keinen Attempt."))
        else:
            if a["challenge_id"] == "":
                problems.append(("bad", "Aktueller Attempt hat challenge_id='' statt NULL."))
            if a["state"] != 0:
                problems.append(("warn", f"Aktueller Attempt ist nicht aktiv: state={a['state']}"))
            if a["ended_at"] is not None:
                problems.append(("warn", "Aktueller Attempt hat ended_at gesetzt."))
            owned_items = {int(x["id"]) for x in rows("SELECT id FROM items WHERE user_id=?", [user_id])}
            for field in ("weapon_ids", "gear_ids"):
                ids = validate_json_array(a[field], field, problems)
                for item_id in ids:
                    try:
                        item_id_int = int(item_id)
                    except Exception:
                        problems.append(("bad", f"{field} enthält keine Integer-ID: {item_id!r}"))
                        continue
                    if item_id_int not in owned_items:
                        problems.append(("bad", f"{field} referenziert Item {item_id_int}, das User {user_id} nicht besitzt."))
            for field in ("abilities", "stats"):
                validate_json_array(a[field], field, problems)
    broken_slots = rows(
        """
        SELECT s.slot_id, s.item_id
        FROM inventory_slots s
        LEFT JOIN items i ON i.id = s.item_id AND i.user_id = s.user_id
        WHERE s.user_id=? AND i.id IS NULL
        """,
        [user_id],
    )
    for s in broken_slots:
        problems.append(("bad", f"Inventory Slot {s['slot_id']} zeigt auf fehlendes/fremdes Item {s['item_id']}"))
    empty_challenges = rows("SELECT attempt_id FROM attempts WHERE user_id=? AND challenge_id=''", [user_id])
    if empty_challenges:
        problems.append(("bad", f"Leere challenge_id in Attempt(s): {', '.join(str(x['attempt_id']) for x in empty_challenges)}"))
    return problems


def render_attempts(user_id: int) -> str:
    attempts = rows("SELECT * FROM attempts WHERE user_id=? ORDER BY attempt_id", [user_id])
    owned_items = rows("SELECT * FROM items WHERE user_id=? ORDER BY id", [user_id])
    items_by_id = {int(i["id"]): i for i in owned_items}
    trs = []
    for a in attempts:
        trs.append(
            f"""<tr>
<td>{h(a['attempt_id'])}</td><td>{h(a['chapter_id'])}</td><td>{h(a['challenge_id'])}</td><td>{h(a['state'])}</td><td>{h(a['completed_stage_count'])}</td><td>{h(a['health_points'])}</td>
<td>{render_item_id_json(a['weapon_ids'], items_by_id)}</td><td>{render_item_id_json(a['gear_ids'], items_by_id)}</td>
<td>{h(a['started_at'])}</td><td>{h(a['ended_at'])}</td>
<td><form class="inline" method="post" action="{url_for('make_attempt_current')}"><input type="hidden" name="user_id" value="{user_id}"><input type="hidden" name="attempt_id" value="{h(a['attempt_id'])}"><button class="secondary">Als current</button></form></td>
</tr>"""
        )
    weapon_ids = [int(x["item_id"]) for x in rows("SELECT item_id FROM inventory_slots WHERE user_id=? AND slot_id IN (1,2) ORDER BY slot_id", [user_id])]
    gear_ids = [int(x["item_id"]) for x in rows("SELECT item_id FROM inventory_slots WHERE user_id=? AND slot_id IN (3,4,5,6,7,8) ORDER BY slot_id", [user_id])]
    weapon_preview = render_item_id_json(json.dumps(weapon_ids), items_by_id)
    gear_preview = render_item_id_json(json.dumps(gear_ids), items_by_id)
    body = f"""
<div class="card">
<h2>Attempts</h2>
<table><thead><tr><th>Attempt</th><th>Chapter</th><th>Challenge</th><th>State</th><th>Stage</th><th>HP</th><th>Weapon IDs</th><th>Gear IDs</th><th>Started</th><th>Ended</th><th>Aktion</th></tr></thead><tbody>{''.join(trs)}</tbody></table>
<h3>Sauberen offenen Attempt erzeugen</h3>
<p class="muted small">Hinweis: <code>weapon_ids</code> und <code>gear_ids</code> sind Item-Instanz-IDs aus <code>items.id</code>, nicht Resource-IDs/RIDs.</p>
<div class="grid"><div><b>Vorschau Waffen</b><br>{weapon_preview}</div><div><b>Vorschau Gear</b><br>{gear_preview}</div></div>
<form method="post" action="{url_for('create_attempt')}">
<input type="hidden" name="user_id" value="{user_id}">
<label>Chapter ID</label><input name="chapter_id" type="number" value="666">
<label>Weapon IDs JSON</label><input name="weapon_ids" value="{h(json.dumps(weapon_ids))}">
<label>Gear IDs JSON</label><input name="gear_ids" value="{h(json.dumps(gear_ids))}">
<p class="muted small">Challenge wird absichtlich als NULL gespeichert. State=0, ended_at=NULL.</p>
<button>Neuen current Attempt erstellen</button>
</form>
</div>
"""
    return body


def render_key_value_table(user_id: int, table: str, fields: list[str], key_field: str, title: str) -> str:
    data = rows(f"SELECT * FROM {table} WHERE user_id=? ORDER BY {key_field}", [user_id])
    headers = []
    for f in fields:
        headers.append(f"<th>{h(f)}</th>")
        if f == key_field:
            headers.append("<th>Bezeichnung</th>")
    trs = []
    for r in data:
        cells = []
        for f in fields:
            cells.append(f"<td>{h(r[f])}</td>")
            if f == key_field:
                label = simple_key_label(table, key_field, r[f])
                cells.append(f"<td><span class='pill'>{h(label)}</span></td>")
        trs.append(f"<tr>{''.join(cells)}</tr>")
    inputs = []
    for f in fields:
        if f == key_field:
            options = simple_key_options(table, key_field)
            if options:
                inputs.append(f'<label>{h(f)}</label><select name="{h(f)}">{options}</select>')
            else:
                inputs.append(f'<label>{h(f)}</label><input name="{h(f)}">')
        elif f.endswith("_at"):
            inputs.append(f'<label>{h(f)}</label><input name="{h(f)}" placeholder="leer = jetzt">')
        else:
            inputs.append(f'<label>{h(f)}</label><input name="{h(f)}" type="number">')
    return f"""
<div class="card">
<h2>{h(title)}</h2>
<table><thead><tr>{''.join(headers)}</tr></thead><tbody>{''.join(trs)}</tbody></table>
<h3>Setzen / Anlegen</h3>
<form method="post" action="{url_for('upsert_simple')}">
<input type="hidden" name="user_id" value="{user_id}">
<input type="hidden" name="table" value="{h(table)}">
<input type="hidden" name="key_field" value="{h(key_field)}">
<input type="hidden" name="fields" value="{h(','.join(fields))}">
{''.join(inputs)}
<button>Speichern</button>
</form>
</div>"""


def render_settings(user_id: int) -> str:
    s = row("SELECT * FROM user_settings WHERE id=?", [user_id])
    selected_cosmetic = s["blood_cosmetic"] if s else ""
    return f"""
<div class="card">
<h2>Settings</h2>
<form method="post" action="{url_for('update_settings')}">
<input type="hidden" name="user_id" value="{user_id}">
<label>blood_built_in</label><input name="blood_built_in" type="number" value="{h(s['blood_built_in'] if s else 0)}">
<label>blood_cosmetic</label><select name="blood_cosmetic">{grouped_resource_options(only_cosmetics=True, selected=selected_cosmetic, include_blank=True)}</select>
<label>confirm_gem_spend</label><select name="confirm_gem_spend"><option value="0" {'selected' if s and not s['confirm_gem_spend'] else ''}>false</option><option value="1" {'selected' if s and s['confirm_gem_spend'] else ''}>true</option></select>
<button>Speichern</button>
</form>
</div>
"""


def render_inventory(user_id: int) -> str:
    items = rows(
        """
        SELECT i.*, s.slot_id AS equipped_slot
        FROM items i
        LEFT JOIN inventory_slots s ON s.item_id = i.id AND s.user_id = i.user_id
        WHERE i.user_id=?
        ORDER BY i.id
        """,
        [user_id],
    )
    trs = []
    for i in items:
        info = resource_info(i["rid"])
        delete_btn = ""
        if i["equipped_slot"] is None:
            delete_btn = f"""<form class="inline" method="post" action="{url_for('delete_item')}"><input type="hidden" name="user_id" value="{user_id}"><input type="hidden" name="item_id" value="{i['id']}"><button class="danger">Löschen</button></form>"""
        compatible_ids = compatible_slot_ids_for_rid(i["rid"])
        equip_select = slot_options(selected=i["equipped_slot"] or "", include_blank=False, compatible_ids=compatible_ids or None)
        equip_form = f"""<form class="inline" method="post" action="{url_for('equip_item')}"><input type="hidden" name="user_id" value="{user_id}"><input type="hidden" name="item_id" value="{i['id']}"><select class="compact" name="slot_id">{equip_select}</select> <button class="secondary">Equip</button></form>"""
        cosmetic_label = ""
        if i["cosmetic"] is not None:
            cosmetic_label = f"<br><span class='muted small'>{h(resource_label(i['cosmetic'], compact=True))}</span>"
        trs.append(
            f"""<tr>
<td class="nowrap">{h(i['id'])}</td>
<td>{h(i['rid'])}</td>
<td><b>{h(info.get('name'))}</b><br><span class="muted small">{h(info.get('tag'))}</span></td>
<td><span class="pill">{h(info.get('category_label'))}</span><br><span class="muted small">{h(info.get('section_label'))}</span></td>
<td>{h(info.get('compatible_slot_text') or '-')}</td>
<td>{h(i['tier'])}</td><td>{h(i['level'])}</td><td>{h(i['cosmetic'])}{cosmetic_label}</td>
<td>{h(i['equipped_slot'])}<br><span class="muted small">{h(slot_label(i['equipped_slot']) if i['equipped_slot'] is not None else '')}</span></td>
<td>{equip_form} {delete_btn}</td></tr>"""
        )
    slots = rows(
        """
        SELECT s.slot_id, s.item_id, i.rid, i.tier, i.level
        FROM inventory_slots s
        LEFT JOIN items i ON i.id=s.item_id AND i.user_id=s.user_id
        WHERE s.user_id=?
        ORDER BY s.slot_id
        """,
        [user_id],
    )
    slot_rows_html = []
    for s in slots:
        if s["rid"] is None:
            label = "fehlendes/fremdes Item"
        else:
            label_parts = [f"#{s['item_id']}", resource_info(s["rid"]).get("name") or f"RID {s['rid']}"]
            if s["tier"] is not None:
                label_parts.append(f"T{s['tier']}")
            if s["level"] is not None:
                label_parts.append(f"L{s['level']}")
            label = " · ".join(str(x) for x in label_parts)
        slot_rows_html.append(f"<tr><td>{h(s['slot_id'])}</td><td>{h(slot_label(s['slot_id']))}</td><td>{h(s['item_id'])}</td><td>{h(label)}</td></tr>")
    slot_trs = "".join(slot_rows_html)
    item_options = "".join(
        f'<option value="{h(i["id"])}">{h(item_instance_label(i))} — RID {h(i["rid"])} — {h(resource_info(i["rid"]).get("category_label"))}</option>'
        for i in items
    )
    return f"""
<div class="card">
<h2>Items</h2>
<p class="muted small">RID = Resource-ID aus game-data. ID = konkrete Item-Instanz aus <code>items.id</code>. <code>inventory_slots.item_id</code> verweist auf diese Item-Instanz-ID.</p>
<table><thead><tr><th>ID</th><th>RID</th><th>Name</th><th>Kategorie</th><th>Kompatible Slots</th><th>Tier</th><th>Level</th><th>Cosmetic</th><th>Equipped Slot</th><th>Aktion</th></tr></thead><tbody>{''.join(trs)}</tbody></table>
<h3>Item geben</h3>
<form method="post" action="{url_for('add_item')}">
<input type="hidden" name="user_id" value="{user_id}">
<div class="grid">
<div><label>Item / RID</label><select name="rid" required>{grouped_resource_options(only_equippable=True)}</select></div>
<div><label>Tier</label><select name="tier"><option value="">NULL / Standard</option>{''.join(f'<option value="{n}">Tier {n}</option>' for n in range(0, 6))}</select></div>
<div><label>Level</label><input name="level" type="number" min="1" value="1"></div>
<div><label>Cosmetic</label><select name="cosmetic">{grouped_resource_options(only_cosmetics=True, include_blank=True)}</select></div>
<div><label>Optional direkt equippen</label><select name="equip_slot">{slot_options(include_blank=True)}</select></div>
</div>
<p><button>Item hinzufügen</button></p>
</form>
<h3>Equipment Slots</h3>
<table><thead><tr><th>Slot ID</th><th>Slot</th><th>Item ID</th><th>Item</th></tr></thead><tbody>{slot_trs}</tbody></table>
<form method="post" action="{url_for('equip_item')}">
<input type="hidden" name="user_id" value="{user_id}">
<div class="grid"><div><label>Slot</label><select name="slot_id">{slot_options()}</select></div><div><label>Item</label><select name="item_id">{item_options}</select></div></div>
<p><button>Equip setzen</button></p>
</form>
</div>
"""


def render_chapter_progress(user_id: int) -> str:
    data = rows("SELECT * FROM chapter_progress WHERE user_id=? ORDER BY chapter_id", [user_id])
    trs = "".join(
        f"<tr><td>{h(x['chapter_id'])}</td><td>{h(x['win_count'])}</td><td>{h(x['attempt_count'])}</td><td>{h(x['highest_stage'])}</td><td>{h(x['highest_reward_claimed'])}</td><td>{h(x['highest_vip_reward_claimed'])}</td></tr>"
        for x in data
    )
    return f"""
<div class="card">
<h2>Chapter Progress</h2>
<table><thead><tr><th>Chapter</th><th>Wins</th><th>Attempts</th><th>Highest Stage</th><th>Reward</th><th>VIP Reward</th></tr></thead><tbody>{trs}</tbody></table>
<form method="post" action="{url_for('upsert_chapter_progress')}">
<input type="hidden" name="user_id" value="{user_id}">
<div class="grid">
<div><label>chapter_id</label><input name="chapter_id" type="number"></div>
<div><label>win_count</label><input name="win_count" type="number" value="0"></div>
<div><label>attempt_count</label><input name="attempt_count" type="number" value="0"></div>
<div><label>highest_stage</label><input name="highest_stage" type="number" value="0"></div>
<div><label>highest_reward_claimed</label><input name="highest_reward_claimed" type="number" value="0"></div>
<div><label>highest_vip_reward_claimed</label><input name="highest_vip_reward_claimed" type="number" value="0"></div>
</div>
<p><button>Chapter Progress speichern</button></p>
</form>
</div>
"""


@app.post("/user/update")
def update_user_core():
    user_id = int(request.form["user_id"])
    make_backup("user-core")
    g.db.execute(
        """
        UPDATE users
        SET uuid=?, level=?, chapter_progression=?, current_attempt_id=?, attempt_count=?
        WHERE id=?
        """,
        [
            request.form["uuid"].strip(),
            int(request.form["level"]),
            int(request.form["chapter_progression"]),
            parse_nullable_int(request.form.get("current_attempt_id")),
            int(request.form["attempt_count"]),
            user_id,
        ],
    )
    g.db.execute(
        """
        INSERT INTO admin_user_flags(user_id, disabled, note, updated_at)
        VALUES(?, COALESCE((SELECT disabled FROM admin_user_flags WHERE user_id=?), 0), ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET note=excluded.note, updated_at=excluded.updated_at
        """,
        [user_id, user_id, request.form.get("note", ""), now_iso()],
    )
    audit("update-user-core", user_id, "users", {"level": int(request.form["level"]), "chapter_progression": int(request.form["chapter_progression"]), "current_attempt_id": parse_nullable_int(request.form.get("current_attempt_id")), "attempt_count": int(request.form["attempt_count"])})
    g.db.commit()
    flash("Core-Daten gespeichert.")
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/user/toggle-disable")
def toggle_disable():
    user_id = int(request.form["user_id"])
    disabled = int(request.form["disabled"])
    u = row("SELECT password_hash FROM users WHERE id=?", [user_id])
    if u is None:
        flash("User nicht gefunden.")
        return redirect(url_for("index"))
    make_backup("disable-user")
    if disabled:
        existing = row("SELECT * FROM admin_user_flags WHERE user_id=?", [user_id])
        backup_hash = existing["password_hash_backup"] if existing and existing["password_hash_backup"] else u["password_hash"]
        random_disabled_password = secrets.token_urlsafe(48).encode("utf-8")
        disabled_hash = bcrypt.hashpw(random_disabled_password, bcrypt.gensalt(rounds=12)).decode("utf-8")
        g.db.execute("UPDATE users SET password_hash=? WHERE id=?", [disabled_hash, user_id])
        g.db.execute(
            """
            INSERT INTO admin_user_flags(user_id, disabled, password_hash_backup, updated_at)
            VALUES(?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET disabled=1, password_hash_backup=excluded.password_hash_backup, updated_at=excluded.updated_at
            """,
            [user_id, backup_hash, now_iso()],
        )
        audit("disable-user", user_id, "users", {"disabled": 1})
        flash("User deaktiviert. Neue Logins sind blockiert; vorhandene Tokens laufen ggf. noch kurz weiter.")
    else:
        existing = row("SELECT password_hash_backup FROM admin_user_flags WHERE user_id=?", [user_id])
        if existing is None or not existing["password_hash_backup"]:
            flash("Kann nicht aktivieren: kein gesicherter password_hash vorhanden.")
        else:
            g.db.execute("UPDATE users SET password_hash=? WHERE id=?", [existing["password_hash_backup"], user_id])
            g.db.execute(
                "UPDATE admin_user_flags SET disabled=0, updated_at=? WHERE user_id=?",
                [now_iso(), user_id],
            )
            audit("enable-user", user_id, "users", {"disabled": 0})
            flash("User wieder aktiviert.")
    g.db.commit()
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/simple/upsert")
def upsert_simple():
    user_id = int(request.form["user_id"])
    table = request.form["table"]
    key_field = request.form["key_field"]
    fields = request.form["fields"].split(",")
    if table not in {"currencies", "energies", "talents", "user_stats"}:
        flash("Tabelle nicht erlaubt.")
        return redirect(url_for("user_detail", user_id=user_id))
    values: dict[str, Any] = {}
    for f in fields:
        raw = request.form.get(f, "")
        if f.endswith("_at"):
            values[f] = raw or now_iso()
        else:
            values[f] = int(raw)
    make_backup(f"upsert-{table}")
    cols = fields + ["user_id"]
    placeholders = ",".join("?" for _ in cols)
    update_fields = ",".join(f"{f}=excluded.{f}" for f in fields if f != key_field)
    conflict = f"user_id,{key_field}"
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT({conflict}) DO UPDATE SET {update_fields}"
    g.db.execute(sql, [values[f] for f in fields] + [user_id])
    audit("upsert-simple", user_id, table, {"key_field": key_field, "values": values})
    g.db.commit()
    flash(f"{table} gespeichert.")
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/settings/update")
def update_settings():
    user_id = int(request.form["user_id"])
    make_backup("settings")
    g.db.execute(
        """
        INSERT INTO user_settings(id, blood_built_in, blood_cosmetic, confirm_gem_spend)
        VALUES(?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          blood_built_in=excluded.blood_built_in,
          blood_cosmetic=excluded.blood_cosmetic,
          confirm_gem_spend=excluded.confirm_gem_spend
        """,
        [
            user_id,
            int(request.form["blood_built_in"]),
            parse_nullable_int(request.form.get("blood_cosmetic")),
            int(request.form["confirm_gem_spend"]),
        ],
    )
    audit("update-settings", user_id, "user_settings", {"blood_built_in": int(request.form["blood_built_in"]), "blood_cosmetic": request.form.get("blood_cosmetic"), "confirm_gem_spend": int(request.form["confirm_gem_spend"])})
    g.db.commit()
    flash("Settings gespeichert.")
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/item/add")
def add_item():
    user_id = int(request.form["user_id"])
    rid = int(request.form["rid"])
    tier = parse_nullable_int(request.form.get("tier"))
    level = int(request.form.get("level") or 1)
    cosmetic = parse_nullable_int(request.form.get("cosmetic"))
    equip_slot = parse_nullable_int(request.form.get("equip_slot"))
    info = resource_info(rid)
    if not info.get("equippable"):
        flash(f"RID {rid} ist laut game-data kein ausrüstbares Item.")
        return redirect(url_for("user_detail", user_id=user_id))
    compatible = compatible_slot_ids_for_rid(rid)
    if equip_slot is not None and compatible and equip_slot not in compatible:
        flash(f"{info.get('name')} passt nicht in {slot_label(equip_slot)}. Kompatibel: {info.get('compatible_slot_text')}.")
        return redirect(url_for("user_detail", user_id=user_id))
    make_backup("add-item")
    cur = g.db.execute(
        "INSERT INTO items(rid,tier,level,cosmetic,user_id,created_at) VALUES(?,?,?,?,?,?)",
        [rid, tier, level, cosmetic, user_id, now_iso()],
    )
    item_id = cur.lastrowid
    if equip_slot is not None:
        g.db.execute(
            """
            INSERT INTO inventory_slots(slot_id,item_id,user_id) VALUES(?,?,?)
            ON CONFLICT(user_id,slot_id) DO UPDATE SET item_id=excluded.item_id
            """,
            [equip_slot, item_id, user_id],
        )
    audit("add-item", user_id, "items", {"item_id": item_id, "rid": rid, "tier": tier, "level": level, "equip_slot": equip_slot})
    g.db.commit()
    flash(f"Item {item_id} hinzugefügt.")
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/item/delete")
def delete_item():
    user_id = int(request.form["user_id"])
    item_id = int(request.form["item_id"])
    equipped = row("SELECT 1 FROM inventory_slots WHERE user_id=? AND item_id=?", [user_id, item_id])
    if equipped:
        flash("Item ist equipped und wurde nicht gelöscht.")
        return redirect(url_for("user_detail", user_id=user_id))
    make_backup("delete-item")
    g.db.execute("DELETE FROM items WHERE user_id=? AND id=?", [user_id, item_id])
    audit("delete-item", user_id, "items", {"item_id": item_id})
    g.db.commit()
    flash(f"Item {item_id} gelöscht.")
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/item/equip")
def equip_item():
    user_id = int(request.form["user_id"])
    slot_id = int(request.form["slot_id"])
    item_id = int(request.form["item_id"])
    owned = row("SELECT * FROM items WHERE user_id=? AND id=?", [user_id, item_id])
    if not owned:
        flash("Item gehört nicht zu diesem User.")
        return redirect(url_for("user_detail", user_id=user_id))
    compatible = compatible_slot_ids_for_rid(owned["rid"])
    if compatible and slot_id not in compatible:
        flash(f"{item_instance_label(owned)} passt nicht in {slot_label(slot_id)}. Kompatibel: {resource_info(owned['rid']).get('compatible_slot_text')}.")
        return redirect(url_for("user_detail", user_id=user_id))
    make_backup("equip")
    g.db.execute(
        """
        INSERT INTO inventory_slots(slot_id,item_id,user_id) VALUES(?,?,?)
        ON CONFLICT(user_id,slot_id) DO UPDATE SET item_id=excluded.item_id
        """,
        [slot_id, item_id, user_id],
    )
    audit("equip-item", user_id, "inventory_slots", {"slot_id": slot_id, "item_id": item_id})
    g.db.commit()
    flash("Slot gesetzt.")
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/chapter/upsert")
def upsert_chapter_progress():
    user_id = int(request.form["user_id"])
    vals = [
        int(request.form["chapter_id"]),
        int(request.form["win_count"]),
        int(request.form["attempt_count"]),
        int(request.form["highest_stage"]),
        int(request.form["highest_reward_claimed"]),
        int(request.form["highest_vip_reward_claimed"]),
        user_id,
    ]
    make_backup("chapter-progress")
    g.db.execute(
        """
        INSERT INTO chapter_progress(chapter_id,win_count,attempt_count,highest_stage,highest_reward_claimed,highest_vip_reward_claimed,user_id)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(user_id,chapter_id) DO UPDATE SET
          win_count=excluded.win_count,
          attempt_count=excluded.attempt_count,
          highest_stage=excluded.highest_stage,
          highest_reward_claimed=excluded.highest_reward_claimed,
          highest_vip_reward_claimed=excluded.highest_vip_reward_claimed
        """,
        vals,
    )
    audit("upsert-chapter-progress", user_id, "chapter_progress", {"chapter_id": vals[0], "win_count": vals[1], "attempt_count": vals[2], "highest_stage": vals[3]})
    g.db.commit()
    flash("Chapter Progress gespeichert.")
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/attempt/current")
def make_attempt_current():
    user_id = int(request.form["user_id"])
    attempt_id = int(request.form["attempt_id"])
    make_backup("current-attempt")
    g.db.execute("UPDATE users SET current_attempt_id=? WHERE id=?", [attempt_id, user_id])
    audit("set-current-attempt", user_id, "users", {"current_attempt_id": attempt_id})
    g.db.commit()
    flash("Current Attempt gesetzt.")
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/attempt/create")
def create_attempt():
    user_id = int(request.form["user_id"])
    chapter_id = int(request.form["chapter_id"])
    weapon_ids = parse_json_text(request.form.get("weapon_ids"), "[]")
    gear_ids = parse_json_text(request.form.get("gear_ids"), "[]")
    max_attempt = row("SELECT COALESCE(MAX(attempt_id),0) AS m FROM attempts WHERE user_id=?", [user_id])["m"]
    next_attempt = int(max_attempt) + 1
    make_backup("create-attempt")
    g.db.execute(
        """
        INSERT INTO attempts(
          attempt_id, chapter_id, challenge_id, state, completed_stage_count,
          health_points, armor_points, ability_level, ability_points, kill_count,
          glory_kill_count, seed, damage_dealt, damage_taken, weapon_ids, gear_ids,
          abilities, stats, playtime, user_id, started_at, ended_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            next_attempt,
            chapter_id,
            None,
            0,
            0,
            0,
            0,
            1,
            0,
            0,
            0,
            random.randint(1, 2_147_483_647),
            0,
            0,
            weapon_ids,
            gear_ids,
            "[]",
            "[]",
            0,
            user_id,
            now_iso(),
            None,
        ],
    )
    g.db.execute("UPDATE users SET current_attempt_id=?, attempt_count=MAX(attempt_count, ?) WHERE id=?", [next_attempt, next_attempt, user_id])
    audit("create-current-attempt", user_id, "attempts", {"attempt_id": next_attempt, "chapter_id": chapter_id, "weapon_ids": weapon_ids, "gear_ids": gear_ids})
    g.db.commit()
    flash(f"Offener Attempt {next_attempt} erstellt und als current gesetzt.")
    return redirect(url_for("user_detail", user_id=user_id))




# ---------------------------------------------------------------------------
# Ingame Inbox / admin message helpers
# ---------------------------------------------------------------------------
INBOX_STATE_LABELS = {
    1: "unread",
    2: "read",
    3: "claimed",
    4: "archiviert",
}


def _now_epoch() -> int:
    return int(time.time())


def _parse_epoch_from_form(value: str | None) -> int | None:
    """Parse a form datetime-local value or unix timestamp to epoch seconds.

    The game server bridge stores inbox message times as INTEGER values. The UI
    displays them as datetime-local fields. Naive datetime-local values are
    treated as UTC to keep the private admin tool deterministic across machines.
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    normalized = value.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return int(parsed.timestamp())


def _epoch_to_datetime_input(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        timestamp = int(value)
    except Exception:
        return ""
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _epoch_to_text(value: Any) -> str:
    if value is None or value == "":
        return "-"
    try:
        timestamp = int(value)
    except Exception:
        return str(value)
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _inbox_state_label(value: Any) -> str:
    try:
        return INBOX_STATE_LABELS.get(int(value), f"state {value}")
    except Exception:
        return str(value or "-")


def _users_select_options(selected: Any = None, include_blank: bool = False) -> str:
    out: list[str] = []
    if include_blank:
        out.append(f'<option value=""{option_selected("", selected)}>—</option>')
    try:
        user_rows = rows("SELECT id, uuid, level, chapter_progression FROM users ORDER BY id LIMIT 5000")
    except Exception:
        user_rows = []
    for user in user_rows:
        label = f"User {user['id']}"
        if "level" in user.keys() and user["level"] is not None:
            label += f" · Level {user['level']}"
        if "chapter_progression" in user.keys() and user["chapter_progression"] is not None:
            label += f" · Chapter {user['chapter_progression']}"
        uuid_text = str(user["uuid"] or "")[:8]
        if uuid_text:
            label += f" · {uuid_text}"
        out.append(f'<option value="{h(user["id"])}"{option_selected(user["id"], selected)}>{h(label)}</option>')
    return "".join(out) or '<option value="">Keine User gefunden</option>'


def _validate_inbox_rewards(rewards: Any) -> list[dict[str, int]]:
    if rewards in (None, ""):
        return []
    if isinstance(rewards, str):
        rewards = json.loads(rewards)
    if not isinstance(rewards, list):
        raise ValueError("resources_json muss eine JSON-Liste sein.")
    cleaned: list[dict[str, int]] = []
    for item in rewards:
        if not isinstance(item, dict):
            raise ValueError("Jeder Reward muss ein Objekt sein.")
        if "rid" not in item or "amount" not in item:
            raise ValueError("Jeder Reward benötigt rid und amount.")
        rid = int(item["rid"])
        amount = int(item["amount"])
        if rid < 0 or amount < 0:
            raise ValueError("Reward rid und amount müssen positive Zahlen sein.")
        cleaned.append({"rid": rid, "amount": amount})
    return cleaned


def _inbox_rewards_from_form(form: Any) -> str:
    rewards: list[dict[str, int]] = []
    for rid_raw, amount_raw in zip(form.getlist("reward_rid"), form.getlist("reward_amount")):
        rid_text = str(rid_raw or "").strip()
        amount_text = str(amount_raw or "").strip()
        if not rid_text and not amount_text:
            continue
        if not rid_text or not amount_text:
            raise ValueError("Bei Rewards müssen RID und Amount zusammen angegeben werden.")
        rewards.append({"rid": int(rid_text), "amount": int(amount_text)})
    # Optional raw JSON fallback for API-like edits from the browser.
    raw_json = str(form.get("resources_json_raw") or "").strip()
    if raw_json and not rewards:
        rewards = _validate_inbox_rewards(raw_json)
    cleaned = _validate_inbox_rewards(rewards)
    return json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))


def _inbox_payload_from_request(data: dict[str, Any]) -> dict[str, Any]:
    title = str(data.get("title") or "").strip()
    body = str(data.get("body") or "").strip()
    if not title:
        raise ValueError("Titel darf nicht leer sein.")
    if not body:
        raise ValueError("Nachrichtentext darf nicht leer sein.")
    target = str(data.get("target") or "all")
    user_id = None if target == "all" else _to_int_or_none(data.get("user_id"))
    if target != "all" and user_id is None:
        raise ValueError("Für eine user-spezifische Nachricht muss ein User ausgewählt werden.")
    display_type = int(data.get("display_type") or 1)
    published = _parse_epoch_from_form(data.get("published"))
    expires = _parse_epoch_from_form(data.get("expires"))
    if published is not None and expires is not None and expires < published:
        raise ValueError("Ablaufzeit darf nicht vor der Veröffentlichungszeit liegen.")
    is_active = 1 if str(data.get("is_active", "1")).lower() in {"1", "true", "on", "yes"} else 0
    if hasattr(data, "getlist"):
        resources_json = _inbox_rewards_from_form(data)
    else:
        resources_json = json.dumps(_validate_inbox_rewards(data.get("resources_json") or []), ensure_ascii=False, separators=(",", ":"))
    return {
        "user_id": user_id,
        "display_type": display_type,
        "title": title,
        "body": body,
        "published": published,
        "expires": expires,
        "resources_json": resources_json,
        # Keep optional image IDs compatible with older local bridge schemas that
        # may have created admin_inbox_messages.image_id as NOT NULL.
        # The game server can treat an empty string the same as no image.
        "image_id": str(data.get("image_id") or "").strip(),
        "conditions_json": json.dumps(_safe_json_loads(str(data.get("conditions_json") or "{}"), {}), ensure_ascii=False, separators=(",", ":")),
        "is_active": is_active,
    }


def _inbox_message_rows() -> list[sqlite3.Row]:
    params: list[Any] = []
    where: list[str] = []
    q = request.args.get("q", "").strip().lower()
    active = request.args.get("active", "").strip()
    target = request.args.get("target", "").strip()
    expired = request.args.get("expired", "").strip()
    now_value = _now_epoch()
    if q:
        where.append("(LOWER(m.title) LIKE ? OR LOWER(m.body) LIKE ? OR CAST(m.id AS TEXT) LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    if active in {"0", "1"}:
        where.append("m.is_active=?")
        params.append(int(active))
    if target == "global":
        where.append("m.user_id IS NULL")
    elif target == "user":
        where.append("m.user_id IS NOT NULL")
    if expired == "1":
        where.append("m.expires IS NOT NULL AND m.expires < ?")
        params.append(now_value)
    elif expired == "0":
        where.append("(m.expires IS NULL OR m.expires >= ?)")
        params.append(now_value)
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    return rows(
        f"""
        SELECT m.*,
          COALESCE(SUM(CASE WHEN s.state >= 2 OR s.read_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS read_count,
          COALESCE(SUM(CASE WHEN s.state = 3 OR s.claimed_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS claimed_count,
          COALESCE(SUM(CASE WHEN s.state = 4 OR s.deleted_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS deleted_count,
          COUNT(s.id) AS state_count
        FROM admin_inbox_messages m
        LEFT JOIN admin_inbox_message_state s ON s.message_id=m.id
        {where_sql}
        GROUP BY m.id
        ORDER BY m.is_active DESC, COALESCE(m.published, m.created_at) DESC, m.id DESC
        LIMIT 1000
        """,
        params,
    )


def _inbox_badges(message: sqlite3.Row | dict[str, Any]) -> str:
    now_value = _now_epoch()
    badges = []
    badges.append('<span class="pill good">aktiv</span>' if int(message["is_active"] or 0) else '<span class="pill muted">inaktiv</span>')
    badges.append('<span class="pill">global</span>' if message["user_id"] is None else '<span class="pill warn">user-spezifisch</span>')
    expires = message["expires"]
    published = message["published"]
    if expires is not None and int(expires) < now_value:
        badges.append('<span class="pill bad">abgelaufen</span>')
    elif published is not None and int(published) > now_value:
        badges.append('<span class="pill warn">geplant</span>')
    else:
        badges.append('<span class="pill good">sichtbar</span>')
    return " ".join(badges)


def _inbox_rewards_editor_html(resources_json: str | None = "[]") -> str:
    try:
        rewards = _validate_inbox_rewards(resources_json or "[]")
    except Exception:
        rewards = []
    while len(rewards) < 3:
        rewards.append({"rid": "", "amount": ""})
    rows_html = []
    for reward in rewards[:30]:
        rows_html.append(f"""
<tr class="reward-row">
  <td><select name="reward_rid">{grouped_resource_options(selected=reward.get('rid'), include_blank=True)}</select></td>
  <td><input name="reward_amount" type="number" min="0" value="{h(reward.get('amount', ''))}" placeholder="Amount"></td>
  <td><button type="button" class="secondary" onclick="this.closest('tr').remove()">Entfernen</button></td>
</tr>""")
    return f"""
<table id="inbox-rewards-table">
<thead><tr><th>Resource/RID</th><th>Amount</th><th>Aktion</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table>
<p><button type="button" class="secondary" onclick="addInboxRewardRow()">Reward-Zeile hinzufügen</button></p>
<template id="inbox-reward-row-template"><tr class="reward-row"><td><select name="reward_rid">{grouped_resource_options(include_blank=True)}</select></td><td><input name="reward_amount" type="number" min="0" placeholder="Amount"></td><td><button type="button" class="secondary" onclick="this.closest('tr').remove()">Entfernen</button></td></tr></template>
<script>
function addInboxRewardRow() {{
  const tpl = document.getElementById('inbox-reward-row-template');
  const tbody = document.querySelector('#inbox-rewards-table tbody');
  if (tpl && tbody) tbody.appendChild(tpl.content.cloneNode(true));
}}
</script>"""


def _message_detail_state_rows(message_id: int) -> list[sqlite3.Row]:
    return rows(
        """
        SELECT * FROM admin_inbox_message_state
        WHERE message_id=?
        ORDER BY updated_at DESC, user_id ASC
        LIMIT 1000
        """,
        [message_id],
    )




@app.get("/events")
def events_view() -> str:
    q = request.args.get("q", "").strip().lower()
    event_type_filter = request.args.get("type", "").strip()
    events = event_catalog()
    if q:
        events = [e for e in events if q in " ".join(str(e.get(k, "")) for k in ("event_definition_id", "tag", "title", "description", "event_type_label")).lower()]
    if event_type_filter:
        type_num = _to_int_or_none(event_type_filter)
        if type_num is not None:
            events = [e for e in events if int(e.get("event_type") or 0) == type_num]
    event_rows = []
    for event in events[:500]:
        event_rows.append(f"""<tr>
<td><code>{h(event.get('event_definition_id'))}</code></td>
<td><b>{h(event.get('tag'))}</b><br><span class="muted small">{h(event.get('source_path'))}</span></td>
<td>{h(event.get('title'))}<br><span class="muted small">{h(event.get('description') or '-')}</span></td>
<td><span class="pill">{h(event.get('event_type_label'))}</span></td>
<td>{h(event.get('stage_count') or '-')}</td>
<td>
<form class="inline" method="post" action="{url_for('events_create_schedule')}">
  <input type="hidden" name="catalog_key" value="{h(event.get('catalog_key'))}">
  <input type="hidden" name="scope" value="all">
  <input type="hidden" name="start_time" value="{h(_iso_for_datetime_input(dt.datetime.now(dt.timezone.utc).isoformat()))}">
  <input type="hidden" name="end_time" value="{h(_iso_for_datetime_input((dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=7)).isoformat()))}">
  <button class="secondary">Event aktivieren</button>
</form>
</td>
</tr>""")
    schedule_rows = []
    for item in _event_schedule_rows():
        schedule_rows.append(f"""<tr>
<td><a href="{url_for('event_detail', schedule_id=item['id'])}">#{h(item['id'])}</a><br><span class="muted small">{h(item['scheduled_event_id'])}</span></td>
<td>{_event_schedule_badges(item)}</td>
<td><b>{h(item['title'] or item['tag'])}</b><br><code>{h(item['event_definition_id'])}</code> · {h(EVENT_TYPE_LABELS.get(item['event_type'], item['event_type']))}</td>
<td>{h(item['user_id'] if item['user_id'] is not None else 'alle')}</td>
<td>{h(item['start_time'])}<br>{h(item['end_time'])}</td>
<td>{h(item['progress_count'])}</td>
<td>{h(item['completed_count'])}</td>
<td>{h(item['max_highest_stage'])}</td>
<td>
  <a class="btn secondary" href="{url_for('event_detail', schedule_id=item['id'])}">Öffnen</a>
  {'<form class="inline" method="post" action="' + url_for('event_deactivate', schedule_id=item['id']) + '"><input type="hidden" name="next" value="events"><button class="danger">Deaktivieren</button></form>' if int(item['is_active'] or 0) else '<form class="inline" method="post" action="' + url_for('event_activate', schedule_id=item['id']) + '"><input type="hidden" name="next" value="events"><button>Aktivieren</button></form>'}
</td>
</tr>""")
    type_options = "".join(f'<option value="{k}" {"selected" if event_type_filter == str(k) else ""}>{h(v)}</option>' for k, v in EVENT_TYPE_LABELS.items())
    default_start = _iso_for_datetime_input(dt.datetime.now(dt.timezone.utc).isoformat())
    default_end = _iso_for_datetime_input((dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)).isoformat())
    body = f"""
<div class="card hero-card">
  <h1>Event-Admin</h1>
  <p class="muted">Verwaltet geplante Events getrennt vom Node.js-Gameserver. Die Konfiguration wird in SQLite gespeichert und kann nach <code>data/admin-events.json</code> exportiert werden.</p>
  {catalog_status_html()}
</div>
<div class="grid">
  <div class="card">
    <h2>Event aktivieren</h2>
    <form method="post" action="{url_for('events_create_schedule')}">
      <label>Event</label><select name="catalog_key" required>{event_catalog_options()}</select>
      <div class="grid">
        <div><label>Startzeit</label><input type="datetime-local" name="start_time" value="{h(default_start)}"></div>
        <div><label>Endzeit</label><input type="datetime-local" name="end_time" value="{h(default_end)}"></div>
      </div>
      <label>Zuordnung</label>
      <select name="scope"><option value="all">Für alle User</option><option value="users">Nur bestimmte User</option></select>
      <label>User-IDs, wenn user-spezifisch</label><input name="user_ids" placeholder="z. B. 7, 11, 15">
      <label><input type="checkbox" name="use_test_rewards" value="1"> Standard-Testrewards setzen</label>
      <p><button>Event aktivieren</button></p>
    </form>
  </div>
  <div class="card">
    <h2>Export/Integration</h2>
    <p class="muted">Der Gameserver kann später entweder die SQLite-Tabellen lesen oder die exportierte JSON-Datei nutzen.</p>
    <form method="post" action="{url_for('events_export')}"><button>Event exportieren</button></form>
    <form method="post" action="{url_for('events_fix_uuid_ids')}"><button class="secondary">Event-UUIDs/Progress reparieren</button></form>
    <p class="small muted">Exportpfad: <code>{h(_admin_events_export_path())}</code></p>
  </div>
</div>
<div class="card">
  <h2>Event-Schedule</h2>
  <table><thead><tr><th>ID / scheduled_event_id</th><th>Status</th><th>Event</th><th>User</th><th>Zeitraum</th><th>User mit Progress</th><th>abgeschlossen</th><th>höchste Stage</th><th>Aktionen</th></tr></thead><tbody>{''.join(schedule_rows) or '<tr><td colspan="9" class="muted">Noch keine Events geplant.</td></tr>'}</tbody></table>
</div>
<div class="card">
  <h2>Event-Katalog</h2>
  <form method="get">
    <div class="grid"><div><label>Suche nach Tag, Name, ID und Typ</label><input name="q" value="{h(request.args.get('q',''))}"></div>
    <div><label>Event-Art</label><select name="type"><option value="">Alle</option>{type_options}</select></div></div>
    <p><button>Suchen</button> <a class="btn secondary" href="{url_for('events_view')}">Alle</a></p>
  </form>
  <p class="muted small">Angezeigt: {len(events)} Treffer, maximal 500 Zeilen.</p>
  <table><thead><tr><th>Event Definition ID</th><th>Tag</th><th>Name/Beschreibung</th><th>Event-Art</th><th>Stages</th><th>Aktion</th></tr></thead><tbody>{''.join(event_rows) or '<tr><td colspan="6" class="muted">Keine Events in game-data.json gefunden.</td></tr>'}</tbody></table>
</div>
"""
    return render_page("Events", body)


@app.post("/events/fix-uuid-ids")
def events_fix_uuid_ids():
    make_backup("event-fix-uuid-ids")
    try:
        result = migrate_event_schedule_uuid_ids(g.db)
        audit("event-fix-uuid-ids", None, "admin_event_schedule", result)
        g.db.commit()
        flash(f"Event-UUID-Fix abgeschlossen: {result['updated_schedules']} Schedule-Zeile(n), {result['migrated_progress']} Progress-Zeile(n) migriert, {result['unassigned_progress']} unzugeordnet.")
    except Exception as exc:
        g.db.rollback()
        flash(f"Event-UUID-Fix fehlgeschlagen: {exc}")
    return redirect(url_for("events_view"))


@app.post("/events/schedule/create")
def events_create_schedule():
    make_backup("event-schedule-create")
    try:
        created_id = create_event_schedule_from_payload(g.db, dict(request.form))
        audit("event-schedule-create", parse_nullable_int(request.form.get("user_ids")), "admin_event_schedule", {"created_id": created_id, "catalog_key": request.form.get("catalog_key")})
        g.db.commit()
        flash("Event aktiviert.")
        return redirect(url_for("event_detail", schedule_id=created_id))
    except Exception as exc:
        g.db.rollback()
        flash(f"Event konnte nicht erstellt werden: {exc}")
        return redirect(url_for("events_view"))


@app.get("/events/<int:schedule_id>")
def event_detail(schedule_id: int) -> str:
    item = row("SELECT * FROM admin_event_schedule WHERE id=?", [schedule_id])
    if item is None:
        return render_page("Nicht gefunden", "<div class='card bad'>Event nicht gefunden.</div>")
    args = _safe_json_loads(item["args_json"], {})
    if not isinstance(args, dict):
        args = {}
    modifiers = ", ".join(str(x) for x in args.get("additional_event_modifiers", []))
    where_sql, where_params = _event_progress_where_for_schedule(item)
    progress_rows = rows(f"SELECT * FROM admin_event_progress WHERE {where_sql} ORDER BY updated_at DESC", where_params)
    progress_html = []
    for pr in progress_rows:
        run_raw = str(pr["run_json"] or "").strip()
        run_active = "ja" if run_raw and run_raw.lower() != "null" else "nein"
        progress_html.append(f"""<tr><td>{h(pr['user_id'])}</td><td>{h(pr['attempts'])}</td><td>{h(pr['highest_stage'])}</td><td>{h(pr['best_completion_time_milliseconds'])}</td><td>{run_active}</td><td>{h(pr['updated_at'])}</td><td><form class="inline" method="post" action="{url_for('event_reset_progress', schedule_id=schedule_id)}"><input type="hidden" name="user_id" value="{h(pr['user_id'])}"><button class="danger">Progress für User zurücksetzen</button></form></td></tr>""")
    unassigned = unassigned_event_progress_rows(g.db, 50)
    unassigned_html = []
    for pr in unassigned:
        run_raw = str(pr["run_json"] or "").strip()
        run_active = "ja" if run_raw and run_raw.lower() != "null" else "nein"
        unassigned_html.append(f"""<tr><td><code>{h(pr['scheduled_event_id'])}</code></td><td>{h(pr['user_id'])}</td><td>{h(pr['attempts'])}</td><td>{h(pr['highest_stage'])}</td><td>{h(pr['best_completion_time_milliseconds'])}</td><td>{run_active}</td><td>{h(pr['updated_at'])}</td></tr>""")
    body = f"""
<div class="card hero-card">
  <h1>Event bearbeiten #{h(item['id'])}</h1>
  <p>{_event_schedule_badges(item)}</p>
  <p class="muted"><code>{h(item['scheduled_event_id'])}</code> · Definition <code>{h(item['event_definition_id'])}</code> · {h(EVENT_TYPE_LABELS.get(item['event_type'], item['event_type']))}</p>
  <p class="small">scheduled_event_id: {'<span class="pill good">gültige UUID</span>' if is_valid_uuid(item['scheduled_event_id']) else '<span class="pill bad">keine gültige UUID</span>'}</p>
</div>
<div class="grid">
  <div class="card">
    <h2>Event-Schedule</h2>
    <form method="post" action="{url_for('event_save', schedule_id=schedule_id)}">
      <label>Titel</label><input name="title" value="{h(item['title'] or '')}">
      <label>Tag</label><input name="tag" value="{h(item['tag'] or '')}">
      <div class="grid"><div><label>Startzeit</label><input type="datetime-local" name="start_time" value="{h(_iso_for_datetime_input(item['start_time']))}"></div><div><label>Endzeit</label><input type="datetime-local" name="end_time" value="{h(_iso_for_datetime_input(item['end_time']))}"></div></div>
      <label>Availability</label><input name="availability" type="number" value="{h(item['availability'])}">
      <label>User-ID leer = alle User</label><input name="user_id" value="{h(item['user_id'] if item['user_id'] is not None else '')}">
      <label>Aktiv</label><select name="is_active"><option value="1" {"selected" if item['is_active'] else ""}>aktiv</option><option value="0" {"selected" if not item['is_active'] else ""}>inaktiv</option></select>
      <label>Additional Event Modifiers</label><input name="additional_event_modifiers" value="{h(modifiers)}" placeholder="z. B. 10, 26">
      <h3>Stage-Rewards</h3>
      {_stage_rewards_editor_html(args)}
      <label>args_json Rohdaten</label><textarea name="args_json" rows="10">{h(json.dumps(args, ensure_ascii=False, indent=2))}</textarea>
      <p><button>Speichern</button></p>
    </form>
  </div>
  <div class="card">
    <h2>Aktionen</h2>
    <form method="post" action="{url_for('event_activate', schedule_id=schedule_id)}"><button>Event aktivieren</button></form>
    <form method="post" action="{url_for('event_deactivate', schedule_id=schedule_id)}"><button class="danger">Event deaktivieren</button></form>
    <form method="post" action="{url_for('event_delete', schedule_id=schedule_id)}" onsubmit="return confirm('Event wirklich komplett aus der Datenbank löschen? Dadurch werden Schedule-Zeilen mit derselben scheduled_event_id und der zugehörige Progress entfernt. Vorher wird automatisch ein Backup erstellt.');"><button class="danger">Event komplett löschen</button></form>
    <p class="small muted">Komplett löschen entfernt alle Schedule-Zeilen mit dieser <code>scheduled_event_id</code> und den passenden Eintrag aus <code>admin_event_progress</code>. Nutze das für alte, abgelaufene oder nicht mehr benötigte Events.</p>
    <form method="post" action="{url_for('event_assign_all', schedule_id=schedule_id)}"><button class="secondary">Event für alle User aktivieren</button></form>
    <form method="post" action="{url_for('event_assign_user', schedule_id=schedule_id)}"><label>Event für User zuweisen</label><input name="user_id" type="number" min="1" placeholder="User-ID"><button class="secondary">User zuweisen</button></form>
    <form method="post" action="{url_for('event_reset_progress', schedule_id=schedule_id)}"><label>Progress für User zurücksetzen</label><input name="user_id" type="number" min="1" value="{h(item['user_id'] if item['user_id'] is not None else '')}" placeholder="User-ID"><button class="danger">Progress für User zurücksetzen</button></form>
    <form method="post" action="{url_for('event_reset_progress', schedule_id=schedule_id)}"><input type="hidden" name="reset_all" value="1"><button class="danger">Progress für alle User zurücksetzen</button></form>
    <form method="post" action="{url_for('event_set_test_rewards', schedule_id=schedule_id)}"><button class="secondary">Standard-Testrewards setzen</button></form>
    <form method="post" action="{url_for('event_import_definition_rewards', schedule_id=schedule_id)}"><button class="secondary">Rewards aus Eventdefinition übernehmen</button></form>
    <form method="post" action="{url_for('events_export')}"><button>Event exportieren</button></form>
  </div>
</div>
<div class="card">
  <h2>Event-Progress</h2>
  <p class="small muted">Progress wird über <code>admin_event_schedule.scheduled_event_id = admin_event_progress.scheduled_event_id</code> geladen und bei user-spezifischen Events zusätzlich nach <code>user_id</code> gefiltert.</p>
  <table><thead><tr><th>User</th><th>attempts</th><th>highest_stage</th><th>best_completion_time_milliseconds</th><th>run aktiv</th><th>updated_at</th><th>Aktion</th></tr></thead><tbody>{''.join(progress_html) or '<tr><td colspan="7" class="muted">Noch kein Progress gespeichert.</td></tr>'}</tbody></table>
</div>
<div class="card">
  <h2>Unzugeordneter Event-Progress</h2>
  <p class="small muted">Diese Zeilen passen aktuell zu keiner Schedule-UUID. Nutze bei alten Events den Button <b>Event-UUIDs/Progress reparieren</b>.</p>
  <table><thead><tr><th>scheduled_event_id</th><th>User</th><th>attempts</th><th>highest_stage</th><th>best_completion_time_milliseconds</th><th>run aktiv</th><th>updated_at</th></tr></thead><tbody>{''.join(unassigned_html) or '<tr><td colspan="7" class="muted">Keine unzugeordneten Progress-Zeilen gefunden.</td></tr>'}</tbody></table>
</div>
"""
    return render_page("Event bearbeiten", body)


@app.post("/events/<int:schedule_id>/save")
def event_save(schedule_id: int):
    item = row("SELECT * FROM admin_event_schedule WHERE id=?", [schedule_id])
    if item is None:
        abort(404)
    make_backup(f"event-save-{schedule_id}")
    try:
        args = _args_from_editor_form(request.form)
        g.db.execute(
            """
            UPDATE admin_event_schedule
            SET title=?, tag=?, user_id=?, start_time=?, end_time=?, availability=?, args_json=?, is_active=?, updated_at=?
            WHERE id=?
            """,
            [
                request.form.get("title") or item["title"],
                request.form.get("tag") or item["tag"],
                parse_nullable_int(request.form.get("user_id")),
                _parse_datetime_to_iso(request.form.get("start_time")),
                _parse_datetime_to_iso(request.form.get("end_time")),
                int(request.form.get("availability") or 1),
                json.dumps(args, ensure_ascii=False, separators=(",", ":")),
                1 if request.form.get("is_active") == "1" else 0,
                now_iso(),
                schedule_id,
            ],
        )
        audit("event-schedule-save", parse_nullable_int(request.form.get("user_id")), "admin_event_schedule", {"schedule_id": schedule_id})
        g.db.commit()
        flash("Event gespeichert.")
    except Exception as exc:
        g.db.rollback()
        flash(f"Event konnte nicht gespeichert werden: {exc}")
    return redirect(url_for("event_detail", schedule_id=schedule_id))


def _event_action_redirect(schedule_id: int):
    """Return to the list view for quick list actions, otherwise the detail page."""
    if request.form.get("next") == "events":
        return redirect(url_for("events_view"))
    return redirect(url_for("event_detail", schedule_id=schedule_id))


@app.post("/events/<int:schedule_id>/activate")
def event_activate(schedule_id: int):
    make_backup(f"event-activate-{schedule_id}")
    g.db.execute("UPDATE admin_event_schedule SET is_active=1, updated_at=? WHERE id=?", [now_iso(), schedule_id])
    audit("event-activate", None, "admin_event_schedule", {"schedule_id": schedule_id})
    g.db.commit()
    flash("Event aktiviert.")
    return _event_action_redirect(schedule_id)


@app.post("/events/<int:schedule_id>/deactivate")
def event_deactivate(schedule_id: int):
    make_backup(f"event-deactivate-{schedule_id}")
    g.db.execute("UPDATE admin_event_schedule SET is_active=0, updated_at=? WHERE id=?", [now_iso(), schedule_id])
    audit("event-deactivate", None, "admin_event_schedule", {"schedule_id": schedule_id})
    g.db.commit()
    flash("Event deaktiviert.")
    return _event_action_redirect(schedule_id)


@app.post("/events/<int:schedule_id>/delete")
def event_delete(schedule_id: int):
    """Delete an admin-created event and its progress rows from SQLite.

    The Node.js server keys game progress by scheduled_event_id. Deleting by that
    UUID removes the visible schedule entry and all matching progress rows in one
    operation, which keeps the Events page clean after old or test events are no
    longer needed. A safety backup is created before any rows are removed.
    """
    item = row("SELECT * FROM admin_event_schedule WHERE id=?", [schedule_id])
    if item is None:
        abort(404)
    scheduled_event_id = str(item["scheduled_event_id"] or "")
    make_backup(f"event-delete-{schedule_id}")
    try:
        progress_deleted = g.db.execute(
            "DELETE FROM admin_event_progress WHERE scheduled_event_id=?",
            [scheduled_event_id],
        ).rowcount
        schedules_deleted = g.db.execute(
            "DELETE FROM admin_event_schedule WHERE scheduled_event_id=?",
            [scheduled_event_id],
        ).rowcount
        audit(
            "event-delete",
            item["user_id"],
            "admin_event_schedule",
            {
                "schedule_id": schedule_id,
                "scheduled_event_id": scheduled_event_id,
                "schedules_deleted": schedules_deleted,
                "progress_deleted": progress_deleted,
            },
        )
        g.db.commit()
        flash(f"Event komplett gelöscht: {schedules_deleted} Schedule-Zeile(n), {progress_deleted} Progress-Zeile(n).")
    except Exception as exc:
        g.db.rollback()
        flash(f"Event konnte nicht gelöscht werden: {exc}")
        return redirect(url_for("event_detail", schedule_id=schedule_id))
    return redirect(url_for("events_view"))


@app.post("/events/<int:schedule_id>/assign-all")
def event_assign_all(schedule_id: int):
    make_backup(f"event-assign-all-{schedule_id}")
    g.db.execute("UPDATE admin_event_schedule SET user_id=NULL, is_active=1, updated_at=? WHERE id=?", [now_iso(), schedule_id])
    audit("event-assign-all", None, "admin_event_schedule", {"schedule_id": schedule_id})
    g.db.commit()
    flash("Event ist jetzt global für alle User aktiv.")
    return redirect(url_for("event_detail", schedule_id=schedule_id))


@app.post("/events/<int:schedule_id>/assign-user")
def event_assign_user(schedule_id: int):
    user_id = parse_nullable_int(request.form.get("user_id"))
    if not user_id:
        flash("Bitte User-ID angeben.")
        return redirect(url_for("event_detail", schedule_id=schedule_id))
    item = row("SELECT * FROM admin_event_schedule WHERE id=?", [schedule_id])
    if item is None:
        abort(404)
    make_backup(f"event-assign-user-{schedule_id}-{user_id}")
    g.db.execute(
        """
        INSERT INTO admin_event_schedule(
          scheduled_event_id, event_definition_id, event_type, tag, title, user_id, start_time, end_time,
          availability, min_api_version, max_api_version, stop_time, args_json, is_active, created_at, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [valid_or_new_uuid(item["scheduled_event_id"]), item["event_definition_id"], item["event_type"], item["tag"], item["title"], user_id, item["start_time"], item["end_time"], item["availability"], item["min_api_version"], item["max_api_version"], item["stop_time"], item["args_json"], 1, now_iso(), now_iso()],
    )
    new_id = int(g.db.execute("SELECT last_insert_rowid()").fetchone()[0])
    new_item = g.db.execute("SELECT scheduled_event_id FROM admin_event_schedule WHERE id=?", [new_id]).fetchone()
    reset_event_progress_defaults(g.db, new_item["scheduled_event_id"], user_id, reset_all=False)
    audit("event-assign-user", user_id, "admin_event_schedule", {"source_schedule_id": schedule_id, "new_schedule_id": new_id})
    g.db.commit()
    flash(f"Event für User #{user_id} zugewiesen.")
    return redirect(url_for("event_detail", schedule_id=new_id))


@app.post("/events/<int:schedule_id>/reset-progress")
def event_reset_progress(schedule_id: int):
    item = row("SELECT * FROM admin_event_schedule WHERE id=?", [schedule_id])
    if item is None:
        abort(404)
    user_id = parse_nullable_int(request.form.get("user_id"))
    reset_all = request.form.get("reset_all") == "1"
    if not reset_all and user_id is None and item["user_id"] is not None:
        user_id = int(item["user_id"])
    if not reset_all and user_id is None:
        flash("Bitte eine User-ID angeben oder 'Progress für alle User zurücksetzen' benutzen.")
        return redirect(url_for("event_detail", schedule_id=schedule_id))
    make_backup(f"event-reset-progress-{schedule_id}")
    changed = reset_event_progress_defaults(g.db, item["scheduled_event_id"], user_id=user_id, reset_all=reset_all)
    audit("event-reset-progress", user_id, "admin_event_progress", {"schedule_id": schedule_id, "scheduled_event_id": item["scheduled_event_id"], "changed": changed, "reset_all": reset_all})
    g.db.commit()
    flash(f"Event-Progress auf Standardwerte zurückgesetzt: {changed} Zeile(n).")
    return redirect(url_for("event_detail", schedule_id=schedule_id))


@app.post("/events/<int:schedule_id>/set-test-rewards")
def event_set_test_rewards(schedule_id: int):
    item = row("SELECT * FROM admin_event_schedule WHERE id=?", [schedule_id])
    if item is None:
        abort(404)
    args = _safe_json_loads(item["args_json"], {})
    if not isinstance(args, dict):
        args = {}
    args["stage_rewards"] = default_test_stage_rewards()
    make_backup(f"event-test-rewards-{schedule_id}")
    g.db.execute("UPDATE admin_event_schedule SET args_json=?, updated_at=? WHERE id=?", [json.dumps(args, ensure_ascii=False, separators=(",", ":")), now_iso(), schedule_id])
    audit("event-test-rewards", item["user_id"], "admin_event_schedule", {"schedule_id": schedule_id})
    g.db.commit()
    flash("Standard-Testrewards gesetzt.")
    return redirect(url_for("event_detail", schedule_id=schedule_id))


@app.post("/events/<int:schedule_id>/import-definition-rewards")
def event_import_definition_rewards(schedule_id: int):
    item = row("SELECT * FROM admin_event_schedule WHERE id=?", [schedule_id])
    if item is None:
        abort(404)
    event = event_definition_by_schedule_row(item)
    args = _safe_json_loads(item["args_json"], {})
    if not isinstance(args, dict):
        args = {}
    rewards = _normalize_stage_rewards((event or {}).get("default_args_json", {}).get("stage_rewards"))
    if not rewards:
        flash("Diese Eventdefinition enthält keine ableitbaren Stage-Rewards.")
        return redirect(url_for("event_detail", schedule_id=schedule_id))
    args["stage_rewards"] = rewards
    make_backup(f"event-import-definition-rewards-{schedule_id}")
    g.db.execute("UPDATE admin_event_schedule SET args_json=?, updated_at=? WHERE id=?", [json.dumps(args, ensure_ascii=False, separators=(",", ":")), now_iso(), schedule_id])
    audit("event-import-definition-rewards", item["user_id"], "admin_event_schedule", {"schedule_id": schedule_id, "rewards": len(rewards)})
    g.db.commit()
    flash("Rewards aus Eventdefinition übernommen.")
    return redirect(url_for("event_detail", schedule_id=schedule_id))


@app.post("/events/export")
def events_export():
    make_backup("event-export")
    path = export_admin_events_json(g.db)
    audit("event-export", None, "admin_event_schedule", {"path": str(path)})
    g.db.commit()
    flash(f"Events exportiert: {path}")
    return redirect(url_for("events_view"))



# ---------------------------------------------------------------------------
# Inbox / ingame messages web UI
# ---------------------------------------------------------------------------
@app.get("/inbox")
def inbox_view() -> str:
    messages = _inbox_message_rows()
    rows_html = []
    for msg in messages:
        has_rewards = bool(_safe_json_loads(msg["resources_json"], []))
        rows_html.append(f"""<tr>
<td><a href="{url_for('inbox_detail', message_id=msg['id'])}">#{h(msg['id'])}</a></td>
<td><b>{h(msg['title'])}</b><br><span class="muted small">{h(str(msg['body'])[:120])}{'…' if len(str(msg['body'])) > 120 else ''}</span></td>
<td>{'Alle User' if msg['user_id'] is None else 'User ' + h(msg['user_id'])}</td>
<td>{_inbox_badges(msg)}</td>
<td>{h(_epoch_to_text(msg['published']))}</td>
<td>{h(_epoch_to_text(msg['expires']))}</td>
<td>{'ja' if has_rewards else 'nein'}</td>
<td>{h(msg['read_count'])}</td>
<td>{h(msg['claimed_count'])}</td>
<td>{h(msg['deleted_count'])}</td>
<td>
  <a class="btn secondary" href="{url_for('inbox_detail', message_id=msg['id'])}">Öffnen</a>
  {'<form class="inline" method="post" action="' + url_for('inbox_deactivate', message_id=msg['id']) + '"><button class="danger">Deaktivieren</button></form>' if int(msg['is_active'] or 0) else '<form class="inline" method="post" action="' + url_for('inbox_activate', message_id=msg['id']) + '"><button>Aktivieren</button></form>'}
</td>
</tr>""")
    active_filter = request.args.get("active", "")
    target_filter = request.args.get("target", "")
    expired_filter = request.args.get("expired", "")
    now_default = _epoch_to_datetime_input(_now_epoch())
    expires_default = _epoch_to_datetime_input(_now_epoch() + 7 * 24 * 3600)
    active_opts = "".join([
        f'<option value=""{option_selected("", active_filter)}>Alle</option>',
        f'<option value="1"{option_selected("1", active_filter)}>aktiv</option>',
        f'<option value="0"{option_selected("0", active_filter)}>inaktiv</option>',
    ])
    target_opts = "".join([
        f'<option value=""{option_selected("", target_filter)}>Alle</option>',
        f'<option value="global"{option_selected("global", target_filter)}>Global</option>',
        f'<option value="user"{option_selected("user", target_filter)}>User-spezifisch</option>',
    ])
    expired_opts = "".join([
        f'<option value=""{option_selected("", expired_filter)}>Alle</option>',
        f'<option value="0"{option_selected("0", expired_filter)}>nicht abgelaufen</option>',
        f'<option value="1"{option_selected("1", expired_filter)}>abgelaufen</option>',
    ])
    body = f"""
<div class="card hero-card">
  <h1>Nachrichten / Inbox</h1>
  <p class="muted">Verwaltet Ingame-Nachrichten für das vorhandene Mighty-DOOM-Inbox-System. Der Adminserver schreibt nur in die SQLite-Bridge-Tabellen; der Node.js-Gameserver liest diese Tabellen später für die App.</p>
</div>
<div class="grid">
  <div class="card">
    <h2>Nachricht erstellen</h2>
    <form method="post" action="{url_for('inbox_create')}">
      <label>Titel</label><input name="title" required>
      <label>Nachrichtentext</label><textarea name="body" rows="5" required></textarea>
      <div class="grid">
        <div><label>Zielgruppe</label><select name="target"><option value="all">Alle User</option><option value="user">bestimmter User</option></select></div>
        <div><label>User-Auswahl</label><select name="user_id">{_users_select_options(include_blank=True)}</select></div>
      </div>
      <div class="grid">
        <div><label>Aktiv</label><select name="is_active"><option value="1">ja</option><option value="0">nein</option></select></div>
        <div><label>Display Type</label><input name="display_type" type="number" value="1" min="1"></div>
      </div>
      <div class="grid">
        <div><label>Veröffentlicht ab</label><input name="published" type="datetime-local" value="{h(now_default)}"></div>
        <div><label>Läuft ab</label><input name="expires" type="datetime-local" value="{h(expires_default)}"></div>
      </div>
      <label>Image ID optional</label><input name="image_id" placeholder="optional">
      <h3>Rewards optional</h3>
      {_inbox_rewards_editor_html('[]')}
      <p><button>Nachricht erstellen</button></p>
    </form>
  </div>
  <div class="card">
    <h2>Filter</h2>
    <form method="get">
      <label>Titel/Textsuche</label><input name="q" value="{h(request.args.get('q',''))}">
      <div class="grid"><div><label>Aktiv/Inaktiv</label><select name="active">{active_opts}</select></div><div><label>Global/User-spezifisch</label><select name="target">{target_opts}</select></div></div>
      <label>Abgelaufen</label><select name="expired">{expired_opts}</select>
      <p><button>Suchen</button> <a class="btn secondary" href="{url_for('inbox_view')}">Alle</a></p>
    </form>
  </div>
</div>
<div class="card">
  <h2>Nachrichtenübersicht</h2>
  <table><thead><tr><th>ID</th><th>Titel</th><th>Zielgruppe</th><th>Status</th><th>Veröffentlicht ab</th><th>Läuft ab</th><th>Hat Rewards</th><th>gelesen</th><th>geclaimt</th><th>gelöscht</th><th>Aktionen</th></tr></thead><tbody>{''.join(rows_html) or '<tr><td colspan="11" class="muted">Noch keine Nachrichten vorhanden.</td></tr>'}</tbody></table>
</div>
"""
    return render_page("Nachrichten", body)


@app.post("/inbox/create")
def inbox_create():
    make_backup("inbox-message-create")
    try:
        payload = _inbox_payload_from_request(request.form)
        now_value = _now_epoch()
        g.db.execute(
            """
            INSERT INTO admin_inbox_messages(
              user_id, display_type, title, body, published, expires, resources_json, image_id,
              conditions_json, is_active, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [payload["user_id"], payload["display_type"], payload["title"], payload["body"], payload["published"], payload["expires"], payload["resources_json"], payload["image_id"], payload["conditions_json"], payload["is_active"], now_value, now_value],
        )
        message_id = int(g.db.execute("SELECT last_insert_rowid()").fetchone()[0])
        audit("inbox-message-create", payload["user_id"], "admin_inbox_messages", {"message_id": message_id, "title": payload["title"], "has_rewards": bool(json.loads(payload["resources_json"]))})
        g.db.commit()
        flash("Nachricht erstellt.")
        return redirect(url_for("inbox_detail", message_id=message_id))
    except Exception as exc:
        g.db.rollback()
        flash(f"Nachricht konnte nicht erstellt werden: {exc}")
        return redirect(url_for("inbox_view"))


@app.get("/inbox/<int:message_id>")
def inbox_detail(message_id: int) -> str:
    msg = row("SELECT * FROM admin_inbox_messages WHERE id=?", [message_id])
    if msg is None:
        return render_page("Nicht gefunden", "<div class='card bad'>Nachricht nicht gefunden.</div>")
    state_rows = _message_detail_state_rows(message_id)
    state_count = len(state_rows)
    status_rows = []
    for st in state_rows:
        run_state = _inbox_state_label(st["state"])
        status_rows.append(f"""<tr>
<td>{h(st['user_id'])}</td><td>{h(run_state)}</td><td>{h(_epoch_to_text(st['read_at']))}</td><td>{h(_epoch_to_text(st['claimed_at']))}</td><td>{h(_epoch_to_text(st['deleted_at']))}</td><td>{h(_epoch_to_text(st['updated_at']))}</td>
<td><form class="inline" method="post" action="{url_for('inbox_reset_state', message_id=message_id)}"><input type="hidden" name="user_id" value="{h(st['user_id'])}"><button class="secondary">Status für User zurücksetzen</button></form></td>
</tr>""")
    target_locked = state_count > 0
    target_notice = "<p class='muted small'>Zielgruppe ist gesperrt, weil bereits User-State-Einträge existieren. Setze den Status zuerst zurück, wenn du die Zielgruppe ändern willst.</p>" if target_locked else ""
    target_select = f"""
<select name="target" {'disabled' if target_locked else ''}>
  <option value="all"{option_selected('all', 'all' if msg['user_id'] is None else 'user')}>Alle User</option>
  <option value="user"{option_selected('user', 'all' if msg['user_id'] is None else 'user')}>bestimmter User</option>
</select>
"""
    user_select = f"<select name='user_id' {'disabled' if target_locked else ''}>{_users_select_options(selected=msg['user_id'], include_blank=True)}</select>"
    if target_locked:
        target_select += f"<input type='hidden' name='target' value='{'all' if msg['user_id'] is None else 'user'}'>"
        if msg['user_id'] is not None:
            user_select += f"<input type='hidden' name='user_id' value='{h(msg['user_id'])}'>"
    raw_rewards = json.dumps(_safe_json_loads(msg["resources_json"], []), ensure_ascii=False, indent=2)
    body = f"""
<div class="card hero-card"><h1>Nachricht #{h(msg['id'])}</h1><p>{_inbox_badges(msg)}</p></div>
<div class="grid">
  <div class="card">
    <h2>Nachricht bearbeiten</h2>
    <form method="post" action="{url_for('inbox_save', message_id=message_id)}">
      <label>Titel</label><input name="title" value="{h(msg['title'])}" required>
      <label>Nachrichtentext</label><textarea name="body" rows="7" required>{h(msg['body'])}</textarea>
      <div class="grid"><div><label>Zielgruppe</label>{target_select}</div><div><label>User-Auswahl</label>{user_select}</div></div>
      {target_notice}
      <div class="grid"><div><label>Aktiv</label><select name="is_active"><option value="1"{option_selected(1,msg['is_active'])}>ja</option><option value="0"{option_selected(0,msg['is_active'])}>nein</option></select></div><div><label>Display Type</label><input name="display_type" type="number" value="{h(msg['display_type'])}" min="1"></div></div>
      <div class="grid"><div><label>Veröffentlicht ab</label><input name="published" type="datetime-local" value="{h(_epoch_to_datetime_input(msg['published']))}"></div><div><label>Läuft ab</label><input name="expires" type="datetime-local" value="{h(_epoch_to_datetime_input(msg['expires']))}"></div></div>
      <label>Image ID optional</label><input name="image_id" value="{h(msg['image_id'])}">
      <h3>Rewards</h3>{_inbox_rewards_editor_html(msg['resources_json'])}
      <details><summary>resources_json raw</summary><pre>{h(raw_rewards)}</pre></details>
      <p><button>Speichern</button></p>
    </form>
  </div>
  <div class="card">
    <h2>Aktionen</h2>
    <div class="actions">
      <form method="post" action="{url_for('inbox_deactivate', message_id=message_id)}"><button class="danger">Deaktivieren</button></form>
      <form method="post" action="{url_for('inbox_activate', message_id=message_id)}"><button>Aktivieren</button></form>
    </div>
    <h3>Status zurücksetzen</h3>
    <form method="post" action="{url_for('inbox_reset_state', message_id=message_id)}"><label>User-ID</label><input name="user_id" placeholder="z. B. 7"><p><button class="secondary">Status für User zurücksetzen</button></p></form>
    <form method="post" action="{url_for('inbox_reset_state', message_id=message_id)}" onsubmit="return confirm('Status für alle User dieser Nachricht zurücksetzen?');"><input type="hidden" name="reset_all" value="1"><button class="secondary">Status für alle User zurücksetzen</button></form>
    <h3>Gefahrenzone</h3>
    <form method="post" action="{url_for('inbox_delete', message_id=message_id)}" onsubmit="return confirm('Nachricht komplett löschen? Zugehörige User-Status-Einträge werden ebenfalls gelöscht. Vorher wird ein Backup erstellt.');"><button class="danger">Komplett löschen</button></form>
  </div>
</div>
<div class="card"><h2>User-Status</h2><table><thead><tr><th>user_id</th><th>state</th><th>read_at</th><th>claimed_at</th><th>deleted_at</th><th>updated_at</th><th>Aktion</th></tr></thead><tbody>{''.join(status_rows) or '<tr><td colspan="7" class="muted">Noch keine User-State-Einträge für diese Nachricht.</td></tr>'}</tbody></table></div>
"""
    return render_page("Nachricht bearbeiten", body)


@app.post("/inbox/<int:message_id>/save")
def inbox_save(message_id: int):
    msg = row("SELECT * FROM admin_inbox_messages WHERE id=?", [message_id])
    if msg is None:
        abort(404)
    state_count = int(row("SELECT COUNT(*) AS c FROM admin_inbox_message_state WHERE message_id=?", [message_id])["c"])
    make_backup(f"inbox-message-save-{message_id}")
    try:
        payload = _inbox_payload_from_request(request.form)
        if state_count > 0:
            payload["user_id"] = msg["user_id"]
        old_rewards = msg["resources_json"] or "[]"
        g.db.execute(
            """
            UPDATE admin_inbox_messages
            SET user_id=?, display_type=?, title=?, body=?, published=?, expires=?, resources_json=?, image_id=?, conditions_json=?, is_active=?, updated_at=?
            WHERE id=?
            """,
            [payload["user_id"], payload["display_type"], payload["title"], payload["body"], payload["published"], payload["expires"], payload["resources_json"], payload["image_id"], payload["conditions_json"], payload["is_active"], _now_epoch(), message_id],
        )
        audit("inbox-message-edit", payload["user_id"], "admin_inbox_messages", {"message_id": message_id, "target_locked": state_count > 0})
        if old_rewards != payload["resources_json"]:
            audit("inbox-rewards-edit", payload["user_id"], "admin_inbox_messages", {"message_id": message_id, "resources_json": payload["resources_json"]})
        g.db.commit()
        flash("Nachricht gespeichert.")
    except Exception as exc:
        g.db.rollback()
        flash(f"Nachricht konnte nicht gespeichert werden: {exc}")
    return redirect(url_for("inbox_detail", message_id=message_id))


@app.post("/inbox/<int:message_id>/activate")
def inbox_activate(message_id: int):
    make_backup(f"inbox-message-activate-{message_id}")
    g.db.execute("UPDATE admin_inbox_messages SET is_active=1, updated_at=? WHERE id=?", [_now_epoch(), message_id])
    audit("inbox-message-activate", None, "admin_inbox_messages", {"message_id": message_id})
    g.db.commit()
    flash("Nachricht aktiviert.")
    return redirect(request.referrer or url_for("inbox_view"))


@app.post("/inbox/<int:message_id>/deactivate")
def inbox_deactivate(message_id: int):
    make_backup(f"inbox-message-deactivate-{message_id}")
    g.db.execute("UPDATE admin_inbox_messages SET is_active=0, updated_at=? WHERE id=?", [_now_epoch(), message_id])
    audit("inbox-message-deactivate", None, "admin_inbox_messages", {"message_id": message_id})
    g.db.commit()
    flash("Nachricht deaktiviert.")
    return redirect(request.referrer or url_for("inbox_view"))


@app.post("/inbox/<int:message_id>/delete")
def inbox_delete(message_id: int):
    msg = row("SELECT * FROM admin_inbox_messages WHERE id=?", [message_id])
    if msg is None:
        abort(404)
    make_backup(f"inbox-message-delete-{message_id}")
    state_deleted = g.db.execute("DELETE FROM admin_inbox_message_state WHERE message_id=?", [message_id]).rowcount
    message_deleted = g.db.execute("DELETE FROM admin_inbox_messages WHERE id=?", [message_id]).rowcount
    audit("inbox-message-delete", msg["user_id"], "admin_inbox_messages", {"message_id": message_id, "state_deleted": state_deleted, "message_deleted": message_deleted})
    g.db.commit()
    flash(f"Nachricht komplett gelöscht: {message_deleted} Nachricht, {state_deleted} Status-Zeile(n).")
    return redirect(url_for("inbox_view"))


@app.post("/inbox/<int:message_id>/reset-state")
def inbox_reset_state(message_id: int):
    msg = row("SELECT * FROM admin_inbox_messages WHERE id=?", [message_id])
    if msg is None:
        abort(404)
    reset_all = request.form.get("reset_all") == "1"
    user_id = parse_nullable_int(request.form.get("user_id"))
    if not reset_all and user_id is None:
        flash("Bitte User-ID angeben oder Status für alle User zurücksetzen.")
        return redirect(url_for("inbox_detail", message_id=message_id))
    make_backup(f"inbox-state-reset-{message_id}")
    if reset_all:
        changed = g.db.execute("DELETE FROM admin_inbox_message_state WHERE message_id=?", [message_id]).rowcount
    else:
        changed = g.db.execute("DELETE FROM admin_inbox_message_state WHERE message_id=? AND user_id=?", [message_id, user_id]).rowcount
    audit("inbox-state-reset", user_id, "admin_inbox_message_state", {"message_id": message_id, "reset_all": reset_all, "changed": changed})
    g.db.commit()
    flash(f"Status zurückgesetzt: {changed} Zeile(n).")
    return redirect(url_for("inbox_detail", message_id=message_id))


@app.get("/catalog")
def catalog_view() -> str:
    catalog = get_catalog()
    q = request.args.get("q", "").strip().lower()
    resources = catalog.get("resources_list", [])
    if q:
        def match(info: dict[str, Any]) -> bool:
            hay = " ".join(str(info.get(k, "")) for k in ("id", "name", "tag", "category_label", "section_label", "description")).lower()
            return q in hay
        resources = [r for r in resources if match(r)]
    trs = []
    for info in resources[:800]:
        trs.append(f"""<tr>
<td>{h(info.get('id'))}</td>
<td><b>{h(info.get('name'))}</b><br><span class="muted small">{h(info.get('tag'))}</span></td>
<td>{h(info.get('section_label'))}</td>
<td><span class="pill">{h(info.get('category_label'))}</span></td>
<td>{h(info.get('compatible_slot_text') or '-')}</td>
<td>{h(_availability_label(info.get('availability')))}</td>
<td>{h(info.get('description'))}</td>
</tr>""")
    slot_rows = "".join(
        f"<tr><td>{h(s['id'])}</td><td>{h(s['label'])}</td><td>{h(s['tag'])}</td><td>{h(s['type'])}</td><td>{h(s['attribute_set'])}</td></tr>"
        for s in sorted(catalog.get("slots_by_id", {}).values(), key=lambda x: x["id"])
    )
    body = f"""
<div class="card"><h1>Resource-Katalog</h1>{catalog_status_html()}
<p class="muted">Dieser Katalog wird aus <code>game-data.json</code> geladen und ist die Grundlage für Item-Namen, Kategorien, Slots und Dropdowns.</p>
<form method="get"><label>Suche nach RID, Name, Tag, Kategorie</label><input name="q" value="{h(request.args.get('q',''))}" placeholder="z. B. heavy_cannon, launcher, 4"><p><button>Suchen</button> <a class="btn secondary" href="{url_for('catalog_view')}">Alle</a></p></form></div>
<div class="card"><h2>Inventory Slots</h2><table><thead><tr><th>Slot ID</th><th>Name</th><th>Tag</th><th>Typ</th><th>Attribute Set</th></tr></thead><tbody>{slot_rows}</tbody></table></div>
<div class="card"><h2>Resources</h2><p class="muted small">Angezeigt: {len(resources)} Treffer, maximal 800 Zeilen.</p><table><thead><tr><th>RID</th><th>Name/Tag</th><th>Quelle</th><th>Kategorie</th><th>Kompatible Slots</th><th>Availability</th><th>Beschreibung</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>
"""
    return render_page("Katalog", body)


@app.get("/energy-autofill")
def energy_autofill() -> str:
    configs = energy_autofill_rows()
    trs = []
    for c in configs:
        status = '<span class="good">aktiv</span>' if c["enabled"] else '<span class="muted">aus</span>'
        trs.append(
            f"""<tr>
<td><a href="{url_for('user_detail', user_id=c['user_id'])}">{h(c['user_id'])}</a></td>
<td><code>{h(c['uuid'])}</code></td>
<td>{status}</td>
<td>{h(resource_label(c['rid'], compact=True))}</td>
<td>{h(c['current_amount'])}</td>
<td>{h(c['target_amount'])}</td>
<td>{h(c['interval_seconds'])} s</td>
<td>{h(c['last_checked_at'])}</td>
<td>{h(c['last_changed_at'])}</td>
<td>
<form class="inline" method="post" action="{url_for('energy_autofill_run_now')}"><input type="hidden" name="user_id" value="{h(c['user_id'])}"><button class="secondary">Jetzt setzen</button></form>
<form class="inline" method="post" action="{url_for('energy_autofill_save')}">
<input type="hidden" name="user_id" value="{h(c['user_id'])}">
<input type="hidden" name="rid" value="{h(c['rid'])}">
<input type="hidden" name="target_amount" value="{h(c['target_amount'])}">
<input type="hidden" name="interval_seconds" value="{h(c['interval_seconds'])}">
<button class="secondary" name="enabled" value="{'0' if c['enabled'] else '1'}">{'Ausschalten' if c['enabled'] else 'Einschalten'}</button>
</form>
</td>
</tr>"""
        )
    body = f"""
<div class="card">
<h1>Energy Auto-Fill</h1>
<p class="muted">Hier kannst du für einzelne User eine Energy-Sperre setzen. Der Admin-Prozess prüft im Hintergrund regelmäßig und setzt <code>energies.amount</code> für RID 28 wieder auf den Zielwert.</p>
<form method="post" action="{url_for('energy_autofill_save')}">
<div class="grid">
<div><label>User-ID</label><input name="user_id" type="number" min="1" placeholder="z. B. 7"></div>
<div><label>Energy-RID</label><select name="rid">{simple_key_options('energies', 'rid', selected=28)}</select></div>
<div><label>Zielwert</label><input name="target_amount" type="number" min="0" value="20"></div>
<div><label>Prüfintervall Sekunden</label><input name="interval_seconds" type="number" min="60" value="120"></div>
<div><label>Aktiv</label><select name="enabled"><option value="1">aktiv</option><option value="0">aus</option></select></div>
</div>
<p><button>Für User speichern</button></p>
</form>
</div>
<div class="card"><h2>Konfigurationen</h2><table><thead><tr><th>User</th><th>UUID</th><th>Status</th><th>Ressource</th><th>Aktuell</th><th>Ziel</th><th>Intervall</th><th>Letzter Check</th><th>Letzte Änderung</th><th>Aktion</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>
"""
    return render_page("Energy Auto-Fill", body)


@app.post("/energy-autofill/save")
def energy_autofill_save():
    user_id = int(request.form["user_id"])
    rid = int(request.form.get("rid") or 28)
    target_amount = max(0, int(request.form.get("target_amount") or 20))
    interval_seconds = max(60, int(request.form.get("interval_seconds") or 120))
    enabled = int(request.form.get("enabled", "1"))
    if row("SELECT id FROM users WHERE id=?", [user_id]) is None:
        flash("User nicht gefunden.")
        return redirect(request.referrer or url_for("energy_autofill"))
    make_backup("energy-autofill-config")
    g.db.execute(
        """
        INSERT INTO admin_energy_autofill(user_id, rid, target_amount, interval_seconds, enabled, updated_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
          rid=excluded.rid,
          target_amount=excluded.target_amount,
          interval_seconds=excluded.interval_seconds,
          enabled=excluded.enabled,
          updated_at=excluded.updated_at
        """,
        [user_id, rid, target_amount, interval_seconds, enabled, now_iso()],
    )
    audit("energy-autofill-config", user_id, "admin_energy_autofill", {"rid": rid, "target_amount": target_amount, "interval_seconds": interval_seconds, "enabled": enabled})
    if request.form.get("run_now") == "1" or enabled:
        cfg = row("SELECT * FROM admin_energy_autofill WHERE user_id=?", [user_id])
        if cfg is not None and request.form.get("run_now") == "1":
            apply_energy_autofill_once(g.db, cfg, source="manual")
    g.db.commit()
    flash(f"Energy Auto-Fill für User {user_id} gespeichert." + (" Direkt gesetzt." if request.form.get("run_now") == "1" else ""))
    return redirect(request.referrer or url_for("energy_autofill"))


@app.post("/energy-autofill/run-now")
def energy_autofill_run_now():
    user_id = int(request.form["user_id"])
    cfg = row("SELECT * FROM admin_energy_autofill WHERE user_id=?", [user_id])
    if cfg is None:
        flash("Für diesen User gibt es noch keine Energy-Auto-Fill-Konfiguration.")
    else:
        apply_energy_autofill_once(g.db, cfg, source="manual")
        flash(f"Energy für User {user_id} geprüft/gesetzt.")
    return redirect(request.referrer or url_for("energy_autofill"))


@app.get("/backups")
def backups() -> str:
    out_dir = backup_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    db_records = rows("SELECT * FROM admin_db_backups ORDER BY id DESC LIMIT 100")
    files = sorted(out_dir.glob("*.sqlite3"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[:100]
    seen = {r["path"] for r in db_records}
    file_rows = []
    for f in files:
        in_log = "ja" if str(f) in seen else "nur Datei"
        file_rows.append(
            f"<tr><td>{h(dt.datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'))}</td><td><code>{h(f.name)}</code></td><td>{h(file_size_text(f))}</td><td>{h(in_log)}</td><td><div class='actions'><a class='btn secondary' href='{url_for('backup_download', name=f.name)}'>Download</a><form class='inline' method='post' action='{url_for('backup_restore')}' onsubmit='return confirm(&quot;Backup {h(f.name)} wirklich zurückspielen? Vorher wird automatisch ein Sicherheitsbackup erstellt.&quot;);'><input type='hidden' name='name' value='{h(f.name)}'><button class='danger'>Zurückspielen</button></form></div></td></tr>"
        )
    log_rows = "".join(
        f"<tr><td>{h(r['created_at'])}</td><td>{h(r['reason'])}</td><td><code>{h(Path(r['path']).name)}</code></td><td>{h(file_size_text(Path(r['path'])))}</td></tr>"
        for r in db_records
    )
    body = f"""
<div class="card">
<h1>Datenbank-Backups</h1>
<p class="muted">Backups werden lokal auf dem Server gespeichert unter <code>{h(out_dir)}</code>.</p>
<form method="post" action="{url_for('backup_create')}">
  <label>Grund / Name</label><input name="reason" value="manual">
  <p><button>Backup jetzt erstellen</button></p>
</form>
<p class="muted small"><b>Restore:</b> Beim Zurückspielen wird vorher automatisch ein Sicherheitsbackup des aktuellen Stands erstellt. Danach wird die gewählte SQLite-Datei über die aktive DB kopiert.</p>
</div>
<div class="card"><h2>Backup-Dateien</h2><table><thead><tr><th>Zeit</th><th>Datei</th><th>Größe</th><th>Log</th><th>Aktion</th></tr></thead><tbody>{''.join(file_rows)}</tbody></table></div>
<div class="card"><h2>Backup-Log</h2><table><thead><tr><th>Zeit</th><th>Grund</th><th>Datei</th><th>Größe</th></tr></thead><tbody>{log_rows}</tbody></table></div>
"""
    return render_page("Backups", body)


@app.post("/backups/create")
def backup_create():
    reason = request.form.get("reason", "manual") or "manual"
    target = make_backup(reason)
    audit("backup-create", None, "admin_db_backups", {"reason": reason, "path": str(target) if target else None})
    g.db.commit()
    flash(f"Backup erstellt: {target}" if target else "Backup ist deaktiviert.")
    return redirect(request.referrer or url_for("backups"))


@app.get("/backups/download/<name>")
def backup_download(name: str):
    if "/" in name or "\\" in name or not name.endswith(".sqlite3"):
        abort(404)
    path = (backup_dir() / name).resolve()
    if backup_dir() not in path.parents and path != backup_dir():
        abort(404)
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True)



@app.post("/backups/restore")
def backup_restore():
    name = request.form.get("name", "")
    try:
        backup_path = _mobile_backup_path_from_name(name)
    except FileNotFoundError as exc:
        flash(str(exc))
        return redirect(url_for("backups"))
    except Exception as exc:
        flash(f"Restore abgebrochen: {exc}")
        return redirect(url_for("backups"))

    source_db = db_path()
    if not source_db.exists():
        flash(f"Aktuelle Datenbank nicht gefunden: {source_db}")
        return redirect(url_for("backups"))

    with _ENERGY_AUTOFILL_LOCK:
        pre_restore_backup = make_backup("pre-restore-web")
        try:
            audit(
                "backup-restore-web-start",
                None,
                "admin_db_backups",
                {
                    "restore_from": str(backup_path),
                    "pre_restore_backup": str(pre_restore_backup) if pre_restore_backup else None,
                },
            )
            g.db.commit()
        except Exception:
            pass

        con = getattr(g, "db", None)
        if con is not None:
            try:
                con.close()
            except Exception:
                pass
            g.db = None

        shutil.copy2(backup_path, source_db)

        restored_con = sqlite3.connect(source_db)
        restored_con.row_factory = sqlite3.Row
        restored_con.execute("PRAGMA foreign_keys = ON")
        restored_con.execute("PRAGMA busy_timeout = 5000")
        ensure_admin_tables(restored_con)
        if pre_restore_backup is not None:
            try:
                restored_con.execute(
                    """
                    INSERT INTO admin_db_backups(created_at, reason, path, size_bytes)
                    VALUES(?,?,?,?)
                    """,
                    [now_iso(), "pre-restore-web", str(pre_restore_backup), pre_restore_backup.stat().st_size],
                )
            except Exception:
                pass
        restored_con.execute(
            """
            INSERT INTO admin_change_log(created_at, action, table_name, user_id, details)
            VALUES(?,?,?,?,?)
            """,
            [
                now_iso(),
                "backup-restore-web",
                "admin_db_backups",
                None,
                json.dumps(
                    {
                        "restored_from": str(backup_path),
                        "pre_restore_backup": str(pre_restore_backup) if pre_restore_backup else None,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ],
        )
        restored_con.commit()
        restored_con.close()

    flash(
        "Backup zurückgespielt: "
        + backup_path.name
        + (f". Sicherheitsbackup vorher: {pre_restore_backup.name}" if pre_restore_backup else ".")
    )
    return redirect(url_for("backups"))


@app.get("/changes")
def change_log() -> str:
    user_id = request.args.get("user_id", "").strip()
    params: list[Any] = []
    where = ""
    if user_id:
        where = "WHERE user_id = ?"
        params.append(int(user_id))
    changes = rows(f"SELECT * FROM admin_change_log {where} ORDER BY id DESC LIMIT 300", params)
    undone = rolled_back_change_ids(g.db)

    trs: list[str] = []
    cards: list[str] = []
    for c in changes:
        details = parse_change_details(c["details"])
        summary = compact_change_summary(c["table_name"] or "", c["action"], details)
        action_html = ""
        if c["action"] in {"db-insert", "db-update", "db-delete"}:
            action_html = rollback_action_html(c["id"], int(c["id"]) in undone, "Rückgängig")
        elif c["action"] == "audit-rollback":
            action_html = "<span class='good small'>Rollback-Protokoll</span>"
        trs.append(
            f"""
<tr>
<td>{h(c['id'])}</td>
<td class="nowrap">{h(c['created_at'])}</td>
<td>{h(c['user_id'])}</td>
<td>{h(c['action'])}</td>
<td>{h(c['table_name'])}</td>
<td>{h(summary)}<details><summary>Rohdaten</summary><pre>{h(c['details'])}</pre></details></td>
<td>{action_html}</td>
</tr>
"""
        )
        if c["action"] in {"db-insert", "db-update", "db-delete", "audit-rollback"}:
            cards.append(
                f"""
<div class="audit-card">
  <div class="audit-card-head"><strong>#{h(c['id'])} · {h(c['action'])}</strong><span>{h(c['created_at'])}</span></div>
  <div class="muted small">User: {h(c['user_id']) or '-'} · Tabelle: {h(c['table_name']) or '-'}</div>
  <p>{h(summary)}</p>
  <details><summary>Rohdaten anzeigen</summary><pre>{h(c['details'])}</pre></details>
  <div class="actions">{action_html}</div>
</div>
"""
            )
    body = f"""
<div class="card">
<h1>Änderungsprotokoll</h1>
<p class="muted small">DB-Audit-Einträge vom Spielserver haben jetzt direkt hier einen Button <strong>Rückgängig</strong>. Vor jedem Rückgängig wird automatisch ein Backup erstellt.</p>
<form method="get"><label>Optional User-ID filtern</label><input name="user_id" value="{h(user_id)}" placeholder="z. B. 7"><p><button>Filtern</button> <a class="btn secondary" href="{url_for('change_log')}">Alle</a> <a class="btn secondary" href="{url_for('external_audit')}">DB-Audit Ansicht</a></p></form>
</div>
<div class="card audit-card-list"><h2>Audit-Änderungen mit Rückgängig-Button</h2>{''.join(cards) or '<p class="muted">Keine DB-Audit-Einträge gefunden.</p>'}</div>
<div class="card"><h2>Alle Protokolleinträge</h2><table><thead><tr><th>ID</th><th>Zeit</th><th>User</th><th>Aktion</th><th>Tabelle</th><th>Details</th><th>Aktion</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>
"""
    return render_page("Änderungen", body)

@app.get("/external-audit")
def external_audit() -> str:
    status = audit_trigger_status(g.db)
    user_id = request.args.get("user_id", "").strip()
    table_filter = request.args.get("table", "").strip()
    action_filter = request.args.get("action", "").strip()
    params: list[Any] = []
    clauses = ["action IN ('db-insert','db-update','db-delete','audit-rollback')"]
    if user_id:
        clauses.append("user_id = ?")
        params.append(int(user_id))
    if table_filter:
        clauses.append("table_name = ?")
        params.append(table_filter)
    if action_filter:
        clauses.append("action = ?")
        params.append(action_filter)
    where = "WHERE " + " AND ".join(clauses)
    changes = rows(f"SELECT * FROM admin_change_log {where} ORDER BY id DESC LIMIT 300", params)

    table_options = ["<option value=''>alle Tabellen</option>"]
    for table in sorted(WRITE_TABLES):
        selected = " selected" if table == table_filter else ""
        table_options.append(f"<option value='{h(table)}'{selected}>{h(table)}</option>")
    action_options = ["<option value=''>alle Audit-Aktionen</option>"]
    for action in ("db-insert", "db-update", "db-delete", "audit-rollback"):
        selected = " selected" if action == action_filter else ""
        action_options.append(f"<option value='{h(action)}'{selected}>{h(action)}</option>")

    trigger_state = '<span class="good">aktiv</span>' if status["enabled"] else '<span class="bad">aus</span>'
    installed_state = '<span class="good">vollständig</span>' if status["installed"] == status["expected"] and status["expected"] else '<span class="warn">unvollständig/nicht installiert</span>'
    missing_text = ""
    if status["missing"]:
        missing_text = f"<p class='muted small'>Fehlende Trigger: {h(', '.join(status['missing'][:20]))}{' …' if len(status['missing']) > 20 else ''}</p>"

    undone = rolled_back_change_ids(g.db)
    trs = []
    cards = []
    for c in changes:
        details = parse_change_details(c["details"])
        summary = compact_change_summary(c["table_name"] or "", c["action"], details)
        rollback_button = ""
        if c["action"] in {"db-insert", "db-update", "db-delete"}:
            rollback_button = rollback_action_html(c["id"], int(c["id"]) in undone, "Rückgängig")
        elif c["action"] == "audit-rollback":
            rollback_button = "<span class='good small'>Rollback-Protokoll</span>"
        trs.append(
            f"""
<tr>
<td>{h(c['id'])}</td>
<td class="nowrap">{h(c['created_at'])}</td>
<td>{h(c['user_id'])}</td>
<td>{h(c['action'])}</td>
<td>{h(c['table_name'])}</td>
<td>{h(summary)}<details><summary>Rohdaten</summary><pre>{h(c['details'])}</pre></details></td>
<td>{rollback_button}</td>
</tr>
"""
        )
        cards.append(
            f"""
<div class="audit-card">
  <div class="audit-card-head"><strong>#{h(c['id'])} · {h(c['action'])}</strong><span>{h(c['created_at'])}</span></div>
  <div class="muted small">User: {h(c['user_id']) or '-'} · Tabelle: {h(c['table_name']) or '-'}</div>
  <p>{h(summary)}</p>
  <details><summary>Rohdaten anzeigen</summary><pre>{h(c['details'])}</pre></details>
  <div class="actions">{rollback_button}</div>
</div>
"""
        )

    table_rows = "".join(
        f"<tr><td>{h(t['table'])}</td><td>{'<span class=good>ja</span>' if t['exists'] else '<span class=bad>fehlt</span>'}</td><td>{h(t['installed'])}/{h(t['expected'])}</td></tr>"
        for t in status["tables"]
    )

    body = f"""
<div class="card">
<h1>DB-Audit / Game-Änderungen</h1>
<p>SQLite-Audit-Trigger: {installed_state} · Logging: {trigger_state}</p>
<p class="muted small">Wenn aktiv, protokolliert die SQLite-Datenbank selbst Änderungen an Spieltabellen. Dadurch werden auch Änderungen erfasst, die der Original-Gameserver macht. Rollback arbeitet pro Audit-Eintrag und erstellt vorher automatisch ein Backup.</p>
<div class="actions">
<form method="post" action="{url_for('external_audit_install')}"><button>Trigger installieren/aktualisieren & aktivieren</button></form>
<form method="post" action="{url_for('external_audit_set_enabled')}"><input type="hidden" name="enabled" value="{0 if status['enabled'] else 1}"><button class="secondary">Logging {'deaktivieren' if status['enabled'] else 'aktivieren'}</button></form>
<form method="post" action="{url_for('external_audit_drop')}" onsubmit="return confirm('Audit-Trigger wirklich entfernen? Danach werden Game-Änderungen nicht mehr mitgeloggt.');"><button class="danger">Trigger entfernen</button></form>
</div>
{missing_text}
</div>
<div class="card">
<h2>Audit-Einträge</h2>
<form method="get" class="grid">
<div><label>User-ID</label><input name="user_id" value="{h(user_id)}" placeholder="z. B. 7"></div>
<div><label>Tabelle</label><select name="table">{''.join(table_options)}</select></div>
<div><label>Aktion</label><select name="action">{''.join(action_options)}</select></div>
<div><label>&nbsp;</label><button>Filtern</button></div>
</form>
</div>
<div class="card audit-card-list"><h2>Änderungen direkt rückgängig machen</h2>{''.join(cards) or '<p class="muted">Keine Audit-Einträge gefunden.</p>'}</div>
<div class="card"><h2>Tabellenansicht</h2><table><thead><tr><th>ID</th><th>Zeit</th><th>User</th><th>Aktion</th><th>Tabelle</th><th>Zusammenfassung</th><th>Aktion</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>
<div class="card"><h2>Trigger-Status je Tabelle</h2><table><thead><tr><th>Tabelle</th><th>existiert</th><th>Trigger</th></tr></thead><tbody>{table_rows}</tbody></table></div>
"""
    return render_page("DB-Audit", body)


@app.post("/external-audit/install")
def external_audit_install():
    make_backup("install-external-audit")
    count = install_audit_triggers_for_all(g.db, recreate=True)
    set_external_audit_enabled(g.db, True, "enabled from web UI")
    audit("external-audit-install", None, "sqlite_master", {"trigger_count": count, "enabled": True})
    g.db.commit()
    flash(f"DB-Audit installiert/aktualisiert und aktiviert: {count} Trigger.")
    return redirect(url_for("external_audit"))


@app.post("/external-audit/enabled")
def external_audit_set_enabled():
    enabled = request.form.get("enabled") == "1"
    make_backup("toggle-external-audit")
    set_external_audit_enabled(g.db, enabled, "changed from web UI")
    audit("external-audit-enabled" if enabled else "external-audit-disabled", None, "admin_audit_control", {"enabled": enabled})
    g.db.commit()
    flash("DB-Audit Logging aktiviert." if enabled else "DB-Audit Logging deaktiviert.")
    return redirect(url_for("external_audit"))


@app.post("/external-audit/drop")
def external_audit_drop():
    make_backup("drop-external-audit")
    dropped = drop_audit_triggers_for_all(g.db)
    set_external_audit_enabled(g.db, False, "triggers dropped from web UI")
    audit("external-audit-drop", None, "sqlite_master", {"dropped": dropped})
    g.db.commit()
    flash(f"DB-Audit-Trigger entfernt: {dropped}.")
    return redirect(url_for("external_audit"))


@app.post("/external-audit/rollback")
def external_audit_rollback():
    change_id = int(request.form["change_id"])
    make_backup(f"audit-rollback-{change_id}")
    try:
        result = rollback_audit_change(g.db, change_id)
        g.db.commit()
        flash(result)
    except Exception as exc:
        g.db.rollback()
        flash(f"Rollback nicht ausgeführt: {exc}")
    return redirect(request.referrer or url_for("external_audit"))


@app.get("/tools")
def tools() -> str:
    broken = rows(
        """
        SELECT u.id, u.level, u.chapter_progression, u.current_attempt_id,
               a.state, a.challenge_id, a.ended_at
        FROM users u
        LEFT JOIN attempts a ON a.user_id = u.id AND a.attempt_id = u.current_attempt_id
        WHERE u.current_attempt_id IS NOT NULL
          AND (a.id IS NULL OR a.state <> 0 OR a.ended_at IS NOT NULL OR a.challenge_id = '')
        ORDER BY u.id
        """
    )
    dupes = rows(
        """
        SELECT uuid, GROUP_CONCAT(id) AS ids, COUNT(*) AS c
        FROM users
        GROUP BY uuid
        HAVING COUNT(*) > 1
        ORDER BY c DESC
        """
    )
    slot_issues = rows(
        """
        SELECT s.user_id, s.slot_id, s.item_id
        FROM inventory_slots s
        LEFT JOIN items i ON i.id = s.item_id AND i.user_id = s.user_id
        WHERE i.id IS NULL
        ORDER BY s.user_id, s.slot_id
        """
    )
    broken_rows = "".join(f"<tr><td><a href='{url_for('user_detail', user_id=b['id'])}'>{h(b['id'])}</a></td><td>{h(b['current_attempt_id'])}</td><td>{h(b['state'])}</td><td>{h(b['challenge_id'])}</td><td>{h(b['ended_at'])}</td></tr>" for b in broken)
    dupe_rows = "".join(f"<tr><td><code>{h(d['uuid'])}</code></td><td>{h(d['ids'])}</td></tr>" for d in dupes)
    slot_rows = "".join(f"<tr><td><a href='{url_for('user_detail', user_id=s['user_id'])}'>{h(s['user_id'])}</a></td><td>{h(s['slot_id'])}</td><td>{h(s['item_id'])}</td></tr>" for s in slot_issues)
    body = f"""
<div class="card"><h1>Reparatur-Tools</h1><p class="muted">Diagnoseansicht für typische Startfehler. Änderungen bitte in der User-Detailansicht ausführen, damit der Kontext stimmt.</p>
<div class="actions"><a class="btn secondary" href="{url_for('external_audit')}">DB-Audit öffnen</a><form method="post" action="{url_for('tools_install_audit_triggers')}"><button>SQLite-Audit-Trigger installieren & aktivieren</button></form></div><p class="muted small">Optional: protokolliert danach auch DB-Änderungen, die der Gameserver selbst auslöst, z. B. beim Spielen, Zerlegen oder Fusionieren. Komfortabler ist der neue Menüpunkt DB-Audit mit Rollback pro Änderung.</p></div>
<div class="card"><h2>Verdächtige Current Attempts</h2><table><thead><tr><th>User</th><th>Current</th><th>State</th><th>Challenge</th><th>Ended</th></tr></thead><tbody>{broken_rows}</tbody></table></div>
<div class="card"><h2>Doppelte UUIDs</h2><table><thead><tr><th>UUID</th><th>User IDs</th></tr></thead><tbody>{dupe_rows}</tbody></table></div>
<div class="card"><h2>Kaputte Inventory Slots</h2><table><thead><tr><th>User</th><th>Slot</th><th>Item</th></tr></thead><tbody>{slot_rows}</tbody></table></div>
"""
    return render_page("Tools", body)


@app.post("/tools/install-audit-triggers")
def tools_install_audit_triggers():
    make_backup("install-audit-triggers")
    count = install_audit_triggers_for_all(g.db, recreate=True)
    set_external_audit_enabled(g.db, True, "enabled from tools page")
    audit("install-audit-triggers", None, "sqlite_master", {"trigger_count": count, "enabled": True})
    g.db.commit()
    flash(f"Audit-Trigger installiert/geprüft und aktiviert: {count} Trigger.")
    return redirect(url_for("tools"))


@app.post("/repair/empty-challenges")
def repair_empty_challenges():
    user_id = int(request.form["user_id"])
    make_backup("repair-empty-challenges")
    count = g.db.execute("UPDATE attempts SET challenge_id=NULL WHERE user_id=? AND challenge_id=''", [user_id]).rowcount
    audit("repair-empty-challenges", user_id, "attempts", {"rows": count})
    g.db.commit()
    flash(f"{count} leere challenge_id-Werte auf NULL gesetzt.")
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/repair/clear-current-attempt")
def repair_clear_current_attempt():
    user_id = int(request.form["user_id"])
    make_backup("repair-clear-current")
    g.db.execute("UPDATE users SET current_attempt_id=NULL WHERE id=?", [user_id])
    audit("repair-clear-current-attempt", user_id, "users", {"current_attempt_id": None})
    g.db.commit()
    flash("Current Attempt geleert.")
    return redirect(url_for("user_detail", user_id=user_id))


@app.post("/repair/attempt-from-equipped")
def repair_attempt_from_equipped():
    user_id = int(request.form["user_id"])
    chapter_id = int(request.form.get("chapter_id") or 666)
    weapon_ids = [r["item_id"] for r in rows("SELECT item_id FROM inventory_slots WHERE user_id=? AND slot_id IN (1,2) ORDER BY slot_id", [user_id])]
    gear_ids = [r["item_id"] for r in rows("SELECT item_id FROM inventory_slots WHERE user_id=? AND slot_id IN (3,4,5,6,7,8) ORDER BY slot_id", [user_id])]
    max_attempt = row("SELECT COALESCE(MAX(attempt_id),0) AS m FROM attempts WHERE user_id=?", [user_id])["m"]
    next_attempt = int(max_attempt) + 1
    make_backup("repair-attempt-equipped")
    g.db.execute(
        """
        INSERT INTO attempts(
          attempt_id, chapter_id, challenge_id, state, completed_stage_count,
          health_points, armor_points, ability_level, ability_points, kill_count,
          glory_kill_count, seed, damage_dealt, damage_taken, weapon_ids, gear_ids,
          abilities, stats, playtime, user_id, started_at, ended_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [next_attempt, chapter_id, None, 0, 0, 0, 0, 1, 0, 0, 0, random.randint(1, 2_147_483_647), 0, 0, json.dumps(weapon_ids), json.dumps(gear_ids), "[]", "[]", 0, user_id, now_iso(), None],
    )
    g.db.execute("UPDATE users SET current_attempt_id=?, attempt_count=MAX(attempt_count, ?) WHERE id=?", [next_attempt, next_attempt, user_id])
    audit("repair-attempt-from-equipped", user_id, "attempts", {"attempt_id": next_attempt, "chapter_id": chapter_id, "weapon_ids": weapon_ids, "gear_ids": gear_ids})
    g.db.commit()
    flash(f"Offener Attempt {next_attempt} aus equipped Items erstellt.")
    return redirect(url_for("user_detail", user_id=user_id))


@app.get("/tables")
def tables() -> str:
    table_rows = rows(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    cards = []
    for t in table_rows:
        name = t["name"]
        count = row(f"SELECT COUNT(*) AS c FROM {name}")["c"]
        cards.append(f"<tr><td><a href='{url_for('table_view', table=name)}'>{h(name)}</a></td><td>{h(count)}</td></tr>")
    body = f"<div class='card'><h1>Tabellen</h1><table><thead><tr><th>Name</th><th>Rows</th></tr></thead><tbody>{''.join(cards)}</tbody></table></div>"
    return render_page("Tables", body)


@app.get("/table/<table>")
def table_view(table: str) -> str:
    if not table.replace("_", "").isalnum():
        return render_page("Fehler", "<div class='card bad'>Ungültiger Tabellenname.</div>")
    exists = row("SELECT name FROM sqlite_master WHERE type='table' AND name=?", [table])
    if not exists:
        return render_page("Fehler", "<div class='card bad'>Tabelle nicht gefunden.</div>")
    limit = min(int(request.args.get("limit", 100)), 500)
    data = rows(f"SELECT * FROM {table} LIMIT ?", [limit])
    cols = [d["name"] for d in rows(f"PRAGMA table_info({table})")]
    def display_cell(r: sqlite3.Row, c: str) -> str:
        value = r[c]
        extra = ""
        if table in {"items", "currencies", "energies"} and c == "rid" and value is not None:
            extra = f"<br><span class='muted small'>{h(resource_label(value, compact=True))}</span>"
        elif table == "items" and c == "cosmetic" and value is not None:
            extra = f"<br><span class='muted small'>{h(resource_label(value, compact=True))}</span>"
        elif table == "inventory_slots" and c == "slot_id" and value is not None:
            extra = f"<br><span class='muted small'>{h(slot_label(value))}</span>"
        elif table == "talents" and c == "talent_id" and value is not None:
            extra = f"<br><span class='muted small'>{h(simple_key_label(table, c, value))}</span>"
        elif table == "user_stats" and c == "stat_id" and value is not None:
            extra = f"<br><span class='muted small'>{h(simple_key_label(table, c, value))}</span>"
        return f"<td>{h(value)}{extra}</td>"
    trs = []
    for r in data:
        trs.append("<tr>" + "".join(display_cell(r, c) for c in cols) + "</tr>")
    body = f"<div class='card'><h1>Tabelle {h(table)}</h1><p class='muted'>Nur Ansicht, maximal {limit} Zeilen.</p><table><thead><tr>{''.join(f'<th>{h(c)}</th>' for c in cols)}</tr></thead><tbody>{''.join(trs)}</tbody></table></div>"
    return render_page(f"Table {table}", body)



# ---------------------------------------------------------------------------
# Mobile App JSON API
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Mobile API helpers and routes
# ---------------------------------------------------------------------------
def _row_to_dict(value: sqlite3.Row | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {k: value[k] for k in value.keys()}


def _rows_to_dicts(values: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [_row_to_dict(v) or {} for v in values]


def _json_response(payload: Any, status: int = 200) -> Response:
    return Response(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        status=status,
        mimetype="application/json; charset=utf-8",
    )


def _json_error(message: str, status: int = 400, **extra: Any) -> Response:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return _json_response(payload, status)


def _request_json() -> dict[str, Any]:
    if request.is_json:
        data = request.get_json(silent=True)
        if isinstance(data, dict):
            return data
    data: dict[str, Any] = {}
    for key, value in request.form.items():
        data[key] = value
    return data


def _int_value(data: dict[str, Any], key: str, default: int | None = None) -> int:
    value = data.get(key, default)
    if value is None or value == "":
        if default is None:
            raise ValueError(f"{key} fehlt")
        return int(default)
    return int(value)


def _mobile_resource(resource_id: Any) -> dict[str, Any]:
    info = resource_info(resource_id)
    return {
        "id": info.get("id"),
        "name": info.get("name"),
        "tag": info.get("tag"),
        "section": info.get("section"),
        "section_label": info.get("section_label"),
        "category_label": info.get("category_label"),
        "slot": info.get("slot"),
        "compatible_slot_ids": info.get("compatible_slot_ids") or [],
        "compatible_slot_text": info.get("compatible_slot_text"),
        "description": info.get("description"),
        "equippable": bool(info.get("equippable")),
    }


def _mobile_item(row_value: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    if row_value is None:
        return None
    d = _row_to_dict(row_value) if isinstance(row_value, sqlite3.Row) else dict(row_value)
    rid = d.get("rid")
    d["resource"] = _mobile_resource(rid)
    d["label"] = item_instance_label(row_value) if isinstance(row_value, sqlite3.Row) else resource_label(rid)
    if d.get("cosmetic") is not None:
        d["cosmetic_resource"] = _mobile_resource(d.get("cosmetic"))
    return d


def item_id_summary(item_id: int) -> dict[str, Any]:
    item = row("SELECT * FROM items WHERE id=?", [item_id])
    if item is None:
        return {"id": item_id, "missing": True, "label": f"Item #{item_id} fehlt/fremd"}
    d = _mobile_item(item) or {"id": item_id}
    d["missing"] = False
    return d

def _mobile_attempt(row_value: sqlite3.Row) -> dict[str, Any]:
    d = _row_to_dict(row_value) or {}
    for field in ("weapon_ids", "gear_ids"):
        raw = d.get(field)
        try:
            ids = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:
            ids = []
        d[field + "_parsed"] = ids
        d[field + "_items"] = [item_id_summary(int(x)) for x in ids if str(x).strip().isdigit()]
    return d


@app.get("/api/mobile/ping")
def api_mobile_ping() -> Response:
    return _json_response({"ok": True, "app": APP_TITLE, "time": now_iso()})


@app.get("/api/mobile/summary")
def api_mobile_summary() -> Response:
    users_raw = rows(
        """
        SELECT u.id, u.uuid, u.level, u.chapter_progression, u.current_attempt_id, u.attempt_count,
               f.disabled, f.note,
               e.amount AS energy_amount, e.last_regen_at,
               af.enabled AS autofill_enabled, af.target_amount AS autofill_target,
               af.interval_seconds AS autofill_interval, af.last_checked_at AS autofill_last_checked,
               af.last_changed_at AS autofill_last_changed
        FROM users u
        LEFT JOIN admin_user_flags f ON f.user_id = u.id
        LEFT JOIN energies e ON e.user_id = u.id AND e.rid = 28
        LEFT JOIN admin_energy_autofill af ON af.user_id = u.id
        ORDER BY u.id
        LIMIT 500
        """
    )
    user_list = _rows_to_dicts(users_raw)
    for u in user_list:
        u["resource_energy"] = _mobile_resource(28)
    backups_recent = _rows_to_dicts(rows("SELECT * FROM admin_db_backups ORDER BY id DESC LIMIT 10"))
    changes_recent = _rows_to_dicts(rows("SELECT * FROM admin_change_log ORDER BY id DESC LIMIT 20"))
    config_rows = _rows_to_dicts(energy_autofill_rows())
    for cfg in config_rows:
        cfg["resource"] = _mobile_resource(cfg.get("rid"))
    catalog = get_catalog()
    return _json_response({
        "ok": True,
        "server_time": now_iso(),
        "app_title": APP_TITLE,
        "db_path": app.config.get("DB_PATH"),
        "catalog": {
            "loaded": bool(catalog.get("loaded")),
            "path": catalog.get("path"),
            "error": catalog.get("error"),
            "resource_count": len(catalog.get("resources_list", [])),
        },
        "counts": {
            "users": row("SELECT COUNT(*) AS c FROM users")["c"],
            "items": row("SELECT COUNT(*) AS c FROM items")["c"],
            "attempts": row("SELECT COUNT(*) AS c FROM attempts")["c"],
            "energy_autofill": row("SELECT COUNT(*) AS c FROM admin_energy_autofill")["c"],
        },
        "users": user_list,
        "energy_autofill": config_rows,
        "backups_recent": backups_recent,
        "changes_recent": changes_recent,
    })


@app.get("/api/mobile/user/<int:user_id>")
def api_mobile_user_detail(user_id: int) -> Response:
    user = row("SELECT * FROM users WHERE id=?", [user_id])
    if user is None:
        return _json_error("User nicht gefunden", 404)
    flags = row("SELECT disabled, note, updated_at FROM admin_user_flags WHERE user_id=?", [user_id])
    settings_row = row("SELECT * FROM user_settings WHERE id=?", [user_id])
    cfg = row(
        """
        SELECT f.*, e.amount AS current_amount, e.last_regen_at
        FROM admin_energy_autofill f
        LEFT JOIN energies e ON e.user_id=f.user_id AND e.rid=f.rid
        WHERE f.user_id=?
        """,
        [user_id],
    )
    energies_raw = rows("SELECT * FROM energies WHERE user_id=? ORDER BY rid", [user_id])
    currencies_raw = rows("SELECT * FROM currencies WHERE user_id=? ORDER BY rid", [user_id])
    items_raw = rows("SELECT * FROM items WHERE user_id=? ORDER BY id", [user_id])
    slots_raw = rows(
        """
        SELECT s.slot_id, s.item_id, s.user_id, i.rid, i.tier, i.level, i.cosmetic, i.created_at
        FROM inventory_slots s
        LEFT JOIN items i ON i.id=s.item_id AND i.user_id=s.user_id
        WHERE s.user_id=?
        ORDER BY s.slot_id
        """,
        [user_id],
    )
    attempts_raw = rows("SELECT * FROM attempts WHERE user_id=? ORDER BY attempt_id DESC LIMIT 40", [user_id])
    energies = []
    for r in energies_raw:
        d = _row_to_dict(r) or {}
        d["resource"] = _mobile_resource(d.get("rid"))
        energies.append(d)
    currencies = []
    for r in currencies_raw:
        d = _row_to_dict(r) or {}
        d["resource"] = _mobile_resource(d.get("rid"))
        currencies.append(d)
    slots = []
    for s in slots_raw:
        d = _row_to_dict(s) or {}
        d["slot_label"] = slot_label(d.get("slot_id"))
        if d.get("rid") is not None:
            d["item"] = _mobile_item({
                "id": d.get("item_id"), "rid": d.get("rid"), "tier": d.get("tier"),
                "level": d.get("level"), "cosmetic": d.get("cosmetic"), "user_id": user_id,
                "created_at": d.get("created_at"),
            })
        else:
            d["item"] = None
        slots.append(d)
    return _json_response({
        "ok": True,
        "user": _row_to_dict(user),
        "flags": _row_to_dict(flags),
        "settings": _row_to_dict(settings_row),
        "energy_autofill": _row_to_dict(cfg),
        "energies": energies,
        "currencies": currencies,
        "items": [_mobile_item(r) for r in items_raw],
        "inventory_slots": slots,
        "talents": _rows_to_dicts(rows("SELECT * FROM talents WHERE user_id=? ORDER BY talent_id", [user_id])),
        "user_stats": _rows_to_dicts(rows("SELECT * FROM user_stats WHERE user_id=? ORDER BY stat_id", [user_id])),
        "chapter_progress": _rows_to_dicts(rows("SELECT * FROM chapter_progress WHERE user_id=? ORDER BY chapter_id", [user_id])),
        "attempts": [_mobile_attempt(r) for r in attempts_raw],
        "missions": _rows_to_dicts(rows("SELECT * FROM missions WHERE user_id=? ORDER BY id DESC LIMIT 80", [user_id])),
        "battle_passes": _rows_to_dicts(rows("SELECT * FROM battle_passes WHERE user_id=? ORDER BY id DESC LIMIT 80", [user_id])),
        "store_quotas": _rows_to_dicts(rows("SELECT * FROM store_quotas WHERE user_id=? ORDER BY id DESC LIMIT 80", [user_id])),
    })




@app.get("/api/events/catalog")
def api_events_catalog() -> Response:
    q = request.args.get("q", "").strip().lower()
    events = event_catalog()
    if q:
        events = [e for e in events if q in " ".join(str(e.get(k, "")) for k in ("event_definition_id", "tag", "title", "description", "event_type_label")).lower()]
    return _json_response({"ok": True, "loaded": bool(get_catalog().get("loaded")), "events": events[:1000]})


@app.get("/api/events/schedule")
def api_events_schedule_get() -> Response:
    return _json_response({"ok": True, "events": [_rows_to_plain_dict(r) for r in _event_schedule_rows(1000)]})


@app.post("/api/events/schedule")
def api_events_schedule_post() -> Response:
    data = _request_json() or dict(request.form)
    make_backup("api-event-schedule-create")
    try:
        created_id = create_event_schedule_from_payload(g.db, data)
        audit("api-event-schedule-create", parse_nullable_int(str(data.get("user_ids") or "")), "admin_event_schedule", {"created_id": created_id, "catalog_key": data.get("catalog_key")})
        g.db.commit()
        return _json_response({"ok": True, "id": created_id})
    except Exception as exc:
        g.db.rollback()
        return _json_error(str(exc), 400)


@app.post("/api/events/<int:schedule_id>/activate")
def api_event_activate(schedule_id: int) -> Response:
    make_backup(f"api-event-activate-{schedule_id}")
    g.db.execute("UPDATE admin_event_schedule SET is_active=1, updated_at=? WHERE id=?", [now_iso(), schedule_id])
    audit("api-event-activate", None, "admin_event_schedule", {"schedule_id": schedule_id})
    g.db.commit()
    return _json_response({"ok": True})


@app.post("/api/events/<int:schedule_id>/deactivate")
def api_event_deactivate(schedule_id: int) -> Response:
    make_backup(f"api-event-deactivate-{schedule_id}")
    g.db.execute("UPDATE admin_event_schedule SET is_active=0, updated_at=? WHERE id=?", [now_iso(), schedule_id])
    audit("api-event-deactivate", None, "admin_event_schedule", {"schedule_id": schedule_id})
    g.db.commit()
    return _json_response({"ok": True})


@app.post("/api/events/<int:schedule_id>/assign-user")
def api_event_assign_user(schedule_id: int) -> Response:
    data = _request_json() or dict(request.form)
    user_id = _to_int_or_none(data.get("user_id"))
    if user_id is None:
        return _json_error("user_id fehlt", 400)
    item = row("SELECT * FROM admin_event_schedule WHERE id=?", [schedule_id])
    if item is None:
        return _json_error("Event nicht gefunden", 404)
    make_backup(f"api-event-assign-user-{schedule_id}-{user_id}")
    new_scheduled_event_id = valid_or_new_uuid(item["scheduled_event_id"])
    g.db.execute(
        """
        INSERT INTO admin_event_schedule(
          scheduled_event_id, event_definition_id, event_type, tag, title, user_id, start_time, end_time,
          availability, min_api_version, max_api_version, stop_time, args_json, is_active, created_at, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [new_scheduled_event_id, item["event_definition_id"], item["event_type"], item["tag"], item["title"], user_id, item["start_time"], item["end_time"], item["availability"], item["min_api_version"], item["max_api_version"], item["stop_time"], item["args_json"], 1, now_iso(), now_iso()],
    )
    new_id = int(g.db.execute("SELECT last_insert_rowid()").fetchone()[0])
    reset_event_progress_defaults(g.db, new_scheduled_event_id, user_id, reset_all=False)
    audit("api-event-assign-user", user_id, "admin_event_schedule", {"source_schedule_id": schedule_id, "new_schedule_id": new_id})
    g.db.commit()
    return _json_response({"ok": True, "id": new_id})


@app.post("/api/events/<int:schedule_id>/assign-all")
def api_event_assign_all(schedule_id: int) -> Response:
    make_backup(f"api-event-assign-all-{schedule_id}")
    g.db.execute("UPDATE admin_event_schedule SET user_id=NULL, is_active=1, updated_at=? WHERE id=?", [now_iso(), schedule_id])
    audit("api-event-assign-all", None, "admin_event_schedule", {"schedule_id": schedule_id})
    g.db.commit()
    return _json_response({"ok": True})


@app.post("/api/events/<int:schedule_id>/reset-progress")
def api_event_reset_progress(schedule_id: int) -> Response:
    data = _request_json() or dict(request.form)
    item = row("SELECT * FROM admin_event_schedule WHERE id=?", [schedule_id])
    if item is None:
        return _json_error("Event nicht gefunden", 404)
    user_id = _to_int_or_none(data.get("user_id"))
    reset_all = bool(data.get("reset_all")) or str(data.get("scope") or "").lower() == "all"
    if not reset_all and user_id is None and item["user_id"] is not None:
        user_id = int(item["user_id"])
    if not reset_all and user_id is None:
        return _json_error("user_id fehlt oder reset_all=true setzen", 400)
    make_backup(f"api-event-reset-progress-{schedule_id}")
    changed = reset_event_progress_defaults(g.db, item["scheduled_event_id"], user_id=user_id, reset_all=reset_all)
    audit("api-event-reset-progress", user_id, "admin_event_progress", {"schedule_id": schedule_id, "changed": changed, "reset_all": reset_all})
    g.db.commit()
    return _json_response({"ok": True, "changed": changed})


@app.post("/api/events/fix-uuid-ids")
def api_events_fix_uuid_ids() -> Response:
    make_backup("api-event-fix-uuid-ids")
    try:
        result = migrate_event_schedule_uuid_ids(g.db)
        audit("api-event-fix-uuid-ids", None, "admin_event_schedule", result)
        g.db.commit()
        return _json_response({"ok": True, **result})
    except Exception as exc:
        g.db.rollback()
        return _json_error(str(exc), 400)


@app.post("/api/events/export")
def api_events_export() -> Response:
    make_backup("api-event-export")
    path = export_admin_events_json(g.db)
    audit("api-event-export", None, "admin_event_schedule", {"path": str(path)})
    g.db.commit()
    return _json_response({"ok": True, "path": str(path)})



@app.get("/api/inbox/messages")
def api_inbox_messages() -> Response:
    return _json_response({"ok": True, "messages": [_rows_to_plain_dict(r) for r in _inbox_message_rows()]})


@app.post("/api/inbox/messages")
def api_inbox_create() -> Response:
    data = _request_json() or dict(request.form)
    make_backup("api-inbox-message-create")
    try:
        payload = _inbox_payload_from_request(data)
        now_value = _now_epoch()
        g.db.execute(
            """
            INSERT INTO admin_inbox_messages(
              user_id, display_type, title, body, published, expires, resources_json, image_id,
              conditions_json, is_active, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [payload["user_id"], payload["display_type"], payload["title"], payload["body"], payload["published"], payload["expires"], payload["resources_json"], payload["image_id"], payload["conditions_json"], payload["is_active"], now_value, now_value],
        )
        message_id = int(g.db.execute("SELECT last_insert_rowid()").fetchone()[0])
        audit("api-inbox-message-create", payload["user_id"], "admin_inbox_messages", {"message_id": message_id})
        g.db.commit()
        return _json_response({"ok": True, "id": message_id})
    except Exception as exc:
        g.db.rollback()
        return _json_error(str(exc), 400)


@app.get("/api/inbox/messages/<int:message_id>")
def api_inbox_message_detail(message_id: int) -> Response:
    msg = row("SELECT * FROM admin_inbox_messages WHERE id=?", [message_id])
    if msg is None:
        return _json_error("Nachricht nicht gefunden", 404)
    states = rows("SELECT * FROM admin_inbox_message_state WHERE message_id=? ORDER BY updated_at DESC", [message_id])
    return _json_response({"ok": True, "message": _rows_to_plain_dict(msg), "states": [_rows_to_plain_dict(s) for s in states]})


@app.post("/api/inbox/messages/<int:message_id>/activate")
def api_inbox_activate(message_id: int) -> Response:
    make_backup(f"api-inbox-message-activate-{message_id}")
    g.db.execute("UPDATE admin_inbox_messages SET is_active=1, updated_at=? WHERE id=?", [_now_epoch(), message_id])
    audit("api-inbox-message-activate", None, "admin_inbox_messages", {"message_id": message_id})
    g.db.commit()
    return _json_response({"ok": True})


@app.post("/api/inbox/messages/<int:message_id>/deactivate")
def api_inbox_deactivate(message_id: int) -> Response:
    make_backup(f"api-inbox-message-deactivate-{message_id}")
    g.db.execute("UPDATE admin_inbox_messages SET is_active=0, updated_at=? WHERE id=?", [_now_epoch(), message_id])
    audit("api-inbox-message-deactivate", None, "admin_inbox_messages", {"message_id": message_id})
    g.db.commit()
    return _json_response({"ok": True})


@app.post("/api/inbox/messages/<int:message_id>/delete")
def api_inbox_delete(message_id: int) -> Response:
    msg = row("SELECT * FROM admin_inbox_messages WHERE id=?", [message_id])
    if msg is None:
        return _json_error("Nachricht nicht gefunden", 404)
    make_backup(f"api-inbox-message-delete-{message_id}")
    state_deleted = g.db.execute("DELETE FROM admin_inbox_message_state WHERE message_id=?", [message_id]).rowcount
    message_deleted = g.db.execute("DELETE FROM admin_inbox_messages WHERE id=?", [message_id]).rowcount
    audit("api-inbox-message-delete", msg["user_id"], "admin_inbox_messages", {"message_id": message_id, "state_deleted": state_deleted, "message_deleted": message_deleted})
    g.db.commit()
    return _json_response({"ok": True, "message_deleted": message_deleted, "state_deleted": state_deleted})


@app.post("/api/inbox/messages/<int:message_id>/reset-state")
def api_inbox_reset_state(message_id: int) -> Response:
    data = _request_json() or dict(request.form)
    reset_all = bool(data.get("reset_all")) or str(data.get("scope") or "").lower() == "all"
    user_id = _to_int_or_none(data.get("user_id"))
    if not reset_all and user_id is None:
        return _json_error("user_id fehlt oder reset_all=true setzen", 400)
    make_backup(f"api-inbox-state-reset-{message_id}")
    if reset_all:
        changed = g.db.execute("DELETE FROM admin_inbox_message_state WHERE message_id=?", [message_id]).rowcount
    else:
        changed = g.db.execute("DELETE FROM admin_inbox_message_state WHERE message_id=? AND user_id=?", [message_id, user_id]).rowcount
    audit("api-inbox-state-reset", user_id, "admin_inbox_message_state", {"message_id": message_id, "reset_all": reset_all, "changed": changed})
    g.db.commit()
    return _json_response({"ok": True, "changed": changed})


@app.get("/api/mobile/catalog")
def api_mobile_catalog() -> Response:
    catalog = get_catalog()
    q = request.args.get("q", "").strip().lower()
    resources = list(catalog.get("resources_list", []))
    if q:
        resources = [r for r in resources if q in " ".join(str(r.get(k, "")) for k in ("id", "name", "tag", "category_label", "section_label", "description")).lower()]
    return _json_response({
        "ok": True,
        "loaded": bool(catalog.get("loaded")),
        "error": catalog.get("error"),
        "resources": resources[:1000],
        "slots": sorted(catalog.get("slots_by_id", {}).values(), key=lambda x: x["id"]),
    })


@app.get("/api/mobile/changes")
def api_mobile_changes() -> Response:
    params: list[Any] = []
    where = ""
    user_id = request.args.get("user_id", "").strip()
    if user_id:
        where = "WHERE user_id=?"
        params.append(int(user_id))
    changes = _rows_to_dicts(rows(f"SELECT * FROM admin_change_log {where} ORDER BY id DESC LIMIT 300", params))
    return _json_response({"ok": True, "changes": changes})



@app.post("/api/mobile/audit/rollback")
def api_mobile_audit_rollback() -> Response:
    data = _request_json()
    try:
        change_id = _int_value(data, "change_id")
    except Exception as exc:
        return _json_error(str(exc), 400)

    change = row("SELECT * FROM admin_change_log WHERE id=?", [change_id])
    if change is None:
        return _json_error("Änderung nicht gefunden", 404)
    if change["action"] not in {"db-insert", "db-update", "db-delete"}:
        return _json_error("Diese Änderung kann nicht automatisch zurückgerollt werden.", 400)
    if change_id in rolled_back_change_ids(g.db):
        return _json_error("Diese Änderung wurde bereits rückgängig gemacht.", 400)

    make_backup(f"mobile-audit-rollback-{change_id}")
    try:
        result = rollback_audit_change(g.db, change_id)
        g.db.commit()
        return _json_response({"ok": True, "change_id": change_id, "result": result})
    except Exception as exc:
        g.db.rollback()
        return _json_error(str(exc), 400)


@app.get("/api/mobile/backups")
def api_mobile_backups() -> Response:
    out_dir = backup_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    db_records = _rows_to_dicts(rows("SELECT * FROM admin_db_backups ORDER BY id DESC LIMIT 100"))
    files = []
    for f in sorted(out_dir.glob("*.sqlite3"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[:100]:
        files.append({"name": f.name, "path": str(f), "size_bytes": f.stat().st_size, "modified_at": dt.datetime.fromtimestamp(f.stat().st_mtime, dt.timezone.utc).replace(microsecond=0).isoformat()})
    return _json_response({"ok": True, "backup_dir": str(out_dir), "records": db_records, "files": files})


@app.post("/api/mobile/backups/create")
def api_mobile_backup_create() -> Response:
    data = _request_json()
    reason = str(data.get("reason") or "mobile-manual")
    target = make_backup(reason)
    audit("backup-create-mobile", None, "admin_db_backups", {"reason": reason, "path": str(target) if target else None})
    g.db.commit()
    return _json_response({"ok": True, "backup_created": bool(target), "path": str(target) if target else None, "name": target.name if target else None})




def _mobile_backup_path_from_name(name: str) -> Path:
    safe_name = str(name or "").strip()
    if not safe_name or "/" in safe_name or "\\" in safe_name or not safe_name.endswith(".sqlite3"):
        raise ValueError("Ungültiger Backup-Dateiname")
    base_dir = backup_dir().resolve()
    path = (base_dir / safe_name).resolve()
    if base_dir not in path.parents and path != base_dir:
        raise ValueError("Backup liegt nicht im Backup-Ordner")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("Backup-Datei nicht gefunden")
    return path


@app.post("/api/mobile/backups/restore")
def api_mobile_backup_restore() -> Response:
    data = _request_json()
    try:
        backup_path = _mobile_backup_path_from_name(str(data.get("name") or ""))
    except FileNotFoundError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        return _json_error(str(exc), 400)

    source_db = db_path()
    if not source_db.exists():
        return _json_error(f"Aktuelle Datenbank nicht gefunden: {source_db}", 500)

    with _ENERGY_AUTOFILL_LOCK:
        # Sicherheitsbackup des aktuellen Stands anlegen, bevor überschrieben wird.
        pre_restore_backup = make_backup("pre-restore-mobile")
        try:
            audit(
                "backup-restore-mobile-start",
                None,
                "admin_db_backups",
                {
                    "restore_from": str(backup_path),
                    "pre_restore_backup": str(pre_restore_backup) if pre_restore_backup else None,
                },
            )
            g.db.commit()
        except Exception:
            pass

        # Die offene Request-Verbindung schließen, damit die SQLite-Datei sauber ersetzt werden kann.
        con = getattr(g, "db", None)
        if con is not None:
            try:
                con.close()
            except Exception:
                pass
            g.db = None

        shutil.copy2(backup_path, source_db)

        # Admin-Tabellen im wiederhergestellten Stand sicherstellen und den Restore dort protokollieren.
        restored_con = sqlite3.connect(source_db)
        restored_con.row_factory = sqlite3.Row
        restored_con.execute("PRAGMA foreign_keys = ON")
        restored_con.execute("PRAGMA busy_timeout = 5000")
        ensure_admin_tables(restored_con)
        restored_con.execute(
            """
            INSERT INTO admin_change_log(created_at, action, table_name, user_id, details)
            VALUES(?,?,?,?,?)
            """,
            [
                now_iso(),
                "backup-restore-mobile",
                "admin_db_backups",
                None,
                json.dumps(
                    {
                        "restored_from": str(backup_path),
                        "pre_restore_backup": str(pre_restore_backup) if pre_restore_backup else None,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ],
        )
        restored_con.commit()
        restored_con.close()

    return _json_response(
        {
            "ok": True,
            "restored": backup_path.name,
            "path": str(backup_path),
            "pre_restore_backup": str(pre_restore_backup) if pre_restore_backup else None,
        }
    )


@app.post("/api/mobile/energy-autofill/save")
def api_mobile_energy_autofill_save() -> Response:
    data = _request_json()
    try:
        user_id = _int_value(data, "user_id")
        rid = _int_value(data, "rid", 28)
        target_amount = max(0, _int_value(data, "target_amount", 20))
        interval_seconds = max(60, _int_value(data, "interval_seconds", 120))
        enabled = 1 if _int_value(data, "enabled", 1) else 0
        run_now = bool(data.get("run_now"))
    except Exception as exc:
        return _json_error(str(exc), 400)
    if row("SELECT id FROM users WHERE id=?", [user_id]) is None:
        return _json_error("User nicht gefunden", 404)
    make_backup("mobile-energy-autofill-config")
    g.db.execute(
        """
        INSERT INTO admin_energy_autofill(user_id, rid, target_amount, interval_seconds, enabled, updated_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
          rid=excluded.rid,
          target_amount=excluded.target_amount,
          interval_seconds=excluded.interval_seconds,
          enabled=excluded.enabled,
          updated_at=excluded.updated_at
        """,
        [user_id, rid, target_amount, interval_seconds, enabled, now_iso()],
    )
    audit("mobile-energy-autofill-config", user_id, "admin_energy_autofill", {"rid": rid, "target_amount": target_amount, "interval_seconds": interval_seconds, "enabled": enabled})
    changed = False
    if run_now:
        cfg = row("SELECT * FROM admin_energy_autofill WHERE user_id=?", [user_id])
        if cfg is not None:
            changed = apply_energy_autofill_once(g.db, cfg, source="mobile")
    g.db.commit()
    cfg_after = row("SELECT * FROM admin_energy_autofill WHERE user_id=?", [user_id])
    return _json_response({"ok": True, "changed_now": changed, "energy_autofill": _row_to_dict(cfg_after)})


@app.post("/api/mobile/energy-autofill/run-now")
def api_mobile_energy_autofill_run_now() -> Response:
    data = _request_json()
    try:
        user_id = _int_value(data, "user_id")
    except Exception as exc:
        return _json_error(str(exc), 400)
    cfg = row("SELECT * FROM admin_energy_autofill WHERE user_id=?", [user_id])
    if cfg is None:
        return _json_error("Für diesen User gibt es noch keine Energy-Auto-Fill-Konfiguration.", 404)
    changed = apply_energy_autofill_once(g.db, cfg, source="mobile")
    return _json_response({"ok": True, "changed": changed})




@app.post("/api/mobile/user/toggle-disabled")
def api_mobile_user_toggle_disabled() -> Response:
    data = _request_json()
    try:
        user_id = _int_value(data, "user_id")
        disabled = 1 if _int_value(data, "disabled", 1) else 0
    except Exception as exc:
        return _json_error(str(exc), 400)

    u = row("SELECT password_hash FROM users WHERE id=?", [user_id])
    if u is None:
        return _json_error("User nicht gefunden", 404)

    make_backup("mobile-toggle-user-disabled")
    if disabled:
        existing = row("SELECT * FROM admin_user_flags WHERE user_id=?", [user_id])
        backup_hash = existing["password_hash_backup"] if existing and existing["password_hash_backup"] else u["password_hash"]
        random_disabled_password = secrets.token_urlsafe(48).encode("utf-8")
        disabled_hash = bcrypt.hashpw(random_disabled_password, bcrypt.gensalt(rounds=12)).decode("utf-8")
        g.db.execute("UPDATE users SET password_hash=? WHERE id=?", [disabled_hash, user_id])
        g.db.execute(
            """
            INSERT INTO admin_user_flags(user_id, disabled, password_hash_backup, updated_at)
            VALUES(?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              disabled=1,
              password_hash_backup=excluded.password_hash_backup,
              updated_at=excluded.updated_at
            """,
            [user_id, backup_hash, now_iso()],
        )
        audit("mobile-disable-user", user_id, "users", {"disabled": 1})
        message = "User deaktiviert"
    else:
        existing = row("SELECT password_hash_backup FROM admin_user_flags WHERE user_id=?", [user_id])
        if existing is None or not existing["password_hash_backup"]:
            return _json_error("Kann nicht aktivieren: kein gesicherter password_hash vorhanden.", 400)
        g.db.execute("UPDATE users SET password_hash=? WHERE id=?", [existing["password_hash_backup"], user_id])
        g.db.execute("UPDATE admin_user_flags SET disabled=0, updated_at=? WHERE user_id=?", [now_iso(), user_id])
        audit("mobile-enable-user", user_id, "users", {"disabled": 0})
        message = "User wieder aktiviert"

    g.db.commit()
    flags = row("SELECT disabled, note, updated_at FROM admin_user_flags WHERE user_id=?", [user_id])
    return _json_response({"ok": True, "message": message, "flags": _row_to_dict(flags)})


@app.post("/api/mobile/simple/upsert")
def api_mobile_simple_upsert() -> Response:
    data = _request_json()
    try:
        user_id = _int_value(data, "user_id")
        table = str(data.get("table") or "")
        key_field = str(data.get("key_field") or "")
        values = data.get("values")
        if not isinstance(values, dict):
            return _json_error("values muss ein Objekt sein", 400)
    except Exception as exc:
        return _json_error(str(exc), 400)
    allowed = {
        "currencies": {"key": "rid", "fields": {"rid", "amount"}},
        "energies": {"key": "rid", "fields": {"rid", "amount", "last_regen_at"}},
        "talents": {"key": "talent_id", "fields": {"talent_id", "level"}},
        "user_stats": {"key": "stat_id", "fields": {"stat_id", "amount"}},
    }
    if table not in allowed or key_field != allowed[table]["key"]:
        return _json_error("Tabelle oder key_field nicht erlaubt", 400)
    fields = [f for f in values.keys() if f in allowed[table]["fields"]]
    if key_field not in fields:
        return _json_error(f"{key_field} fehlt", 400)
    converted: dict[str, Any] = {}
    for f in fields:
        raw = values.get(f)
        if f.endswith("_at"):
            converted[f] = raw or now_iso()
        else:
            converted[f] = int(raw)
    make_backup(f"mobile-upsert-{table}")
    cols = fields + ["user_id"]
    placeholders = ",".join("?" for _ in cols)
    update_fields = ",".join(f"{f}=excluded.{f}" for f in fields if f != key_field)
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT(user_id,{key_field}) DO UPDATE SET {update_fields}"
    g.db.execute(sql, [converted[f] for f in fields] + [user_id])
    audit("mobile-upsert-simple", user_id, table, {"key_field": key_field, "values": converted})
    g.db.commit()
    return _json_response({"ok": True, "table": table, "user_id": user_id, "values": converted})


@app.get("/api/mobile/table/<table>")
def api_mobile_table(table: str) -> Response:
    if not table.replace("_", "").isalnum():
        return _json_error("Ungültiger Tabellenname", 400)
    exists = row("SELECT name FROM sqlite_master WHERE type='table' AND name=?", [table])
    if not exists:
        return _json_error("Tabelle nicht gefunden", 404)
    limit = min(int(request.args.get("limit", 100)), 500)
    data = _rows_to_dicts(rows(f"SELECT * FROM {table} LIMIT ?", [limit]))
    cols = [d["name"] for d in rows(f"PRAGMA table_info({table})")]
    return _json_response({"ok": True, "table": table, "columns": cols, "rows": data, "limit": limit})




# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mighty DOOM SQLite admin interface")
    parser.add_argument("--db", default=os.environ.get("MIGHTYDOOM_DB", "db/local.sqlite3"), help="Path to local.sqlite3")
    parser.add_argument("--host", default=os.environ.get("ADMIN_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ADMIN_PORT", "8090")))
    parser.add_argument("--user", default=os.environ.get("ADMIN_USER", "admin"))
    parser.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD"))
    parser.add_argument("--no-backup", action="store_true", help="Do not create automatic backups before writes")
    parser.add_argument("--backup-dir", default=os.environ.get("ADMIN_BACKUP_DIR"))
    parser.add_argument("--game-data", default=os.environ.get("MIGHTYDOOM_GAME_DATA"), help="Path to game-data.json for resource names and slots")
    return parser.parse_args()


def main() -> None:
    """Start the private admin server from the command line."""
    args = parse_args()
    if not args.password:
        args.password = secrets.token_urlsafe(18)
        print("No --password/ADMIN_PASSWORD provided. Temporary admin password:", args.password)
    db = Path(args.db).resolve()
    if not db.exists():
        raise SystemExit(f"Database not found: {db}")
    app.config.update(
        DB_PATH=str(db),
        ADMIN_USER=args.user,
        ADMIN_PASSWORD=args.password,
        AUTO_BACKUP=not args.no_backup,
        BACKUP_DIR=args.backup_dir,
        GAME_DATA_PATH=args.game_data,
    )
    start_energy_autofill_worker()
    print(f"{APP_TITLE} running on http://{args.host}:{args.port}")
    print(f"DB: {db}")
    print(f"Login: {args.user} / {args.password}")
    print("Energy Auto-Fill worker: active")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()


@app.get("/admin-version")
def admin_version() -> str:
    """Return a tiny version marker to verify that the expected server code is running."""
    return f"{APP_TITLE} {APP_VERSION}\n"
