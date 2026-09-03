try:
    import sdl2
    import sdl2.ext
    import sdl2.sdlttf as sdlttf
except ImportError:
    pass
from constants import SCREEN_W, SCREEN_H, THEMES, LIBRARY_THEMES

def draw_about_dialog(renderer, theme_idx, font_medium, font_large, font_small, render_text):
    lib_t = LIBRARY_THEMES[theme_idx % len(LIBRARY_THEMES)]
    sdl2.SDL_SetRenderDrawBlendMode(renderer.sdlrenderer, sdl2.SDL_BLENDMODE_BLEND)
    sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 0, 0, 0, 160)
    sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, 0, SCREEN_W, SCREEN_H))
    
    pop_w, pop_h = 640, 400
    pop_x, pop_y = (SCREEN_W - pop_w) // 2, (SCREEN_H - pop_h) // 2
    renderer.fill((pop_x, pop_y, pop_w, pop_h), lib_t["sel_border"])
    renderer.fill((pop_x + 2, pop_y + 2, pop_w - 4, pop_h - 4), lib_t["bg"])
    
    # Title
    tex, tw, th = render_text("APPLICATION INFO", font_medium, lib_t["accent"])
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + (pop_w - tw)//2, pop_y + 24, tw, th))
        sdl2.SDL_DestroyTexture(tex)
        
    # App Name
    tex, tw, th = render_text("RetroBooks v1.0", font_large, lib_t["text"])
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + (pop_w - tw)//2, pop_y + 68, tw, th))
        sdl2.SDL_DestroyTexture(tex)
        
    # Subtitle
    tex, tw, th = render_text("Ebook & Novel Reader for TrimUI Brick Pro", font_small, lib_t["secondary"])
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + (pop_w - tw)//2, pop_y + 128, tw, th))
        sdl2.SDL_DestroyTexture(tex)
        
    renderer.fill((pop_x + 40, pop_y + 166, pop_w - 80, 1), lib_t["divider"])
    
    # Info lines
    lines = [
        "Author: Nguyen Ngoc Cuong",
        "Email: nn.cuong.404@gmail.com",
        "Facebook: aegony98 / Instagram: ich_heisse_cuong"
    ]
    iy = pop_y + 200
    for line in lines:
        tex, tw, th = render_text(line, font_small, lib_t["text"])
        if tex:
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + 35, iy, min(tw, pop_w - 70), th))
            sdl2.SDL_DestroyTexture(tex)
        iy += 40
        
    renderer.fill((pop_x + 40, pop_y + pop_h - 55, pop_w - 80, 1), lib_t["divider"])
    tex, tw, th = render_text("B / SELECT: Close", font_small, lib_t["secondary"])
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + (pop_w - tw)//2, pop_y + pop_h - 40, tw, th))
        sdl2.SDL_DestroyTexture(tex)

def draw_quit_confirm_dialog(renderer, theme, font_large, font_ui_medium, render_text):
    sdl2.SDL_SetRenderDrawBlendMode(renderer.sdlrenderer, sdl2.SDL_BLENDMODE_BLEND)
    sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 0, 0, 0, 150)
    sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, 0, SCREEN_W, SCREEN_H))
    
    pop_w, pop_h = 600, 200
    pop_x, pop_y = (SCREEN_W - pop_w)//2, (SCREEN_H - pop_h)//2
    
    renderer.fill((pop_x, pop_y, pop_w, pop_h), theme["sel"])
    renderer.fill((pop_x + 2, pop_y + 2, pop_w - 4, pop_h - 4), theme["bg"])
    
    msg = "Exit RetroBooks?"
    sdlttf.TTF_SetFontStyle(font_large, sdlttf.TTF_STYLE_BOLD)
    tex, tw, th = render_text(msg, font_large, theme["text"])
    sdlttf.TTF_SetFontStyle(font_large, sdlttf.TTF_STYLE_NORMAL)
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + pop_w//2 - tw//2, pop_y + 40, tw, th))
        sdl2.SDL_DestroyTexture(tex)
    
    msg2 = "A: Confirm   B: Cancel"
    tex, tw, th = render_text(msg2, font_ui_medium, theme["text"])
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + pop_w//2 - tw//2, pop_y + 130, tw, th))
        sdl2.SDL_DestroyTexture(tex)

