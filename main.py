import sys
import os
import textwrap
import traceback
import json
import re

SAVES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saves.json")
SETTINGS_KEY = "__retroread_settings__"

def load_save(filepath):
    try:
        with open(SAVES_FILE, 'r') as f:
            saves = json.load(f)
        return saves.get(filepath, {"scroll_y": 0, "font_size": 34})
    except:
        return {"scroll_y": 0, "font_size": 34}

def write_save(filepath, scroll_y, font_size):
    try:
        saves = {}
        if os.path.exists(SAVES_FILE):
            with open(SAVES_FILE, 'r') as f:
                saves = json.load(f)
        saves[filepath] = {"scroll_y": scroll_y, "font_size": font_size}
        with open(SAVES_FILE, 'w') as f:
            json.dump(saves, f)
    except:
        pass

# Add local bundled vendor
VENDOR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
if os.path.exists(VENDOR_PATH):
    sys.path.insert(0, VENDOR_PATH)

os.environ["PYSDL2_DLL_PATH"] = "/usr/trimui/lib"

try:
    import sdl2
    import sdl2.ext
    import sdl2.sdlttf as sdlttf
except ImportError as e:
    sys.stderr.write("Cannot load SDL2. Error: " + str(e))
    sys.exit(1)

FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "font.ttf")

SCREEN_W = 1024
SCREEN_H = 768

# Themes
THEMES = [
    {
        "name": "Paper (Vintage)",
        "bg": sdl2.ext.Color(40, 30, 20),         # Dark brown background
        "text": sdl2.SDL_Color(235, 213, 171, 255), # EBD5AB text
        "header": sdl2.ext.Color(30, 20, 15),
        "sel": sdl2.ext.Color(139, 69, 19)
    },
    {
        "name": "Night Mode",
        "bg": sdl2.ext.Color(23, 25, 28),         # 17191C
        "text": sdl2.SDL_Color(232, 229, 221, 255), # E8E5DD
        "header": sdl2.ext.Color(15, 17, 19),
        "sel": sdl2.ext.Color(60, 60, 60)
    },
    {
        "name": "Light Mode",
        "bg": sdl2.ext.Color(245, 241, 230),      # F5F1E6
        "text": sdl2.SDL_Color(51, 48, 43, 255),  # 33302B
        "header": sdl2.ext.Color(230, 225, 210),
        "sel": sdl2.ext.Color(118, 107, 90)
    },
    {
        "name": "Warm Night Light",
        "bg": sdl2.ext.Color(243, 231, 199),
        "text": sdl2.SDL_Color(61, 52, 40, 255),
        "header": sdl2.ext.Color(230, 213, 173),
        "sel": sdl2.ext.Color(216, 185, 110)
    }
]

# Library-only palette.  The reader keeps its existing themes and rendering.
LIBRARY_THEMES = [
    {
        "bg": sdl2.ext.Color(40, 30, 20), "header": sdl2.ext.Color(30, 20, 15),
        "text": sdl2.SDL_Color(235, 213, 171, 255), "secondary": sdl2.SDL_Color(184, 159, 118, 255),
        "accent": sdl2.ext.Color(210, 149, 93), "selected": sdl2.ext.Color(63, 46, 32),
        "border": sdl2.ext.Color(139, 69, 19), "divider": sdl2.ext.Color(76, 56, 39),
        "sel_border": sdl2.ext.Color(168, 120, 40), "sel_bg": sdl2.ext.Color(238, 224, 185),
        "sel_text": sdl2.SDL_Color(55, 42, 25, 255), "sel_sec": sdl2.SDL_Color(110, 85, 55, 255)
    },
    {
        "bg": sdl2.ext.Color(20, 20, 20), "header": sdl2.ext.Color(10, 10, 10),
        "text": sdl2.SDL_Color(212, 212, 212, 255), "secondary": sdl2.SDL_Color(154, 154, 154, 255),
        "accent": sdl2.ext.Color(184, 168, 216), "selected": sdl2.ext.Color(60, 60, 60),
        "border": sdl2.ext.Color(136, 156, 192), "divider": sdl2.ext.Color(52, 52, 52),
        "sel_border": sdl2.ext.Color(102, 137, 181), "sel_bg": sdl2.ext.Color(229, 235, 241),
        "sel_text": sdl2.SDL_Color(30, 30, 30, 255), "sel_sec": sdl2.SDL_Color(80, 80, 80, 255)
    },
    {
        "bg": sdl2.ext.Color(244, 236, 216), "header": sdl2.ext.Color(220, 210, 190),
        "text": sdl2.SDL_Color(59, 52, 40, 255), "secondary": sdl2.SDL_Color(118, 107, 90, 255),
        "accent": sdl2.ext.Color(107, 91, 149), "selected": sdl2.ext.Color(229, 235, 241),
        "border": sdl2.ext.Color(102, 137, 181), "divider": sdl2.ext.Color(204, 193, 171),
        "sel_border": sdl2.ext.Color(102, 137, 181), "sel_bg": sdl2.ext.Color(229, 235, 241),
        "sel_text": sdl2.SDL_Color(30, 30, 30, 255), "sel_sec": sdl2.SDL_Color(80, 80, 80, 255)
    },
    {
        "bg": sdl2.ext.Color(243, 231, 199), "header": sdl2.ext.Color(230, 213, 173),
        "text": sdl2.SDL_Color(61, 52, 40, 255), "secondary": sdl2.SDL_Color(117, 104, 84, 255),
        "accent": sdl2.ext.Color(168, 120, 40), "selected": sdl2.ext.Color(216, 185, 110),
        "border": sdl2.ext.Color(216, 197, 157), "divider": sdl2.ext.Color(216, 197, 157),
        "sel_border": sdl2.ext.Color(168, 120, 40), "sel_bg": sdl2.ext.Color(238, 224, 185),
        "sel_text": sdl2.SDL_Color(55, 42, 25, 255), "sel_sec": sdl2.SDL_Color(110, 85, 55, 255)
    },
]

