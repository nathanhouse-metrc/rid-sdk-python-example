"""
Drive every panel of the app against the real SDK.

API calls go to a small local HTTP server that stands in for the Retail ID API,
so the tests need no keys and change nothing in Metrc. Run with:

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
import tkinter as tk
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from retailid import RetailIdPair

VENDOR, USER = "vendor-key-123", "user-key-456"

RESPONSES = {
    ("GET", "/facilities/v2/"): {"Data": [{"Name": "Test Dispensary",
                                           "License": {"Number": "LIC-1"}}]},
    ("GET", "/retailid/v2/allotment"): {"FacilityId": 1, "FacilityLicenseNumber": "LIC-1",
                                        "Allotment": 500},
    ("GET", "/tags/v2/package/available"): {"Data": [{"Label": "1A4000000000000000000001"}]},
    ("GET", "/packages/v2/PKG-1"): {"Id": 7, "Label": "PKG-1", "ProductLabel": "Gummies"},
    ("POST", "/retailid/v2/packages/info"): [{"PackageLabel": "PKG-1", "QrCount": 3,
                                              "HasQrs": True, "Issuances": []}],
    ("POST", "/retailid/v2/generate"): {"IssuanceId": "iss-42"},
    ("GET", "/retailid/v2/receive/PKG-1"): {"Eaches": ["HTTPS://1A4.COM/10NOIEYKAJDG6CF0EXGJL"],
                                            "SiblingTags": [], "RequiresVerification": False},
    ("GET", "/retailid/v2/receive/qr/10NOIEYKAJDG6CF0EXGJL"): {"Eaches": ["X"],
                                                              "SiblingTags": ["PKG-2"]},
    ("POST", "/retailid/v2/associate"): {"Ids": [1]},
    ("POST", "/retailid/v2/merge"): {"Ids": [2], "Warnings": None},
    ("POST", "/sales/v2/receipts"): None,
    ("GET", "/globalproducts/v2"): {"Data": [{"Id": 9}], "TotalPages": 1},
    ("GET", "/globalproducts/v2/9"): {"Id": 9, "Name": "Widget"},
}


class FakeApi(BaseHTTPRequestHandler):
    calls: list[dict] = []

    def _handle(self, method: str) -> None:
        parts = urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length)) if length else None
        auth = base64.b64decode(self.headers["Authorization"].split()[1]).decode()
        FakeApi.calls.append({"method": method, "path": parts.path,
                              "query": parse_qs(parts.query), "body": body, "auth": auth})
        key = (method, parts.path)
        if parts.path == "/retailid/v2/receive/MISSING":
            self._send(404, {"Message": "Package not found"})
        elif key in RESPONSES:
            self._send(200, RESPONSES[key])
        else:
            self._send(404, {"Message": f"no fake for {key}"})

    def _send(self, status: int, payload: object) -> None:
        data = b"" if payload is None else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def log_message(self, *args: object) -> None:
        pass


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeApi)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings_file = Path(self.tmp.name) / "settings.json"
        env = mock.patch.dict(os.environ, {"RID_EXAMPLE_SETTINGS": str(self.settings_file)})
        env.start()
        self.addCleanup(env.stop)
        from rid_example.app import App
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = App(self.root, background=False)
        FakeApi.calls.clear()

    def tearDown(self) -> None:
        self.root.destroy()
        self.tmp.cleanup()

    def configure(self) -> None:
        tab = self.app.settings_tab
        tab.vars["vendor_api_key"].set(VENDOR)
        tab.vars["user_api_key"].set(USER)
        tab.vars["state_code"].set("MD")
        tab.vars["base_url"].set(self.base_url)
        tab.save()

    # -- settings ------------------------------------------------------------

    def test_settings_persist_between_runs(self) -> None:
        self.configure()
        saved = json.loads(self.settings_file.read_text())
        self.assertEqual(saved["vendor_api_key"], VENDOR)
        self.assertEqual(saved["state_code"], "md")
        self.assertEqual(saved["base_url"], self.base_url)
        # A fresh app reads the same values back.
        from rid_example.app import App
        root2 = tk.Tk()
        root2.withdraw()
        try:
            app2 = App(root2, background=False)
            self.assertEqual(app2.settings_tab.vars["user_api_key"].get(), USER)
        finally:
            root2.destroy()
        # Keys are masked in the summary.
        self.assertNotIn(VENDOR, self.app.settings_tab.results.get())

    def test_test_connection(self) -> None:
        self.configure()
        self.app.settings_tab.test_connection()
        out = self.app.settings_tab.results.get()
        self.assertIn("Connected — 1 facility", out)
        self.assertIn("LIC-1  Test Dispensary", out)
        self.assertEqual(FakeApi.calls[-1]["auth"], f"{VENDOR}:{USER}")

    def test_api_without_settings_reports_incomplete(self) -> None:
        tab = self.app.api_tabs["Access"]
        tab.invoke("facilities")
        self.assertIn("Settings incomplete", tab.results.get())
        self.assertEqual(FakeApi.calls, [])

    # -- encode / decode -------------------------------------------------------

    def test_encode_known_vector(self) -> None:
        tab = self.app.encode_tab
        tab.load_example()
        self.assertEqual(tab.last_url, "HTTPS://1A4.COM/10NOIEYKAJDG6CF0EXGJL")
        tab.encoding.set("base64")
        tab.domain.set("example.com")
        tab.encode()
        self.assertTrue(tab.last_url.startswith("https://example.com/"))
        pair = RetailIdPair(tab.last_url)
        self.assertEqual((pair.batch_id.to_hex_string(), pair.index),
                         ("abcdef012345670000027190", 1))

    def test_encode_bad_input(self) -> None:
        tab = self.app.encode_tab
        tab.batch_id.set("xyz")
        tab.encode()
        self.assertIn("Could not encode", tab.results.get())
        tab.batch_id.set("abcdef012345670000027190")
        tab.index.set("-1")
        tab.encode()
        self.assertIn("whole number", tab.results.get())

    def test_encode_then_decode_round_trip(self) -> None:
        enc = self.app.encode_tab
        enc.index.set("300")
        enc.encoding.set("base64")
        enc.encode()
        enc.decode_result()
        out = self.app.decode_tab.results.get()
        self.assertIn("abcdef012345670000027190", out)
        self.assertIn("300", out)
        self.assertIn("base64", out)

    def test_decode_known_vector(self) -> None:
        tab = self.app.decode_tab
        tab.load_example()
        out = tab.results.get()
        self.assertIn("abcdef012345670000027190", out)
        self.assertIn("Index\n1\n", out)
        self.assertIn("Detected encoding\nbase36", out)

    def test_decode_bad_input(self) -> None:
        tab = self.app.decode_tab
        tab.url.set("https://1a4.com/!!")
        tab.decode()
        self.assertIn("Could not decode", tab.results.get())

    # -- API tabs ----------------------------------------------------------------

    def run_action(self, tab_title: str, key: str, **inputs: str) -> tuple[str, dict]:
        tab = self.app.api_tabs[tab_title]
        for field, value in inputs.items():
            tab.set_input(key, field, value)
        tab.invoke(key, confirm=False)
        out = tab.results.get()
        self.assertTrue(out.startswith("✔"), f"{key} failed:\n{out}")
        return out, FakeApi.calls[-1]

    def test_every_api_action(self) -> None:
        self.configure()
        self.app.license_number.set("LIC-1")

        out, call = self.run_action("Access", "facilities")
        self.assertIn("Test Dispensary", out)
        self.assertNotIn("licenseNumber", call["query"])

        out, call = self.run_action("Label printing", "allotment")
        self.assertIn('"allotment": 500', out)
        self.assertEqual(call["query"]["licenseNumber"], ["LIC-1"])

        out, _ = self.run_action("Label printing", "available_tags")
        self.assertIn("1A4000000000000000000001", out)

        out, _ = self.run_action("Label printing", "package", id_or_label="PKG-1")
        self.assertIn("Gummies", out)

        out, call = self.run_action("Label printing", "packages_info", labels="PKG-1\nPKG-2")
        self.assertEqual(call["body"], {"packageLabels": ["PKG-1", "PKG-2"]})
        self.assertIn('"qr_count": 3', out)

        out, call = self.run_action("Label printing", "generate", package_label="PKG-1",
                                    quantity="3")
        self.assertEqual(call["body"], {"PackageLabel": "PKG-1", "Quantity": 3})
        self.assertIn("iss-42", out)

        out, _ = self.run_action("Receiving", "receive", package_label="PKG-1")
        self.assertIn("10NOIEYKAJDG6CF0EXGJL", out)

        _, call = self.run_action("Receiving", "receive_qr")
        self.assertEqual(call["path"], "/retailid/v2/receive/qr/10NOIEYKAJDG6CF0EXGJL")

        _, call = self.run_action("Receiving", "associate", package_label="PKG-1",
                                  qr_urls="https://1a4.com/a\nhttps://1a4.com/b")
        self.assertEqual(call["body"], [{"PackageLabel": "PKG-1",
                                         "QrUrls": ["https://1a4.com/a", "https://1a4.com/b"]}])

        _, call = self.run_action("Receiving", "merge", target="PKG-1", source="PKG-2")
        self.assertEqual(call["body"], {"packageLabels": ["PKG-1", "PKG-2"]})

        out, call = self.run_action("Point of sale", "sales")
        self.assertEqual(call["path"], "/sales/v2/receipts")
        self.assertEqual(call["body"][0]["Transactions"][0]["QrCodes"],
                         ["HTTPS://1A4.COM/10NOIEYKAJDG6CF0EXGJL"])
        self.assertIn("(empty response)", out)

        out, call = self.run_action("Catalog", "global_products", brand_id="5", page_size="20")
        self.assertEqual(call["query"]["brandId"], ["5"])
        self.assertEqual(call["query"]["pageSize"], ["20"])
        self.assertIn("1 record", out)

        out, _ = self.run_action("Catalog", "global_product", product_id="9")
        self.assertIn("Widget", out)

        # The license number is remembered between runs.
        self.assertEqual(json.loads(self.settings_file.read_text())["license_number"], "LIC-1")

    def test_api_error_is_shown(self) -> None:
        self.configure()
        self.app.license_number.set("LIC-1")
        tab = self.app.api_tabs["Receiving"]
        tab.set_input("receive", "package_label", "MISSING")
        tab.invoke("receive")
        out = tab.results.get()
        self.assertIn("HTTP 404 (NotFoundError)", out)
        self.assertIn("Package not found", out)

    def test_license_required(self) -> None:
        self.configure()
        self.app.license_number.set("")
        tab = self.app.api_tabs["Label printing"]
        tab.invoke("allotment")
        self.assertIn("license number", tab.results.get())

    def test_invalid_json_input(self) -> None:
        self.configure()
        self.app.license_number.set("LIC-1")
        tab = self.app.api_tabs["Point of sale"]
        tab.set_input("sales", "records", "{not json")
        tab.invoke("sales", confirm=False)
        self.assertIn("not valid JSON", tab.results.get())


if __name__ == "__main__":
    unittest.main()
