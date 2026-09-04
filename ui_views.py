import os
import sys

try:
    import sdl2
    import sdl2.ext
    import sdl2.sdlttf as sdlttf
except ImportError:
    pass

from constants import SCREEN_W, SCREEN_H, THEMES, LIBRARY_THEMES, get_book_display_metadata
from covers import get_inline_image, get_book_img_thumbnail

def draw_book_icon(renderer, x, y, color, background):
    """Small pixel-friendly book glyph."""
    renderer.fill((x, y, 15, 20), color)
    renderer.fill((x + 3, y + 3, 2, 14), background)


def draw_browse_view(
    renderer, theme_idx, base_path, current_path, folders, files,
    sel_index, scroll_y, library_view_mode, current_ticks, sel_time,
    font_large, font_small, font_medium, render_text, cover_manager
):
    """Renders the Library Browse view in Grid or List mode with smooth marquee."""
    library_theme = LIBRARY_THEMES[theme_idx % len(LIBRARY_THEMES)]
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
                label = ".." if item["name"] == ".." else "[DIR]"
                t_lbl, lw, lh = render_text(label, font_medium, library_theme["secondary"])
                if t_lbl:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, t_lbl, None, sdl2.SDL_Rect(cover_x + (cover_w - lw)//2, cover_y + (cover_h - lh)//2, lw, lh))
                    sdl2.SDL_DestroyTexture(t_lbl)
            else:
                fp = os.path.join(current_path, item["name"])
                c_tex, cw, ch = cover_manager.get_cover_texture(fp)
                if c_tex and cw > 0 and ch > 0:
                    scale = min(cover_w / cw, cover_h / ch)
                    dw = max(1, int(cw * scale))
                    dh = max(1, int(ch * scale))
                    dx = cover_x + (cover_w - dw) // 2
                    dy = cover_y + (cover_h - dh) // 2
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, c_tex, None, sdl2.SDL_Rect(dx, dy, dw, dh))
                else:
                    renderer.fill((cover_x, cover_y, cover_w, cover_h), library_theme["bg"])
                    draw_book_icon(renderer, cover_x + (cover_w - 15)//2, cover_y + (cover_h - 20)//2, library_theme["secondary"], library_theme["bg"])

            title_str = item["name"] if item["is_dir"] else os.path.splitext(item["name"])[0].strip()
            max_tw = col_w - 16
            t_tex, tw, th = render_text(title_str, font_small, card_text_col)
            if t_tex:
                ty = cy + 224
                if is_sel and tw > max_tw:
                    marquee_active = True
                    elapsed = current_ticks - sel_time
                    delay = 1000
                    overflow = tw - max_tw
                    speed = 0.05
                    cycle = int(overflow / speed) + 2000
                    sub_t = elapsed % cycle
                    if sub_t < delay:
                        offset = 0
                    elif sub_t < delay + int(overflow / speed):
                        offset = int((sub_t - delay) * speed)
                    else:
                        offset = overflow

                    clip_rect = sdl2.SDL_Rect(cx + 8, ty, max_tw, th)
                    sdl2.SDL_RenderSetClipRect(renderer.sdlrenderer, clip_rect)
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, t_tex, None, sdl2.SDL_Rect(cx + 8 - offset, ty, tw, th))
                    sdl2.SDL_RenderSetClipRect(renderer.sdlrenderer, None)
                else:
                    draw_w = min(tw, max_tw)
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, t_tex, sdl2.SDL_Rect(0, 0, draw_w, th), sdl2.SDL_Rect(cx + (col_w - draw_w) // 2, ty, draw_w, th))
                sdl2.SDL_DestroyTexture(t_tex)

        page_str = f"Page {grid_page + 1} / {max(1, (len(list_items) + 7) // 8)}"
        tex, tw, th = render_text(page_str, font_small, library_theme["secondary"])
        if tex:
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(SCREEN_W - 32 - tw, SCREEN_H - 50 + (50 - th)//2, tw, th))
            sdl2.SDL_DestroyTexture(tex)

    else:
        # LIST MODE
        library_visible_items = 8
        item_h = 72
        list_y_start = 96
        max_title_w = SCREEN_W - 120

        for i in range(scroll_y, min(len(list_items), scroll_y + library_visible_items)):
            item = list_items[i]
            y = list_y_start + (i - scroll_y) * item_h
            is_sel = (i == sel_index)

            if is_sel:
                renderer.fill((24, y, SCREEN_W - 48, item_h - 4), sel_bg)
                renderer.fill((24, y, 6, item_h - 4), sel_border)
                title_col = sel_text
            else:
                title_col = library_theme["text"]

            icon_x = 44
            icon_y = y + (item_h - 4 - 20) // 2
            if item["is_dir"]:
                t_lbl, lw, lh = render_text("📁", font_small, title_col)
                if t_lbl:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, t_lbl, None, sdl2.SDL_Rect(icon_x, icon_y, lw, lh))
                    sdl2.SDL_DestroyTexture(t_lbl)
            else:
                draw_book_icon(renderer, icon_x, icon_y, title_col, library_theme["bg"])

            title_str = item["name"] if item["is_dir"] else os.path.splitext(item["name"])[0].strip()
            tex, tw, th = render_text(title_str, font_medium, title_col)
            if tex:
                tx = 80
                ty = y + (item_h - 4 - th) // 2
                if is_sel and tw > max_title_w:
                    marquee_active = True
                    elapsed = current_ticks - sel_time
                    delay = 1000
                    overflow = tw - max_title_w
                    speed = 0.05
                    cycle = int(overflow / speed) + 2000
                    sub_t = elapsed % cycle
                    if sub_t < delay:
                        offset = 0
                    elif sub_t < delay + int(overflow / speed):
                        offset = int((sub_t - delay) * speed)
                    else:
                        offset = overflow

                    clip_rect = sdl2.SDL_Rect(tx, ty, max_title_w, th)
                    sdl2.SDL_RenderSetClipRect(renderer.sdlrenderer, clip_rect)
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(tx - offset, ty, tw, th))
                    sdl2.SDL_RenderSetClipRect(renderer.sdlrenderer, None)
                else:
                    draw_w = min(tw, max_title_w)
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, sdl2.SDL_Rect(0, 0, draw_w, th), sdl2.SDL_Rect(tx, ty, draw_w, th))
                sdl2.SDL_DestroyTexture(tex)

        if len(list_items) > library_visible_items:
            sb_h = int((library_visible_items / len(list_items)) * (SCREEN_H - 160))
            sb_y = list_y_start + int((scroll_y / len(list_items)) * (SCREEN_H - 160))
            renderer.fill((SCREEN_W - 14, sb_y, 4, max(10, sb_h)), library_theme["divider"])

    footer_hint = "A: Open   B: Back / Up   X: Mode   Y: Theme   SELECT: Info   [START] Exit"
    tex_foot, fw, fh = render_text(footer_hint, font_small, library_theme["secondary"])
    if tex_foot:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_foot, None, sdl2.SDL_Rect(32, SCREEN_H - 50 + (50 - fh)//2, fw, fh))
        sdl2.SDL_DestroyTexture(tex_foot)

    return marquee_active


def draw_book_reader_view(
    renderer, theme, target, reader_w, reader_h, reader_lines, reader_scroll_y,
    lines_per_page, line_height, font_medium, font_small, render_text,
    current_filepath, chapter_offsets, show_hud, current_font_size,
    word_spacing_mult, margin_side, space_width, inline_image_cache,
    image_loader, reader_rotation_idx
):
    """Draws book reader view with formatted text, images, footnotes, and progress bar."""
    drawing_rotated = (reader_rotation_idx != 0)
    reader_angle = reader_rotation_idx * 90
    if drawing_rotated:
        if target:
            sdl2.SDL_SetRenderTarget(renderer.sdlrenderer, target)
            renderer.clear(theme["bg"])
        else:
            drawing_rotated = False
            reader_w, reader_h = SCREEN_W, SCREEN_H

    y_pos = 50
    max_y = reader_h - 55
    max_content_w = max(100, reader_w - (margin_side * 2))
    i = reader_scroll_y

    while i < len(reader_lines):
        item = reader_lines[i]
        if isinstance(item, dict) and item.get("type") == "image":
            cached = get_inline_image(item["src"], image_loader, renderer, inline_image_cache, max_content_w, reader_h - 110)
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

        book_title = os.path.splitext(os.path.basename(current_filepath))[0].strip()
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
        sdl2.SDL_RenderCopyEx(renderer.sdlrenderer, target, src_rect, dst_rect, float(reader_angle), None, sdl2.SDL_FLIP_NONE)

    return max(1, i - reader_scroll_y)


def draw_toc_view(
    renderer, theme, toc_tab, toc_sel_index, toc_img_sel_index,
    chapter_offsets, book_images, visible_items, font_medium, font_small,
    render_text, image_loader, book_img_thumb_cache
):
    """Draws Table of Contents modal (Chapters tab and Inline Images tab)."""
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
                
        footer = "DPAD / Sticks: Move   |   A: Select Chapter   |   L1/R1: Switch Tab   |   B: Cancel"
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

            renderer.fill((cell_x, cell_y, thumb_w, thumb_h), theme["header"])

            img_path = book_images[idx]
            thumb_info = get_book_img_thumbnail(img_path, image_loader, renderer, book_img_thumb_cache, thumb_w - 8, thumb_h - 8)
            if thumb_info and thumb_info["tex"]:
                tw = thumb_info["w"]
                th = thumb_info["h"]
                dst_x = cell_x + (thumb_w - tw) // 2
                dst_y = cell_y + (thumb_h - th) // 2
                sdl2.SDL_RenderCopy(renderer.sdlrenderer, thumb_info["tex"], None, sdl2.SDL_Rect(dst_x, dst_y, tw, th))
            else:
                tex_ph, pw, ph = render_text(f"Img {idx + 1}", font_small, theme.get("secondary", theme["text"]))
                if tex_ph:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_ph, None, sdl2.SDL_Rect(cell_x + (thumb_w - pw)//2, cell_y + (thumb_h - ph)//2, pw, ph))
                    sdl2.SDL_DestroyTexture(tex_ph)

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

            img_fn = os.path.basename(img_path)
            if len(img_fn) > 18:
                img_fn = img_fn[:15] + "..."
            lbl_text = f"{idx + 1}. {img_fn}"
            lbl_color = theme["sel"] if is_sel else theme["text"]
            tex_lbl, lw, lh = render_text(lbl_text, font_small, lbl_color)
            if tex_lbl:
                sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_lbl, None, sdl2.SDL_Rect(cell_x + (thumb_w - min(lw, thumb_w))//2, cell_y + thumb_h + 6, min(lw, thumb_w), lh))
                sdl2.SDL_DestroyTexture(tex_lbl)

        footer = "DPAD / Sticks: Move   |   A: Jump to Text   |   X: Fullscreen   |   L1/R1: Tab   |   B: Cancel"

    tex, tw, th = render_text(footer, font_small, theme["text"])
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(20, SCREEN_H - 40, tw, th))
        sdl2.SDL_DestroyTexture(tex)


def draw_image_view(
    renderer, theme, tex, image_w, image_h, image_zoom,
    image_pan_x, image_pan_y, image_rotation, show_hud, book_images,
    current_image_idx, current_filepath, font_medium, font_small, render_text
):
    """Draws standalone image viewer with pan, zoom, rotation, and HUD."""
    renderer.clear(theme["bg"])
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
        renderer.fill((0, 0, SCREEN_W, 55), theme["header"])
        renderer.fill((0, 53, SCREEN_W, 2), theme["sel"])

        cur_img_name = os.path.basename(book_images[current_image_idx]) if current_image_idx < len(book_images) else "Image"
        book_title, _ = get_book_display_metadata(os.path.basename(current_filepath))
        hud_top = f"{book_title} - Image {current_image_idx + 1}/{len(book_images)} - {cur_img_name}"
        tex_top, tw, th = render_text(hud_top, font_small, theme["text"])
        if tex_top:
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_top, None, sdl2.SDL_Rect(20, 15, min(tw, SCREEN_W - 40), th))
            sdl2.SDL_DestroyTexture(tex_top)

        renderer.fill((0, SCREEN_H - 55, SCREEN_W, 55), theme["header"])
        renderer.fill((0, SCREEN_H - 55, SCREEN_W, 2), theme["sel"])
        zoom_str = "Fit" if image_zoom <= 0 else f"{int(round((image_zoom / fit_zoom if fit_zoom > 0 else image_zoom) * 100))}%"
        hud_bot = f"L/R: Switch | Y: Zoom ({zoom_str}) | X: Rotate | A: HUD | B: Cancel"
        tex_bot, bw, bh = render_text(hud_bot, font_small, theme["text"])
        if tex_bot:
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_bot, None, sdl2.SDL_Rect(20, SCREEN_H - 38, min(bw, SCREEN_W - 40), bh))
            sdl2.SDL_DestroyTexture(tex_bot)
