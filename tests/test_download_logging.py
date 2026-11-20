import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from library import fetch


class DownloadLoggingTest(unittest.TestCase):
    def test_download_progress_is_logged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "101.mp3"

            def fake_ffmpeg(*args: str) -> None:
                Path(args[-1]).write_bytes(b"audio")

            with patch("library.manifest", return_value="https://example.test/stream"), \
                 patch("library.ffmpeg", side_effect=fake_ffmpeg), \
                 self.assertLogs(level="INFO") as logs:
                self.assertTrue(fetch("101", path))
            self.assertTrue(any("Téléchargement du média 101" in line for line in logs.output))
            self.assertTrue(any("Média 101 téléchargé" in line for line in logs.output))
            self.assertEqual(path.read_bytes(), b"audio")

    def test_failed_download_is_not_logged_as_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "101.mp3"
            with patch("library.manifest", return_value="https://example.test/stream"), \
                 patch("library.ffmpeg", side_effect=subprocess.CalledProcessError(1, "ffmpeg")), \
                 self.assertLogs(level="INFO") as logs:
                with self.assertRaises(subprocess.CalledProcessError):
                    fetch("101", path)
            self.assertFalse(any("téléchargé" in line for line in logs.output))
            self.assertFalse(path.exists())
