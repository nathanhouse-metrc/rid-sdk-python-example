"""
Regenerate the README screenshots in docs/screenshots/.

Opens the app with sample settings, runs one action per tab (API calls go to the
local fake Retail ID API from the tests, so no keys are needed and nothing changes
in Metrc) and captures the window. Needs Pillow. On Windows the window is
captured with PrintWindow, so it works even when covered; elsewhere the window
must be visible on screen while it runs:

    pip install pillow
    python tools/take_screenshots.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import tkinter as tk
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["RID_EXAMPLE_SETTINGS"] = str(Path(tempfile.mkdtemp()) / "settings.json")

from PIL import Image, ImageGrab  # noqa: E402

from rid_example import settings  # noqa: E402
from rid_example.app import App  # noqa: E402
from tests.test_app import FakeApi  # noqa: E402

OUT = ROOT / "docs" / "screenshots"


def capture(root: tk.Tk) -> Image.Image:
    """Capture the window's client area."""
    if sys.platform == "win32":
        return _print_window(root)
    x, y = root.winfo_rootx(), root.winfo_rooty()
    return ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height()))


def _print_window(root: tk.Tk) -> Image.Image:
    import ctypes
    from ctypes import wintypes

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd = int(root.wm_frame(), 16)
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    width, height = rect.right, rect.bottom
    window_dc = user32.GetDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    PW_CLIENTONLY, PW_RENDERFULLCONTENT = 1, 2
    user32.PrintWindow(hwnd, mem_dc, PW_CLIENTONLY | PW_RENDERFULLCONTENT)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0,
                              0, 0, 0, 0, 0)
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, window_dc)
    return Image.frombuffer("RGB", (width, height), buffer, "raw", "BGRX", 0, 1)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeApi)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # Show the default location rather than this run's temporary file.
    settings.display_path = lambda path=None: "settings.json"
    root = tk.Tk()
    app = App(root, background=False)
    root.geometry("1280x820+40+40")
    root.attributes("-topmost", True)

    # Sample settings (not real keys).
    tab = app.settings_tab
    tab.vars["vendor_api_key"].set("sample-vendor-key-0001")
    tab.vars["user_api_key"].set("sample-user-key-0002")
    tab.vars["state_code"].set("md")
    tab.save()
    app.license_number.set("LIC-1")

    def use_fake_api() -> None:
        # Shown after the Settings screenshot: point API calls at the fake server.
        app.saved["base_url"] = f"http://127.0.0.1:{server.server_port}"

    def api(title: str, key: str, **inputs: str):
        def run() -> None:
            api_tab = app.api_tabs[title]
            for field, value in inputs.items():
                api_tab.set_input(key, field, value)
            api_tab.invoke(key, confirm=False)
        return run

    steps = [
        ("settings", app.settings_tab, lambda: None),
        ("encode", app.encode_tab, app.encode_tab.load_example),
        ("decode", app.decode_tab, app.decode_tab.load_example),
        ("access", app.api_tabs["Access"], api("Access", "facilities")),
        ("label-printing", app.api_tabs["Label printing"],
         api("Label printing", "packages_info", labels="PKG-1")),
        ("receiving", app.api_tabs["Receiving"],
         api("Receiving", "receive", package_label="PKG-1")),
        ("point-of-sale", app.api_tabs["Point of sale"], api("Point of sale", "sales")),
        ("catalog", app.api_tabs["Catalog"], api("Catalog", "global_product", product_id="9")),
    ]

    def shoot(i: int = 0) -> None:
        if i == 1:
            use_fake_api()
        if i >= len(steps):
            server.shutdown()
            root.destroy()
            return
        name, widget, prepare = steps[i]
        app.notebook.select(widget)
        prepare()
        app.set_status("Ready")
        root.update()

        def grab() -> None:
            image = capture(root)
            image.save(OUT / f"{name}.png", optimize=True)
            print(f"wrote {OUT / name}.png")
            shoot(i + 1)

        root.after(500, grab)

    root.after(800, shoot)
    root.mainloop()


if __name__ == "__main__":
    main()
