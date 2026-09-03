import os
import sys
import re
import html
import base64
import shutil
import zipfile
import xml.etree.ElementTree as ET

def process_inline_footnotes(text):
    if not text:
        return text
    lines = text.split('\n')
    cleaned_paras = [l.strip() for l in lines if l.strip()]
    if not cleaned_paras:
        return text
    
    # Footnote regex patterns: (*), (**), [1], (1), 1., etc.
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
    
    # 1. Replace image tags with structured inline image markers
    def img_tag_sub(m):
        src = m.group(1).split('?')[0].split('#')[0].strip()
        return f"\n\n[[INLINE_IMAGE:{src}]]\n\n"
    html_str = re.sub(r'<(?:img|image)[^>]+(?:src|href|xlink:href)=[\x27\x22]([^\x27\x22]+)[\x27\x22][^>]*>', img_tag_sub, html_str, flags=re.IGNORECASE)
    
    # 2. Strip <head>...</head>
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
    
    # 8. Clean up junk metadata lines
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

class EPUBParser:
    @staticmethod
    def parse(filepath) -> Book:
        book = Book(filepath=filepath)
        with zipfile.ZipFile(filepath, 'r') as zf:
            # Collect all image files
            img_exts = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')
            for name in zf.namelist():
                if name.lower().endswith(img_exts) and not name.startswith('__MACOSX') and not os.path.basename(name).startswith('.'):
                    book.images.append(name)
            
            def natural_keys(text):
                return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
            book.images.sort(key=natural_keys)
            
            epub_path = filepath
            book.image_loader = lambda img_name: zipfile.ZipFile(epub_path, 'r').read(img_name)

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
                                clean_chapter_content = process_inline_footnotes(clean_text)
                                book.chapters.append(Chapter(title, clean_chapter_content))
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
                        binaries[bin_id] = base64.b64decode(bin_node.text.strip())
                        book.images.append(bin_id)
                    except Exception:
                        pass
            book.image_loader = lambda b_id: binaries.get(b_id)

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
                    
                    raw_sec = "\n\n".join(text_parts)
                    clean_sec = process_inline_footnotes(raw_sec)
                    book.chapters.append(Chapter(title_text, clean_sec))
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
            parsed_content = process_inline_footnotes(text_data)
            book.chapters.append(Chapter("Content", parsed_content))
        else:
            for i in range(10):
                book.chapters.append(Chapter(f"Part {i+1} ({(i)*10}%)", text_data[i*chunk_len:(i+1)*chunk_len]))
        return book

class KindleParser:
    @staticmethod
    def parse(filepath) -> Book:
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
                    
                    img_dict = {}
                    img_exts = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')
                    for root_dir, _, fnames in os.walk(extracted_dir):
                        for fn in fnames:
                            if fn.lower().endswith(img_exts):
                                f_full = os.path.join(root_dir, fn)
                                try:
                                    with open(f_full, 'rb') as img_f:
                                        img_dict[fn] = img_f.read()
                                except Exception:
                                    pass
                    if img_dict:
                        def natural_keys(text):
                            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
                        book.images = sorted(list(img_dict.keys()), key=natural_keys)
                        book.image_loader = lambda img_fn: img_dict.get(img_fn)

                    parts = re.split(r'<mbp:pagebreak[^>]*>', html_str, flags=re.IGNORECASE)
                    
                    for idx, part in enumerate(parts):
                        part_clean = clean_html_to_clean_text(part)
                        if part_clean:
                            lines = [l.strip() for l in part_clean.split('\n') if l.strip()]
                            title = f"Part {idx+1}"
                            if lines and len(lines[0]) < 60 and not lines[0].startswith("[["):
                                title = lines[0]
                            part_final = process_inline_footnotes(part_clean)
                            book.chapters.append(Chapter(title, part_final))
                            
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
    if ext == '.epub': return EPUBParser()
    elif ext == '.fb2': return FB2Parser()
    elif ext in ['.mobi', '.azw', '.azw3']: return KindleParser()
    else: return TXTParser()

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