def load_theme_idx():
    settings = load_settings()
    try:
        return int(settings.get("theme_idx", 0)) % len(THEMES)
    except:
        return 0

def write_theme_idx(theme_idx):
    write_settings({"theme_idx": theme_idx % len(THEMES)})

def load_reader_rotation_idx():
    settings = load_settings()
    try:
        return int(settings.get("reader_rotation_idx", 0)) % 4
    except:
        return 0

def write_reader_rotation_idx(rotation_idx):
    write_settings({"reader_rotation_idx": rotation_idx % 4})

def load_settings():
    try:
        with open(SAVES_FILE, 'r') as f:
            saves = json.load(f)
        return saves.get(SETTINGS_KEY, {})
    except:
        return {}

def write_settings(settings_update):
    try:
        saves = {}
        if os.path.exists(SAVES_FILE):
            with open(SAVES_FILE, 'r') as f:
                saves = json.load(f)
        settings = saves.get(SETTINGS_KEY, {})
        settings.update(settings_update)
        saves[SETTINGS_KEY] = settings
        with open(SAVES_FILE, 'w') as f:
            json.dump(saves, f)
    except:
        pass

STATE_BROWSE = 0
STATE_READER = 1
STATE_TOC = 2
STATE_QUIT_CONFIRM = 3

def get_directory_contents(path):
    try:
        items = os.listdir(path)
        folders = []
        files = []
        valid_exts = ['.txt', '.md', '.log', '.csv', '.json', '.epub', '.fb2', '.mobi', '.azw', '.azw3']
        for item in items:
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                folders.append(item)
            else:
                ext = os.path.splitext(item)[1].lower()
                if ext in valid_exts:
                    files.append(item)
        folders.sort(key=str.lower)
        files.sort(key=str.lower)
        return folders, files
    except Exception as e:
        return [], []

def get_book_display_metadata(filename):
    """Derive library labels from a filename without changing the real path."""
    stem = os.path.splitext(filename)[0]
    title, separator, author = stem.rpartition(" - ")
    if not separator:
        return stem, ""
    # Keep common initials readable in the small secondary line; discard only
    # the existing display suffix used by the bundled naming convention.
    author = re.sub(r"\b([A-Z])\.([A-Z])\.", r"\1. \2.", author.strip())
    author = re.sub(r"\s+AU$", "", author)
    return title.strip(), author

def draw_book_icon(renderer, x, y, color, background):
    """Small pixel-friendly book glyph, deliberately free of emoji assets."""
    renderer.fill((x, y, 15, 20), color)
    renderer.fill((x + 3, y + 3, 2, 14), background)

class Chapter:
    def __init__(self, title, content):
        self.title = title
        self.content = content

class Book:
    def __init__(self, title="", author="", filepath=""):
        self.title = title
        self.author = author
        self.filepath = filepath
        self.chapters = []
        self.metadata = {}

class EPUBParser:
    @staticmethod
    def parse(filepath) -> Book:
        import zipfile
        import xml.etree.ElementTree as ET
        import html
        import re
        
        book = Book(filepath=filepath)
        with zipfile.ZipFile(filepath, 'r') as zf:
            container_xml = zf.read('META-INF/container.xml')
            root = ET.fromstring(container_xml)
            opf_path = ""
            for child in root.iter():
                if child.tag.endswith('rootfile'):
                    opf_path = child.attrib.get('full-path')
                    break
            if opf_path:
                opf_dir = os.path.dirname(opf_path)
                opf_content = zf.read(opf_path)
                opf_root = ET.fromstring(opf_content)
                
                manifest = {}
                spine = []
                for child in opf_root.iter():
                    if child.tag.endswith('item'):
                        manifest[child.attrib.get('id')] = child.attrib.get('href')
                    elif child.tag.endswith('itemref'):
                        spine.append(child.attrib.get('idref'))
                
                toc_map = {}
                for item_id, href in manifest.items():
                    if href.endswith('.ncx'):
                        try:
                            ncx_content = zf.read(href if not opf_dir else f"{opf_dir}/{href}")
                            ncx_root = ET.fromstring(ncx_content)
                            for navPoint in ncx_root.iter():
                                if navPoint.tag.endswith('navPoint'):
                                    text_node = navPoint.find('.//*{http://www.daisy.org/z3986/2005/ncx/}text')
                                    content_node = navPoint.find('.//*{http://www.daisy.org/z3986/2005/ncx/}content')
                                    if text_node is not None and content_node is not None:
                                        src = content_node.attrib.get('src', '').split('#')[0]
                                        toc_map[src] = text_node.text
                        except:
                            pass
                
                for idx, item_id in enumerate(spine):
                    if item_id in manifest:
                        href = manifest[item_id]
                        item_path = href if not opf_dir else f"{opf_dir}/{href}"
                        try:
                            html_bytes = zf.read(item_path)
                            html_str = html_bytes.decode('utf-8', errors='ignore')
                            html_str = re.sub(r'<(p|br|div|h[1-6]|li|tr|td|th)[^>]*>', '\n', html_str, flags=re.IGNORECASE)
                            html_str = re.sub(r'<[^>]+>', '', html_str)
                            html_str = html.unescape(html_str)
                            html_str = re.sub(r'\n{3,}', '\n\n', html_str)
                            
                            title = toc_map.get(href, f"Chapter {idx+1}")
                            book.chapters.append(Chapter(title, html_str.strip()))
                        except:
                            pass
        return book

