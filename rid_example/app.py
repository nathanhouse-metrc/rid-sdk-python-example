"""Main window: header, tabs and status bar."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

import retailid
from retailid import RetailIdClient, RetailIdConfig, RetailIdConfigError

from . import api_tabs, settings, theme
from .codec_tabs import DecodeTab, EncodeTab
from .widgets import Card, ResultView

Done = Callable[[Any, "BaseException | None"], None]


def _mask(key: str) -> str:
    return "(not set)" if not key else "•" * 8 + key[-4:] if len(key) > 8 else "•" * len(key)


def _target(config: RetailIdConfig) -> str:
    if config.base_url:
        return config.base_url.rstrip("/")
    return f"https://api-{(config.state_code or '').strip().lower()}.metrc.com"


class SettingsTab(ttk.Frame):
    LABELS = {
        "vendor_api_key": ("Vendor API key", "Your software's key (Basic auth username)"),
        "user_api_key": ("User API key", "The Metrc user's key (Basic auth password)"),
        "state_code": ("State code", "Two-letter market, e.g. md → https://api-md.metrc.com"),
        "base_url": ("Base URL", "Optional; overrides the state code (use for the Sandbox)"),
    }

    def __init__(self, master: tk.Misc, app: App):
        super().__init__(master)
        self.app = app
        fonts = app.fonts
        self.columnconfigure(0, weight=2, uniform="cols")
        self.columnconfigure(1, weight=3, uniform="cols")
        self.rowconfigure(0, weight=1)
        left = ttk.Frame(self)
        left.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)

        card = Card(left, "Retail ID API settings",
                    f"Saved to {settings.display_path()} — this file is git-ignored. "
                    "API tabs use the saved values.")
        card.pack(fill="x")

        self.vars = {key: tk.StringVar(value=app.saved.get(key, "")) for key in settings.FIELDS}
        self.key_entries: list[ttk.Entry] = []
        for key in settings.FIELDS:
            label, hint = self.LABELS[key]
            secret = key.endswith("api_key")
            entry = ttk.Entry(card.form, textvariable=self.vars[key], font=fonts.mono,
                              show="•" if secret else "")
            if secret:
                self.key_entries.append(entry)
            card.add_row(label, entry, hint)
            self.vars[key].trace_add("write", lambda *_: self._update_dirty())

        self.show_keys = tk.BooleanVar(value=False)
        card.add_row("", ttk.Checkbutton(card.form, text="Show keys", variable=self.show_keys,
                                         command=self._toggle_keys))
        self.dirty_label = ttk.Label(card.form, text="", style="CardHint.TLabel")
        card.add_row("", self.dirty_label)

        card.add_button("Save", self.save, style="Primary.TButton")
        card.add_button("Revert", self.revert)
        self.test_button = card.add_button("Test connection", self.test_connection)

        self.results = ResultView(self, fonts)
        self.results.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        self.show_summary("Loaded settings" if any(app.saved.values()) else "No settings saved yet")

    def values(self) -> dict[str, str]:
        return {key: var.get().strip() for key, var in self.vars.items()}

    def _toggle_keys(self) -> None:
        for entry in self.key_entries:
            entry.configure(show="" if self.show_keys.get() else "•")

    def _update_dirty(self) -> None:
        dirty = any(self.values()[k] != self.app.saved.get(k, "") for k in settings.FIELDS)
        self.dirty_label.configure(text="Unsaved changes" if dirty else "")

    def show_summary(self, title: str) -> None:
        saved = self.app.saved
        try:
            target = _target(settings.to_config(saved))
            state = "Ready: API tabs will use these settings."
        except RetailIdConfigError as e:
            target = "(incomplete)"
            state = f"Incomplete: {e}"
        self.results.show_fields(title, [
            ("Vendor API key", _mask(saved.get("vendor_api_key", ""))),
            ("User API key", _mask(saved.get("user_api_key", ""))),
            ("State code", saved.get("state_code") or "(not set)"),
            ("Base URL", saved.get("base_url") or "(not set)"),
            ("Requests go to", target),
            ("Status", state),
        ])

    def save(self) -> None:
        values = {**self.app.saved, **self.values()}
        values["state_code"] = values["state_code"].lower()
        self.vars["state_code"].set(values["state_code"])
        path = settings.save_settings(values)
        self.app.saved = settings.load_settings(path)
        self._update_dirty()
        self.show_summary("Settings saved")
        self.app.set_status(f"Settings saved to {path}")

    def revert(self) -> None:
        for key, var in self.vars.items():
            var.set(self.app.saved.get(key, ""))
        self.show_summary("Reverted to saved settings")

    def test_connection(self) -> None:
        try:
            config = self.app.saved_config()
        except RetailIdConfigError as e:
            self.results.show_error(*api_tabs.describe_error(e))
            return
        self.test_button.state(["disabled"])
        self.results.show_pending(f"GET {_target(config)}/facilities/v2/")

        def work() -> Any:
            with RetailIdClient.from_config(config) as client:
                return client.get_facilities()

        def done(result: Any, error: BaseException | None) -> None:
            self.test_button.state(["!disabled"])
            if error is not None:
                self.results.show_error(*api_tabs.describe_error(error))
                self.app.set_status("Connection test failed", ok=False)
                return
            names = [f"{f.get('License', {}).get('Number', '?')}  {f.get('Name', '')}"
                     if isinstance(f, dict) else str(f) for f in result]
            self.results.show_success(f"Connected — {len(result)} facility(ies) visible",
                                      "\n".join(names))
            self.app.set_status("Connection test succeeded")

        self.app.run_task(work, done)


class App:
    """The application. ``background=False`` runs API calls inline (used by tests)."""

    def __init__(self, root: tk.Tk, background: bool = True):
        self.root = root
        self.background = background
        self.fonts = theme.apply(root)
        root.title("Retail ID SDK Explorer")
        root.geometry("1280x820")
        root.minsize(980, 640)

        self.saved = settings.load_settings()
        self.license_number = tk.StringVar(value=self.saved.get(settings.LICENSE_FIELD, ""))
        self._results: queue.Queue[tuple[Done, Any, BaseException | None]] = queue.Queue()

        self._build_header()
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)
        self.status = ttk.Label(root, text="Ready", style="Status.TLabel", anchor="w")
        self.status.pack(fill="x", side="bottom")

        self.settings_tab = SettingsTab(self.notebook, self)
        self.decode_tab = DecodeTab(self.notebook, self.fonts)
        self.encode_tab = EncodeTab(self.notebook, self.fonts, self.send_to_decode)
        self.notebook.add(self.settings_tab, text="Settings")
        self.notebook.add(self.encode_tab, text="Encode")
        self.notebook.add(self.decode_tab, text="Decode")
        self.api_tabs = api_tabs.build(self.notebook, self)
        # Start on Encode when settings are already saved, otherwise on Settings.
        if any(self.saved.get(k) for k in settings.FIELDS):
            self.notebook.select(self.encode_tab)

        root.after(100, self._drain_results)

    def _build_header(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(16, 10))
        header.pack(fill="x")
        # White rounded-square monogram, as in Metrc's prototype headers.
        mark = tk.Canvas(header, width=34, height=34, background=theme.PRIMARY,
                         highlightthickness=0)
        r, x0, y0, x1, y1 = 7, 1, 1, 33, 33
        mark.create_polygon(
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
            x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
            smooth=True, fill=theme.SURFACE, outline="")
        mark.create_text(17, 17, text="RID", fill=theme.MARK_TEXT, font=self.fonts.mark)
        mark.pack(side="left", padx=(0, 14))
        ttk.Label(header, text="Metrc", style="HeaderBrand.TLabel").pack(side="left")
        ttk.Label(header, text="Retail ID SDK Explorer", style="HeaderTitle.TLabel").pack(
            side="left", padx=(10, 0))
        ttk.Label(header, text=f"retailid {retailid.__version__}  ·  Python SDK showcase",
                  style="HeaderSub.TLabel").pack(side="right")
        ttk.Frame(self.root, style="Rule.TFrame", height=3).pack(fill="x")

    # -- shared services for tabs --------------------------------------------

    def saved_config(self) -> RetailIdConfig:
        return settings.to_config(self.saved)

    def remember_license(self) -> None:
        value = self.license_number.get().strip()
        if value != self.saved.get(settings.LICENSE_FIELD, ""):
            self.saved[settings.LICENSE_FIELD] = value
            settings.save_settings(self.saved)

    def set_status(self, text: str, ok: bool = True) -> None:
        self.status.configure(text=text, foreground=theme.TEXT_MUTED if ok else theme.ERROR)

    def send_to_decode(self, url: str) -> None:
        self.notebook.select(self.decode_tab)
        self.decode_tab.decode_url(url)

    def run_task(self, work: Callable[[], Any], done: Done) -> None:
        """Run ``work`` off the UI thread, then call ``done(result, error)`` on it."""
        def target() -> None:
            try:
                self._results.put((done, work(), None))
            except BaseException as e:  # noqa: BLE001 - reported in the UI
                self._results.put((done, None, e))

        if self.background:
            threading.Thread(target=target, daemon=True).start()
        else:
            target()
            self._drain_results(reschedule=False)

    def _drain_results(self, reschedule: bool = True) -> None:
        while True:
            try:
                done, result, error = self._results.get_nowait()
            except queue.Empty:
                break
            done(result, error)
        if reschedule:
            self.root.after(100, self._drain_results)


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()
