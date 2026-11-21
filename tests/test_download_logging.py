import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from threading import Event
from unittest.mock import patch

from downloader import TORONTO, run
from library import fetch
from ohdio import Episode


class DownloadLoggingTest(unittest.TestCase):
    def test_verification_uses_the_discovered_show_name(self) -> None:
        now = datetime.now(TORONTO)
        episode = Episode("1", "Titre", "", now, now, False, (), "Un balado public")
        with tempfile.TemporaryDirectory() as directory, \
             patch("downloader.discover", return_value=[episode]), \
             patch("downloader.sync_balado", return_value=True), \
             self.assertLogs(level="INFO") as logs:
            run("987654", Path(directory), Event(), True)
        self.assertTrue(any("Vérification de l'émission Un balado public" in line
                            for line in logs.output))
        self.assertFalse(any("987654" in line for line in logs.output))

    def test_known_show_error_uses_its_name_before_discovery(self) -> None:
        class StopAfterWait(Event):
            def wait(self, timeout=None):
                self.set()
                return True

        with tempfile.TemporaryDirectory() as directory, \
             patch("downloader.discover", side_effect=OSError("réseau inaccessible")), \
             self.assertLogs(level="WARNING") as logs:
            run("302", Path(directory), StopAfterWait(), False)
        self.assertTrue(any("À la une" in line and "réseau inaccessible" in line
                            for line in logs.output))
        self.assertFalse(any("302" in line for line in logs.output))

    def test_invalid_page_error_uses_the_known_name_without_the_id(self) -> None:
        class StopAfterWait(Event):
            def wait(self, timeout=None):
                self.set()
                return True

        with tempfile.TemporaryDirectory() as directory, \
             patch("ohdio.read", return_value="page invalide"), \
             self.assertLogs(level="WARNING") as logs:
            run("302", Path(directory), StopAfterWait(), False)
        self.assertTrue(any("À la une" in line and "état OHdio absent" in line
                            for line in logs.output))
        self.assertFalse(any("302" in line for line in logs.output))

    def test_empty_unknown_show_has_an_explicit_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory, \
             patch("downloader.discover", return_value=[]), \
             self.assertLogs(level="INFO") as logs:
            run("987654", Path(directory), Event(), True)
        self.assertTrue(any("Vérification de l'émission nom inconnu" in line
                            for line in logs.output))
        self.assertFalse(any("987654" in line for line in logs.output))

    def test_discovered_name_is_reused_when_next_check_fails(self) -> None:
        now = datetime.now(TORONTO)
        episode = Episode("1", "Titre", "", now, now, False, (), "Un balado public")

        class StopAfterTwoWaits(Event):
            waits = 0

            def wait(self, timeout=None):
                self.waits += 1
                if self.waits == 2:
                    self.set()
                return self.is_set()

        with tempfile.TemporaryDirectory() as directory, \
             patch("downloader.discover", side_effect=[[episode], OSError("réseau inaccessible")]), \
             patch("downloader.sync_balado", return_value=True), \
             self.assertLogs(level="INFO") as logs:
            run("987654", Path(directory), StopAfterTwoWaits(), False)
        self.assertTrue(any("Un balado public" in line and "réseau inaccessible" in line
                            for line in logs.output))
        self.assertFalse(any("987654" in line for line in logs.output))

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
