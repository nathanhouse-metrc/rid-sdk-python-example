"""
Tabs for the Retail ID API: one card per ``RetailIdClient`` method.

Each card is described by an :class:`Action` (its inputs and the client call),
so the tabs below are mostly data.
"""

from __future__ import annotations

import json
import time
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any, Callable

import requests
from retailid import RetailIdApiError, RetailIdClient, RetailIdConfigError, RetailIdTimeoutError
from retailid.api import SALES_ENDPOINTS

from .widgets import Card, ResultView, ScrollFrame, format_result, text_box

if TYPE_CHECKING:
    from .app import App


@dataclass
class Field:
    key: str
    label: str
    kind: str = "text"  # text | int | optional_int | lines | json | choice
    default: str = ""
    hint: str = ""
    choices: tuple[str, ...] = ()


@dataclass
class Action:
    key: str
    title: str
    endpoint: str
    hint: str
    call: Callable[[RetailIdClient, str, dict[str, Any]], Any]
    fields: list[Field] = field(default_factory=list)
    needs_license: bool = True
    changes_data: bool = False


# -- input parsing -----------------------------------------------------------


def _parse(f: Field, raw: str) -> Any:
    raw = raw.strip()
    if f.kind == "int":
        if not raw.lstrip("-").isdigit():
            raise ValueError(f"{f.label} must be a whole number")
        return int(raw)
    if f.kind == "optional_int":
        if not raw:
            return None
        if not raw.isdigit():
            raise ValueError(f"{f.label} must be a whole number or blank")
        return int(raw)
    if f.kind == "lines":
        items = [line.strip() for line in raw.replace(",", "\n").splitlines() if line.strip()]
        if not items:
            raise ValueError(f"{f.label}: enter at least one value")
        return items
    if f.kind == "json":
        try:
            return json.loads(raw)
        except ValueError as e:
            raise ValueError(f"{f.label} is not valid JSON: {e}") from e
    if not raw:
        raise ValueError(f"{f.label} is required")
    return raw


