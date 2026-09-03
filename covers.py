import os
import sys
import threading
import queue as _queue_mod
import hashlib

try:
    import sdl2
    import sdl2.ext
    import sdl2.sdlimage as sdlimage
except ImportError:
    pass

from parsers import extract_epub_cover_data, extract_kindle_cover_data

def log_debug(msg):
    pass

class CoverManager:
    """Fast Async Cover System: background worker threads + disk cache + native surfaces."""
    def __init__(self, cache_dir="/mnt/SDCARD/.cover_cache", num_threads=3):
        self.cache_dir = cache_dir
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception:
            pass
        self.cover_cache = {}          # filepath -> (SDL_Texture, w, h)
        self.cover_pending = set()
        self._cover_q = _queue_mod.Queue()
        self._cover_q_lock = threading.Lock()
        self.cover_ready = {}          # filepath -> (surf, w, h) or (None, 0, 0)
        self.cover_ready_lock = threading.Lock()
        self.cover_threads_running = [True]
        self._threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            self._threads.append(t)

    def _disk_path(self, fp):
        h = hashlib.sha1(fp.encode("utf-8", errors="replace")).hexdigest()[:16]
        return os.path.join(self.cache_dir, h + ".bmp")

    def _decode_cover(self, img_data):
        if "sdl2" not in sys.modules:
            return None, 0, 0
        rw = sdl2.SDL_RWFromConstMem(img_data, len(img_data))
        src = sdlimage.IMG_Load_RW(rw, 1)
        if not src:
            return None, 0, 0
        sw, sh = src.contents.w, src.contents.h
        if sw <= 0 or sh <= 0:
            sdl2.SDL_FreeSurface(src)
            return None, 0, 0
        return src, sw, sh

    def _worker(self):
        while self.cover_threads_running[0]:
            try:
                filepath = self._cover_q.get(timeout=0.5)
            except Exception:
                continue
            disk = self._disk_path(filepath)
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
                elif _ext in ('.mobi', '.azw', '.azw3'):
                    img_data = extract_kindle_cover_data(filepath)
            if not img_data:
                with self.cover_ready_lock:
                    self.cover_ready[filepath] = (None, 0, 0)
                self._cover_q.task_done()
                continue
            surf, dw, dh = self._decode_cover(img_data)
            if surf and dw > 0:
                if not os.path.exists(disk):
                    try:
                        sdl2.SDL_SaveBMP(surf, disk.encode("utf-8"))
                    except Exception:
                        pass
                with self.cover_ready_lock:
                    self.cover_ready[filepath] = (surf, dw, dh)
            else:
                if surf:
                    sdl2.SDL_FreeSurface(surf)
                with self.cover_ready_lock:
                    self.cover_ready[filepath] = (None, 0, 0)
            self._cover_q.task_done()

    def pump_ready(self, renderer):
        """Promote finished CPU surfaces -> GPU textures."""
        with self.cover_ready_lock:
            if not self.cover_ready:
                return
            batch = list(self.cover_ready.items())
            self.cover_ready.clear()
        for fp, result in batch:
            if len(result) == 3 and result[0] is not None:
                surf, dw, dh = result
                tex = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, surf)
                sdl2.SDL_FreeSurface(surf)
                self.cover_cache[fp] = (tex, dw, dh) if tex else (None, 0, 0)
            else:
                self.cover_cache[fp] = (None, 0, 0)

    def get_cover_texture(self, filepath):
        """Non-blocking: returns cached texture or queues background load."""
        if filepath in self.cover_cache:
            return self.cover_cache[filepath]
        with self.cover_ready_lock:
            already = filepath in self.cover_ready
        if not already:
            with self._cover_q_lock:
                if filepath not in self.cover_pending:
                    self.cover_pending.add(filepath)
                    self._cover_q.put_nowait(filepath)
        return (None, 0, 0)

    def prewarm_covers(self, item_list, path):
        """Pre-queue all file items immediately when entering a directory."""
        for item in item_list:
            if not item["is_dir"]:
                fp = os.path.join(path, item["name"])
                if fp not in self.cover_cache:
                    with self.cover_ready_lock:
                        already = fp in self.cover_ready
                    if not already:
                        with self._cover_q_lock:
                            if fp not in self.cover_pending:
                                self.cover_pending.add(fp)
                                self._cover_q.put_nowait(fp)

    def clear(self):
        with self._cover_q_lock:
            self.cover_pending.clear()
        while not self._cover_q.empty():
            try:
                self._cover_q.get_nowait()
                self._cover_q.task_done()
            except Exception:
                break
        with self.cover_ready_lock:
            for result in self.cover_ready.values():
                if len(result) == 3 and result[0] is not None:
                    sdl2.SDL_FreeSurface(result[0])
            self.cover_ready.clear()
        for tex, _, _ in self.cover_cache.values():
            if tex:
                sdl2.SDL_DestroyTexture(tex)
        self.cover_cache.clear()

    def shutdown(self):
        self.cover_threads_running[0] = False
        self.clear()


