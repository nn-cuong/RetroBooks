import os
import sys
import re
import html
import base64
import shutil
import zipfile
import struct
import urllib.parse
import xml.etree.ElementTree as ET

def process_inline_footnotes(text):
    if not text:
        return text
    lines = text.split('\n')
    cleaned_paras = [l.strip() for l in lines if l.strip()]
    if not cleaned_paras:
        return text
    
    fn_header_regex = re.compile(r'^(\(\*+\)|\*+|\(?\d+\)?(?:\.|\:)|\[\d+\])\s*(.*)$', re.DOTALL)
    trailing_defs = []
    end_idx = len(cleaned_paras)
    
    while end_idx > 0:
        p = cleaned_paras[end_idx - 1]
        m = fn_header_regex.match(p)
        if m and len(p) > 2:
            marker = m.group(1).strip()
            content = m.group(2).strip()
            if not content:
                content = marker
            trailing_defs.append((marker, content, end_idx - 1))
            end_idx -= 1
        elif p.lower() in ("chú thích", "chú thích:", "footnotes", "footnotes:", "notes", "notes:", "ghi chú", "ghi chú:"):
            end_idx -= 1
            break
        else:
            break
            
    if not trailing_defs:
        return text
        
    trailing_defs.reverse()
    body_paras = list(cleaned_paras[:end_idx])
    
    for marker, content, _ in trailing_defs:
        search_markers = [marker]
        if marker.startswith('(') and marker.endswith(')'):
            search_markers.append(marker[1:-1])
        elif marker.startswith('[') and marker.endswith(']'):
            search_markers.append(marker[1:-1])
            search_markers.append(f"({marker[1:-1]})")
        
        found = False
        for b_idx in range(len(body_paras) - 1, -1, -1):
            bp = body_paras[b_idx]
            if bp.startswith("[[INLINE_FOOTNOTE:") or bp.startswith("[[INLINE_IMAGE:"):
                continue
            for sm in search_markers:
                if sm in bp:
                    fn_tag = f"[[INLINE_FOOTNOTE:{marker}|{content}]]"
                    body_paras.insert(b_idx + 1, fn_tag)
                    found = True
                    break
            if found:
                break
                
        if not found:
            body_paras.append(f"[[INLINE_FOOTNOTE:{marker}|{content}]]")
            
    return "\n\n".join(body_paras)