def _sales_records(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


SAMPLE_RECEIPT = json.dumps([{
    "SalesDateTime": "2026-01-01T12:00:00Z",
    "SalesCustomerType": "Consumer",
    "Transactions": [{
        "PackageLabel": "1A4060300007777000000001",
        "Quantity": 1,
        "UnitOfMeasure": "Each",
        "TotalAmount": 10.00,
        "QrCodes": ["HTTPS://1A4.COM/10NOIEYKAJDG6CF0EXGJL"],
    }],
}], indent=2)


# -- the actions -------------------------------------------------------------

PACKAGE = Field("package_label", "Package label", hint="e.g. 1A4060300007777000000001")

ACCESS = [
    Action("facilities", "Check access: list facilities", "GET /facilities/v2/",
           "Confirms the saved keys work and lists the facilities this user can see. "
           "Use one of the license numbers above.",
           lambda c, lic, v: c.get_facilities(), needs_license=False),
]

LABEL_PRINTING = [
    Action("allotment", "Allotment", "GET /retailid/v2/allotment",
           "Remaining Retail Item IDs for the facility (New York only).",
           lambda c, lic, v: c.get_allotment(lic)),
    Action("available_tags", "Available tags", "GET /tags/v2/package/available",
           "Unused package tags, for staging labels.",
           lambda c, lic, v: c.get_available_tags(lic)),
    Action("package", "Get package", "GET /packages/v2/{id or label}",
           "Package details, including ProductLabel.",
           lambda c, lic, v: c.get_package(lic, v["id_or_label"]),
           [Field("id_or_label", "ID or label", hint="Numeric package ID or package label")]),
    Action("packages_info", "Package Retail ID info", "POST /retailid/v2/packages/info",
           "QR count, issuances and verification status. Read-only; sent in batches of 10.",
           lambda c, lic, v: c.get_packages_info(lic, v["labels"]),
           [Field("labels", "Package labels", "lines", hint="One per line (or comma-separated)")]),
    Action("generate", "Generate Retail IDs", "POST /retailid/v2/generate",
           "Creates Retail IDs for a package. Changes data and is not retried; if it times out, "
           "check Package Retail ID info before trying again.",
           lambda c, lic, v: c.generate(lic, v["package_label"], v["quantity"]),
           [PACKAGE, Field("quantity", "Quantity", "int", "1")], changes_data=True),
]

RECEIVING = [
    Action("receive", "Receive by package label", "GET /retailid/v2/receive/{label}",
           "QR URLs (eaches) and receiving status for a package.",
           lambda c, lic, v: c.receive(lic, v["package_label"]), [PACKAGE]),
    Action("receive_qr", "Receive by scanned QR", "GET /retailid/v2/receive/qr/{shortCode}",
           "Start from one scanned unit: paste its QR URL or short code.",
           lambda c, lic, v: c.receive_by_qr(lic, v["qr"]),
           [Field("qr", "QR URL or code", default="HTTPS://1A4.COM/10NOIEYKAJDG6CF0EXGJL")]),
    Action("associate", "Scan and associate", "POST /retailid/v2/associate",
           "Link scanned units to the package they are physically in. Use full QR URLs, "
           "not short codes. Changes data.",
           lambda c, lic, v: c.associate_package(lic, v["package_label"], v["qr_urls"]),
           [PACKAGE, Field("qr_urls", "QR URLs", "lines", hint="One full URL per line")],
           changes_data=True),
    Action("merge", "Merge packages", "POST /retailid/v2/merge",
           "The target keeps and receives all Retail ID links; the source gives its links up. "
           "Changes data.",
           lambda c, lic, v: c.merge(lic, v["target"], v["source"]),
           [Field("target", "Target label"), Field("source", "Source label")],
           changes_data=True),
]

POINT_OF_SALE = [
    Action("sales", "Report sales with Retail IDs", "POST /sales/v2/…",
           "Sales objects from the market's Sales docs; Retail IDs go in "
           "Transactions[].QrCodes next to PackageLabel. At most 10 records. Changes data.",
           lambda c, lic, v: c.post_sales(lic, _sales_records(v["records"]),
                                          endpoint=v["endpoint"]),
           [Field("endpoint", "Endpoint", "choice", "receipts",
                  choices=tuple(SALES_ENDPOINTS)),
            Field("records", "Records (JSON)", "json", SAMPLE_RECEIPT)],
           changes_data=True),
]

CATALOG = [
    Action("global_products", "Global products for a brand", "GET /globalproducts/v2?brandId=",
           "Every Global Product for the brand, across all pages.",
           lambda c, lic, v: c.get_global_products(v["brand_id"], page_size=v["page_size"]),
           [Field("brand_id", "Brand ID"),
            Field("page_size", "Page size", "optional_int", hint="Optional")],
           needs_license=False),
    Action("global_product", "Global product by ID", "GET /globalproducts/v2/{id}",
           "One Global Product.",
           lambda c, lic, v: c.get_global_product(v["product_id"]),
           [Field("product_id", "Product ID")], needs_license=False),
]

TABS = [
    ("Access", ACCESS),
    ("Label printing", LABEL_PRINTING),
    ("Receiving", RECEIVING),
    ("Point of sale", POINT_OF_SALE),
    ("Catalog", CATALOG),
]


# -- the tab -----------------------------------------------------------------


def describe_error(e: BaseException) -> tuple[str, str, str]:
    """Return (title, message, detail) for an exception raised by an API call."""
    if isinstance(e, RetailIdConfigError):
        return ("Settings incomplete", str(e),
                "Open the Settings tab, fill in the keys and a state code or base URL, and Save.")
    if isinstance(e, RetailIdApiError):
        detail = format_result(e.body) if e.body not in (None, "") else ""
        return (f"{e.method} {e.path} → HTTP {e.status_code} ({type(e).__name__})",
                e.message or "", detail)
    if isinstance(e, RetailIdTimeoutError):
        return ("Request timed out", str(e),
                "Calls that change data are not retried; check the result before sending again.")
    if isinstance(e, requests.ConnectionError):
        return ("Could not connect", str(e), "Check the state code or base URL in Settings.")
    if isinstance(e, ValueError):
        return ("Invalid input", str(e), "")
    return (type(e).__name__, str(e), "")


class ApiTab(ttk.Frame):
    def __init__(self, master: tk.Misc, app: App, actions: list[Action]):
        super().__init__(master)
        self.app = app
        fonts = app.fonts
        self.columnconfigure(0, weight=2, uniform="cols")
        self.columnconfigure(1, weight=3, uniform="cols")
        self.rowconfigure(0, weight=1)

        scroll = ScrollFrame(self)
        scroll.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
        self.results = ResultView(self, fonts)
        self.results.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)

        if any(a.needs_license for a in actions):
            lic = Card(scroll.body, "Facility",
                       "The license number is sent as ?licenseNumber= on each call. "
                       "It is shared by every API tab and remembered between runs.")
            lic.add_row("License number", ttk.Entry(lic.form, textvariable=app.license_number,
                                                    font=fonts.mono))
            lic.buttons.destroy()
            lic.pack(fill="x", pady=(0, 12), padx=(0, 4))

        self.actions = {a.key: a for a in actions}
        self.inputs: dict[str, dict[str, Callable[[], str]]] = {}
        self.setters: dict[str, dict[str, Callable[[str], None]]] = {}
        self.buttons: dict[str, ttk.Button] = {}
        for action in actions:
            self._build_card(scroll.body, action)

    def _build_card(self, parent: tk.Misc, action: Action) -> None:
        fonts = self.app.fonts
        card = Card(parent, action.title, action.hint)
        ttk.Label(card.form, text=action.endpoint, style="CardHint.TLabel",
                  font=fonts.mono).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        card._row = 1
        getters: dict[str, Callable[[], str]] = {}
        setters: dict[str, Callable[[str], None]] = {}
        for f in action.fields:
            if f.kind in ("lines", "json"):
                box = text_box(card.form, fonts, height=10 if f.kind == "json" else 4)
                box.insert("1.0", f.default)
                card.add_row(f.label, box, f.hint)
                getters[f.key] = lambda b=box: b.get("1.0", "end-1c")
                setters[f.key] = lambda s, b=box: (b.delete("1.0", "end"), b.insert("1.0", s))
            else:
                var = tk.StringVar(value=f.default)
                if f.kind == "choice":
                    widget: tk.Widget = ttk.Combobox(card.form, textvariable=var,
                                                     values=f.choices, state="readonly")
                else:
                    widget = ttk.Entry(card.form, textvariable=var, font=fonts.mono)
                card.add_row(f.label, widget, f.hint)
                getters[f.key] = var.get
                setters[f.key] = var.set
        self.inputs[action.key] = getters
        self.setters[action.key] = setters
        style = "Danger.TButton" if action.changes_data else "Primary.TButton"
        label = "Send (changes data)" if action.changes_data else "Send"
        self.buttons[action.key] = card.add_button(label, lambda a=action: self.invoke(a.key),
                                                   style=style)
        card.pack(fill="x", pady=(0, 12), padx=(0, 4))

    # -- running -----------------------------------------------------------

    def set_input(self, action_key: str, field_key: str, value: str) -> None:
        self.setters[action_key][field_key](value)

    def invoke(self, action_key: str, confirm: bool = True) -> None:
        action = self.actions[action_key]
        try:
            values = {f.key: _parse(f, self.inputs[action.key][f.key]()) for f in action.fields}
            license_number = self.app.license_number.get().strip()
            if action.needs_license and not license_number:
                raise ValueError("Enter a facility license number first")
            config = self.app.saved_config()
        except (ValueError, RetailIdConfigError) as e:
            self.results.show_error(*describe_error(e))
            return

        if confirm and action.changes_data and not messagebox.askyesno(
                "Send request?",
                f"{action.title} changes data in Metrc ({config.base_url or config.state_code}).\n\n"
                "Send it?", parent=self):
            return

        self.app.remember_license()
        button = self.buttons[action.key]
        button.state(["disabled"])
        self.results.show_pending(f"{action.title}: {action.endpoint}")
        started = time.monotonic()

        def work() -> Any:
            with RetailIdClient.from_config(config) as client:
                return action.call(client, license_number, values)

        def done(result: Any, error: BaseException | None) -> None:
            button.state(["!disabled"])
            elapsed = time.monotonic() - started
            if error is not None:
                self.results.show_error(*describe_error(error))
                self.app.set_status(f"{action.title} failed", ok=False)
                return
            count = f" — {len(result)} record(s)" if isinstance(result, list) else ""
            self.results.show_success(f"{action.title}{count}",
                                      format_result(result), elapsed)
            self.app.set_status(f"{action.title} succeeded in {elapsed:.2f}s")

        self.app.run_task(work, done)


def build(notebook: ttk.Notebook, app: App) -> dict[str, ApiTab]:
    tabs = {}
    for title, actions in TABS:
        tab = ApiTab(notebook, app, actions)
        notebook.add(tab, text=title)
        tabs[title] = tab
    return tabs