def get_book_img_thumbnail(img_path, image_loader, renderer, cache_dict, max_w=216, max_h=260):
    if not img_path or not image_loader:
        return None
    if img_path in cache_dict:
        return cache_dict[img_path]
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
                cache_dict[img_path] = info
                return info
    except Exception as e:
        log_debug(f"get_book_img_thumbnail error: {e}")
    return None

def get_inline_image(img_src, image_loader, renderer, cache_dict, max_w, max_h):
    """Loads inline book images for inline rendering within book text with fallbacks."""
    if not img_src or not image_loader:
        return None
    if img_src in cache_dict:
        item = cache_dict[img_src]
        if "sdl2" in sys.modules:
            item["last_used"] = sdl2.SDL_GetTicks()
        return item
    try:
        data = image_loader(img_src)
        if not data:
            data = image_loader(os.path.basename(img_src))
        if not data:
            import urllib.parse
            data = image_loader(urllib.parse.unquote(img_src))
        if not data:
            import urllib.parse
            data = image_loader(urllib.parse.unquote(os.path.basename(img_src)))
        if not data:
            return None
        rw = sdl2.SDL_RWFromConstMem(data, len(data))
        surf = sdlimage.IMG_Load_RW(rw, 1)
        if surf:
            ow = surf.contents.w
            oh = surf.contents.h
            scale = min(float(max_w) / max(1, ow), float(max_h) / max(1, oh), 1.0)
            tw = max(1, int(ow * scale))
            th = max(1, int(oh * scale))
            tex = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, surf)
            sdl2.SDL_FreeSurface(surf)
            if tex:
                cur_t = sdl2.SDL_GetTicks() if "sdl2" in sys.modules else 0
                if len(cache_dict) >= 12:
                    oldest_key = min(cache_dict.keys(), key=lambda k: cache_dict[k].get("last_used", 0))
                    try:
                        sdl2.SDL_DestroyTexture(cache_dict[oldest_key]["tex"])
                    except Exception:
                        pass
                    del cache_dict[oldest_key]
                info = {"tex": tex, "w": tw, "h": th, "last_used": cur_t}
                cache_dict[img_src] = info
                return info
    except Exception as e:
        log_debug(f"get_inline_image error: {e}")
    return None

def find_image_key(src, book_images):
    if not book_images:
        return None
    if src in book_images:
        return src
    clean_src = os.path.basename(src.split('?')[0].split('#')[0]).lower()
    for bi in book_images:
        if os.path.basename(bi).lower() == clean_src:
            return bi
    for bi in book_images:
        if clean_src in bi.lower():
            return bi
    return None

def find_image_reader_line(target_img_path, reader_lines):
    if not target_img_path or not reader_lines:
        return None
    clean_target = os.path.basename(target_img_path.split('?')[0].split('#')[0]).lower()
    for line_idx, line in enumerate(reader_lines):
        if isinstance(line, dict) and line.get("type") == "image":
            src = line.get("src", "")
            if src == target_img_path or os.path.basename(src.split('?')[0].split('#')[0]).lower() == clean_target:
                return line_idx
    return None
