import sys
import os
import textwrap
import traceback
import json
import re
import html
import ctypes
import threading
import queue as _queue_mod
import hashlib
import zipfile
import shutil
import base64
import urllib.parse as urllib
import xml.etree.ElementTree as ET

from constants import (
    SCREEN_W, SCREEN_H,
    STATE_BROWSE, STATE_READER, STATE_TOC, STATE_QUIT_CONFIRM, STATE_IMAGE_VIEW, STATE_ABOUT,
    VALID_EXTS, VALID_EXTS_SET,
    THEMES, LIBRARY_THEMES
)

from storage import (
    load_settings, write_settings,
    load_typography_settings, write_typography_settings,
    load_save, write_save,
    load_theme_idx, write_theme_idx,
    load_library_view, write_library_view,
    load_reader_rotation_idx, write_reader_rotation_idx
)

from parsers import (
    Chapter, Book,
    EPUBParser, FB2Parser, TXTParser, KindleParser,
    get_parser, extract_epub_cover_data,
    process_inline_footnotes, clean_html_to_clean_text
)

from ui_dialogs import (
    draw_about_dialog,
    draw_quit_confirm_dialog,
    draw_typography_popup,
    draw_toast_notification
)

# Add local bundled vendor
VENDOR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
if os.path.exists(VENDOR_PATH):
    sys.path.insert(0, VENDOR_PATH)

os.environ["PYSDL2_DLL_PATH"] = "/usr/trimui/lib"

try:
    import sdl2
    import sdl2.ext
    import sdl2.sdlttf as sdlttf
    import sdl2.sdlimage as sdlimage
except ImportError as e:
    sys.stderr.write("Cannot load SDL2. Error: " + str(e))
    sys.exit(1)

FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "font.ttf")

def log_debug(msg):
    pass

def get_directory_contents(path):
    folders = []
    files = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.name.startswith('.'):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        folders.append(entry.name)
                    else:
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in VALID_EXTS_SET:
                            files.append(entry.name)
                except OSError:
                    pass
    except Exception:
        pass
    folders.sort(key=str.lower)
    files.sort(key=str.lower)
    return folders, files

def get_book_display_metadata(filename):
    """Derive library label from a filename without changing the real path."""
    stem = os.path.splitext(filename)[0]
    return stem.strip(), ""

def draw_book_icon(renderer, x, y, color, background):
    """Small pixel-friendly book glyph, deliberately free of emoji assets."""
    renderer.fill((x, y, 15, 20), color)
    renderer.fill((x + 3, y + 3, 2, 14), background)