class FB2Parser:
    @staticmethod
    def parse(filepath) -> Book:
        import xml.etree.ElementTree as ET
        import re
        book = Book(filepath=filepath)
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            xml_content = f.read()
        xml_content = re.sub(r'\sxmlns="[^"]+"', '', xml_content, count=1)
        try:
            root = ET.fromstring(xml_content)
            bodies = root.findall('body')
            main_body = bodies[0] if bodies else root
            
            sections = main_body.findall('.//section')
            if not sections:
                text_parts = ["".join(p.itertext()).strip() for p in main_body.findall('.//p')]
                book.chapters.append(Chapter("Book", "\n\n".join(text_parts)))
            else:
                for idx, sec in enumerate(sections):
                    title_node = sec.find('title')
                    title_text = "".join(title_node.itertext()).strip() if title_node is not None else f"Chapter {idx+1}"
                    
                    text_parts = []
                    for p in sec.findall('p'):
                        p_text = "".join(p.itertext()).strip()
                        if p_text: text_parts.append(p_text)
                    
                    book.chapters.append(Chapter(title_text, "\n\n".join(text_parts)))
        except Exception as e:
            book.chapters.append(Chapter("Error", f"Could not parse FB2: {str(e)}"))
        return book

class TXTParser:
    @staticmethod
    def parse(filepath) -> Book:
        book = Book(filepath=filepath)
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            text_data = f.read()
        
        chunk_len = len(text_data) // 10
        if chunk_len == 0:
            book.chapters.append(Chapter("Full Text", text_data))
        else:
            for i in range(10):
                book.chapters.append(Chapter(f"Part {i+1} ({(i)*10}%)", text_data[i*chunk_len:(i+1)*chunk_len]))
        return book

class KindleParser:
    @staticmethod
    def parse(filepath) -> Book:
        import shutil
        import re
        import html
        
        try:
            import mobi
            extracted_dir, filepath_extracted = mobi.extract(filepath)
            try:
                if filepath_extracted.lower().endswith('.epub'):
                    return EPUBParser.parse(filepath_extracted)
                else:
                    book = Book(filepath=filepath)
                    with open(filepath_extracted, 'r', encoding='utf-8', errors='ignore') as f:
                        html_str = f.read()
                        
                    parts = re.split(r'<mbp:pagebreak[^>]*>', html_str, flags=re.IGNORECASE)
                    
                    for idx, part in enumerate(parts):
                        part = re.sub(r'<(p|br|div|h[1-6]|li|tr|td|th)[^>]*>', '\n', part, flags=re.IGNORECASE)
                        part = re.sub(r'<[^>]+>', '', part)
                        part = html.unescape(part)
                        part = re.sub(r'\n{3,}', '\n\n', part).strip()
                        
                        if part:
                            lines = [l.strip() for l in part.split('\n') if l.strip()]
                            title = f"Part {idx+1}"
                            if lines and len(lines[0]) < 60:
                                title = lines[0]
                            book.chapters.append(Chapter(title, part))
                            
                    if not book.chapters:
                        book.chapters.append(Chapter("Content", "No readable text found."))
                    return book
            finally:
                try:
                    shutil.rmtree(extracted_dir)
                except: pass
        except Exception as e:
            book = Book(filepath=filepath)
            book.chapters.append(Chapter("Error", "This ebook is DRM-protected or unsupported.\n\nError details: " + str(e)))
            return book

