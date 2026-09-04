import os
import sys

# Add local bundled vendor
VENDOR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
if os.path.exists(VENDOR_PATH):
    sys.path.insert(0, VENDOR_PATH)

if os.path.exists("/usr/trimui/lib"):
    os.environ["PYSDL2_DLL_PATH"] = "/usr/trimui/lib"

try:
    import sdl2
    import sdl2.ext
    def make_ext_color(r, g, b, a=255):
        return sdl2.ext.Color(r, g, b, a)
    def make_sdl_color(r, g, b, a=255):
        return sdl2.SDL_Color(r, g, b, a)
except Exception:
    class DummyColor:
        def __init__(self, r, g, b, a=255):
            self.r, self.g, self.b, self.a = r, g, b, a
    def make_ext_color(r, g, b, a=255):
        return DummyColor(r, g, b, a)
    def make_sdl_color(r, g, b, a=255):
        return DummyColor(r, g, b, a)

# Resolution & Hardware Dimensions
SCREEN_W = 1024
SCREEN_H = 768

# State Definitions
STATE_BROWSE = 0
STATE_READER = 1
STATE_TOC = 2
STATE_QUIT_CONFIRM = 3
STATE_IMAGE_VIEW = 4
STATE_ABOUT = 5

# Supported Book Extensions
VALID_EXTS = ['.txt', '.md', '.log', '.csv', '.json', '.epub', '.fb2', '.mobi', '.azw', '.azw3']
VALID_EXTS_SET = set(VALID_EXTS)

# Reader Themes
THEMES = [
    {
        "name": "Vintage Dark",
        "bg": make_ext_color(40, 30, 20),          # #281E14
        "text": make_sdl_color(235, 213, 171, 255),# #EBD5AB
        "header": make_ext_color(30, 20, 15),      # #1E140F
        "sel": make_ext_color(139, 69, 19),        # #8B4513
    },
    {
        "name": "Night Mode",
        "bg": make_ext_color(23, 25, 28),          # #17191C
        "text": make_sdl_color(232, 229, 221, 255),# #E8E5DD
        "header": make_ext_color(15, 17, 19),      # #0F1113
        "sel": make_ext_color(60, 60, 60),         # #3C3C3C
    },
    {
        "name": "Paper",
        "bg": make_ext_color(245, 241, 230),       # #F5F1E6
        "text": make_sdl_color(51, 48, 43, 255),   # #33302B
        "header": make_ext_color(230, 225, 210),   # #E6E1D2
        "sel": make_ext_color(118, 107, 90),       # #766B5A
    },
    {
        "name": "Warm Night",
        "bg": make_ext_color(243, 231, 199),       # #F3E7C7
        "text": make_sdl_color(61, 52, 40, 255),   # #3D3428
        "header": make_ext_color(230, 213, 173),   # #E6D5AD
        "sel": make_ext_color(216, 185, 110),      # #D8B96E
    },
    {
        "name": "AMOLED Black",
        "bg": make_ext_color(0, 0, 0),             # #000000
        "text": make_sdl_color(218, 218, 218, 255),# #DADADA
        "header": make_ext_color(5, 5, 5),         # #050505
        "sel": make_ext_color(37, 37, 37),         # #252525
    },
    {
        "name": "Forest",
        "bg": make_ext_color(24, 32, 27),          # #18201B
        "text": make_sdl_color(217, 226, 213, 255),# #D9E2D5
        "header": make_ext_color(16, 23, 17),      # #101711
        "sel": make_ext_color(73, 98, 79),         # #49624F
    },
    {
        "name": "Coastal Earth",
        "bg": make_ext_color(44, 54, 57),          # #2C3639 Dark Charcoal Blue
        "text": make_sdl_color(220, 215, 201, 255),# #DCD7C9 Warm Ivory
        "header": make_ext_color(63, 78, 79),      # #3F4E4F Muted Slate Green
        "sel": make_ext_color(162, 123, 92),       # #A27B5C Dusty Earth Brown
    }
]

