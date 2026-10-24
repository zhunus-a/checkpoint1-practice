"""The notes service against the M1 contract.

Checkpoint 1: the marker runs its OWN copy of this file, so editing it here never
changes your mark. Run the tests with:  ./scripts/test.sh
"""
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from server import make_server  # noqa: E402


def get(port, path, timeout=2.0):
    """GET a path. Returns (status, body). An error status is an answer too."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestNotesService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_root_answers(self):
        self.assertEqual(get(self.port, "/")[0], 200)

    def test_notes_counts_three(self):
        self.assertEqual(get(self.port, "/notes"), (200, "3"))

    def test_first_and_latest_note(self):
        self.assertEqual(get(self.port, "/notes/first"), (200, "alpha"))
        self.assertEqual(get(self.port, "/notes/latest"), (200, "gamma"))

    def test_healthz_is_ok(self):
        status, body = get(self.port, "/healthz")
        self.assertEqual(status, 200, "GET /healthz must answer 200 (the M1 contract)")
        self.assertEqual(body, "ok")

    def test_listens_on_all_interfaces(self):
        self.assertEqual(self.server.server_address[0], "0.0.0.0",
                         "bind 0.0.0.0 - on 127.0.0.1 nothing outside the container can connect")

    def test_run_sh_honours_port(self):
        port = free_port()
        env = dict(os.environ, PORT=str(port))
        proc = subprocess.Popen([os.path.join(ROOT, "scripts", "run.sh")], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        answer = None
        try:
            deadline = time.time() + 5
            while answer is None and time.time() < deadline:
                try:
                    answer = get(port, "/", timeout=1)
                except OSError:
                    time.sleep(0.2)
        finally:
            proc.terminate()
            proc.wait(timeout=5)
        self.assertIsNotNone(answer, f"with PORT={port}, nothing answered on port {port} "
                                     "(the M1 contract: scripts/run.sh honours $PORT)")


if __name__ == "__main__":
    unittest.main()