def get_parser(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.epub': return EPUBParser()
    elif ext == '.fb2': return FB2Parser()
    elif ext in ['.mobi', '.azw', '.azw3']: return KindleParser()
    else: return TXTParser()

def main():
    sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_JOYSTICK | sdl2.SDL_INIT_GAMECONTROLLER)
    sdlttf.TTF_Init()

    controllers = []
    for i in range(sdl2.SDL_NumJoysticks()):
        if sdl2.SDL_IsGameController(i):
            controllers.append(sdl2.SDL_GameControllerOpen(i))

    window = sdl2.ext.Window("RetroRead", size=(SCREEN_W, SCREEN_H), flags=sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP)
    window.show()
    renderer = sdl2.ext.Renderer(window, flags=sdl2.SDL_RENDERER_ACCELERATED | sdl2.SDL_RENDERER_PRESENTVSYNC)
    reader_target = None
    reader_target_w = 0
    reader_target_h = 0

    font_path = FONT_PATH.encode('utf-8')
    reading_font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reading_font.ttf")
    if os.path.exists(reading_font_path):
        reading_font_bytes = reading_font_path.encode('utf-8')
    else:
        reading_font_bytes = font_path

    if not os.path.exists(FONT_PATH):
        sys.exit(1)
        
    font_large = sdlttf.TTF_OpenFont(font_path, 48)
    font_small = sdlttf.TTF_OpenFont(font_path, 24)
    font_ui_medium = sdlttf.TTF_OpenFont(font_path, 32)
    
    current_font_size = 34
    font_medium = sdlttf.TTF_OpenFont(reading_font_bytes, current_font_size)

    def render_text(text, font, color):
        if not text.strip(): return None, 0, 0
        if isinstance(color, sdl2.ext.Color):
            color = sdl2.SDL_Color(color.r, color.g, color.b, color.a)
        elif isinstance(color, tuple):
            color = sdl2.SDL_Color(color[0], color[1], color[2], color[3] if len(color)>3 else 255)
        tsurf = sdlttf.TTF_RenderUTF8_Blended(font, text.encode('utf-8'), color)
        if tsurf:
            ttex = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, tsurf)
            w, h = tsurf.contents.w, tsurf.contents.h
            sdl2.SDL_FreeSurface(tsurf)
            return ttex, w, h
        return None, 0, 0

    base_path = "/mnt/SDCARD/Books"
    if not os.path.exists(base_path):
        os.makedirs(base_path, exist_ok=True)
    
    current_path = base_path
    folders, files = get_directory_contents(current_path)
    
    state = STATE_BROWSE
    sel_index = 0
    scroll_y = 0
    dpad_up_held = False
    dpad_down_held = False
    dpad_timer = 0
    visible_items = 15
    theme_idx = load_theme_idx()
    reader_rotation_idx = load_reader_rotation_idx()
    
    # Reader Data
    raw_chapters = [] # List of (title, text_string)
    reader_lines = []
    chapter_offsets = [] # List of (title, line_index)
    
    current_filepath = ""
    reader_scroll_y = 0
    toc_sel_index = 0
    
    state_before_quit = STATE_BROWSE
    
    # Dynamic calculations
    lines_per_page = 15
    line_height = 45
    chars_per_line = 55

    def get_reader_view_size():
        if reader_rotation_idx % 2 == 1:
            return SCREEN_H, SCREEN_W
        return SCREEN_W, SCREEN_H

    def ensure_reader_target(target_w, target_h):
        nonlocal reader_target, reader_target_w, reader_target_h
        if reader_target and reader_target_w == target_w and reader_target_h == target_h:
            return reader_target
        if reader_target:
            sdl2.SDL_DestroyTexture(reader_target)
        reader_target = sdl2.SDL_CreateTexture(
            renderer.sdlrenderer,
            sdl2.SDL_PIXELFORMAT_RGBA8888,
            sdl2.SDL_TEXTUREACCESS_TARGET,
            target_w,
            target_h
        )
        reader_target_w = target_w
        reader_target_h = target_h
        return reader_target

    def rotate_reader_direction(dx, dy):
        rot = reader_rotation_idx % 4
        if rot == 1:
            return -dy, dx
        elif rot == 2:
            return -dx, -dy
        elif rot == 3:
            return dy, -dx
        return dx, dy

    def handle_reader_direction(dx, dy):
        nonlocal reader_scroll_y
        dx, dy = rotate_reader_direction(dx, dy)
        max_s = max(0, len(reader_lines) - lines_per_page)
        
        if dy < 0:
            reader_scroll_y = max(0, reader_scroll_y - 1)
            while reader_scroll_y > 0 and reader_lines[reader_scroll_y] == "":
                reader_scroll_y -= 1
        elif dy > 0:
            reader_scroll_y = min(max_s, reader_scroll_y + 1)
            while reader_scroll_y < max_s and reader_lines[reader_scroll_y] == "":
                reader_scroll_y += 1
        elif dx < 0:
            reader_scroll_y = max(0, reader_scroll_y - lines_per_page)
            while reader_scroll_y > 0 and reader_lines[reader_scroll_y] == "":
                reader_scroll_y -= 1
        elif dx > 0:
            reader_scroll_y = min(max_s, reader_scroll_y + lines_per_page)
            while reader_scroll_y < max_s and reader_lines[reader_scroll_y] == "":
                reader_scroll_y += 1
    
    def recalculate_layout():
        nonlocal lines_per_page, line_height, chars_per_line, font_medium, reader_lines, chapter_offsets
        # Close old font
        if font_medium:
            sdlttf.TTF_CloseFont(font_medium)
        font_medium = sdlttf.TTF_OpenFont(reading_font_bytes, current_font_size)
        
        # Calculate fitting
        reader_w, reader_h = get_reader_view_size()
        line_height = int(current_font_size * 1.32)
        # Reserve 55px for footer + 50px top padding = 105px reserved
        lines_per_page = max(1, (reader_h - 105) // line_height)
        
        max_line_width = reader_w - 40 # 20px left, 20px right
        
        import ctypes
        w = ctypes.c_int()
        h = ctypes.c_int()
        
        # Re-wrap text
        reader_lines = []
        chapter_offsets = []
        
        # Cache to dramatically speed up width calculation (avoid C calls for every word)
        word_width_cache = {}
        def get_word_width(w_str):
            if w_str not in word_width_cache:
                sdlttf.TTF_SizeUTF8(font_medium, w_str.encode('utf-8', errors='replace'), ctypes.byref(w), ctypes.byref(h))
                word_width_cache[w_str] = w.value
            return word_width_cache[w_str]
            
        space_width = get_word_width(" ")
        indent_width = get_word_width("   ")
        
        for title, text in raw_chapters:
            chapter_offsets.append((title, len(reader_lines)))
            # Split text into paragraphs
            for paragraph in text.split('\n'):
                paragraph = paragraph.replace('\t', '    ').strip()
                if not paragraph:
                    reader_lines.append("")
                    continue
                
                # Split by space to prevent breaking Vietnamese words
                words = paragraph.split(' ')
                current_line = []
                current_w = indent_width
                is_first_line = True
                
                for word in words:
                    if not word: continue
                    ww = get_word_width(word)
                    
                    if not current_line:
                        current_line.append(word)
                        current_w += ww
                    else:
                        if current_w + space_width + ww <= max_line_width:
                            current_line.append(word)
                            current_w += space_width + ww
                        else:
                            prefix = "   " if is_first_line else ""
                            reader_lines.append(prefix + " ".join(current_line))
                            current_line = [word]
                            current_w = ww
                            is_first_line = False
                            
                if current_line:
                    prefix = "   " if is_first_line else ""
                    reader_lines.append(prefix + " ".join(current_line))
                    
    def load_book(filepath):
        nonlocal raw_chapters, reader_scroll_y, current_font_size, current_filepath
        raw_chapters = []
        
        save_data = load_save(filepath)
        reader_scroll_y = save_data.get("scroll_y", 0)
        current_font_size = save_data.get("font_size", 34)
        current_filepath = filepath
        
        try:
            parser = get_parser(filepath)
            book = parser.parse(filepath)
            if not book.chapters:
                return False
                
            for ch in book.chapters:
                raw_chapters.append((ch.title, ch.content))
                
            recalculate_layout()
            if reader_lines:
                reader_scroll_y = max(0, min(reader_scroll_y, len(reader_lines) - lines_per_page))
            return True
        except Exception as e:
            return False

    running = True
    needs_redraw = True
    last_axis_scroll = 0
    show_hud = True
    
    while running:
        events = sdl2.ext.get_events()
        if len(events) > 0:
            needs_redraw = True
            
        current_ticks = sdl2.SDL_GetTicks()
        axis_up = False
        axis_down = False
        for c in controllers:
            lx = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_LEFTX)
            ly = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_LEFTY)
            rx = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_RIGHTX)
            ry = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_RIGHTY)
            ax = lx if abs(lx) >= abs(rx) else rx
            ay = ly if abs(ly) >= abs(ry) else ry
            if ay < -16000:
                axis_up = True
            elif ay > 16000:
                axis_down = True
            if state == STATE_READER and (current_ticks - last_axis_scroll > 100):
                if abs(ax) >= 16000 or abs(ay) >= 16000:
                    if abs(ax) > abs(ay):
                        handle_reader_direction(1 if ax > 0 else -1, 0)
                    else:
                        handle_reader_direction(0, 1 if ay > 0 else -1)
                    last_axis_scroll = current_ticks
                    needs_redraw = True
                    break
                    
        for event in events:
            if event.type == sdl2.SDL_QUIT:
                if state in (STATE_READER, STATE_TOC):
                    write_save(current_filepath, reader_scroll_y, current_font_size)
                running = False
            elif event.type == sdl2.SDL_KEYDOWN:
                if event.key.keysym.sym == sdl2.SDLK_ESCAPE:
                    if state in (STATE_READER, STATE_TOC):
                        write_save(current_filepath, reader_scroll_y, current_font_size)
                    running = False
                    
            elif event.type == sdl2.SDL_CONTROLLERBUTTONUP:
                btn = event.cbutton.button
                if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                    dpad_up_held = False
                elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                    dpad_down_held = False
            elif event.type == sdl2.SDL_CONTROLLERBUTTONDOWN:
                btn = event.cbutton.button
                if btn == sdl2.SDL_CONTROLLER_BUTTON_START:
                    state_before_quit = state
                    state = STATE_QUIT_CONFIRM
                    
                if state == STATE_BROWSE:
                    list_items = [{"name": "..", "is_dir": True}] if current_path != base_path else []
                    list_items += [{"name": f, "is_dir": True} for f in folders]
                    list_items += [{"name": f, "is_dir": False} for f in files]
                    
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                        dpad_up_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                        dpad_down_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: # Page Up
                        visible_items = 8
                        sel_index = max(0, sel_index - visible_items)
                        scroll_y = max(0, scroll_y - visible_items)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: # Page Down
                        visible_items = 8
                        sel_index = min(len(list_items) - 1, sel_index + visible_items)
                        scroll_y = min(max(0, len(list_items) - visible_items), scroll_y + visible_items)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_X: # Physical Y - Theme Toggle
                        theme_idx = (theme_idx + 1) % len(THEMES)
                        write_theme_idx(theme_idx)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A - Enter
                        if len(list_items) > 0:
                            item = list_items[sel_index]
                            if item["name"] == "..":
                                current_path = os.path.dirname(current_path)
                                folders, files = get_directory_contents(current_path)
                                sel_index = 0
                                scroll_y = 0
                            elif item["is_dir"]:
                                current_path = os.path.join(current_path, item["name"])
                                folders, files = get_directory_contents(current_path)
                                sel_index = 0
                                scroll_y = 0
                            else:
                                filepath = os.path.join(current_path, item["name"])
                                if load_book(filepath):
                                    state = STATE_READER
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B - Back
                        if current_path != base_path:
                            current_path = os.path.dirname(current_path)
                            folders, files = get_directory_contents(current_path)
                            sel_index = 0
                            scroll_y = 0
                        
                elif state == STATE_READER:
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                        handle_reader_direction(0, -1)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                        handle_reader_direction(0, 1)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                        handle_reader_direction(-1, 0)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
                        handle_reader_direction(1, 0)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: # Decrease Font
                        current_font_size = max(30, current_font_size - 2)
                        recalculate_layout()
                        if reader_lines:
                            reader_scroll_y = max(0, min(reader_scroll_y, len(reader_lines) - lines_per_page))
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: # Increase Font
                        current_font_size = min(44, current_font_size + 2)
                        recalculate_layout()
                        if reader_lines:
                            reader_scroll_y = max(0, min(reader_scroll_y, len(reader_lines) - lines_per_page))
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_X: # Physical Y - Theme Toggle
                        theme_idx = (theme_idx + 1) % len(THEMES)
                        write_theme_idx(theme_idx)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_Y: # Physical X - Rotate reader
                        reader_rotation_idx = (reader_rotation_idx + 1) % 4
                        write_reader_rotation_idx(reader_rotation_idx)
                        recalculate_layout()
                        if reader_lines:
                            reader_scroll_y = max(0, min(reader_scroll_y, len(reader_lines) - lines_per_page))
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_BACK: # SELECT - TOC
                        state = STATE_TOC
                        toc_sel_index = 0
                        for idx, (ch_title, ch_line) in enumerate(chapter_offsets):
                            if ch_line <= reader_scroll_y:
                                toc_sel_index = idx
                            else:
                                break
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B - Exit Reader
                        write_save(current_filepath, reader_scroll_y, current_font_size)
                        state = STATE_BROWSE
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A - Toggle HUD
                        show_hud = not show_hud
                        
                elif state == STATE_TOC:
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                        dpad_up_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                        dpad_down_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A - Select chapter
                        if len(chapter_offsets) > 0:
                            reader_scroll_y = chapter_offsets[toc_sel_index][1]
                        state = STATE_READER
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A or btn == sdl2.SDL_CONTROLLER_BUTTON_BACK: # Physical B or Select - Back to Reader
                        state = STATE_READER
                        
                elif state == STATE_QUIT_CONFIRM:
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A (Confirm)
                        if state_before_quit in (STATE_READER, STATE_TOC):
                            write_save(current_filepath, reader_scroll_y, current_font_size)
                        running = False
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B (Cancel)
                        state = state_before_quit

        # Key repeat logic for library (exact Files app behavior)
        is_up = dpad_up_held or axis_up
        is_down = dpad_down_held or axis_down
        
        if state == STATE_BROWSE:
            list_items = [{"name": "..", "is_dir": True}] if current_path != base_path else []
            list_items += [{"name": f, "is_dir": True} for f in folders]
            list_items += [{"name": f, "is_dir": False} for f in files]
            library_visible_items = 8
            
            if is_up:
                if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                    if len(list_items) > 0:
                        if sel_index == 0:
                            sel_index = len(list_items) - 1
                            scroll_y = max(0, len(list_items) - library_visible_items)
                        else:
                            sel_index -= 1
                            if sel_index < scroll_y:
                                scroll_y = sel_index
                    needs_redraw = True
                dpad_timer += 1
            elif is_down:
                if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                    if len(list_items) > 0:
                        if sel_index == len(list_items) - 1:
                            sel_index = 0
                            scroll_y = 0
                        else:
                            sel_index += 1
                            if sel_index >= scroll_y + library_visible_items:
                                scroll_y = sel_index - library_visible_items + 1
                    needs_redraw = True
                dpad_timer += 1
            else:
                dpad_timer = 0
        elif state == STATE_TOC:
            if is_up:
                if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                    if len(chapter_offsets) > 0:
                        toc_sel_index = (toc_sel_index - 1) % len(chapter_offsets)
                    needs_redraw = True
                dpad_timer += 1
            elif is_down:
                if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                    if len(chapter_offsets) > 0:
                        toc_sel_index = (toc_sel_index + 1) % len(chapter_offsets)
                    needs_redraw = True
                dpad_timer += 1
            else:
                dpad_timer = 0
        elif state != STATE_READER:
            dpad_up_held = False
            dpad_down_held = False
            dpad_timer = 0

        if needs_redraw:
            theme = THEMES[theme_idx]
            renderer.clear(theme["bg"])
            
            render_state = state_before_quit if state == STATE_QUIT_CONFIRM else state

            if render_state == STATE_BROWSE:
                library_theme = LIBRARY_THEMES[theme_idx]
                renderer.clear(library_theme["bg"])
                renderer.fill((0, 0, SCREEN_W, 76), library_theme["header"])
                renderer.fill((0, 74, SCREEN_W, 2), library_theme["divider"])
                sdlttf.TTF_SetFontStyle(font_large, sdlttf.TTF_STYLE_BOLD)
                tex, tw, th = render_text("LIBRARY", font_large, library_theme["text"])
                sdlttf.TTF_SetFontStyle(font_large, sdlttf.TTF_STYLE_NORMAL)
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(32, 12, tw, th))
                    sdl2.SDL_DestroyTexture(tex)

                list_items = [{"name": "..", "is_dir": True}] if current_path != base_path else []
                list_items += [{"name": f, "is_dir": True} for f in folders]
                list_items += [{"name": f, "is_dir": False} for f in files]

                library_visible_items = 8
                book_count = f"{len(files)} BOOK" + ("" if len(files) == 1 else "S")
                tex, tw, th = render_text(book_count, font_small, library_theme["secondary"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(SCREEN_W - 32 - tw, 27, tw, th))
                    sdl2.SDL_DestroyTexture(tex)

                start_idx = scroll_y
                end_idx = min(len(list_items), start_idx + library_visible_items)
                
                sel_border = library_theme.get("sel_border", sdl2.ext.Color(102, 137, 181))
                sel_bg = library_theme.get("sel_bg", sdl2.ext.Color(229, 235, 241))
                sel_text = library_theme.get("sel_text", sdl2.SDL_Color(30, 30, 30, 255))
                sel_sec = library_theme.get("sel_sec", sdl2.SDL_Color(80, 80, 80, 255))

                y_start = 86
                row_h = 74
                for i in range(start_idx, end_idx):
                    item = list_items[i]
                    iy = y_start + (i - start_idx) * row_h
                    
                    text_col = sel_text if i == sel_index else library_theme["text"]
                    sec_col = sel_sec if i == sel_index else library_theme["secondary"]
                    
                    if i == sel_index:
                        sel_x, sel_y, sel_w, sel_h = 20, iy, SCREEN_W - 40, 68
                        renderer.fill((sel_x, sel_y, sel_w, sel_h), sel_border)
                        renderer.fill((sel_x + 2, sel_y + 2, sel_w - 4, sel_h - 4), sel_bg)

                    if item["is_dir"]:
                        renderer.fill((42, iy + 18, 18, 14), library_theme["accent"])
                        renderer.fill((44, iy + 15, 9, 4), library_theme["accent"])
                        tex, tw, th = render_text(item["name"], font_ui_medium, text_col)
                        if tex:
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(78, iy + 13, min(tw, SCREEN_W - 110), th))
                            sdl2.SDL_DestroyTexture(tex)
                    else:
                        title, author = get_book_display_metadata(item["name"])
                        icon_bg = sel_bg if i == sel_index else library_theme["bg"]
                        draw_book_icon(renderer, 42, iy + 16, library_theme["accent"], icon_bg)
                        sdlttf.TTF_SetFontStyle(font_ui_medium, sdlttf.TTF_STYLE_BOLD)
                        tex, tw, th = render_text(title, font_ui_medium, text_col)
                        sdlttf.TTF_SetFontStyle(font_ui_medium, sdlttf.TTF_STYLE_NORMAL)
                        if tex:
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(78, iy + 4, min(tw, SCREEN_W - 110), th))
                            sdl2.SDL_DestroyTexture(tex)
                        if author:
                            tex, tw, th = render_text(author, font_small, sec_col)
                            if tex:
                                sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(78, iy + 37, min(tw, SCREEN_W - 110), th))
                                sdl2.SDL_DestroyTexture(tex)
                        
                renderer.fill((0, SCREEN_H - 58, SCREEN_W, 1), library_theme["divider"])
                footer = "A: Open    B: Back    Y: Theme    [START] Exit"
                tex, tw, th = render_text(footer, font_small, library_theme["secondary"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(32, SCREEN_H - 38, tw, th))
                    sdl2.SDL_DestroyTexture(tex)

            elif render_state == STATE_READER:
                reader_w, reader_h = get_reader_view_size()
                reader_angle = reader_rotation_idx * 90
                drawing_rotated = reader_rotation_idx != 0
                if drawing_rotated:
                    target = ensure_reader_target(reader_w, reader_h)
                    if target:
                        sdl2.SDL_SetRenderTarget(renderer.sdlrenderer, target)
                        renderer.clear(theme["bg"])
                    else:
                        drawing_rotated = False
                        reader_w, reader_h = SCREEN_W, SCREEN_H

                y_pos = 50
                max_y = reader_h - 55 # Leave room for footer
                i = reader_scroll_y
                while i < len(reader_lines):
                    line = reader_lines[i]
                    step = max(2, line_height // 6) if line == "" else line_height
                    if y_pos + step > max_y:
                        break
                        
                    if line == "":
                        y_pos += step
                    else:
                        tex, tw, th = render_text(line, font_medium, theme["text"])
                        if tex:
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(20, y_pos, tw, th))
                            sdl2.SDL_DestroyTexture(tex)
                        y_pos += step
                    i += 1
                
                # HUD Elements
                if show_hud:
                    # Progress bar
                    if len(reader_lines) > 0:
                        progress = min(1.0, reader_scroll_y / max(1, len(reader_lines) - lines_per_page))
                        bar_w = int((reader_w - 40) * progress)
                        renderer.fill((20, reader_h - 10, reader_w - 40, 5), theme["sel"])
                        renderer.fill((20, reader_h - 10, bar_w, 5), theme["text"])
                    
                    # Top HUD: Chapter Name and Page Number
                    curr_chap = "Chapter 1"
                    for ch_title, ch_line in chapter_offsets:
                        if ch_line <= reader_scroll_y:
                            curr_chap = ch_title
                        else:
                            break
                    
                    total_pages = max(1, len(reader_lines) // lines_per_page + 1)
                    curr_page = reader_scroll_y // lines_per_page + 1
                    
                    book_name = os.path.basename(current_filepath)
                    hud_top = f"{book_name} - {curr_chap} - Page {curr_page}/{total_pages}"
                    tex, tw, th = render_text(hud_top, font_small, theme["text"])
                    if tex:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(20, 15, min(tw, reader_w-40), th))
                        sdl2.SDL_DestroyTexture(tex)
                    
                    # Bottom HUD: Instructions
                    footer = f"Size: {current_font_size} | L/R: Aa | A: HUD | B: Back | X: Rotate | Y: Theme | SELECT: Contents | START: Exit"
                    tex, tw, th = render_text(footer, font_small, theme["text"])
                    if tex:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(20, reader_h - 45, min(tw, reader_w-40), th))
                        sdl2.SDL_DestroyTexture(tex)

                if drawing_rotated:
                    sdl2.SDL_SetRenderTarget(renderer.sdlrenderer, None)
                    renderer.clear(theme["bg"])
                    src_rect = sdl2.SDL_Rect(0, 0, reader_w, reader_h)
                    dst_rect = sdl2.SDL_Rect((SCREEN_W - reader_w) // 2, (SCREEN_H - reader_h) // 2, reader_w, reader_h)
                    sdl2.SDL_RenderCopyEx(renderer.sdlrenderer, target, src_rect, dst_rect, reader_angle, None, sdl2.SDL_FLIP_NONE)

            elif render_state == STATE_TOC:
                renderer.fill((0, 0, SCREEN_W, 60), theme["header"])
                tex, tw, th = render_text("TABLE OF CONTENTS", font_medium, theme["text"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(SCREEN_W//2 - tw//2, 10, tw, th))
                    sdl2.SDL_DestroyTexture(tex)
                    
                start_idx = max(0, toc_sel_index - visible_items // 2)
                end_idx = min(len(chapter_offsets), start_idx + visible_items)
                
                y_start = 80
                for i in range(start_idx, end_idx):
                    ch_title, ch_line = chapter_offsets[i]
                    iy = y_start + (i - start_idx) * 40
                    
                    if i == toc_sel_index:
                        renderer.fill((0, iy, SCREEN_W, 40), theme["sel"])
                        
                    tex, tw, th = render_text(ch_title, font_small, theme["text"])
                    if tex:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(40, iy + 5, min(tw, SCREEN_W-80), th))
                        sdl2.SDL_DestroyTexture(tex)
                        
                footer = "A: Jump | B: Cancel"
                tex, tw, th = render_text(footer, font_small, theme["text"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(20, SCREEN_H - 40, tw, th))
                    sdl2.SDL_DestroyTexture(tex)

            if state == STATE_QUIT_CONFIRM:
                sdl2.SDL_SetRenderDrawBlendMode(renderer.sdlrenderer, sdl2.SDL_BLENDMODE_BLEND)
                sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 0, 0, 0, 150)
                sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, 0, SCREEN_W, SCREEN_H))
                
                pop_w, pop_h = 600, 200
                pop_x, pop_y = (SCREEN_W - pop_w)//2, (SCREEN_H - pop_h)//2
                
                renderer.fill((pop_x, pop_y, pop_w, pop_h), theme["bg"])
                renderer.fill((pop_x+2, pop_y+2, pop_w-4, pop_h-4), theme["header"])
                
                msg = "Exit RetroRead?"
                tex, tw, th = render_text(msg, font_large, theme["text"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + pop_w//2 - tw//2, pop_y + 40, tw, th))
                    sdl2.SDL_DestroyTexture(tex)
                
                msg2 = "A: Confirm   B: Cancel"
                tex, tw, th = render_text(msg2, font_ui_medium, theme["text"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + pop_w//2 - tw//2, pop_y + 130, tw, th))
                    sdl2.SDL_DestroyTexture(tex)

            renderer.present()
            needs_redraw = False
            
        sdl2.SDL_Delay(16)

    if font_medium:
        sdlttf.TTF_CloseFont(font_medium)
    if reader_target:
        sdl2.SDL_DestroyTexture(reader_target)
    sdlttf.TTF_CloseFont(font_large)
    sdlttf.TTF_CloseFont(font_small)
    sdlttf.TTF_CloseFont(font_ui_medium)
    sdlttf.TTF_Quit()
    sdl2.SDL_Quit()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        with open("crash_python.log", "w") as f:
            traceback.print_exc(file=f)
        sys.exit(1)