def clean_html_to_clean_text(html_str):
    if not html_str:
        return ""
    import re
    import html
    
    # 1. Replace image tags with structured inline image markers
    def img_tag_sub(m):
        src = m.group(1).split('?')[0].split('#')[0].strip()
        return f"\n\n[[INLINE_IMAGE:{src}]]\n\n"
    html_str = re.sub(r'<(?:img|image)[^>]+(?:src|href|xlink:href)=[\x27\x22]([^\x27\x22]+)[\x27\x22][^>]*>', img_tag_sub, html_str, flags=re.IGNORECASE)
    
    # 2. Strip <head>...</head> (contains meta tags, stylesheets, scripts)
    html_str = re.sub(r'<head[^>]*>.*?</head>', '', html_str, flags=re.DOTALL | re.IGNORECASE)
    
    # 3. Strip <style>...</style> and <script>...</script>
    html_str = re.sub(r'<style[^>]*>.*?</style>', '', html_str, flags=re.DOTALL | re.IGNORECASE)
    html_str = re.sub(r'<script[^>]*>.*?</script>', '', html_str, flags=re.DOTALL | re.IGNORECASE)
    
    # 4. Strip XML processing instructions and comments
    html_str = re.sub(r'<\?xml.*?\?>', '', html_str, flags=re.DOTALL | re.IGNORECASE)
    html_str = re.sub(r'<!--.*?-->', '', html_str, flags=re.DOTALL | re.IGNORECASE)
    
    # 5. Convert block tags to newlines
    html_str = re.sub(r'<(p|br|div|h[1-6]|li|tr|td|th|blockquote|section|article)[^>]*>', '\n', html_str, flags=re.IGNORECASE)
    
    # 6. Strip all remaining HTML tags
    html_str = re.sub(r'<[^>]+>', '', html_str)
    
    # 7. Unescape HTML entities
    html_str = html.unescape(html_str)
    html_str = html_str.replace('\xa0', ' ')
    
    # 8. Clean up junk metadata lines (Calibre metadata, CSS residue, UUIDs, ISBNs)
    clean_lines = []
    metadata_patterns = [
        re.compile(r'^calibre:.*', re.IGNORECASE),
        re.compile(r'^@page\s*\{.*', re.IGNORECASE),
        re.compile(r'^\.[a-zA-Z0-9_-]+\s*\{.*', re.IGNORECASE),
        re.compile(r'^(?:urn:)?uuid:[0-9a-fA-F-]+', re.IGNORECASE),
        re.compile(r'^(?:file|ebook)\s+generated\s+by\s+.*', re.IGNORECASE),
        re.compile(r'^body\s*\{.*', re.IGNORECASE),
        re.compile(r'^\s*\{\s*margin[^}]*\}', re.IGNORECASE),
    ]
    for line in html_str.split('\n'):
        l_str = line.strip()
        if not l_str:
            clean_lines.append("")
            continue
        is_junk = any(p.match(l_str) for p in metadata_patterns)
        if not is_junk:
            clean_lines.append(line)
            
    res_text = "\n".join(clean_lines)
    res_text = re.sub(r'\n{3,}', '\n\n', res_text).strip()
    return res_text

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
        self.images = []
        self.image_loader = None
        self.metadata = {}

def make_epub_image_loader(epub_file, all_image_names, opf_dir="", in_memory_dict=None):
    import urllib.parse
    lookup = {}
    for name in all_image_names:
        norm_name = name.replace('\\', '/')
        lookup[norm_name] = norm_name
        lookup[norm_name.lower()] = norm_name
        unq_lower = urllib.parse.unquote(norm_name).lower()
        lookup[unq_lower] = norm_name
        
        base = os.path.basename(norm_name).lower()
        if base not in lookup:
            lookup[base] = norm_name
        unq_base = urllib.parse.unquote(base).lower()
        if unq_base not in lookup:
            lookup[unq_base] = norm_name
            
        subparts = norm_name.split('/')
        for i in range(1, len(subparts)):
            subpath = '/'.join(subparts[i:]).lower()
            if subpath not in lookup:
                lookup[subpath] = norm_name

    def loader(img_src):
        if not img_src:
            return None
        clean_src = img_src.replace('\\', '/').strip()
        target = lookup.get(clean_src)
        if not target:
            target = lookup.get(clean_src.lower())
        if not target:
            target = lookup.get(urllib.parse.unquote(clean_src).lower())
        if not target:
            norm_without_dots = clean_src.lstrip('./').lstrip('../')
            target = lookup.get(norm_without_dots.lower())
            if not target and opf_dir:
                combined = f"{opf_dir}/{norm_without_dots}".replace('\\', '/').lstrip('/')
                target = lookup.get(combined.lower())
        if not target:
            base = os.path.basename(clean_src).lower()
            unquoted_base = urllib.parse.unquote(base).lower()
            target = lookup.get(base) or lookup.get(unquoted_base)
        if not target:
            clean_base = os.path.basename(clean_src).lower()
            for img_n in all_image_names:
                if os.path.basename(img_n).lower() == clean_base:
                    target = img_n
                    break
        if not target:
            target = clean_src

        if in_memory_dict is not None:
            clean_b = os.path.basename(clean_src).lower()
            return (in_memory_dict.get(target) or 
                    in_memory_dict.get(target.lower()) or 
                    in_memory_dict.get(clean_b) or 
                    in_memory_dict.get(urllib.parse.unquote(clean_b).lower()))

        try:
            with zipfile.ZipFile(epub_file, 'r') as zf_loader:
                return zf_loader.read(target)
        except Exception:
            return None

    return loader

