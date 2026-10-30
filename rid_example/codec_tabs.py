"""Encode and Decode tabs: offline features of the SDK (no API keys needed)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

import retailid
from retailid import ObjectId, RetailIdPair, VarInt, get_short_url, short_code_from_url

from . import theme
from .widgets import Card, ResultView

EXAMPLE_BATCH_ID = "abcdef012345670000027190"
EXAMPLE_INDEX = 1
EXAMPLE_URL = "HTTPS://1A4.COM/10NOIEYKAJDG6CF0EXGJL"
DEFAULT_DOMAIN = "1a4.com"


def _two_column(tab: ttk.Frame) -> tuple[ttk.Frame, ttk.Frame]:
    tab.columnconfigure(0, weight=2, uniform="cols")
    tab.columnconfigure(1, weight=3, uniform="cols")
    tab.rowconfigure(0, weight=1)
    left = ttk.Frame(tab)
    left.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
    right = ttk.Frame(tab)
    right.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
    return left, right


def _guess_encoding(short_code: str, pair: RetailIdPair, domain: str) -> str:
    if short_code_from_url(pair.encode(domain, base64=True)) == short_code:
        return "base64 (URL-safe)"
    if short_code_from_url(pair.encode(domain)).upper() == short_code.upper():
        return "base36"
    return "unknown"


class EncodeTab(ttk.Frame):
    """``get_short_url``: batch ID + index -> Retail ID URL."""

    def __init__(self, master: tk.Misc, fonts: theme.Fonts,
                 send_to_decode: Callable[[str], None]):
        super().__init__(master)
        self._send_to_decode = send_to_decode
        left, right = _two_column(self)

        card = Card(left, "Encode a Retail ID URL",
                    "Combine a 24-character hex batch ID (an ObjectId) and an item index "
                    "into the short URL printed in a Retail ID QR code. Uses get_short_url().")
        card.pack(fill="x")

        self.batch_id = tk.StringVar(value=EXAMPLE_BATCH_ID)
        self.index = tk.StringVar(value=str(EXAMPLE_INDEX))
        self.domain = tk.StringVar(value=DEFAULT_DOMAIN)
        self.encoding = tk.StringVar(value="base36")

        batch_row = ttk.Frame(card.form, style="Card.TFrame", borderwidth=0)
        ttk.Entry(batch_row, textvariable=self.batch_id, font=fonts.mono).pack(
            side="left", fill="x", expand=True)
        ttk.Button(batch_row, text="Random", command=self.random_batch_id).pack(
            side="left", padx=(8, 0))
        card.add_row("Batch ID", batch_row, "24 hex characters, e.g. abcdef012345670000027190")
        card.add_row("Index", ttk.Entry(card.form, textvariable=self.index, font=fonts.mono),
                     "Whole number ≥ 0 (the item's position in the batch)")
        card.add_row("Domain", ttk.Entry(card.form, textvariable=self.domain),
                     f"Leave as {DEFAULT_DOMAIN} unless you use a custom domain")

        radios = ttk.Frame(card.form, style="Card.TFrame", borderwidth=0)
        ttk.Radiobutton(radios, text="Base36 (uppercase, smaller QR)", value="base36",
                        variable=self.encoding).pack(anchor="w")
        ttk.Radiobutton(radios, text="Base64 (URL-safe, shorter text)", value="base64",
                        variable=self.encoding).pack(anchor="w")
        card.add_row("Encoding", radios)

        card.add_button("Encode", self.encode, style="Primary.TButton")
        card.add_button("Load example", self.load_example)
        self.decode_button = card.add_button("Decode this URL →", self.decode_result)
        self.decode_button.state(["disabled"])

        self.results = ResultView(right, fonts)
        self.results.pack(fill="both", expand=True)
        self.last_url = ""

    def random_batch_id(self) -> None:
        self.batch_id.set(ObjectId().to_hex_string())

    def load_example(self) -> None:
        self.batch_id.set(EXAMPLE_BATCH_ID)
        self.index.set(str(EXAMPLE_INDEX))
        self.domain.set(DEFAULT_DOMAIN)
        self.encoding.set("base36")
        self.encode()

    def encode(self) -> None:
        try:
            batch_id = ObjectId(self.batch_id.get().strip())
            index_text = self.index.get().strip()
            if not index_text.isdigit():
                raise ValueError(f"Index must be a whole number ≥ 0, got {index_text!r}")
            index = int(index_text)
            domain = self.domain.get().strip() or None
            use_base64 = self.encoding.get() == "base64"
            url = get_short_url(batch_id, index, domain=domain, base64=use_base64)
        except ValueError as e:
            self.last_url = ""
            self.decode_button.state(["disabled"])
            self.results.show_error("Could not encode", str(e))
            return

        self.last_url = url
        self.decode_button.state(["!disabled"])
        varint = VarInt(index)
        self.results.show_fields(
            "Encoded",
            [
                ("URL", url),
                ("Short code", short_code_from_url(url)),
                ("Encoding", "base64 (URL-safe)" if use_base64 else "base36"),
                ("Batch ID", batch_id.to_hex_string()),
                ("Index", f"{index}  (varint bytes: {varint.to_hex_string()})"),
                ("Payload", f"{12 + len(varint)} bytes = 12-byte batch ID + "
                            f"{len(varint)}-byte varint index"),
            ],
            url_keys=("URL",),
        )

    def decode_result(self) -> None:
        if self.last_url:
            self._send_to_decode(self.last_url)


class DecodeTab(ttk.Frame):
    """``RetailIdPair``: Retail ID URL -> batch ID + index."""

    def __init__(self, master: tk.Misc, fonts: theme.Fonts):
        super().__init__(master)
        left, right = _two_column(self)

        card = Card(left, "Decode a Retail ID URL",
                    "Paste a scanned QR URL (or just its short code). RetailIdPair detects "
                    "base36 or base64 and returns the batch ID and index.")
        card.pack(fill="x")

        self.url = tk.StringVar(value=EXAMPLE_URL)
        self.strict = tk.BooleanVar(value=False)
        card.add_row("URL or code", ttk.Entry(card.form, textvariable=self.url, font=fonts.mono),
                     "e.g. HTTPS://1A4.COM/10NOIEYKAJDG6CF0EXGJL")
        card.add_row("Strict", ttk.Checkbutton(
            card.form, variable=self.strict,
            text="Require a known prefix or a valid ObjectId timestamp"))
        card.add_button("Decode", self.decode, style="Primary.TButton")
        card.add_button("Load example", self.load_example)

        self.results = ResultView(right, fonts)
        self.results.pack(fill="both", expand=True)

    def load_example(self) -> None:
        self.url.set(EXAMPLE_URL)
        self.strict.set(False)
        self.decode()

    def decode_url(self, url: str) -> None:
        self.url.set(url)
        self.decode()

    def decode(self) -> None:
        text = self.url.get().strip()
        try:
            if not text:
                raise ValueError("Enter a Retail ID URL or short code")
            pair = RetailIdPair(text, strict=self.strict.get())
            short_code = short_code_from_url(text)
        except ValueError as e:
            self.results.show_error("Could not decode", str(e))
            return

        domain = DEFAULT_DOMAIN
        if "://" in text:
            domain = text.split("://", 1)[1].split("/", 1)[0].lower() or DEFAULT_DOMAIN
        hex_id = pair.batch_id.to_hex_string()
        known = any(hex_id.startswith(p) for p in retailid.RETAILID_PREFIXES)
        self.results.show_fields(
            "Decoded",
            [
                ("Batch ID", hex_id),
                ("Index", str(pair.index)),
                ("Short code", short_code),
                ("Detected encoding", _guess_encoding(short_code, pair, domain)),
                ("Known Retail ID prefix", "yes" if known else
                 f"no (known prefixes: {', '.join(retailid.RETAILID_PREFIXES)})"),
                ("Re-encoded as base36", pair.encode(domain)),
                ("Re-encoded as base64", pair.encode(domain, base64=True)),
            ],
        )
