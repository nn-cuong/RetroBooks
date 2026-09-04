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

from covers import (
    CoverManager,
    get_book_img_thumbnail,
    get_inline_image,
    find_image_key,
    find_image_reader_line
)
from ui_views import (
    draw_book_icon,
    draw_browse_view,
    draw_book_reader_view,
    draw_toc_view,
    draw_image_view
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



def main():
    sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_JOYSTICK | sdl2.SDL_INIT_GAMECONTROLLER)
    sdlttf.TTF_Init()
    sdlimage.IMG_Init(sdlimage.IMG_INIT_JPG | sdlimage.IMG_INIT_PNG | sdlimage.IMG_INIT_WEBP)

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



    cover_manager = CoverManager()

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
            if reader_scroll_y > 0:
                prev_y = 0
                idx = reader_scroll_y - 1
                max_content_h = max(100, (get_reader_view_size()[1] - 105))
                target_idx = max(0, reader_scroll_y - (page_items_drawn if page_items_drawn > 0 else lines_per_page))
                while idx >= 0:
                    item = reader_lines[idx]
                    if isinstance(item, dict) and item.get("type") == "image":
                        h_step = line_height * 4
                    elif isinstance(item, dict) and item.get("type") == "footnote":
                        f_lines = item.get("lines", [])
                        f_line_h = int(line_height * 0.85)
                        box_h = 20 + (len(f_lines) + 1) * f_line_h
                        h_step = box_h + 14
                    elif item == "":
                        h_step = max(2, line_height // 6)
                    else:
                        h_step = line_height
                    if prev_y + h_step > max_content_h:
                        target_idx = idx + 1
                        break
                    prev_y += h_step
                    idx -= 1
                if idx < 0:
                    target_idx = 0
                reader_scroll_y = target_idx
                while reader_scroll_y > 0 and is_blank(reader_scroll_y):
                    reader_scroll_y -= 1
        elif dx > 0:
            step = page_items_drawn if page_items_drawn > 0 else lines_per_page
            reader_scroll_y = min(max_s, reader_scroll_y + step)
            while reader_scroll_y < max_s and is_blank(reader_scroll_y):
                reader_scroll_y += 1
    
    space_width = 12
    font_cache = {} # font_size -> (font_handle, char_widths, base_space_w)

    def recalculate_layout(only_metrics=False):
        nonlocal lines_per_page, line_height, font_medium, reader_lines, chapter_offsets, space_width, page_items_drawn
        reader_w, reader_h = get_reader_view_size()
        line_height = max(16, int(current_font_size * line_spacing_mult))
        lines_per_page = max(1, (reader_h - 105) // line_height)
        page_items_drawn = lines_per_page
        
        if only_metrics:
            return

        w = ctypes.c_int()
        h = ctypes.c_int()
        if current_font_size in font_cache:
            font_medium, char_widths, base_space_w = font_cache[current_font_size]
        else:
            font_medium = sdlttf.TTF_OpenFont(reading_font_bytes, current_font_size)
            char_widths = {}
            common_chars = " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~" \
                           "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ" \
                           "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ" \
                           "“”‘’…—–·•«»"
            for ch in common_chars:
                sdlttf.TTF_SizeUTF8(font_medium, ch.encode('utf-8', errors='replace'), ctypes.byref(w), ctypes.byref(h))
                char_widths[ch] = w.value
            sdlttf.TTF_SizeUTF8(font_medium, b" ", ctypes.byref(w), ctypes.byref(h))
            base_space_w = w.value if w.value > 0 else (current_font_size // 3)
            font_cache[current_font_size] = (font_medium, char_widths, base_space_w)

        base_space_w = base_space_w or char_widths.get(" ", current_font_size // 3)
        space_width = max(2, int(base_space_w * word_spacing_mult))
        indent_width = space_width * 3
        max_line_width = max(100, reader_w - (margin_side * 2))
        
        # Word width caching for maximum performance
        word_widths = {}
        get_cw = char_widths.get
        fallback_cw = char_widths.get("m", current_font_size // 2)
        
        def get_word_w(word_str):
            ww = word_widths.get(word_str)
            if ww is None:
                total_w = 0
                for c in word_str:
                    cw = get_cw(c)
                    if cw is None:
                        w_tmp = ctypes.c_int()
                        h_tmp = ctypes.c_int()
                        sdlttf.TTF_SizeUTF8(font_medium, c.encode('utf-8', errors='replace'), ctypes.byref(w_tmp), ctypes.byref(h_tmp))
                        cw = char_widths[c] = w_tmp.value if w_tmp.value > 0 else fallback_cw
                    total_w += cw
                ww = word_widths[word_str] = total_w
            return ww
        
        reader_lines = []
        chapter_offsets = []
        
        for title, text in raw_chapters:
            chapter_offsets.append((title, len(reader_lines)))
            for paragraph in text.split('\n'):
                paragraph = paragraph.strip()
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
                    
                    f_words = note_text.split()
                    f_lines = []
                    cur_f_line = []
                    cur_f_w = 0
                    f_max_w = max_line_width - 40
                    for fw in f_words:
                        fww = get_word_w(fw)
                        if not cur_f_line:
                            cur_f_line.append(fw)
                            cur_f_w = fww
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
                
                words = paragraph.split()
                if not words:
                    reader_lines.append("")
                    continue
                    
                current_line = []
                current_w = indent_width
                is_first_line = True
                
                for word in words:
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
                                cover_manager.clear()
                                current_path = os.path.dirname(current_path)
                                folders, files = get_directory_contents(current_path)
                                sel_index = 0
                                scroll_y = 0
                                cover_manager.prewarm_covers(_make_list_items_for_path(folders, files, current_path, base_path), current_path)
                                needs_redraw = True
                            elif item["is_dir"]:
                                cover_manager.clear()
                                current_path = os.path.join(current_path, item["name"])
                                folders, files = get_directory_contents(current_path)
                                sel_index = 0
                                scroll_y = 0
                                cover_manager.prewarm_covers(_make_list_items_for_path(folders, files, current_path, base_path), current_path)
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
                            old_ch_idx = 0
                            old_rel_line = 0
                            for idx, (ch_t, ch_off) in enumerate(chapter_offsets):
                                if ch_off <= reader_scroll_y:
                                    old_ch_idx = idx
                                    old_rel_line = reader_scroll_y - ch_off
                                else:
                                    break
                            old_total_ch_lines = (chapter_offsets[old_ch_idx+1][1] - chapter_offsets[old_ch_idx][1]) if old_ch_idx + 1 < len(chapter_offsets) else max(1, len(reader_lines) - chapter_offsets[old_ch_idx][1])
                            old_ratio = old_rel_line / max(1, old_total_ch_lines)

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

                            if typography_sel_idx in (0, 2, 3) and reader_lines and chapter_offsets:
                                new_ch_off = chapter_offsets[old_ch_idx][1] if old_ch_idx < len(chapter_offsets) else 0
                                new_total_ch_lines = (chapter_offsets[old_ch_idx+1][1] - new_ch_off) if old_ch_idx + 1 < len(chapter_offsets) else max(1, len(reader_lines) - new_ch_off)
                                reader_scroll_y = max(0, min(new_ch_off + int(old_ratio * new_total_ch_lines), max(0, len(reader_lines) - lines_per_page)))
                            elif reader_lines:
                                reader_scroll_y = max(0, min(reader_scroll_y, max(0, len(reader_lines) - lines_per_page)))
                            needs_redraw = True

                        elif btn in (sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT, sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER):
                            old_ch_idx = 0
                            old_rel_line = 0
                            for idx, (ch_t, ch_off) in enumerate(chapter_offsets):
                                if ch_off <= reader_scroll_y:
                                    old_ch_idx = idx
                                    old_rel_line = reader_scroll_y - ch_off
                                else:
                                    break
                            old_total_ch_lines = (chapter_offsets[old_ch_idx+1][1] - chapter_offsets[old_ch_idx][1]) if old_ch_idx + 1 < len(chapter_offsets) else max(1, len(reader_lines) - chapter_offsets[old_ch_idx][1])
                            old_ratio = old_rel_line / max(1, old_total_ch_lines)

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

                            if typography_sel_idx in (0, 2, 3) and reader_lines and chapter_offsets:
                                new_ch_off = chapter_offsets[old_ch_idx][1] if old_ch_idx < len(chapter_offsets) else 0
                                new_total_ch_lines = (chapter_offsets[old_ch_idx+1][1] - new_ch_off) if old_ch_idx + 1 < len(chapter_offsets) else max(1, len(reader_lines) - new_ch_off)
                                reader_scroll_y = max(0, min(new_ch_off + int(old_ratio * new_total_ch_lines), max(0, len(reader_lines) - lines_per_page)))
                            elif reader_lines:
                                reader_scroll_y = max(0, min(reader_scroll_y, max(0, len(reader_lines) - lines_per_page)))
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
                            need_full_recalc = (current_font_size != orig_font_size or word_spacing_mult != orig_word_spacing or margin_side != orig_margin_side)
                            current_font_size = orig_font_size
                            line_spacing_mult = orig_line_spacing
                            word_spacing_mult = orig_word_spacing
                            margin_side = orig_margin_side
                            theme_idx = orig_theme_idx
                            write_theme_idx(theme_idx)
                            if need_full_recalc:
                                recalculate_layout(only_metrics=False)
                            else:
                                recalculate_layout(only_metrics=True)
                            if reader_lines:
                                reader_scroll_y = max(0, min(reader_scroll_y, max(0, len(reader_lines) - lines_per_page)))
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
                                target_line = find_image_reader_line(target_img, reader_lines)
                                if target_line is not None:
                                    reader_scroll_y = max(0, min(target_line, max(0, len(reader_lines) - 1)))
                                    state = STATE_READER
                                else:
                                    toast_msg = "Image not in text (use X to view)"
                                    toast_timer = current_ticks
                            else:
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
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_X: # Physical Y - Zoom In
                        if image_zoom <= 0:
                            vw, vh = SCREEN_W, SCREEN_H
                            eff_w, eff_h = (image_h, image_w) if image_rotation % 2 == 1 else (image_w, image_h)
                            fit_zoom = min(float(vw) / eff_w, float(vh) / eff_h) if eff_w > 0 and eff_h > 0 else 1.0
                            image_zoom = min(fit_zoom * 1.25, 4.0)
                        else:
                            image_zoom = min(image_zoom * 1.25, 4.0)
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A - Zoom Out
                        vw, vh = SCREEN_W, SCREEN_H
                        eff_w, eff_h = (image_h, image_w) if image_rotation % 2 == 1 else (image_w, image_h)
                        fit_zoom = min(float(vw) / eff_w, float(vh) / eff_h) if eff_w > 0 and eff_h > 0 else 1.0
                        if image_zoom > fit_zoom * 1.05:
                            image_zoom = max(image_zoom / 1.25, fit_zoom)
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
                    elif btn in (sdl2.SDL_CONTROLLER_BUTTON_A, sdl2.SDL_CONTROLLER_BUTTON_BACK): # Physical B or Select - Back
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

        cover_manager.pump_ready(renderer)  # promote background-loaded covers to GPU textures
        if needs_redraw:
            theme = THEMES[theme_idx]
            renderer.clear(theme["bg"])
            
            if state in (STATE_QUIT_CONFIRM, STATE_ABOUT):
                render_state = state_before_quit if state == STATE_QUIT_CONFIRM else STATE_BROWSE
            else:
                render_state = state

            if render_state == STATE_BROWSE:
                marquee_active = draw_browse_view(
                    renderer, theme_idx, base_path, current_path, folders, files,
                    sel_index, scroll_y, library_view_mode, current_ticks, sel_time,
                    font_large, font_small, font_medium, render_text, cover_manager
                )
            elif render_state == STATE_READER:
                reader_w, reader_h = get_reader_view_size()
                target = ensure_reader_target(reader_w, reader_h)
                page_items_drawn = draw_book_reader_view(
                    renderer, theme, target, reader_w, reader_h, reader_lines, reader_scroll_y,
                    lines_per_page, line_height, font_medium, font_small, render_text,
                    current_filepath, chapter_offsets, show_hud, current_font_size,
                    word_spacing_mult, margin_side, space_width, inline_image_cache,
                    image_loader, reader_rotation_idx
                )
            elif render_state == STATE_TOC:
                draw_toc_view(
                    renderer, theme, toc_tab, toc_sel_index, toc_img_sel_index,
                    chapter_offsets, book_images, visible_items, font_medium, font_small,
                    render_text, image_loader, book_img_thumb_cache
                )
            elif render_state == STATE_IMAGE_VIEW:
                tex = get_current_image_texture()
                draw_image_view(
                    renderer, theme, tex, image_w, image_h, image_zoom,
                    image_pan_x, image_pan_y, image_rotation, show_hud, book_images,
                    current_image_idx, current_filepath, font_medium, font_small, render_text
                )

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

    cover_manager.shutdown()
    clear_book_img_thumb_cache()
    for f_h, _, _ in font_cache.values():
        if f_h:
            sdlttf.TTF_CloseFont(f_h)
    font_cache.clear()
    if font_medium and not any(font_medium == fh for fh, _, _ in font_cache.values()):
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