def draw_typography_popup(renderer, theme, current_font_size, line_spacing_mult, word_spacing_mult, margin_side, theme_idx, typography_sel_idx, font_ui_medium, font_small, render_text):
    sdl2.SDL_SetRenderDrawBlendMode(renderer.sdlrenderer, sdl2.SDL_BLENDMODE_BLEND)
    sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 0, 0, 0, 160)
    sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, 0, SCREEN_W, SCREEN_H))
    
    pop_w = 680
    pop_h = 470
    pop_x = (SCREEN_W - pop_w) // 2
    pop_y = (SCREEN_H - pop_h) // 2
    
    renderer.fill((pop_x, pop_y, pop_w, pop_h), theme["sel"])
    renderer.fill((pop_x + 3, pop_y + 3, pop_w - 6, pop_h - 6), theme["bg"])
    
    header_h = 56
    renderer.fill((pop_x + 3, pop_y + 3, pop_w - 6, header_h), theme.get("header", theme["bg"]))
    renderer.fill((pop_x + 3, pop_y + header_h + 3, pop_w - 6, 2), theme["sel"])
    
    sdlttf.TTF_SetFontStyle(font_ui_medium, sdlttf.TTF_STYLE_BOLD)
    tex_hdr, hw, hh = render_text("TYPOGRAPHY SETTINGS", font_ui_medium, theme["text"])
    sdlttf.TTF_SetFontStyle(font_ui_medium, sdlttf.TTF_STYLE_NORMAL)
    if tex_hdr:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_hdr, None, sdl2.SDL_Rect(pop_x + (pop_w - hw) // 2, pop_y + (header_h - hh) // 2 + 3, hw, hh))
        sdl2.SDL_DestroyTexture(tex_hdr)
        
    options = [
        ("Font Size", f"{current_font_size} px"),
        ("Line Spacing", f"{line_spacing_mult:.2f}x"),
        ("Word Spacing", f"{word_spacing_mult:.1f}x"),
        ("Side Margin", f"{margin_side} px"),
        ("Theme", THEMES[theme_idx % len(THEMES)].get("name", f"Theme {theme_idx+1}"))
    ]
    
    row_y_start = pop_y + header_h + 18
    row_h = 56
    for r_idx, (label, val_str) in enumerate(options):
        ry = row_y_start + r_idx * (row_h + 8)
        rx = pop_x + 24
        rw = pop_w - 48
        is_sel = (r_idx == typography_sel_idx)
        
        if is_sel:
            renderer.fill((rx, ry, rw, row_h), theme["sel"])
            renderer.fill((rx + 2, ry + 2, rw - 4, row_h - 4), theme.get("header", theme["bg"]))
            label_col = theme["text"]
            val_col = theme["sel"]
        else:
            renderer.fill((rx, ry, rw, row_h), theme.get("header", theme["bg"]))
            label_col = theme["text"]
            val_col = theme["text"]
            
        sdlttf.TTF_SetFontStyle(font_small, sdlttf.TTF_STYLE_BOLD if is_sel else sdlttf.TTF_STYLE_NORMAL)
        tex_lbl, lw, lh = render_text(label, font_small, label_col)
        sdlttf.TTF_SetFontStyle(font_small, sdlttf.TTF_STYLE_NORMAL)
        if tex_lbl:
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_lbl, None, sdl2.SDL_Rect(rx + 16, ry + (row_h - lh) // 2, lw, lh))
            sdl2.SDL_DestroyTexture(tex_lbl)
            
        display_val = f"◀  {val_str}  ▶" if is_sel else val_str
        sdlttf.TTF_SetFontStyle(font_small, sdlttf.TTF_STYLE_BOLD if is_sel else sdlttf.TTF_STYLE_NORMAL)
        tex_v, vw, vh = render_text(display_val, font_small, val_col)
        sdlttf.TTF_SetFontStyle(font_small, sdlttf.TTF_STYLE_NORMAL)
        if tex_v:
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_v, None, sdl2.SDL_Rect(rx + rw - vw - 16, ry + (row_h - vh) // 2, vw, vh))
            sdl2.SDL_DestroyTexture(tex_v)
            
    footer_y = pop_y + pop_h - 42
    msg_foot = "A: Save   |   B / R2: Cancel   |   D-Pad: Select & Adjust"
    tex_foot, fw, fh = render_text(msg_foot, font_small, theme["text"])
    if tex_foot:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_foot, None, sdl2.SDL_Rect(pop_x + (pop_w - fw) // 2, footer_y, fw, fh))
        sdl2.SDL_DestroyTexture(tex_foot)

def draw_toast_notification(renderer, toast_msg, toast_timer, current_ticks, font_small, render_text):
    if toast_msg and (current_ticks - toast_timer < 2000):
        t_tex, tw, th = render_text(toast_msg, font_small, sdl2.SDL_Color(255, 255, 255, 255))
        if t_tex:
            pad = 16
            box_w = tw + pad * 2
            box_h = th + pad
            box_x = (SCREEN_W - box_w) // 2
            box_y = SCREEN_H - 120
            renderer.fill((box_x, box_y, box_w, box_h), sdl2.ext.Color(30, 30, 30))
            renderer.fill((box_x + 2, box_y + 2, box_w - 4, box_h - 4), sdl2.ext.Color(60, 60, 60))
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, t_tex, None, sdl2.SDL_Rect(box_x + pad, box_y + pad // 2, tw, th))
            sdl2.SDL_DestroyTexture(t_tex)
        return toast_msg
    return ""