class EPUBParser:
    @staticmethod
    def parse(filepath) -> Book:
        book = Book(filepath=filepath)
        with zipfile.ZipFile(filepath, 'r') as zf:
            img_exts = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')
            for name in zf.namelist():
                if name.lower().endswith(img_exts) and not name.startswith('__MACOSX') and not os.path.basename(name).startswith('.'):
                    book.images.append(name)
            
            def natural_keys(text):
                return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
            book.images.sort(key=natural_keys)
            
            epub_path = filepath
            container_xml = zf.read('META-INF/container.xml')
            root = ET.fromstring(container_xml)
            opf_path = ""
            for child in root.iter():
                if child.tag.endswith('rootfile'):
                    opf_path = child.attrib.get('full-path')
                    break
            opf_dir = os.path.dirname(opf_path) if opf_path else ""
            book.image_loader = make_epub_image_loader(epub_path, book.images, opf_dir)

            if opf_path:
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
                        except Exception:
                            pass
                
                for idx, item_id in enumerate(spine):
                    if item_id in manifest:
                        href = manifest[item_id]
                        item_path = href if not opf_dir else f"{opf_dir}/{href}"
                        try:
                            html_bytes = zf.read(item_path)
                            html_str = html_bytes.decode('utf-8', errors='ignore')
                            clean_text = clean_html_to_clean_text(html_str)
                            if clean_text:
                                title = toc_map.get(href, f"Chapter {idx+1}")
                                book.chapters.append(Chapter(title, clean_text))
                        except Exception:
                            pass
        return book

