import os
import json
from constants import THEMES

SAVES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saves.json")
SETTINGS_KEY = "__retroread_settings__"

def load_settings():
    try:
        if os.path.exists(SAVES_FILE):
            with open(SAVES_FILE, 'r', encoding='utf-8') as f:
                saves = json.load(f)
            return saves.get(SETTINGS_KEY, {})
    except Exception:
        pass
    return {}

def write_settings(new_settings):
    try:
        saves = {}
        if os.path.exists(SAVES_FILE):
            with open(SAVES_FILE, 'r', encoding='utf-8') as f:
                saves = json.load(f)
        current = saves.get(SETTINGS_KEY, {})
        current.update(new_settings)
        saves[SETTINGS_KEY] = current
        with open(SAVES_FILE, 'w', encoding='utf-8') as f:
            json.dump(saves, f)
    except Exception:
        pass

def load_typography_settings():
    settings = load_settings()
    try:
        font_size = int(settings.get("font_size", 34))
        line_spacing = float(settings.get("line_spacing", 1.32))
        word_spacing = float(settings.get("word_spacing", 1.0))
        margin_side = int(settings.get("margin_side", 20))
        return {
            "font_size": font_size,
            "line_spacing": line_spacing,
            "word_spacing": word_spacing,
            "margin_side": margin_side
        }
    except Exception:
        return {
            "font_size": 34,
            "line_spacing": 1.32,
            "word_spacing": 1.0,
            "margin_side": 20
        }

def write_typography_settings(font_size, line_spacing=None, word_spacing=None, margin_side=None):
    if isinstance(font_size, dict):
        d = font_size
        font_size = d.get("font_size", 34)
        line_spacing = d.get("line_spacing", 1.32)
        word_spacing = d.get("word_spacing", 1.0)
        margin_side = d.get("margin_side", 20)
    write_settings({
        "font_size": int(font_size) if font_size is not None else 34,
        "line_spacing": float(line_spacing) if line_spacing is not None else 1.32,
        "word_spacing": float(word_spacing) if word_spacing is not None else 1.0,
        "margin_side": int(margin_side) if margin_side is not None else 20
    })

def load_save(filepath):
    typo = load_typography_settings()
    try:
        with open(SAVES_FILE, 'r', encoding='utf-8') as f:
            saves = json.load(f)
        book_save = saves.get(filepath, {})
        return {
            "scroll_y": book_save.get("scroll_y", 0),
            "font_size": typo["font_size"],
            "line_spacing": typo["line_spacing"],
            "word_spacing": typo["word_spacing"],
            "margin_side": typo["margin_side"]
        }
    except Exception:
        return {
            "scroll_y": 0,
            "font_size": typo["font_size"],
            "line_spacing": typo["line_spacing"],
            "word_spacing": typo["word_spacing"],
            "margin_side": typo["margin_side"]
        }

def write_save(filepath, scroll_y, font_size=None, line_spacing=None, word_spacing=None, margin_side=None):
    try:
        saves = {}
        if os.path.exists(SAVES_FILE):
            with open(SAVES_FILE, 'r', encoding='utf-8') as f:
                saves = json.load(f)
        saves[filepath] = {
            "scroll_y": scroll_y
        }
        if font_size is not None:
            settings = saves.get(SETTINGS_KEY, {})
            settings["font_size"] = font_size
            if line_spacing is not None: settings["line_spacing"] = line_spacing
            if word_spacing is not None: settings["word_spacing"] = word_spacing
            if margin_side is not None: settings["margin_side"] = margin_side
            saves[SETTINGS_KEY] = settings
            
        with open(SAVES_FILE, 'w', encoding='utf-8') as f:
            json.dump(saves, f)
    except Exception:
        pass

def load_theme_idx():
    settings = load_settings()
    try:
        return int(settings.get("theme_idx", 0)) % len(THEMES)
    except Exception:
        return 0

def write_theme_idx(theme_idx):
    write_settings({"theme_idx": theme_idx % len(THEMES)})

def load_library_view():
    settings = load_settings()
    return settings.get("library_view", "list")

def write_library_view(view_mode):
    write_settings({"library_view": view_mode})

def load_reader_rotation_idx():
    settings = load_settings()
    try:
        return int(settings.get("reader_rotation_idx", 0)) % 4
    except Exception:
        return 0

def write_reader_rotation_idx(rotation_idx):
    write_settings({"reader_rotation_idx": rotation_idx % 4})
