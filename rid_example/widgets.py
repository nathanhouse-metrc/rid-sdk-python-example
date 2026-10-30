"""Reusable widgets: scrolling column, input cards and the results view."""

from __future__ import annotations

import dataclasses
import json
import tkinter as tk
from collections.abc import Mapping
from tkinter import ttk
from typing import Any

from . import theme


def to_jsonable(value: Any) -> Any:
    """Turn SDK results (dataclasses, ObjectIds, mappings) into plain JSON-able data."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        out = {f.name: to_jsonable(getattr(value, f.name))
               for f in dataclasses.fields(value) if f.name != "raw"}
        raw = getattr(value, "raw", None)
        if raw:
            out["raw"] = to_jsonable(raw)
        return out
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def format_result(value: Any) -> str:
    if value is None:
        return "(empty response)"
    if isinstance(value, str):
        return value
    return json.dumps(to_jsonable(value), indent=2)


class ScrollFrame(ttk.Frame):
    """A vertically scrolling frame; put children in ``.body``."""

    def __init__(self, master: tk.Misc, **kwargs: Any):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, background=theme.BACKGROUND, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)
        self.body.bind("<Configure>",
                       lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(window, width=e.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        # Scroll with the wheel only while the pointer is over this frame.
        self.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", self._on_wheel))
        self.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))

    def _on_wheel(self, event: tk.Event) -> None:
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(int(-event.delta / 120), "units")


class Card(ttk.Frame):
    """A white panel with a title, an optional hint and a grid of inputs in ``.form``."""

    def __init__(self, master: tk.Misc, title: str, hint: str = "", **kwargs: Any):
        super().__init__(master, style="Card.TFrame", padding=16, **kwargs)
        ttk.Label(self, text=title, style="CardTitle.TLabel").pack(anchor="w")
        if hint:
            hint_label = ttk.Label(self, text=hint, style="CardHint.TLabel", justify="left")
            hint_label.pack(anchor="w", fill="x", pady=(2, 0))
            hint_label.bind("<Configure>", lambda e: e.widget.configure(wraplength=e.width))
        self.form = ttk.Frame(self, style="Card.TFrame", borderwidth=0)
        self.form.pack(fill="x", pady=(10, 0))
        self.form.columnconfigure(1, weight=1)
        self.buttons = ttk.Frame(self, style="Card.TFrame", borderwidth=0)
        self.buttons.pack(fill="x", pady=(12, 0))
        self._row = 0

    def add_row(self, label: str, widget: tk.Widget, hint: str = "") -> tk.Widget:
        ttk.Label(self.form, text=label, style="Card.TLabel").grid(
            row=self._row, column=0, sticky="nw", padx=(0, 12), pady=4)
        widget.grid(row=self._row, column=1, sticky="ew", pady=4)
        self._row += 1
        if hint:
            ttk.Label(self.form, text=hint, style="CardHint.TLabel").grid(
                row=self._row, column=1, sticky="w")
            self._row += 1
        return widget

    def add_button(self, text: str, command: Any, style: str = "TButton") -> ttk.Button:
        button = ttk.Button(self.buttons, text=text, command=command, style=style)
        button.pack(side="left", padx=(0, 8))
        return button


def text_box(master: tk.Misc, fonts: theme.Fonts, height: int = 4) -> tk.Text:
    return tk.Text(master, height=height, wrap="none", font=fonts.mono, background=theme.SURFACE,
                   foreground=theme.TEXT, relief="solid", borderwidth=1,
                   highlightthickness=1, highlightcolor=theme.ACCENT,
                   highlightbackground=theme.BORDER, insertbackground=theme.TEXT, undo=True)


class ResultView(ttk.Frame):
    """Read-only panel showing the outcome of the last action."""

    def __init__(self, master: tk.Misc, fonts: theme.Fonts, title: str = "Results"):
        super().__init__(master, style="Card.TFrame", padding=16)
        top = ttk.Frame(self, style="Card.TFrame", borderwidth=0)
        top.pack(fill="x")
        ttk.Label(top, text=title, style="CardTitle.TLabel").pack(side="left")
        ttk.Button(top, text="Clear", command=self.clear).pack(side="right")
        ttk.Button(top, text="Copy", command=self.copy).pack(side="right", padx=(0, 8))

        frame = ttk.Frame(self, style="Card.TFrame", borderwidth=0)
        frame.pack(fill="both", expand=True, pady=(10, 0))
        self.text = tk.Text(frame, wrap="word", font=fonts.mono, background=theme.SURFACE,
                            foreground=theme.TEXT, relief="flat", borderwidth=0,
                            padx=4, pady=4, state="disabled", cursor="xterm")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.text.tag_configure("ok", foreground=theme.SUCCESS, font=fonts.body_bold)
        self.text.tag_configure("error", foreground=theme.ERROR, font=fonts.body_bold)
        self.text.tag_configure("pending", foreground=theme.TEXT_MUTED, font=fonts.body_bold)
        self.text.tag_configure("label", foreground=theme.TEXT_MUTED, font=fonts.body)
        self.text.tag_configure("value", foreground=theme.TEXT, font=fonts.mono)
        self.text.tag_configure("url", foreground=theme.PRIMARY, font=fonts.result_url)
        self.text.bind("<Control-a>", lambda e: (self.text.tag_add("sel", "1.0", "end"), "break")[1])

    # -- writing -----------------------------------------------------------

    def _write(self, chunks: list[tuple[str, str]]) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for text, tag in chunks:
            self.text.insert("end", text, tag)
        self.text.configure(state="disabled")
        self.text.see("1.0")

    def show_pending(self, title: str) -> None:
        self._write([(f"… {title}\n", "pending")])

    def show_success(self, title: str, body: str = "", elapsed: float | None = None) -> None:
        timing = f"  ({elapsed:.2f}s)" if elapsed is not None else ""
        chunks = [(f"✔ {title}{timing}\n\n", "ok")]
        if body:
            chunks.append((body + "\n", "value"))
        self._write(chunks)

    def show_fields(self, title: str, fields: list[tuple[str, str]], url_keys: tuple[str, ...] = ()) -> None:
        chunks = [(f"✔ {title}\n\n", "ok")]
        for key, value in fields:
            chunks.append((f"{key}\n", "label"))
            chunks.append((f"{value}\n\n", "url" if key in url_keys else "value"))
        self._write(chunks)

    def show_error(self, title: str, message: str, detail: str = "") -> None:
        chunks = [(f"✖ {title}\n\n", "error"), (message + "\n", "value")]
        if detail:
            chunks.append(("\n" + detail + "\n", "value"))
        self._write(chunks)

    def clear(self) -> None:
        self._write([])

    def get(self) -> str:
        return self.text.get("1.0", "end-1c")

    def copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.get())