class FB2Parser:
    @staticmethod
    def parse(filepath) -> Book:
        book = Book(filepath=filepath)
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            xml_content = f.read()
        xml_content = re.sub(r'\sxmlns="[^"]+"', '', xml_content, count=1)
        
        def fb2_img_sub(m):
            src = m.group(1).lstrip('#').strip()
            return f"\n\n[[INLINE_IMAGE:{src}]]\n\n"
        xml_content = re.sub(r'<image[^>]+(?:href|xlink:href)=[\x27\x22]([^\x27\x22]+)[\x27\x22][^>]*>', fb2_img_sub, xml_content, flags=re.IGNORECASE)

        try:
            root = ET.fromstring(xml_content)
            
            binaries = {}
            for bin_node in root.findall('.//binary'):
                bin_id = bin_node.attrib.get('id', '')
                if bin_id and bin_node.text:
                    try:
                        bin_bytes = base64.b64decode(bin_node.text.strip())
                        binaries[bin_id] = bin_bytes
                        binaries[bin_id.lower()] = bin_bytes
                        base = os.path.basename(bin_id.replace('\\', '/')).lower()
                        binaries[base] = bin_bytes
                        book.images.append(bin_id)
                    except Exception:
                        pass
            
            def fb2_loader(b_id):
                if not b_id: return None
                clean_id = b_id.lstrip('#').strip()
                base = os.path.basename(clean_id.replace('\\', '/')).lower()
                return binaries.get(b_id) or binaries.get(clean_id) or binaries.get(clean_id.lower()) or binaries.get(base)

            book.image_loader = fb2_loader

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
                        if p_text:
                            text_parts.append(p_text)
                    
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
        try:
            try:
                import imghdr
            except ImportError:
                import types
                _ih = types.ModuleType('imghdr')
                def _what(file, h=None):
                    if h is None:
                        if isinstance(file, (str, bytes)):
                            with open(file, 'rb') as f: h = f.read(32)
                        elif hasattr(file, 'tell') and hasattr(file, 'seek'):
                            pos = file.tell(); h = file.read(32); file.seek(pos)
                        else: return None
                    if len(h) >= 2 and h[:2] == b'\xff\xd8': return 'jpeg'
                    if len(h) >= 8 and h[:8] == b'\x89PNG\r\n\x1a\n': return 'png'
                    if len(h) >= 6 and h[:6] in (b'GIF87a', b'GIF89a'): return 'gif'
                    if len(h) >= 2 and h[:2] == b'BM': return 'bmp'
                    if len(h) >= 12 and h[:4] == b'RIFF' and h[8:12] == b'WEBP': return 'webp'
                    return None
                _ih.what = _what
                sys.modules['imghdr'] = _ih
            import mobi
            extracted_dir, filepath_extracted = mobi.extract(filepath)
            try:
                if filepath_extracted.lower().endswith('.epub'):
                    book = EPUBParser.parse(filepath_extracted)
                    book.filepath = filepath # Restore real filepath
                    
                    # Pre-cache images into memory before temp directory is deleted
                    in_mem_images = {}
                    try:
                        with zipfile.ZipFile(filepath_extracted, 'r') as zf:
                            for img_name in book.images:
                                try:
                                    bdata = zf.read(img_name)
                                    in_mem_images[img_name] = bdata
                                    in_mem_images[img_name.lower()] = bdata
                                    base = os.path.basename(img_name).lower()
                                    in_mem_images[base] = bdata
                                    in_mem_images[urllib.parse.unquote(base).lower()] = bdata
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    
                    # Extract opf_dir from container
                    opf_dir = ""
                    try:
                        with zipfile.ZipFile(filepath_extracted, 'r') as zf:
                            container_xml = zf.read('META-INF/container.xml')
                            root = ET.fromstring(container_xml)
                            for child in root.iter():
                                if child.tag.endswith('rootfile'):
                                    opf_p = child.attrib.get('full-path')
                                    if opf_p:
                                        opf_dir = os.path.dirname(opf_p)
                                    break
                    except Exception:
                        pass

                    book.image_loader = make_epub_image_loader("", book.images, opf_dir, in_memory_dict=in_mem_images)
                    return book
                else:
                    book = Book(filepath=filepath)
                    with open(filepath_extracted, 'r', encoding='utf-8', errors='ignore') as f:
                        html_str = f.read()
                    
                    img_dict = {}
                    img_exts = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')
                    for root_dir, _, fnames in os.walk(extracted_dir):
                        for fn in fnames:
                            if fn.lower().endswith(img_exts):
                                f_full = os.path.join(root_dir, fn)
                                try:
                                    with open(f_full, 'rb') as img_f:
                                        bdata = img_f.read()
                                        img_dict[fn] = bdata
                                        img_dict[fn.lower()] = bdata
                                        img_dict[f_full] = bdata
                                except Exception:
                                    pass
                    if img_dict:
                        def natural_keys(text):
                            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
                        book.images = sorted(list(set(img_dict.keys())), key=natural_keys)
                        def kindle_loader(img_fn):
                            if not img_fn: return None
                            base = os.path.basename(img_fn.replace('\\', '/'))
                            return img_dict.get(img_fn) or img_dict.get(img_fn.lower()) or img_dict.get(base) or img_dict.get(base.lower())
                        book.image_loader = kindle_loader

                    parts = re.split(r'<mbp:pagebreak[^>]*>', html_str, flags=re.IGNORECASE)
                    
                    for idx, part in enumerate(parts):
                        part_clean = clean_html_to_clean_text(part)
                        if part_clean:
                            lines = [l.strip() for l in part_clean.split('\n') if l.strip()]
                            title = f"Part {idx+1}"
                            if lines and len(lines[0]) < 60 and not lines[0].startswith("[["):
                                title = lines[0]
                            book.chapters.append(Chapter(title, part_clean))
                            
                    if not book.chapters:
                        book.chapters.append(Chapter("Content", "No readable text found."))
                    return book
            finally:
                try:
                    shutil.rmtree(extracted_dir)
                except Exception:
                    pass
        except Exception as e:
            book = Book(filepath=filepath)
            book.chapters.append(Chapter("Error", "This ebook is DRM-protected or unsupported.\n\nError details: " + str(e)))
            return book

