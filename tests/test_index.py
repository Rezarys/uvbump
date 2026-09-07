"""The network path, exercised against a local index that speaks PEP 691."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from uvbump.index import IndexUnavailable, fetch_versions, make_resolver, resolve_all

PAYLOADS = {
    "/simple/requests/": {
        "meta": {"api-version": "1.1"},
        "name": "requests",
        "versions": ["2.31.0", "2.32.5", "3.0.0b1"],
        "files": [],
    },
    "/simple/legacy-project/": {  # An index too old to advertise `versions`.
        "meta": {"api-version": "1.0"},
        "name": "legacy-project",
        "files": [
            {"filename": "legacy_project-1.2.0-py3-none-any.whl"},
            {"filename": "legacy-project-1.3.0.tar.gz"},
        ],
    },
    "/simple/withdrawn/": {
        "meta": {"api-version": "1.1"},
        "name": "withdrawn",
        "versions": ["1.0", "1.1", "1.2"],
        "files": [
            {"filename": "withdrawn-1.0.tar.gz", "yanked": False},
            {"filename": "withdrawn-1.1-py3-none-any.whl", "yanked": False},
            {"filename": "withdrawn-1.1.tar.gz", "yanked": "broken build"},
            {"filename": "withdrawn-1.2-py3-none-any.whl", "yanked": "does not import"},
            {"filename": "withdrawn-1.2.tar.gz", "yanked": "does not import"},
        ],
    },
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/simple/teapot/":
            self.send_error(418, "teapot")
            return
        payload = PAYLOADS.get(self.path)
        if payload is None:
            self.send_error(404, "not found")
            return
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.pypi.simple.v1+json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TestAgainstALocalIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.server.server_address
        cls.index = f"http://{host}:{port}/simple"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_reads_the_versions_key(self):
        self.assertEqual(
            fetch_versions("requests", self.index), ["2.31.0", "2.32.5", "3.0.0b1"]
        )

    def test_normalises_the_project_name_in_the_url(self):
        self.assertEqual(fetch_versions("Legacy_Project", self.index), ["1.2.0", "1.3.0"])

    def test_drops_a_version_whose_every_file_is_yanked(self):
        # 1.2 is gone entirely, 1.1 still has one usable file so it stays.
        self.assertEqual(fetch_versions("withdrawn", self.index), ["1.0", "1.1"])
        self.assertEqual(str(make_resolver(self.index)("withdrawn")), "1.1")

    def test_unknown_project_is_empty_not_an_error(self):
        self.assertEqual(fetch_versions("ghost", self.index), [])

    def test_other_http_errors_are_reported(self):
        with self.assertRaises(IndexUnavailable):
            fetch_versions("teapot", self.index)

    def test_resolver_picks_the_latest_stable_and_caches(self):
        resolver = make_resolver(self.index)
        self.assertEqual(str(resolver("requests")), "2.32.5")
        self.assertEqual(str(resolver("Requests")), "2.32.5")

    def test_resolver_can_take_prereleases(self):
        resolver = make_resolver(self.index, allow_prereleases=True)
        self.assertEqual(str(resolver("requests")), "3.0.0b1")

    def test_resolve_all_returns_failures_instead_of_raising(self):
        results = resolve_all(["requests", "teapot", "ghost"], make_resolver(self.index))
        self.assertEqual(str(results["requests"]), "2.32.5")
        self.assertIsInstance(results["teapot"], IndexUnavailable)
        self.assertIsNone(results["ghost"])

    def test_an_index_that_is_not_there_is_reported(self):
        with self.assertRaises(IndexUnavailable):
            fetch_versions("requests", "http://127.0.0.1:1/simple", timeout=2.0)


if __name__ == "__main__":
    unittest.main()
