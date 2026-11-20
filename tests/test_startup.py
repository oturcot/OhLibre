import os
import tempfile
import unittest
from unittest.mock import patch

from downloader import main


class StartupTest(unittest.TestCase):
    def test_startup_logs_the_running_release_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"OHDIO_SHOWS": "302", "OHDIO_OUTPUT": directory,
                                         "OHDIO_VERSION": "0.4.2-beta.1"}), \
                 patch("sys.argv", ["downloader.py", "--once"]), \
                 patch("downloader.signal.signal"), patch("downloader.run"), \
                 self.assertLogs(level="INFO") as logs:
                main()
            self.assertTrue(any("Démarrage" in line and "0.4.2-beta.1" in line
                                for line in logs.output))