def get_parser(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.epub':
        return EPUBParser()
    elif ext == '.fb2':
        return FB2Parser()
    elif ext in ['.mobi', '.azw', '.azw3']:
        return KindleParser()
    else:
        return TXTParser()

def extract_epub_cover_data(filepath):
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            names = zf.namelist()
            img_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
            covers = [n for n in names if any(n.lower().endswith(ext) for ext in img_exts) and 'cover' in os.path.basename(n).lower() and not n.startswith('__MACOSX')]
            if covers:
                return zf.read(covers[0])
            imgs = [n for n in names if any(n.lower().endswith(ext) for ext in img_exts) and not n.startswith('__MACOSX') and not os.path.basename(n).startswith('.')]
            if imgs:
                return zf.read(imgs[0])
    except Exception:
        pass
    return None

def extract_kindle_cover_data(filepath):
    """Extracts raw cover image data from MOBI, AZW, or AZW3 files via PDB header in <1ms."""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(78)
            if len(header) < 78:
                return None
            num_sections = struct.unpack_from('>H', header, 76)[0]
            if num_sections <= 0:
                return None
            sec_table_len = num_sections * 8
            sec_table = f.read(sec_table_len)
            if len(sec_table) < sec_table_len:
                return None
            offsets = [struct.unpack_from('>I', sec_table, i * 8)[0] for i in range(num_sections)]
            
            sec0_len = (offsets[1] - offsets[0]) if num_sections > 1 else 4096
            f.seek(offsets[0])
            sec0 = f.read(min(sec0_len, 4096))
            
            first_img_idx = None
            cover_offset = None
            
            if len(sec0) >= 112 and sec0[16:20] == b'MOBI':
                header_len = struct.unpack_from('>I', sec0, 20)[0]
                first_img_idx = struct.unpack_from('>I', sec0, 108)[0]
                if len(sec0) >= 132:
                    exth_flags = struct.unpack_from('>I', sec0, 128)[0]
                    if exth_flags & 0x40:
                        exth_offset = 16 + header_len
                        if len(sec0) >= exth_offset + 12 and sec0[exth_offset:exth_offset+4] == b'EXTH':
                            exth_len, rec_count = struct.unpack_from('>II', sec0, exth_offset+4)
                            pos = exth_offset + 12
                            for _ in range(rec_count):
                                if pos + 8 > len(sec0):
                                    break
                                rec_type, rec_len = struct.unpack_from('>II', sec0, pos)
                                if rec_len < 8 or pos + rec_len > len(sec0):
                                    break
                                if rec_type == 201: # CoverOffset
                                    val_len = rec_len - 8
                                    if val_len == 4:
                                        cover_offset = struct.unpack_from('>I', sec0, pos + 8)[0]
                                    elif val_len == 2:
                                        cover_offset = struct.unpack_from('>H', sec0, pos + 8)[0]
                                    break
                                pos += rec_len
            
            target_sec = None
            if first_img_idx is not None and first_img_idx < num_sections:
                if cover_offset is not None and (first_img_idx + cover_offset) < num_sections:
                    target_sec = first_img_idx + cover_offset
                else:
                    target_sec = first_img_idx
            
            if target_sec is not None and target_sec < num_sections:
                f.seek(offsets[target_sec])
                end_off = offsets[target_sec + 1] if target_sec + 1 < num_sections else None
                data = f.read(end_off - offsets[target_sec]) if end_off else f.read()
                if data.startswith((b'\xff\xd8\xff', b'\x89PNG', b'GIF8', b'RIFF')):
                    return data
                    
            for i in range(min(num_sections, 500)):
                f.seek(offsets[i])
                sig = f.read(4)
                if sig.startswith((b'\xff\xd8\xff', b'\x89PNG', b'GIF8', b'RIFF')):
                    f.seek(offsets[i])
                    end_off = offsets[i + 1] if i + 1 < num_sections else None
                    return f.read(end_off - offsets[i]) if end_off else f.read()
    except Exception:
        pass
    return None