# Library-only palette
LIBRARY_THEMES = [
    {
        "bg": make_ext_color(40, 30, 20),          # #281E14
        "header": make_ext_color(30, 20, 15),      # #1E140F
        "divider": make_ext_color(76, 56, 39),     # #4C3827
        "text": make_sdl_color(235, 213, 171, 255),# #EBD5AB
        "secondary": make_sdl_color(184, 159, 118, 255),# #B89F76
        "accent": make_ext_color(210, 149, 93),    # #D2955D
        "sel_border": make_ext_color(210, 149, 93),# #D2955D
        "sel_bg": make_ext_color(64, 48, 33),      # #403021
        "sel_text": make_sdl_color(245, 225, 190, 255),# #F5E1BE
        "sel_sec": make_sdl_color(195, 175, 140, 255), # #C3AF8C
    },
    {
        "bg": make_ext_color(20, 20, 20),          # #141414
        "header": make_ext_color(10, 10, 10),      # #0A0A0A
        "divider": make_ext_color(52, 52, 52),     # #343434
        "text": make_sdl_color(212, 212, 212, 255),# #D4D4D4
        "secondary": make_sdl_color(154, 154, 154, 255),# #9A9A9A
        "accent": make_ext_color(164, 177, 194),   # #A4B1C2
        "sel_border": make_ext_color(102, 137, 181),# #6689B5
        "sel_bg": make_ext_color(38, 42, 48),      # #262A30
        "sel_text": make_sdl_color(240, 240, 240, 255),# #F0F0F0
        "sel_sec": make_sdl_color(180, 180, 180, 255), # #B4B4B4
    },
    {
        "bg": make_ext_color(244, 236, 216),       # #F4ECD8
        "header": make_ext_color(220, 210, 190),   # #DCD2BE
        "divider": make_ext_color(204, 193, 171),  # #CCC1AB
        "text": make_sdl_color(59, 52, 40, 255),   # #3B3428
        "secondary": make_sdl_color(118, 107, 90, 255),# #766B5A
        "accent": make_ext_color(107, 91, 149),    # #6B5B95
        "sel_border": make_ext_color(168, 120, 40),# #A87828
        "sel_bg": make_ext_color(252, 247, 235),   # #FCF7EB
        "sel_text": make_sdl_color(30, 26, 18, 255),# #1E1A12
        "sel_sec": make_sdl_color(95, 85, 70, 255),# #5F5546
    },
    {
        "bg": make_ext_color(243, 231, 199),       # #F3E7C7
        "header": make_ext_color(230, 213, 173),   # #E6D5AD
        "divider": make_ext_color(216, 197, 157),  # #D8C59D
        "text": make_sdl_color(61, 52, 40, 255),   # #3D3428
        "secondary": make_sdl_color(117, 104, 84, 255),# #756854
        "accent": make_ext_color(168, 120, 40),    # #A87828
        "sel_border": make_ext_color(168, 120, 40),# #A87828
        "sel_bg": make_ext_color(238, 224, 185),   # #EEE0B9
        "sel_text": make_sdl_color(55, 42, 25, 255),# #372A19
        "sel_sec": make_sdl_color(110, 85, 55, 255),# #6E5537
    },
    {
        "bg": make_ext_color(0, 0, 0),             # #000000
        "header": make_ext_color(5, 5, 5),         # #050505
        "divider": make_ext_color(26, 26, 26),     # #1A1A1A
        "text": make_sdl_color(216, 216, 216, 255),# #D8D8D8
        "secondary": make_sdl_color(136, 136, 136, 255),# #888888
        "accent": make_ext_color(143, 168, 199),   # #8FA8C7
        "sel_border": make_ext_color(112, 112, 112),# #707070
        "sel_bg": make_ext_color(28, 28, 28),      # #1C1C1C
        "sel_text": make_sdl_color(240, 240, 240, 255),# #F0F0F0
        "sel_sec": make_sdl_color(170, 170, 170, 255), # #AAAAAA
    },
    {
        "bg": make_ext_color(24, 32, 27),          # #18201B
        "header": make_ext_color(16, 23, 17),      # #101711
        "divider": make_ext_color(52, 66, 55),     # #344237
        "text": make_sdl_color(217, 226, 213, 255),# #D9E2D5
        "secondary": make_sdl_color(158, 173, 159, 255),# #9EAD9F
        "accent": make_ext_color(168, 184, 138),   # #A8B88A
        "sel_border": make_ext_color(112, 138, 104),# #708A68
        "sel_bg": make_ext_color(41, 54, 45),      # #29362D
        "sel_text": make_sdl_color(240, 244, 237, 255),# #F0F4ED
        "sel_sec": make_sdl_color(184, 195, 184, 255), # #B8C3B8
    },
    {
        "bg": make_ext_color(44, 54, 57),          # #2C3639 Dark Charcoal Blue
        "header": make_ext_color(63, 78, 79),      # #3F4E4F Muted Slate Green
        "divider": make_ext_color(74, 91, 92),     # #4A5B5C Muted Slate Divider
        "text": make_sdl_color(220, 215, 201, 255),# #DCD7C9 Warm Ivory
        "secondary": make_sdl_color(170, 166, 155, 255),# #AAA69B Muted Ivory
        "accent": make_ext_color(162, 123, 92),    # #A27B5C Dusty Earth Brown
        "sel_border": make_ext_color(162, 123, 92),# #A27B5C Dusty Earth Brown
        "sel_bg": make_ext_color(58, 68, 71),      # #3A4447 Deep Slate
        "sel_text": make_sdl_color(240, 237, 228, 255),# #F0EDE4 Pure Ivory
        "sel_sec": make_sdl_color(190, 185, 172, 255), # #BEB9AC
    }
]

def get_book_display_metadata(filename):
    """Derive library label from a filename without changing the real path."""
    stem = os.path.splitext(filename)[0]
    return stem.strip(), ""

