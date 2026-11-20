import io
import shutil
import unittest
import zipfile
from unittest.mock import patch

from app.components.core import updater


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.url = "https://downloads.example.test/mixput-linux-x64.zip"
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=65536):
        for offset in range(0, len(self.payload), chunk_size):
            yield self.payload[offset:offset + chunk_size]


class UpdaterTests(unittest.TestCase):
    def make_archive(self, filename="mixput"):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(filename, b"fake executable")
        return buffer.getvalue()

    def test_rejects_path_traversal(self):
        payload = self.make_archive("../mixput")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            with self.assertRaises(ValueError):
                updater._validate_archive(archive)

    def test_download_reports_progress_and_extracts_expected_binary(self):
        payload = self.make_archive()
        response = FakeResponse(payload)
        updates = []
        with patch.object(updater.platform, "system", return_value="Linux"):
            with patch.object(updater.requests, "get", return_value=response):
                extracted = updater.download_and_stage(
                    "https://downloads.example.test/mixput-linux-x64.zip",
                    "mixput-linux-x64.zip",
                    progress_callback=lambda *values: updates.append(values),
                )
        try:
            self.assertTrue((extracted / "mixput").is_file())
            self.assertIn("download", [item[0] for item in updates])
            self.assertIn("verify", [item[0] for item in updates])
            self.assertIn("extract", [item[0] for item in updates])
            self.assertEqual(updates[-1][0], "ready")
        finally:
            shutil.rmtree(extracted.parent, ignore_errors=True)

    def test_rejects_non_https_download(self):
        with self.assertRaises(ValueError):
            updater.download_and_stage("http://example.test/mixput.zip", "mixput.zip")


if __name__ == "__main__":
    unittest.main()