def main():
    sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_JOYSTICK | sdl2.SDL_INIT_GAMECONTROLLER)
    sdlttf.TTF_Init()

    controllers = []
    for i in range(sdl2.SDL_NumJoysticks()):
        if sdl2.SDL_IsGameController(i):
            controllers.append(sdl2.SDL_GameControllerOpen(i))

    window = sdl2.ext.Window("RetroBooks", size=(SCREEN_W, SCREEN_H), flags=sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP)
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
    prev_sel_index = 0
    sel_time = 0
    marquee_active = False
    scroll_y = 0
    dpad_up_held = False
    dpad_down_held = False
    dpad_left_held = False
    dpad_right_held = False
    dpad_timer = 0
    dpad_horiz_timer = 0
    visible_items = 15
    theme_idx = load_theme_idx()
    reader_rotation_idx = load_reader_rotation_idx()
    library_view_mode = load_library_view() # "list" or "grid"
    cover_cache = {}  # filepath -> (SDL_Texture, w, h)



    # -----------------------------------------------------------------------
    # Fast Async Cover System: background thread + disk cache + downscaling
    # Cover cell on screen: 170x200 px. We store covers at 255x300 (1.5x for
    # crisp rendering) — that is the 3/4-of-source downscale quality setting.
    # -----------------------------------------------------------------------
    import threading, hashlib
    import queue as _queue_mod
    COVER_CACHE_DIR = "/mnt/SDCARD/.cover_cache"
    try:
        os.makedirs(COVER_CACHE_DIR, exist_ok=True)
    except Exception:
        pass

    def _cover_disk_path(fp):
        h = hashlib.sha1(fp.encode("utf-8", errors="replace")).hexdigest()[:16]
        return os.path.join(COVER_CACHE_DIR, h + ".bmp")

    def _decode_cover(img_data):
        """CPU-side: decode bytes -> SDL_Surface at full native resolution.
        No downscaling here: GPU handles display scaling at render time for
        maximum sharpness at any cover cell size."""
        rw = sdl2.SDL_RWFromConstMem(img_data, len(img_data))
        src = sdlimage.IMG_Load_RW(rw, 1)
        if not src:
            return None, 0, 0
        sw, sh = src.contents.w, src.contents.h
        if sw <= 0 or sh <= 0:
            sdl2.SDL_FreeSurface(src)
            return None, 0, 0
        return src, sw, sh

    cover_pending        = set()              # guarded by _cover_q_lock
    _cover_q             = _queue_mod.Queue() # blocking FIFO for workers
    _cover_q_lock        = threading.Lock()   # guard cover_pending
    cover_ready          = {}                 # filepath -> (surf,w,h) or (None,0,0)
    cover_ready_lock     = threading.Lock()
    cover_thread_running = [True]

    def _cover_worker():
        while cover_thread_running[0]:
            try:
                filepath = _cover_q.get(timeout=0.5)
            except Exception:
                continue
            disk = _cover_disk_path(filepath)
            img_data = None
            if os.path.exists(disk):
                try:
                    with open(disk, "rb") as f:
                        img_data = f.read()
                except Exception:
                    img_data = None
            if not img_data:
                _ext = os.path.splitext(filepath)[1].lower()
                if _ext == '.epub':
                    img_data = extract_epub_cover_data(filepath)
            if not img_data:
                with cover_ready_lock:
                    cover_ready[filepath] = (None, 0, 0)
                _cover_q.task_done()
                continue
            surf, dw, dh = _decode_cover(img_data)
            if surf and dw > 0:
                if not os.path.exists(disk):
                    try:
                        sdl2.SDL_SaveBMP(surf, disk.encode("utf-8"))
                    except Exception:
                        pass
                with cover_ready_lock:
                    cover_ready[filepath] = (surf, dw, dh)
            else:
                if surf:
                    sdl2.SDL_FreeSurface(surf)
                with cover_ready_lock:
                    cover_ready[filepath] = (None, 0, 0)
            _cover_q.task_done()

    # 3 parallel decode threads
    _cover_threads = []
    for _i in range(3):
        _t = threading.Thread(target=_cover_worker, daemon=True)
        _t.start()
        _cover_threads.append(_t)

    def pump_cover_ready():
        """Call once per frame: promote finished CPU surfaces -> GPU textures."""
        with cover_ready_lock:
            if not cover_ready:
                return
            batch = list(cover_ready.items())
            cover_ready.clear()
        for fp, result in batch:
            if len(result) == 3 and result[0] is not None:
                surf, dw, dh = result
                tex = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, surf)
                sdl2.SDL_FreeSurface(surf)
                cover_cache[fp] = (tex, dw, dh) if tex else (None, 0, 0)
            else:
                cover_cache[fp] = (None, 0, 0)

    def get_cover_texture(filepath):
        """Non-blocking: returns cached texture or queues background load."""
        if filepath in cover_cache:
            return cover_cache[filepath]
        with cover_ready_lock:
            already = filepath in cover_ready
        if not already:
            with _cover_q_lock:
                if filepath not in cover_pending:
                    cover_pending.add(filepath)
                    _cover_q.put_nowait(filepath)
        return (None, 0, 0)

    def prewarm_covers(item_list, path):
        """Pre-queue all file items immediately when entering a directory."""
        for item in item_list:
            if not item["is_dir"]:
                fp = os.path.join(path, item["name"])
                if fp not in cover_cache:
                    with cover_ready_lock:
                        already = fp in cover_ready
                    if not already:
                        with _cover_q_lock:
                            if fp not in cover_pending:
                                cover_pending.add(fp)
                                _cover_q.put_nowait(fp)

    def clear_cover_cache():
        with _cover_q_lock:
            cover_pending.clear()
        while not _cover_q.empty():
            try: _cover_q.get_nowait(); _cover_q.task_done()
            except Exception: break
        with cover_ready_lock:
            for result in cover_ready.values():
                if len(result) == 3 and result[0] is not None:
                    sdl2.SDL_FreeSurface(result[0])
            cover_ready.clear()
        for tex, _, _ in cover_cache.values():
            if tex:
                sdl2.SDL_DestroyTexture(tex)
        cover_cache.clear()

    
    # NOTE: cover_queue_lock replaced by _cover_q_lock -- no references remain

    def _make_list_items_for_path(fldrs, fls, cur_path, base_path):
        li = ([{"name": "..", "is_dir": True}] if cur_path != base_path else [])
        li += [{"name": f, "is_dir": True} for f in fldrs]
        li += [{"name": f, "is_dir": False} for f in fls]
        return li

    raw_chapters = [] # List of (title, text_string)
    reader_lines = []
    chapter_offsets = [] # List of (title, line_index)
    
    current_filepath = ""
    reader_scroll_y = 0
    toc_sel_index = 0

    # Image Viewer Data
    book_images = []
    image_loader = None
    current_image_idx = 0
    loaded_image_tex = None
    loaded_image_idx = -1
    image_w = 0
    image_h = 0
    image_zoom = -1.0
    image_pan_x = 0
    image_pan_y = 0
    image_rotation = 0
    toast_msg = ""
    toast_timer = 0
    toc_tab = 0 # 0: Chapters, 1: Images
    toc_img_sel_index = 0
    l2_pressed = False
    r2_pressed = False

    def get_current_image_texture():
        nonlocal loaded_image_tex, loaded_image_idx, image_w, image_h, image_zoom, image_pan_x, image_pan_y
        if not book_images or current_image_idx < 0 or current_image_idx >= len(book_images):
            return None
        if loaded_image_idx == current_image_idx and loaded_image_tex:
            return loaded_image_tex
        if loaded_image_tex:
            sdl2.SDL_DestroyTexture(loaded_image_tex)
            loaded_image_tex = None
            loaded_image_idx = -1
        try:
            img_id = book_images[current_image_idx]
            data = image_loader(img_id) if image_loader else None
            if data:
                rw = sdl2.SDL_RWFromConstMem(data, len(data))
                surf = sdlimage.IMG_Load_RW(rw, 1)
                if surf:
                    image_w = surf.contents.w
                    image_h = surf.contents.h
                    loaded_image_tex = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, surf)
                    sdl2.SDL_FreeSurface(surf)
                    loaded_image_idx = current_image_idx
                    image_zoom = -1.0
                    image_pan_x = 0
                    image_pan_y = 0
                    return loaded_image_tex
        except:
            pass
        return None

    inline_image_cache = {}
    book_img_thumb_cache = {}
    page_items_drawn = 15

    def clear_book_img_thumb_cache():
        nonlocal book_img_thumb_cache
        for k in list(book_img_thumb_cache.keys()):
            try:
                sdl2.SDL_DestroyTexture(book_img_thumb_cache[k]["tex"])
            except Exception:
                pass
        book_img_thumb_cache.clear()

    def get_book_img_thumbnail(img_path, max_w=216, max_h=260):
        nonlocal book_img_thumb_cache
        if not img_path or not image_loader:
            return None
        if img_path in book_img_thumb_cache:
            return book_img_thumb_cache[img_path]
        try:
            data = image_loader(img_path)
            if not data:
                return None
            rw = sdl2.SDL_RWFromConstMem(data, len(data))
            orig_surf = sdlimage.IMG_Load_RW(rw, 1)
            if orig_surf:
                ow = orig_surf.contents.w
                oh = orig_surf.contents.h
                scale = min(float(max_w) / max(1, ow), float(max_h) / max(1, oh))
                tw = max(1, int(ow * scale))
                th = max(1, int(oh * scale))
                small_surf = sdl2.SDL_CreateRGBSurfaceWithFormat(0, tw, th, 32, sdl2.SDL_PIXELFORMAT_RGBA8888)
                if small_surf:
                    sdl2.SDL_BlitScaled(orig_surf, None, small_surf, None)
                    tex = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, small_surf)
                    sdl2.SDL_FreeSurface(small_surf)
                else:
                    tex = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, orig_surf)
                sdl2.SDL_FreeSurface(orig_surf)
                if tex:
                    info = {"tex": tex, "w": tw, "h": th}
                    book_img_thumb_cache[img_path] = info
                    return info
        except Exception as e:
            log_debug(f"get_book_img_thumbnail error: {e}")
        return None

    def find_image_key(src):
        if not book_images:
            return None
        if src in book_images:
            return src
        clean_src = os.path.basename(src.split('?')[0].split('#')[0]).lower()
        for img_path in book_images:
            if os.path.basename(img_path).lower() == clean_src:
                return img_path
        for img_path in book_images:
            if img_path.lower().endswith(clean_src):
                return img_path
        import urllib.parse
        unquoted = urllib.parse.unquote(clean_src)
        for img_path in book_images:
            if os.path.basename(img_path).lower() == unquoted:
                return img_path
        return None

    def find_image_reader_line(target_img_path):
        if not target_img_path or not reader_lines:
            return None
        target_clean = os.path.basename(target_img_path.split('?')[0].split('#')[0]).lower()
        for line_idx, line in enumerate(reader_lines):
            if isinstance(line, dict) and line.get("type") == "image":
                src = line.get("src", "")
                if src == target_img_path:
                    return line_idx
                resolved = find_image_key(src)
                if resolved == target_img_path:
                    return line_idx
                clean_src = os.path.basename(src.split('?')[0].split('#')[0]).lower()
                if clean_src == target_clean:
                    return line_idx
        return None

    def get_inline_image(img_src, max_w, max_h):
        nonlocal inline_image_cache
        resolved = find_image_key(img_src)
        if not resolved or not image_loader:
            return None
        cache_key = (resolved, max_w, max_h)
        if cache_key in inline_image_cache:
            item = inline_image_cache[cache_key]
            item["last_used"] = sdl2.SDL_GetTicks()
            return item
        try:
            data = image_loader(resolved)
            if not data:
                return None
            rw = sdl2.SDL_RWFromConstMem(data, len(data))
            surf = sdlimage.IMG_Load_RW(rw, 1)
            if surf:
                ow = surf.contents.w
                oh = surf.contents.h
                scale = min(float(max_w) / ow, float(max_h) / oh)
                if scale > 1.0:
                    scale = 1.0
                sw = max(1, int(ow * scale))
                sh = max(1, int(oh * scale))
                
                tex = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, surf)
                sdl2.SDL_FreeSurface(surf)
                if tex:
                    if len(inline_image_cache) >= 12:
                        oldest_key = min(inline_image_cache.keys(), key=lambda k: inline_image_cache[k]["last_used"])
                        sdl2.SDL_DestroyTexture(inline_image_cache[oldest_key]["tex"])
                        del inline_image_cache[oldest_key]
                    entry = {"tex": tex, "w": sw, "h": sh, "last_used": sdl2.SDL_GetTicks()}
                    inline_image_cache[cache_key] = entry
                    return entry
        except:
            pass
        return None

    def clear_inline_image_cache():
        nonlocal inline_image_cache
        for entry in inline_image_cache.values():
            if entry.get("tex"):
                sdl2.SDL_DestroyTexture(entry["tex"])
        inline_image_cache.clear()
    
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
            return dy, -dx
        elif rot == 2:
            return -dx, -dy
        elif rot == 3:
            return -dy, dx
        return dx, dy

    def handle_reader_direction(dx, dy):
        nonlocal reader_scroll_y
        dx, dy = rotate_reader_direction(dx, dy)
        max_s = max(0, len(reader_lines) - 1)
        
        def is_blank(idx):
            return 0 <= idx < len(reader_lines) and isinstance(reader_lines[idx], str) and reader_lines[idx] == ""
        
        if dy < 0:
            reader_scroll_y = max(0, reader_scroll_y - 1)
            while reader_scroll_y > 0 and is_blank(reader_scroll_y):
                reader_scroll_y -= 1
        elif dy > 0:
            reader_scroll_y = min(max_s, reader_scroll_y + 1)
            while reader_scroll_y < max_s and is_blank(reader_scroll_y):
                reader_scroll_y += 1
        elif dx < 0:
            step = page_items_drawn if page_items_drawn > 0 else lines_per_page
            reader_scroll_y = max(0, reader_scroll_y - step)
            while reader_scroll_y > 0 and is_blank(reader_scroll_y):
                reader_scroll_y -= 1
        elif dx > 0:
            step = page_items_drawn if page_items_drawn > 0 else lines_per_page
            reader_scroll_y = min(max_s, reader_scroll_y + step)
            while reader_scroll_y < max_s and is_blank(reader_scroll_y):
                reader_scroll_y += 1
    
    space_width = 12

    def recalculate_layout(only_metrics=False):
        nonlocal lines_per_page, line_height, font_medium, reader_lines, chapter_offsets, space_width
        reader_w, reader_h = get_reader_view_size()
        line_height = max(16, int(current_font_size * line_spacing_mult))
        lines_per_page = max(1, (reader_h - 105) // line_height)
        
        if only_metrics:
            return

        if font_medium:
            sdlttf.TTF_CloseFont(font_medium)
        font_medium = sdlttf.TTF_OpenFont(reading_font_bytes, current_font_size)
        
        # Fast character width measurement
        w = ctypes.c_int()
        h = ctypes.c_int()
        char_widths = {}
        
        # Pre-measure common characters to eliminate CTypes FFI overhead during paragraph wrapping
        common_chars = " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~" \
                       "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ" \
                       "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ" \
                       "“”‘’…—–·•«»"
        for ch in common_chars:
            sdlttf.TTF_SizeUTF8(font_medium, ch.encode('utf-8', errors='replace'), ctypes.byref(w), ctypes.byref(h))
            char_widths[ch] = w.value
            
        def get_w(ch):
            if ch not in char_widths:
                sdlttf.TTF_SizeUTF8(font_medium, ch.encode('utf-8', errors='replace'), ctypes.byref(w), ctypes.byref(h))
                char_widths[ch] = w.value
            return char_widths[ch]
            
        def get_word_w(word_str):
            return sum(get_w(c) for c in word_str)
            
        base_space_w = get_w(" ")
        space_width = max(2, int(base_space_w * word_spacing_mult))
        indent_width = space_width * 3
        max_line_width = max(100, reader_w - (margin_side * 2))
        
        reader_lines = []
        chapter_offsets = []
        
        for title, text in raw_chapters:
            chapter_offsets.append((title, len(reader_lines)))
            for paragraph in text.split('\n'):
                paragraph = paragraph.replace('\t', '    ').strip()
                if not paragraph:
                    reader_lines.append("")
                    continue
                
                if paragraph.startswith("[[INLINE_IMAGE:") and paragraph.endswith("]]"):
                    img_src = paragraph[len("[[INLINE_IMAGE:"): -2].strip()
                    reader_lines.append({"type": "image", "src": img_src})
                    continue
                
                if paragraph.startswith("[[INLINE_FOOTNOTE:") and paragraph.endswith("]]"):
                    inner = paragraph[len("[[INLINE_FOOTNOTE:"): -2]
                    marker = "(*)"
                    note_text = inner
                    if "|" in inner:
                        marker, note_text = inner.split("|", 1)
                    
                    f_words = note_text.split(' ')
                    f_lines = []
                    cur_f_line = []
                    cur_f_w = 0
                    f_max_w = max_line_width - 40
                    for fw in f_words:
                        if not fw: continue
                        fww = get_word_w(fw)
                        if not cur_f_line:
                            cur_f_line.append(fw)
                            cur_f_w += fww
                        else:
                            if cur_f_w + space_width + fww <= f_max_w:
                                cur_f_line.append(fw)
                                cur_f_w += space_width + fww
                            else:
                                f_lines.append(" ".join(cur_f_line))
                                cur_f_line = [fw]
                                cur_f_w = fww
                    if cur_f_line:
                        f_lines.append(" ".join(cur_f_line))
                    
                    reader_lines.append({"type": "footnote", "marker": marker, "lines": f_lines})
                    continue
                
                # Split words
                words = paragraph.split(' ')
                current_line = []
                current_w = indent_width
                is_first_line = True
                
                for word in words:
                    if not word: continue
                    ww = get_word_w(word)
                    
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
                    
    def save_current_reader_state():
        if current_filepath:
            write_save(current_filepath, reader_scroll_y, current_font_size, line_spacing_mult, word_spacing_mult, margin_side)

    def load_book(filepath):
        nonlocal raw_chapters, reader_scroll_y, current_font_size, current_filepath, book_images, image_loader, current_image_idx, loaded_image_tex, loaded_image_idx, toc_tab, toc_img_sel_index, line_spacing_mult, word_spacing_mult, margin_side, show_typography_popup, typography_sel_idx, image_view_source
        raw_chapters = []
        book_images = []
        image_loader = None
        current_image_idx = 0
        toc_tab = 0
        toc_img_sel_index = 0
        clear_inline_image_cache()
        clear_book_img_thumb_cache()
        if loaded_image_tex:
            sdl2.SDL_DestroyTexture(loaded_image_tex)
            loaded_image_tex = None
            loaded_image_idx = -1
        
        save_data = load_save(filepath)
        reader_scroll_y = save_data.get("scroll_y", 0)
        typo = load_typography_settings()
        current_font_size = typo["font_size"]
        line_spacing_mult = float(typo["line_spacing"])
        word_spacing_mult = float(typo["word_spacing"])
        margin_side = int(typo["margin_side"])
        show_typography_popup = False
        typography_sel_idx = 0
        image_view_source = "reader"
        current_filepath = filepath
        
        try:
            parser = get_parser(filepath)
            book = parser.parse(filepath)
            if not book.chapters:
                return False
                
            for ch in book.chapters:
                raw_chapters.append((ch.title, ch.content))
                
            book_images = getattr(book, "images", [])
            image_loader = getattr(book, "image_loader", None)
            
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
    
    line_spacing_mult = 1.32
    word_spacing_mult = 1.0
    margin_side = 20
    show_typography_popup = False
    typography_sel_idx = 0
    image_view_source = "reader"
    
    orig_font_size = 34
    orig_line_spacing = 1.32
    orig_word_spacing = 1.0
    orig_margin_side = 20
    orig_theme_idx = 0
    
    left_axis_held = False
    last_left_axis_time = 0
    right_axis_held = False
    last_right_axis_time = 0
    
    while running:
        events = sdl2.ext.get_events()
        if len(events) > 0:
            needs_redraw = True
            
        current_ticks = sdl2.SDL_GetTicks()
        axis_up = False
        axis_down = False
        axis_left = False
        axis_right = False
        for c in controllers:
            lx = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_LEFTX)
            ly = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_LEFTY)
            rx = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_RIGHTX)
            ry = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_RIGHTY)
            ax = lx if abs(lx) >= abs(rx) else rx
            ay = ly if abs(ly) >= abs(ry) else ry

            if abs(lx) < 8000 and abs(ly) < 8000 and abs(rx) < 8000 and abs(ry) < 8000:
                left_axis_held = False
                right_axis_held = False

            if abs(ay) >= 12000 and abs(ay) >= abs(ax):
                if ay < 0:
                    axis_up = True
                else:
                    axis_down = True
            elif abs(ax) >= 12000 and abs(ax) > abs(ay):
                if ax < 0:
                    axis_left = True
                else:
                    axis_right = True

            # Dedicated Joystick Axis handling for STATE_TOC (Fast 50ms repeat rate, highly sensitive)
            if state == STATE_TOC:
                if not left_axis_held or (current_ticks - last_left_axis_time > 50):
                    if abs(ay) >= 12000 and abs(ay) >= abs(ax):
                        if toc_tab == 0:
                            # Tab 0: Chapter List (Up/Down 1 item)
                            if len(chapter_offsets) > 0:
                                if ay < 0: # Up
                                    toc_sel_index = (toc_sel_index - 1) % len(chapter_offsets)
                                else: # Down
                                    toc_sel_index = (toc_sel_index + 1) % len(chapter_offsets)
                                needs_redraw = True
                        else:
                            # Tab 1: Images Grid 2x4 (Up/Down jump row 4 items)
                            img_cols = 4
                            total_imgs = len(book_images)
                            if total_imgs > 0:
                                if ay < 0: # Up
                                    if toc_img_sel_index >= img_cols:
                                        toc_img_sel_index -= img_cols
                                    else:
                                        toc_img_sel_index = 0
                                else: # Down
                                    if toc_img_sel_index + img_cols < total_imgs:
                                        toc_img_sel_index += img_cols
                                    else:
                                        toc_img_sel_index = total_imgs - 1
                                needs_redraw = True
                        left_axis_held = True
                        last_left_axis_time = current_ticks
                        break
                    elif abs(ax) >= 12000 and abs(ax) > abs(ay):
                        if toc_tab == 0:
                            # Tab 0: Jump 8 chapters
                            if len(chapter_offsets) > 0:
                                if ax < 0: # Left
                                    toc_sel_index = max(0, toc_sel_index - visible_items)
                                else: # Right
                                    toc_sel_index = min(len(chapter_offsets) - 1, toc_sel_index + visible_items)
                                needs_redraw = True
                        else:
                            # Tab 1: Image Left/Right 1 item
                            total_imgs = len(book_images)
                            if total_imgs > 0:
                                if ax < 0: # Left
                                    toc_img_sel_index = max(0, toc_img_sel_index - 1)
                                else: # Right
                                    toc_img_sel_index = min(total_imgs - 1, toc_img_sel_index + 1)
                                needs_redraw = True
                        left_axis_held = True
                        last_left_axis_time = current_ticks
                        break

            elif state == STATE_READER and (current_ticks - last_axis_scroll > 100):
                if show_typography_popup:
                    if abs(ax) >= 15000 or abs(ay) >= 15000:
                        if abs(ay) > abs(ax):
                            if ay < 0: # Up
                                typography_sel_idx = (typography_sel_idx - 1) % 5
                            else: # Down
                                typography_sel_idx = (typography_sel_idx + 1) % 5
                        else:
                            if ax < 0: # Left
                                if typography_sel_idx == 0:
                                    current_font_size = max(20, current_font_size - 2)
                                    recalculate_layout(only_metrics=False)
                                elif typography_sel_idx == 1:
                                    line_spacing_mult = max(1.05, round(line_spacing_mult - 0.05, 2))
                                    recalculate_layout(only_metrics=True)
                                elif typography_sel_idx == 2:
                                    word_spacing_mult = max(0.6, round(word_spacing_mult - 0.1, 2))
                                    recalculate_layout(only_metrics=False)
                                elif typography_sel_idx == 3:
                                    margin_side = max(10, margin_side - 5)
                                    recalculate_layout(only_metrics=False)
                                elif typography_sel_idx == 4:
                                    theme_idx = (theme_idx - 1) % len(THEMES)
                                    write_theme_idx(theme_idx)
                                if reader_lines:
                                    reader_scroll_y = max(0, min(reader_scroll_y, len(reader_lines) - lines_per_page))
                            else: # Right
                                if typography_sel_idx == 0:
                                    current_font_size = min(60, current_font_size + 2)
                                    recalculate_layout(only_metrics=False)
                                elif typography_sel_idx == 1:
                                    line_spacing_mult = min(1.80, round(line_spacing_mult + 0.05, 2))
                                    recalculate_layout(only_metrics=True)
                                elif typography_sel_idx == 2:
                                    word_spacing_mult = min(1.6, round(word_spacing_mult + 0.1, 2))
                                    recalculate_layout(only_metrics=False)
                                elif typography_sel_idx == 3:
                                    margin_side = min(50, margin_side + 5)
                                    recalculate_layout(only_metrics=False)
                                elif typography_sel_idx == 4:
                                    theme_idx = (theme_idx + 1) % len(THEMES)
                                    write_theme_idx(theme_idx)
                                if reader_lines:
                                    reader_scroll_y = max(0, min(reader_scroll_y, len(reader_lines) - lines_per_page))
                        last_axis_scroll = current_ticks
                        needs_redraw = True
                        break
                else:
                    if abs(ax) >= 15000 or abs(ay) >= 15000:
                        if abs(ax) > abs(ay):
                            handle_reader_direction(1 if ax > 0 else -1, 0)
                        else:
                            handle_reader_direction(0, 1 if ay > 0 else -1)
                        last_axis_scroll = current_ticks
                        needs_redraw = True
                        break
            elif state == STATE_IMAGE_VIEW:
                if image_zoom > 0 and (current_ticks - last_axis_scroll > 40):
                    if abs(ax) >= 12000 or abs(ay) >= 12000:
                        image_pan_x -= int(ax / 1200)
                        image_pan_y -= int(ay / 1200)
                        last_axis_scroll = current_ticks
                        needs_redraw = True
                        break
                elif image_zoom <= 0 and (current_ticks - last_axis_scroll > 200):
                    if abs(ax) >= 15000:
                        if ax < 0: # Left
                            if len(book_images) > 0:
                                current_image_idx = (current_image_idx - 1) % len(book_images)
                                image_zoom = -1.0
                                image_pan_x = 0
                                image_pan_y = 0
                                needs_redraw = True
                        else: # Right
                            if len(book_images) > 0:
                                current_image_idx = (current_image_idx + 1) % len(book_images)
                                image_zoom = -1.0
                                image_pan_x = 0
                                image_pan_y = 0
                                needs_redraw = True
                        last_axis_scroll = current_ticks
                        break
                    
        for event in events:
            if event.type == sdl2.SDL_QUIT:
                if state in (STATE_READER, STATE_TOC, STATE_IMAGE_VIEW):
                    save_current_reader_state()
                running = False
            elif event.type == sdl2.SDL_KEYDOWN:
                if event.key.keysym.sym == sdl2.SDLK_ESCAPE:
                    if state in (STATE_READER, STATE_TOC, STATE_IMAGE_VIEW):
                        save_current_reader_state()
                    running = False
            elif event.type == sdl2.SDL_CONTROLLERAXISMOTION:
                axis = event.caxis.axis
                val = event.caxis.value
                if axis == sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT:
                    if val > 16000:
                        if not l2_pressed:
                            l2_pressed = True
                            if state == STATE_READER:
                                if show_typography_popup:
                                    current_font_size = orig_font_size
                                    line_spacing_mult = orig_line_spacing
                                    word_spacing_mult = orig_word_spacing
                                    margin_side = orig_margin_side
                                    theme_idx = orig_theme_idx
                                    write_theme_idx(theme_idx)
                                    recalculate_layout()
                                    show_typography_popup = False
                                state = STATE_TOC
                                toc_tab = 0
                                toc_sel_index = 0
                                for idx, (ch_title, ch_line) in enumerate(chapter_offsets):
                                    if ch_line <= reader_scroll_y:
                                        toc_sel_index = idx
                                    else:
                                        break
                                needs_redraw = True
                            elif state in (STATE_TOC, STATE_IMAGE_VIEW):
                                if state == STATE_IMAGE_VIEW and image_view_source == "toc":
                                    state = STATE_TOC
                                    toc_tab = 1
                                    toc_img_sel_index = current_image_idx
                                else:
                                    state = STATE_READER
                                needs_redraw = True
                    elif val < 8000:
                        l2_pressed = False
                elif axis == sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT:
                    if val > 16000:
                        if not r2_pressed:
                            r2_pressed = True
                            if state == STATE_READER:
                                if show_typography_popup:
                                    # Cancel & Revert
                                    current_font_size = orig_font_size
                                    line_spacing_mult = orig_line_spacing
                                    word_spacing_mult = orig_word_spacing
                                    margin_side = orig_margin_side
                                    theme_idx = orig_theme_idx
                                    write_theme_idx(theme_idx)
                                    recalculate_layout()
                                    show_typography_popup = False
                                else:
                                    # Open & Snapshot
                                    orig_font_size = current_font_size
                                    orig_line_spacing = line_spacing_mult
                                    orig_word_spacing = word_spacing_mult
                                    orig_margin_side = margin_side
                                    orig_theme_idx = theme_idx
                                    typography_sel_idx = 0
                                    show_typography_popup = True
                                needs_redraw = True
                    elif val < 8000:
                        r2_pressed = False
                    
            elif event.type == sdl2.SDL_CONTROLLERBUTTONUP:
                btn = event.cbutton.button
                if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                    dpad_up_held = False
                elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                    dpad_down_held = False
                elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                    dpad_left_held = False
                elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
                    dpad_right_held = False
            elif event.type == sdl2.SDL_CONTROLLERBUTTONDOWN:
                btn = event.cbutton.button
                if state == STATE_QUIT_CONFIRM:
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A (Confirm)
                        if state_before_quit in (STATE_READER, STATE_TOC, STATE_IMAGE_VIEW):
                            save_current_reader_state()
                        running = False
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B (Cancel)
                        state = state_before_quit
                elif btn == sdl2.SDL_CONTROLLER_BUTTON_START:
                    state_before_quit = state
                    state = STATE_QUIT_CONFIRM
                    
                elif state == STATE_BROWSE:
                    list_items = [{"name": "..", "is_dir": True}] if current_path != base_path else []
                    list_items += [{"name": f, "is_dir": True} for f in folders]
                    list_items += [{"name": f, "is_dir": False} for f in files]
                    
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                        dpad_up_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                        dpad_down_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                        dpad_left_held = True
                        dpad_horiz_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
                        dpad_right_held = True
                        dpad_horiz_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: # L: Prev Theme
                        theme_idx = (theme_idx - 1) % len(THEMES)
                        write_theme_idx(theme_idx)
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: # R: Next Theme
                        theme_idx = (theme_idx + 1) % len(THEMES)
                        write_theme_idx(theme_idx)
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A - Enter
                        if len(list_items) > 0:
                            item = list_items[sel_index]
                            if item["name"] == "..":
                                clear_cover_cache()
                                current_path = os.path.dirname(current_path)
                                folders, files = get_directory_contents(current_path)
                                sel_index = 0
                                scroll_y = 0
                                prewarm_covers(_make_list_items_for_path(folders, files, current_path, base_path), current_path)
                                needs_redraw = True
                            elif item["is_dir"]:
                                clear_cover_cache()
                                current_path = os.path.join(current_path, item["name"])
                                folders, files = get_directory_contents(current_path)
                                sel_index = 0
                                scroll_y = 0
                                prewarm_covers(_make_list_items_for_path(folders, files, current_path, base_path), current_path)
                                needs_redraw = True
                            else:
                                filepath = os.path.join(current_path, item["name"])
                                if load_book(filepath):
                                    state = STATE_READER
                                    needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B - Toggle View Mode
                        library_view_mode = "grid" if library_view_mode == "list" else "list"
                        write_library_view(library_view_mode)
                        if library_view_mode == "grid":
                            scroll_y = (sel_index // 8) * 8
                        else:
                            if sel_index >= scroll_y + 8:
                                scroll_y = max(0, sel_index - 7)
                            elif sel_index < scroll_y:
                                scroll_y = sel_index
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_BACK: # SELECT - Info Dialog
                        state = STATE_ABOUT
                        needs_redraw = True
                        
                elif state == STATE_ABOUT:
                    if btn in (sdl2.SDL_CONTROLLER_BUTTON_A, sdl2.SDL_CONTROLLER_BUTTON_B, sdl2.SDL_CONTROLLER_BUTTON_BACK):
                        state = STATE_BROWSE
                        needs_redraw = True

                elif state == STATE_READER:
                    if show_typography_popup:
                        if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                            typography_sel_idx = (typography_sel_idx - 1) % 5
                            needs_redraw = True
                        elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                            typography_sel_idx = (typography_sel_idx + 1) % 5
                            needs_redraw = True
                        elif btn in (sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT, sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER):
                            if typography_sel_idx == 0:
                                current_font_size = max(20, current_font_size - 2)
                                recalculate_layout(only_metrics=False)
                            elif typography_sel_idx == 1:
                                line_spacing_mult = max(1.05, round(line_spacing_mult - 0.05, 2))
                                recalculate_layout(only_metrics=True)
                            elif typography_sel_idx == 2:
                                word_spacing_mult = max(0.6, round(word_spacing_mult - 0.1, 2))
                                recalculate_layout(only_metrics=False)
                            elif typography_sel_idx == 3:
                                margin_side = max(10, margin_side - 5)
                                recalculate_layout(only_metrics=False)
                            elif typography_sel_idx == 4:
                                theme_idx = (theme_idx - 1) % len(THEMES)
                                write_theme_idx(theme_idx)
                            if reader_lines:
                                reader_scroll_y = max(0, min(reader_scroll_y, len(reader_lines) - lines_per_page))
                            needs_redraw = True
                        elif btn in (sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT, sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER):
                            if typography_sel_idx == 0:
                                current_font_size = min(60, current_font_size + 2)
                                recalculate_layout(only_metrics=False)
                            elif typography_sel_idx == 1:
                                line_spacing_mult = min(1.80, round(line_spacing_mult + 0.05, 2))
                                recalculate_layout(only_metrics=True)
                            elif typography_sel_idx == 2:
                                word_spacing_mult = min(1.6, round(word_spacing_mult + 0.1, 2))
                                recalculate_layout(only_metrics=False)
                            elif typography_sel_idx == 3:
                                margin_side = min(50, margin_side + 5)
                                recalculate_layout(only_metrics=False)
                            elif typography_sel_idx == 4:
                                theme_idx = (theme_idx + 1) % len(THEMES)
                                write_theme_idx(theme_idx)
                            if reader_lines:
                                reader_scroll_y = max(0, min(reader_scroll_y, len(reader_lines) - lines_per_page))
                            needs_redraw = True
                        elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A: Save
                            write_typography_settings(current_font_size, line_spacing_mult, word_spacing_mult, margin_side)
                            write_theme_idx(theme_idx)
                            show_typography_popup = False
                            save_current_reader_state()
                            toast_msg = "Saved Typography for All Books"
                            toast_timer = current_ticks
                            needs_redraw = True
                        elif btn in (sdl2.SDL_CONTROLLER_BUTTON_A, sdl2.SDL_CONTROLLER_BUTTON_BACK): # Physical B / Select: Cancel
                            current_font_size = orig_font_size
                            line_spacing_mult = orig_line_spacing
                            word_spacing_mult = orig_word_spacing
                            margin_side = orig_margin_side
                            theme_idx = orig_theme_idx
                            write_theme_idx(theme_idx)
                            recalculate_layout()
                            show_typography_popup = False
                            needs_redraw = True
                    else:
                        if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                            handle_reader_direction(0, -1)
                        elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                            handle_reader_direction(0, 1)
                        elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                            handle_reader_direction(-1, 0)
                        elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
                            handle_reader_direction(1, 0)
                        elif btn == sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: # Decrease Font
                            current_font_size = max(20, current_font_size - 2)
                            write_typography_settings(current_font_size, line_spacing_mult, word_spacing_mult, margin_side)
                            recalculate_layout()
                            if reader_lines:
                                reader_scroll_y = max(0, min(reader_scroll_y, len(reader_lines) - lines_per_page))
                        elif btn == sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: # Increase Font
                            current_font_size = min(60, current_font_size + 2)
                            write_typography_settings(current_font_size, line_spacing_mult, word_spacing_mult, margin_side)
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
                        elif btn == sdl2.SDL_CONTROLLER_BUTTON_BACK: # SELECT - Return to Library
                            save_current_reader_state()
                            state = STATE_BROWSE
                            needs_redraw = True
                        elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B - Open TOC
                            state = STATE_TOC
                            toc_tab = 0
                            toc_sel_index = 0
                            for idx, (ch_title, ch_line) in enumerate(chapter_offsets):
                                if ch_line <= reader_scroll_y:
                                    toc_sel_index = idx
                                else:
                                    break
                            needs_redraw = True
                        elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A - Toggle HUD
                            show_hud = not show_hud
                            needs_redraw = True
                        
                elif state == STATE_TOC:
                    if btn in (sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER, sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER):
                        if len(book_images) > 0:
                            toc_tab = 1 - toc_tab
                            needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                        dpad_up_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                        dpad_down_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                        dpad_left_held = True
                        dpad_horiz_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
                        dpad_right_held = True
                        dpad_horiz_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A - Select Chapter or Jump to Image
                        if toc_tab == 0:
                            if len(chapter_offsets) > 0:
                                reader_scroll_y = chapter_offsets[toc_sel_index][1]
                            state = STATE_READER
                        else:
                            # Tab 1: Jump directly to image position in reading mode
                            if len(book_images) > 0:
                                target_img = book_images[toc_img_sel_index]
                                target_line = find_image_reader_line(target_img)
                                if target_line is not None:
                                    reader_scroll_y = max(0, min(target_line, len(reader_lines) - 1))
                            state = STATE_READER
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_Y: # Physical X - View Image Fullscreen
                        if toc_tab == 1 and len(book_images) > 0:
                            current_image_idx = toc_img_sel_index
                            image_view_source = "toc"
                            state = STATE_IMAGE_VIEW
                            image_zoom = -1.0
                            image_pan_x = 0
                            image_pan_y = 0
                            needs_redraw = True
                    elif btn in (sdl2.SDL_CONTROLLER_BUTTON_A, sdl2.SDL_CONTROLLER_BUTTON_BACK): # Physical B or Select - Back to Reader
                        state = STATE_READER
                        needs_redraw = True

                elif state == STATE_IMAGE_VIEW:
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT or btn == sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER:
                        if len(book_images) > 0:
                            current_image_idx = (current_image_idx - 1) % len(book_images)
                            image_zoom = -1.0
                            image_pan_x = 0
                            image_pan_y = 0
                            needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT or btn == sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER:
                        if len(book_images) > 0:
                            current_image_idx = (current_image_idx + 1) % len(book_images)
                            image_zoom = -1.0
                            image_pan_x = 0
                            image_pan_y = 0
                            needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_X: # Physical Y - Zoom Toggle
                        if image_zoom <= 0:
                            image_zoom = 1.5
                        elif image_zoom == 1.5:
                            image_zoom = 2.0
                        else:
                            image_zoom = -1.0
                        image_pan_x = 0
                        image_pan_y = 0
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_Y: # Physical X - Rotate
                        image_rotation = (image_rotation + 1) % 4
                        image_zoom = -1.0
                        image_pan_x = 0
                        image_pan_y = 0
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A - Toggle HUD
                        show_hud = not show_hud
                    elif btn in (sdl2.SDL_CONTROLLER_BUTTON_A, sdl2.SDL_CONTROLLER_BUTTON_BACK): # Physical B or Select
                        if image_view_source == "toc":
                            state = STATE_TOC
                            toc_tab = 1
                            toc_img_sel_index = current_image_idx
                        else:
                            state = STATE_READER
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                        if image_zoom > 0:
                            image_pan_y += 60
                            needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                        if image_zoom > 0:
                            image_pan_y -= 60
                            needs_redraw = True

        # Key repeat logic for library (exact Files app behavior)
        is_up = dpad_up_held or axis_up
        is_down = dpad_down_held or axis_down
        is_left = dpad_left_held or axis_left
        is_right = dpad_right_held or axis_right
        
        if state == STATE_BROWSE:
            list_items = [{"name": "..", "is_dir": True}] if current_path != base_path else []
            list_items += [{"name": f, "is_dir": True} for f in folders]
            list_items += [{"name": f, "is_dir": False} for f in files]
            library_visible_items = 8
            
            if library_view_mode == "grid":
                grid_cols = 4
                if is_up:
                    if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                        if len(list_items) > 0:
                            if sel_index >= grid_cols:
                                sel_index -= grid_cols
                            else:
                                sel_index = 0
                            scroll_y = (sel_index // 8) * 8
                        needs_redraw = True
                    dpad_timer += 1
                elif is_down:
                    if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                        if len(list_items) > 0:
                            if sel_index + grid_cols < len(list_items):
                                sel_index += grid_cols
                            else:
                                sel_index = len(list_items) - 1
                            scroll_y = (sel_index // 8) * 8
                        needs_redraw = True
                    dpad_timer += 1
                else:
                    dpad_timer = 0

                if is_left:
                    if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 4 == 0):
                        if len(list_items) > 0:
                            sel_index = max(0, sel_index - 1)
                            scroll_y = (sel_index // 8) * 8
                        needs_redraw = True
                    dpad_horiz_timer += 1
                elif is_right:
                    if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 4 == 0):
                        if len(list_items) > 0:
                            sel_index = min(len(list_items) - 1, sel_index + 1)
                            scroll_y = (sel_index // 8) * 8
                        needs_redraw = True
                    dpad_horiz_timer += 1
                else:
                    dpad_horiz_timer = 0
            else:
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

                if is_left:
                    if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 4 == 0):
                        sel_index = max(0, sel_index - library_visible_items)
                        scroll_y = max(0, scroll_y - library_visible_items)
                        needs_redraw = True
                    dpad_horiz_timer += 1
                elif is_right:
                    if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 4 == 0):
                        sel_index = min(len(list_items) - 1, sel_index + library_visible_items)
                        scroll_y = min(max(0, len(list_items) - library_visible_items), scroll_y + library_visible_items)
                        needs_redraw = True
                    dpad_horiz_timer += 1
                else:
                    dpad_horiz_timer = 0

            if prev_sel_index != sel_index:
                sel_time = current_ticks
                prev_sel_index = sel_index

        elif state == STATE_TOC:
            if toc_tab == 0:
                # Tab 0: Chapters List (D-Pad)
                if dpad_up_held:
                    if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                        if len(chapter_offsets) > 0:
                            toc_sel_index = (toc_sel_index - 1) % len(chapter_offsets)
                        needs_redraw = True
                    dpad_timer += 1
                elif dpad_down_held:
                    if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                        if len(chapter_offsets) > 0:
                            toc_sel_index = (toc_sel_index + 1) % len(chapter_offsets)
                        needs_redraw = True
                    dpad_timer += 1
                else:
                    dpad_timer = 0

                if dpad_left_held:
                    if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 4 == 0):
                        if len(chapter_offsets) > 0:
                            toc_sel_index = max(0, toc_sel_index - visible_items)
                        needs_redraw = True
                    dpad_horiz_timer += 1
                elif dpad_right_held:
                    if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 4 == 0):
                        if len(chapter_offsets) > 0:
                            toc_sel_index = min(len(chapter_offsets) - 1, toc_sel_index + visible_items)
                        needs_redraw = True
                    dpad_horiz_timer += 1
                else:
                    dpad_horiz_timer = 0
            else:
                # Tab 1: Images Grid 2x4 (D-Pad)
                img_cols = 4
                total_imgs = len(book_images)
                if dpad_up_held:
                    if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                        if total_imgs > 0:
                            if toc_img_sel_index >= img_cols:
                                toc_img_sel_index -= img_cols
                            else:
                                toc_img_sel_index = 0
                        needs_redraw = True
                    dpad_timer += 1
                elif dpad_down_held:
                    if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                        if total_imgs > 0:
                            if toc_img_sel_index + img_cols < total_imgs:
                                toc_img_sel_index += img_cols
                            else:
                                toc_img_sel_index = total_imgs - 1
                        needs_redraw = True
                    dpad_timer += 1
                else:
                    dpad_timer = 0

                if dpad_left_held:
                    if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 3 == 0):
                        if total_imgs > 0:
                            toc_img_sel_index = max(0, toc_img_sel_index - 1)
                        needs_redraw = True
                    dpad_horiz_timer += 1
                elif dpad_right_held:
                    if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 3 == 0):
                        if total_imgs > 0:
                            toc_img_sel_index = min(total_imgs - 1, toc_img_sel_index + 1)
                        needs_redraw = True
                    dpad_horiz_timer += 1
                else:
                    dpad_horiz_timer = 0

        elif state != STATE_READER and state != STATE_IMAGE_VIEW:
            dpad_up_held = False
            dpad_down_held = False
            dpad_left_held = False
            dpad_right_held = False
            dpad_timer = 0
            dpad_horiz_timer = 0

        pump_cover_ready()  # promote background-loaded covers to GPU textures
        if needs_redraw:
            theme = THEMES[theme_idx]
            renderer.clear(theme["bg"])
            
            if state in (STATE_QUIT_CONFIRM, STATE_ABOUT):
                render_state = state_before_quit if state == STATE_QUIT_CONFIRM else STATE_BROWSE
            else:
                render_state = state

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

                mode_str = "[GRID]" if library_view_mode == "grid" else "[LIST]"
                book_count = f"{len(files)} BOOK" + ("" if len(files) == 1 else "S") + f"    {mode_str}"
                tex, tw, th = render_text(book_count, font_small, library_theme["secondary"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(SCREEN_W - 32 - tw, 27, tw, th))
                    sdl2.SDL_DestroyTexture(tex)

                sel_border = library_theme.get("sel_border", sdl2.ext.Color(102, 137, 181))
                sel_bg = library_theme.get("sel_bg", sdl2.ext.Color(229, 235, 241))
                sel_text = library_theme.get("sel_text", sdl2.SDL_Color(30, 30, 30, 255))
                sel_sec = library_theme.get("sel_sec", sdl2.SDL_Color(80, 80, 80, 255))
                marquee_active = False

                if library_view_mode == "grid":
                    grid_page = sel_index // 8
                    start_idx = grid_page * 8
                    end_idx = min(len(list_items), start_idx + 8)

                    col_w = 232
                    row_h = 286
                    start_x = 24
                    start_y = 96
                    gap_x = 16
                    gap_y = 16

                    for idx in range(start_idx, end_idx):
                        rel_i = idx - start_idx
                        col = rel_i % 4
                        row = rel_i // 4
                        cx = start_x + col * (col_w + gap_x)
                        cy = start_y + row * (row_h + gap_y)

                        item = list_items[idx]
                        is_sel = (idx == sel_index)

                        if is_sel:
                            renderer.fill((cx, cy, col_w, row_h), sel_border)
                            renderer.fill((cx + 2, cy + 2, col_w - 4, row_h - 4), sel_bg)
                            card_text_col = sel_text
                        else:
                            renderer.fill((cx, cy, col_w, row_h), library_theme["divider"])
                            renderer.fill((cx + 1, cy + 1, col_w - 2, row_h - 2), library_theme["header"])
                            card_text_col = library_theme["text"]

                        cover_w, cover_h = 170, 200
                        cover_x = cx + (col_w - cover_w) // 2
                        cover_y = cy + 14

                        if item["is_dir"]:
                            renderer.fill((cover_x, cover_y, cover_w, cover_h), library_theme["bg"])
                            if item["name"] == "..":
                                renderer.fill((cover_x + 50, cover_y + 80, 70, 40), library_theme["accent"])
                                renderer.fill((cover_x + 52, cover_y + 82, 66, 36), library_theme["bg"])
                                t_back, bw, bh = render_text("BACK", font_small, library_theme["accent"])
                                if t_back:
                                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, t_back, None, sdl2.SDL_Rect(cover_x + (cover_w - bw) // 2, cover_y + 90, bw, bh))
                                    sdl2.SDL_DestroyTexture(t_back)
                            else:
                                fx = cover_x + (cover_w - 90) // 2
                                fy = cover_y + 60
                                renderer.fill((fx, fy - 12, 45, 14), library_theme["accent"])
                                renderer.fill((fx, fy, 90, 65), library_theme["accent"])
                                renderer.fill((fx + 3, fy + 3, 84, 59), library_theme["bg"])
                                t_dir, dw, dh = render_text("FOLDER", font_small, library_theme["accent"])
                                if t_dir:
                                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, t_dir, None, sdl2.SDL_Rect(cover_x + (cover_w - dw) // 2, fy + 20, dw, dh))
                                    sdl2.SDL_DestroyTexture(t_dir)
                        else:
                            filepath = os.path.join(current_path, item["name"])
                            ext = os.path.splitext(item["name"])[1].lower()
                            c_tex, orig_w, orig_h = get_cover_texture(filepath)
                            if c_tex and orig_w > 0 and orig_h > 0:
                                scale = min(cover_w / float(orig_w), cover_h / float(orig_h))
                                dw = int(orig_w * scale)
                                dh = int(orig_h * scale)
                                tx = cover_x + (cover_w - dw) // 2
                                ty = cover_y + (cover_h - dh) // 2
                                renderer.fill((tx - 1, ty - 1, dw + 2, dh + 2), library_theme["divider"])
                                sdl2.SDL_RenderCopy(renderer.sdlrenderer, c_tex, None, sdl2.SDL_Rect(tx, ty, dw, dh))
                            else:
                                renderer.fill((cover_x, cover_y, cover_w, cover_h), library_theme["bg"])
                                renderer.fill((cover_x + 2, cover_y + 2, cover_w - 4, cover_h - 4), library_theme["header"])
                                renderer.fill((cover_x + 14, cover_y + 2, 2, cover_h - 4), library_theme["divider"])
                                draw_book_icon(renderer, cover_x + (cover_w - 15) // 2 + 5, cover_y + 65, library_theme["accent"], library_theme["header"])
                                badge_str = ext.upper().lstrip('.') if ext else "BOOK"
                                t_badge, bw, bh = render_text(f"[ {badge_str} ]", font_small, library_theme["secondary"])
                                if t_badge:
                                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, t_badge, None, sdl2.SDL_Rect(cover_x + (cover_w - bw) // 2 + 5, cover_y + 115, bw, bh))
                                    sdl2.SDL_DestroyTexture(t_badge)

                        title, _ = get_book_display_metadata(item["name"]) if not item["is_dir"] else (item["name"], "")
                        sdlttf.TTF_SetFontStyle(font_small, sdlttf.TTF_STYLE_BOLD if is_sel else sdlttf.TTF_STYLE_NORMAL)
                        tex_title, tw, th = render_text(title, font_small, card_text_col)
                        sdlttf.TTF_SetFontStyle(font_small, sdlttf.TTF_STYLE_NORMAL)
                        if tex_title:
                            title_y = cy + 236
                            max_title_w = col_w - 16
                            if tw > max_title_w and is_sel:
                                marquee_active = True
                                overflow = tw - max_title_w
                                dt = current_ticks - sel_time
                                pause_start = 1200
                                speed = 0.04
                                scroll_time = int(overflow / speed)
                                pause_end = 1200
                                total_cycle = pause_start + scroll_time + pause_end + scroll_time
                                cycle_pos = dt % total_cycle
                                if cycle_pos < pause_start:
                                    offset = 0
                                elif cycle_pos < pause_start + scroll_time:
                                    offset = int((cycle_pos - pause_start) * speed)
                                elif cycle_pos < pause_start + scroll_time + pause_end:
                                    offset = overflow
                                else:
                                    back_t = cycle_pos - (pause_start + scroll_time + pause_end)
                                    offset = overflow - int(back_t * speed)
                                offset = max(0, min(overflow, offset))
                                src = sdl2.SDL_Rect(offset, 0, max_title_w, th)
                                dst = sdl2.SDL_Rect(cx + 8, title_y, max_title_w, th)
                                sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_title, src, dst)
                            else:
                                dw = min(tw, max_title_w)
                                tx = cx + (col_w - dw) // 2
                                src = sdl2.SDL_Rect(0, 0, dw, th)
                                dst = sdl2.SDL_Rect(tx, title_y, dw, th)
                                sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_title, src, dst)
                            sdl2.SDL_DestroyTexture(tex_title)
                else:
                    library_visible_items = 8
                    start_idx = scroll_y
                    end_idx = min(len(list_items), start_idx + library_visible_items)

                    def draw_label(tex, tw, th, y_pos, is_sel):
                        nonlocal marquee_active
                        max_w = SCREEN_W - 110
                        overflow = tw - max_w
                        if overflow > 0 and is_sel:
                            marquee_active = True
                            dt = current_ticks - sel_time
                            pause_start = 1200
                            speed = 0.04
                            scroll_time = int(overflow / speed)
                            pause_end = 1200
                            total_cycle = pause_start + scroll_time + pause_end + scroll_time
                            cycle_pos = dt % total_cycle
                            if cycle_pos < pause_start:
                                offset = 0
                            elif cycle_pos < pause_start + scroll_time:
                                offset = int((cycle_pos - pause_start) * speed)
                            elif cycle_pos < pause_start + scroll_time + pause_end:
                                offset = overflow
                            else:
                                back_t = cycle_pos - (pause_start + scroll_time + pause_end)
                                offset = overflow - int(back_t * speed)
                            offset = max(0, min(overflow, offset))
                            src = sdl2.SDL_Rect(offset, 0, max_w, th)
                            dst = sdl2.SDL_Rect(78, y_pos, max_w, th)
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, src, dst)
                        else:
                            draw_w = min(tw, max_w)
                            src = sdl2.SDL_Rect(0, 0, draw_w, th)
                            dst = sdl2.SDL_Rect(78, y_pos, draw_w, th)
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, src, dst)

                    y_start = 86
                    row_h = 74
                    for i in range(start_idx, end_idx):
                        item = list_items[i]
                        iy = y_start + (i - start_idx) * row_h
                        
                        text_col = sel_text if i == sel_index else library_theme["text"]
                        
                        if i == sel_index:
                            sel_x, sel_y, sel_w, sel_h = 20, iy, SCREEN_W - 40, 68
                            renderer.fill((sel_x, sel_y, sel_w, sel_h), sel_border)
                            renderer.fill((sel_x + 2, sel_y + 2, sel_w - 4, sel_h - 4), sel_bg)

                        if item["is_dir"]:
                            renderer.fill((44, iy + 21, 9, 4), library_theme["accent"])
                            renderer.fill((42, iy + 24, 18, 14), library_theme["accent"])
                            tex, tw, th = render_text(item["name"], font_ui_medium, text_col)
                            if tex:
                                title_y = iy + 16
                                draw_label(tex, tw, th, title_y, i == sel_index)
                                sdl2.SDL_DestroyTexture(tex)
                        else:
                            title, _ = get_book_display_metadata(item["name"])
                            icon_bg = sel_bg if i == sel_index else library_theme["bg"]
                            draw_book_icon(renderer, 42, iy + 23, library_theme["accent"], icon_bg)
                            sdlttf.TTF_SetFontStyle(font_ui_medium, sdlttf.TTF_STYLE_BOLD)
                            tex, tw, th = render_text(title, font_ui_medium, text_col)
                            sdlttf.TTF_SetFontStyle(font_ui_medium, sdlttf.TTF_STYLE_NORMAL)
                            if tex:
                                title_y = iy + 16
                                draw_label(tex, tw, th, title_y, i == sel_index)
                                sdl2.SDL_DestroyTexture(tex)

                renderer.fill((0, SCREEN_H - 58, SCREEN_W, 1), library_theme["divider"])
                footer = f"A: Open   B: {'List' if library_view_mode == 'grid' else 'Grid'}   L/R: Theme   SELECT: Info   [START] Exit"
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
                max_content_w = max(100, reader_w - (margin_side * 2))
                i = reader_scroll_y
                while i < len(reader_lines):
                    item = reader_lines[i]
                    if isinstance(item, dict) and item.get("type") == "image":
                        cached = get_inline_image(item["src"], max_content_w, reader_h - 110)
                        if cached:
                            tex = cached["tex"]
                            iw = cached["w"]
                            ih = cached["h"]
                            step = ih + 12
                            if y_pos > 50 and (y_pos + step > max_y):
                                break
                            draw_x = margin_side + (max_content_w - iw) // 2
                            draw_y = y_pos
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(draw_x, draw_y, iw, ih))
                            y_pos += step
                        else:
                            fn = os.path.basename(item["src"])
                            tex, tw, th = render_text(f"[ {fn} ]", font_small, theme["sel"])
                            if tex:
                                sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(margin_side, y_pos, tw, th))
                                sdl2.SDL_DestroyTexture(tex)
                            y_pos += line_height
                    elif isinstance(item, dict) and item.get("type") == "footnote":
                        marker = item.get("marker", "(*)")
                        f_lines = item.get("lines", [])
                        f_pad_x = 18
                        f_pad_y = 10
                        f_line_h = int(line_height * 0.85)
                        box_w = max_content_w
                        box_h = f_pad_y * 2 + (len(f_lines) + 1) * f_line_h
                        step = box_h + 14
                        if y_pos > 50 and (y_pos + step > max_y):
                            break
                        
                        # Glassmorphic Callout Box
                        renderer.fill((margin_side, y_pos, box_w, box_h), theme.get("header", theme["bg"]))
                        renderer.fill((margin_side, y_pos, 4, box_h), theme["sel"])
                        divider_col = theme.get("divider", theme["header"])
                        renderer.fill((margin_side, y_pos, box_w, 1), divider_col)
                        renderer.fill((margin_side, y_pos + box_h - 1, box_w, 1), divider_col)
                        renderer.fill((margin_side + box_w - 1, y_pos, 1, box_h), divider_col)
                        
                        cur_fy = y_pos + f_pad_y
                        tex_title, tw, th = render_text(f"💡 Footnote {marker}:", font_small, theme["sel"])
                        if tex_title:
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_title, None, sdl2.SDL_Rect(margin_side + f_pad_x, cur_fy, min(tw, box_w - f_pad_x * 2), th))
                            sdl2.SDL_DestroyTexture(tex_title)
                        cur_fy += f_line_h
                        
                        for fl in f_lines:
                            tex_fl, fw, fh = render_text(fl, font_small, theme.get("secondary", theme["text"]))
                            if tex_fl:
                                sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_fl, None, sdl2.SDL_Rect(margin_side + f_pad_x, cur_fy, min(fw, box_w - f_pad_x * 2), fh))
                                sdl2.SDL_DestroyTexture(tex_fl)
                            cur_fy += f_line_h
                            
                        y_pos += step
                    elif item == "":
                        step = max(2, line_height // 6)
                        if y_pos + step > max_y:
                            break
                        y_pos += step
                    else:
                        line = item
                        step = line_height
                        if y_pos + step > max_y:
                            break
                        if word_spacing_mult == 1.0:
                            tex, tw, th = render_text(line, font_medium, theme["text"])
                            if tex:
                                sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(margin_side, y_pos, min(tw, max_content_w), th))
                                sdl2.SDL_DestroyTexture(tex)
                        else:
                            # Render word-by-word with true custom word spacing
                            cur_x = margin_side
                            words = line.split(' ')
                            for w_item in words:
                                if not w_item:
                                    cur_x += space_width
                                    continue
                                tex_w, tw, th = render_text(w_item, font_medium, theme["text"])
                                if tex_w:
                                    if cur_x + tw <= margin_side + max_content_w:
                                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_w, None, sdl2.SDL_Rect(cur_x, y_pos, tw, th))
                                    sdl2.SDL_DestroyTexture(tex_w)
                                cur_x += tw + space_width
                        y_pos += step
                    i += 1
                
                page_items_drawn = max(1, i - reader_scroll_y)
                
                # HUD Elements
                if show_hud:
                    if len(reader_lines) > 0:
                        progress = min(1.0, reader_scroll_y / max(1, len(reader_lines) - lines_per_page))
                        bar_w = int((reader_w - (margin_side * 2)) * progress)
                        renderer.fill((margin_side, reader_h - 10, reader_w - (margin_side * 2), 5), theme["sel"])
                        renderer.fill((margin_side, reader_h - 10, bar_w, 5), theme["text"])
                    
                    curr_chap = "Chapter 1"
                    for ch_title, ch_line in chapter_offsets:
                        if ch_line <= reader_scroll_y:
                            curr_chap = ch_title
                        else:
                            break
                    
                    total_pages = max(1, len(reader_lines) // lines_per_page + 1)
                    curr_page = reader_scroll_y // lines_per_page + 1
                    
                    book_title, _ = get_book_display_metadata(os.path.basename(current_filepath))
                    if curr_chap:
                        hud_top = f"{book_title} - {curr_chap} - Page {curr_page}/{total_pages}"
                    else:
                        hud_top = f"{book_title} - Page {curr_page}/{total_pages}"
                    tex, tw, th = render_text(hud_top, font_small, theme["text"])
                    if tex:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(margin_side, 15, min(tw, reader_w - (margin_side * 2)), th))
                        sdl2.SDL_DestroyTexture(tex)
                    
                    footer = f"R2: Typography | Size: {current_font_size} | L/R: Aa | X: Rotate | Y: Theme | B/L2: TOC | SELECT: LIB"
                    tex, tw, th = render_text(footer, font_small, theme["text"])
                    if tex:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(margin_side, reader_h - 45, min(tw, reader_w - (margin_side * 2)), th))
                        sdl2.SDL_DestroyTexture(tex)

                if drawing_rotated:
                    sdl2.SDL_SetRenderTarget(renderer.sdlrenderer, None)
                    renderer.clear(theme["bg"])
                    src_rect = sdl2.SDL_Rect(0, 0, reader_w, reader_h)
                    dst_rect = sdl2.SDL_Rect((SCREEN_W - reader_w) // 2, (SCREEN_H - reader_h) // 2, reader_w, reader_h)
                    sdl2.SDL_RenderCopyEx(renderer.sdlrenderer, target, src_rect, dst_rect, reader_angle, None, sdl2.SDL_FLIP_NONE)

            elif render_state == STATE_TOC:
                renderer.fill((0, 0, SCREEN_W, 60), theme["header"])
                if len(book_images) > 0:
                    tab0 = f"[ CHAPTERS ({len(chapter_offsets)}) ]" if toc_tab == 0 else f"CHAPTERS ({len(chapter_offsets)})"
                    tab1 = f"[ IMAGES ({len(book_images)}) ]" if toc_tab == 1 else f"IMAGES ({len(book_images)})"
                    toc_title = f"{tab0}    |    {tab1}  (L1/R1)"
                else:
                    toc_title = "CONTENTS"
                tex, tw, th = render_text(toc_title, font_medium, theme["text"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(SCREEN_W//2 - tw//2, 10, min(tw, SCREEN_W-40), th))
                    sdl2.SDL_DestroyTexture(tex)
                    
                if toc_tab == 0:
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
                            
                    footer = "D-Pad / Sticks: Move   |   A: Select Chapter   |   L1/R1: Switch Tab   |   B: Cancel"
                else:
                    total_imgs = len(book_images)
                    items_per_page = 8
                    cols = 4
                    start_page = (toc_img_sel_index // items_per_page) * items_per_page
                    end_page = min(total_imgs, start_page + items_per_page)

                    margin_x = 44
                    gap_x = 24
                    thumb_w = 216
                    thumb_h = 260
                    gap_y = 40
                    y_start = 80

                    for idx in range(start_page, end_page):
                        slot = idx - start_page
                        row = slot // cols
                        col = slot % cols
                        cell_x = margin_x + col * (thumb_w + gap_x)
                        cell_y = y_start + row * (thumb_h + gap_y)
                        is_sel = (idx == toc_img_sel_index)

                        # Card Background
                        renderer.fill((cell_x, cell_y, thumb_w, thumb_h), theme["header"])

                        # Render Thumbnail image
                        img_path = book_images[idx]
                        thumb_info = get_book_img_thumbnail(img_path, thumb_w - 8, thumb_h - 8)
                        if thumb_info and thumb_info["tex"]:
                            tw = thumb_info["w"]
                            th = thumb_info["h"]
                            dst_x = cell_x + (thumb_w - tw) // 2
                            dst_y = cell_y + (thumb_h - th) // 2
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, thumb_info["tex"], None, sdl2.SDL_Rect(dst_x, dst_y, tw, th))
                        else:
                            # Placeholder card
                            tex_ph, pw, ph = render_text(f"Img {idx + 1}", font_small, theme.get("secondary", theme["text"]))
                            if tex_ph:
                                sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_ph, None, sdl2.SDL_Rect(cell_x + (thumb_w - pw)//2, cell_y + (thumb_h - ph)//2, pw, ph))
                                sdl2.SDL_DestroyTexture(tex_ph)

                        # Selection border
                        if is_sel:
                            renderer.fill((cell_x - 3, cell_y - 3, thumb_w + 6, 3), theme["sel"])
                            renderer.fill((cell_x - 3, cell_y + thumb_h, thumb_w + 6, 3), theme["sel"])
                            renderer.fill((cell_x - 3, cell_y, 3, thumb_h), theme["sel"])
                            renderer.fill((cell_x + thumb_w, cell_y, 3, thumb_h), theme["sel"])
                        else:
                            renderer.fill((cell_x - 1, cell_y - 1, thumb_w + 2, 1), theme.get("divider", theme["header"]))
                            renderer.fill((cell_x - 1, cell_y + thumb_h, thumb_w + 2, 1), theme.get("divider", theme["header"]))
                            renderer.fill((cell_x - 1, cell_y, 1, thumb_h), theme.get("divider", theme["header"]))
                            renderer.fill((cell_x + thumb_w, cell_y, 1, thumb_h), theme.get("divider", theme["header"]))

                        # Label below thumbnail
                        img_fn = os.path.basename(img_path)
                        if len(img_fn) > 18:
                            img_fn = img_fn[:15] + "..."
                        lbl_text = f"{idx + 1}. {img_fn}"
                        lbl_color = theme["sel"] if is_sel else theme["text"]
                        tex_lbl, lw, lh = render_text(lbl_text, font_small, lbl_color)
                        if tex_lbl:
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_lbl, None, sdl2.SDL_Rect(cell_x + (thumb_w - min(lw, thumb_w))//2, cell_y + thumb_h + 6, min(lw, thumb_w), lh))
                            sdl2.SDL_DestroyTexture(tex_lbl)

                    footer = "D-Pad / Sticks: Move   |   A: Jump to Text   |   X: Fullscreen   |   L1/R1: Tab   |   B: Cancel"

                tex, tw, th = render_text(footer, font_small, theme["text"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(20, SCREEN_H - 40, tw, th))
                    sdl2.SDL_DestroyTexture(tex)

            elif render_state == STATE_IMAGE_VIEW:
                renderer.clear(theme["bg"])
                tex = get_current_image_texture()
                if tex and image_w > 0 and image_h > 0:
                    vw, vh = SCREEN_W, SCREEN_H
                    angle = float(image_rotation * 90)
                    eff_w, eff_h = (image_h, image_w) if image_rotation % 2 == 1 else (image_w, image_h)
                    
                    fit_zoom = min(float(vw) / eff_w, float(vh) / eff_h)
                    zoom = image_zoom if image_zoom > 0 else fit_zoom
                    
                    scaled_w = int(image_w * zoom)
                    scaled_h = int(image_h * zoom)
                    
                    draw_x = (vw - scaled_w) // 2 + image_pan_x
                    draw_y = (vh - scaled_h) // 2 + image_pan_y
                    
                    dst_rect = sdl2.SDL_Rect(draw_x, draw_y, scaled_w, scaled_h)
                    if angle != 0.0:
                        sdl2.SDL_RenderCopyEx(renderer.sdlrenderer, tex, None, dst_rect, angle, None, sdl2.SDL_FLIP_NONE)
                    else:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, dst_rect)
                else:
                    msg = "Cannot load this image"
                    tex_err, ew, eh = render_text(msg, font_medium, theme["text"])
                    if tex_err:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_err, None, sdl2.SDL_Rect((SCREEN_W-ew)//2, (SCREEN_H-eh)//2, ew, eh))
                        sdl2.SDL_DestroyTexture(tex_err)
                
                if show_hud and book_images:
                    # Top HUD
                    renderer.fill((0, 0, SCREEN_W, 55), theme["header"])
                    renderer.fill((0, 53, SCREEN_W, 2), theme["sel"])
                    
                    cur_img_name = os.path.basename(book_images[current_image_idx])
                    book_title, _ = get_book_display_metadata(os.path.basename(current_filepath))
                    hud_top = f"{book_title} - Image {current_image_idx + 1}/{len(book_images)} - {cur_img_name}"
                    tex_top, tw, th = render_text(hud_top, font_small, theme["text"])
                    if tex_top:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_top, None, sdl2.SDL_Rect(20, 15, min(tw, SCREEN_W - 40), th))
                        sdl2.SDL_DestroyTexture(tex_top)
                    
                    # Bottom HUD
                    renderer.fill((0, SCREEN_H - 55, SCREEN_W, 55), theme["header"])
                    renderer.fill((0, SCREEN_H - 55, SCREEN_W, 2), theme["sel"])
                    zoom_str = "Fit" if image_zoom <= 0 else f"{int(image_zoom*100)}%"
                    hud_bot = f"L/R: Switch Image | Y: Zoom ({zoom_str}) | X: Rotate | B: Back to Reading"
                    tex_bot, bw, bh = render_text(hud_bot, font_small, theme["text"])
                    if tex_bot:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_bot, None, sdl2.SDL_Rect(20, SCREEN_H - 38, min(bw, SCREEN_W - 40), bh))
                        sdl2.SDL_DestroyTexture(tex_bot)

            if state == STATE_ABOUT:
                draw_about_dialog(renderer, theme_idx, font_medium, font_large, font_small, render_text)
            elif state == STATE_QUIT_CONFIRM:
                draw_quit_confirm_dialog(renderer, theme, font_large, font_ui_medium, render_text)

            # Typography Modal Popup on Top of Reader (matching Exit Popup style)
            if show_typography_popup and state == STATE_READER:
                draw_typography_popup(renderer, theme, current_font_size, line_spacing_mult, word_spacing_mult, margin_side, theme_idx, typography_sel_idx, font_ui_medium, font_small, render_text)

            # Toast notification
            toast_msg = draw_toast_notification(renderer, toast_msg, toast_timer, current_ticks, font_small, render_text)

            renderer.present()
            needs_redraw = False
            if marquee_active and render_state == STATE_BROWSE:
                needs_redraw = True
            
        sdl2.SDL_Delay(16)

    cover_thread_running[0] = False
    for _t in _cover_threads: _t.join(timeout=0.3)
    clear_cover_cache()
    clear_book_img_thumb_cache()
    if font_medium:
        sdlttf.TTF_CloseFont(font_medium)
    if reader_target:
        sdl2.SDL_DestroyTexture(reader_target)
    if loaded_image_tex:
        sdl2.SDL_DestroyTexture(loaded_image_tex)
    clear_inline_image_cache()
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
