"""
Colours, fonts and ttk styles for the app.

Every colour and font the UI uses is defined here, so the look can be changed
in one place.

PLACEHOLDERS: these values are neutral stand-ins, not Metrc brand values. Replace
them (and add the logo in ``App._build_header``) from the metrc-brand-guidelines
skill once it is available.
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# -- colours -----------------------------------------------------------------

PRIMARY = "#0B3D5C"        # header bar, primary buttons, selected tab
PRIMARY_ACTIVE = "#145A85"  # primary button hover/pressed
ACCENT = "#2BA8A4"          # header rule, focus highlights
BACKGROUND = "#F4F6F8"      # window background
SURFACE = "#FFFFFF"         # cards and inputs
BORDER = "#D5DBE1"
TEXT = "#1E2A33"
TEXT_MUTED = "#5B6B78"
TEXT_ON_PRIMARY = "#FFFFFF"
SUCCESS = "#1E7D4F"
ERROR = "#B3261E"
WARNING = "#8A5A00"

# -- fonts -------------------------------------------------------------------

# First installed family wins; Tk falls back to its default otherwise.
HEADING_FAMILIES = ("Segoe UI Semibold", "Segoe UI", "Helvetica Neue", "Arial")
BODY_FAMILIES = ("Segoe UI", "Helvetica Neue", "Arial")
MONO_FAMILIES = ("Cascadia Mono", "Consolas", "Menlo", "Courier New")


def _first_installed(root: tk.Misc, families: tuple[str, ...]) -> str:
    installed = set(tkfont.families(root))
    return next((f for f in families if f in installed), "TkDefaultFont")


class Fonts:
    """Named Tk fonts (named fonts survive ttk style configuration reliably)."""

    def __init__(self, root: tk.Misc):
        heading = _first_installed(root, HEADING_FAMILIES)
        body = _first_installed(root, BODY_FAMILIES)
        mono = _first_installed(root, MONO_FAMILIES)

        def font(family: str, size: int, weight: str = "normal") -> tkfont.Font:
            return tkfont.Font(root, family=family, size=size, weight=weight)

        self.title = font(heading, 16)
        self.heading = font(heading, 12)
        self.body = font(body, 10)
        self.body_bold = font(body, 10, "bold")
        self.small = font(body, 9)
        self.mono = font(mono, 10)
        self.result_url = font(mono, 13, "bold")


def apply(root: tk.Tk) -> Fonts:
    """Configure ttk styles on ``root`` and return the fonts in use."""
    fonts = Fonts(root)
    root.configure(background=BACKGROUND)
    # Classic and ttk widgets without an explicit font use these named defaults.
    # (Setting "*Font" in the option database would override ttk style fonts.)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        tkfont.nametofont(name, root).configure(family=fonts.body.cget("family"),
                                                size=fonts.body.cget("size"))
    root.option_add("*TCombobox*Listbox.font", fonts.body)

    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=BACKGROUND, foreground=TEXT, font=fonts.body,
                    bordercolor=BORDER, focuscolor=ACCENT)
    style.configure("TFrame", background=BACKGROUND)
    style.configure("Card.TFrame", background=SURFACE, relief="solid", borderwidth=1)
    style.configure("Header.TFrame", background=PRIMARY)
    style.configure("Rule.TFrame", background=ACCENT)

    style.configure("TLabel", background=BACKGROUND, foreground=TEXT)
    style.configure("Card.TLabel", background=SURFACE)
    style.configure("CardTitle.TLabel", background=SURFACE, font=fonts.heading, foreground=PRIMARY)
    style.configure("CardHint.TLabel", background=SURFACE, foreground=TEXT_MUTED, font=fonts.small)
    style.configure("Hint.TLabel", foreground=TEXT_MUTED, font=fonts.small)
    style.configure("Section.TLabel", font=fonts.heading, foreground=PRIMARY)
    style.configure("HeaderTitle.TLabel", background=PRIMARY, foreground=TEXT_ON_PRIMARY,
                    font=fonts.title)
    style.configure("HeaderSub.TLabel", background=PRIMARY, foreground=TEXT_ON_PRIMARY,
                    font=fonts.small)
    style.configure("Status.TLabel", background=SURFACE, foreground=TEXT_MUTED, font=fonts.small,
                    padding=(12, 4))

    style.configure("TCheckbutton", background=SURFACE)
    style.configure("TRadiobutton", background=SURFACE)
    style.map("TCheckbutton", background=[("active", SURFACE)])
    style.map("TRadiobutton", background=[("active", SURFACE)])

    style.configure("TEntry", fieldbackground=SURFACE, padding=4)
    style.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)])
    style.configure("TCombobox", fieldbackground=SURFACE, padding=4)
    style.map("TCombobox", fieldbackground=[("readonly", SURFACE)],
              selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", TEXT)])
    style.configure("TSpinbox", fieldbackground=SURFACE, padding=4)

    style.configure("TButton", padding=(12, 6), background=SURFACE, bordercolor=BORDER)
    style.map("TButton", background=[("active", BACKGROUND)])
    style.configure("Primary.TButton", background=PRIMARY, foreground=TEXT_ON_PRIMARY,
                    bordercolor=PRIMARY, font=fonts.body_bold)
    style.map("Primary.TButton",
              background=[("disabled", BORDER), ("active", PRIMARY_ACTIVE)],
              foreground=[("disabled", TEXT_MUTED)])
    style.configure("Danger.TButton", background=SURFACE, foreground=ERROR, bordercolor=ERROR,
                    font=fonts.body_bold)
    style.map("Danger.TButton", background=[("active", BACKGROUND)])

    style.configure("TNotebook", background=BACKGROUND, borderwidth=0, tabmargins=(12, 8, 12, 0))
    style.configure("TNotebook.Tab", padding=(14, 6), background=BACKGROUND, foreground=TEXT_MUTED,
                    bordercolor=BORDER)
    style.map("TNotebook.Tab",
              background=[("selected", SURFACE)],
              foreground=[("selected", PRIMARY)],
              font=[("selected", fonts.body_bold)])
    return fonts
