import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from unittest.mock import patch

from downloader import TORONTO, run
from library import Library, ffmpeg
from ohdio import episodes
from test_podcast import fixture, probe


def audio(media_id: str, path: Path) -> bool:
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=431", "-t", "1",
           "-ac", "2", "-ar", "44100", "-b:a", "128k",
           "-write_xing", "0", str(path))
    return True


class TitleRefreshTest(unittest.TestCase):
    def test_title_and_metadata_update_without_downloading_again(self) -> None:
        aired = datetime(2026, 11, 16, tzinfo=TORONTO)
        episode, = episodes(fixture("302", aired, [101]), "302")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = Library(root, "302")
            with patch("library.fetch", side_effect=audio):
                self.assertTrue(library.publish(episode, "2026-11-16", "05:30", 1))
            entry = library.state["entries"][episode.id]
            due = datetime.fromisoformat(entry["title_next"])
            until = datetime.fromisoformat(entry["title_until"])
            old, = library.output.glob("*.mp3")
            changed = replace(episode, title="Le vrai titre : suite")
            library.refresh_titles([changed], due - timedelta(seconds=1))
            self.assertTrue(old.exists())

            library = Library(root, "302")
            with patch("library.fetch") as fetch:
                library.refresh_titles([changed], due)
                fetch.assert_not_called()
            new, = library.output.glob("*.mp3")
            self.assertEqual(new.name, "2026-11-16_Le vrai titre suite.mp3")
            self.assertFalse(old.exists())
            self.assertEqual(probe(new)["tags"]["title"], changed.title)
            self.assertEqual(probe(new)["tags"]["date"], "2026-11-16T05:30")
            self.assertEqual(library.state["entries"][episode.id]["filename"], new.name)

            changed_again = replace(episode, title="Dernière correction")
            library.refresh_titles([changed_again], due + timedelta(minutes=15))
            final, = library.output.glob("*.mp3")
            self.assertEqual(probe(final)["tags"]["title"], changed_again.title)
            library.refresh_titles([replace(episode, title="Trop tard")], until + timedelta(seconds=1))
            self.assertEqual(list(library.output.glob("*.mp3")), [final])
            self.assertIsNone(library.next_title_check(until + timedelta(seconds=1)))

    def test_conflict_and_missing_episode_do_not_erase_existing_files(self) -> None:
        aired = datetime(2026, 11, 16, tzinfo=TORONTO)
        episode, = episodes(fixture("302", aired, [101]), "302")
        with tempfile.TemporaryDirectory() as directory:
            library = Library(Path(directory), "302")
            with patch("library.fetch", side_effect=audio):
                library.publish(episode, "2026-11-16", "05:30", 1)
            entry = library.state["entries"][episode.id]
            due = datetime.fromisoformat(entry["title_next"])
            original, = library.output.glob("*.mp3")
            collision = library.output / "2026-11-16_Nouveau.mp3"
            collision.write_bytes(b"autre")
            with self.assertLogs(level="WARNING"):
                library.refresh_titles([replace(episode, title="Nouveau")], due)
            self.assertEqual(collision.read_bytes(), b"autre")
            self.assertEqual(probe(original)["tags"]["title"], episode.title)
            self.assertEqual(entry["filename"], original.name)
            with self.assertLogs(level="WARNING"):
                library.refresh_titles([], due + timedelta(minutes=15))
            self.assertEqual(datetime.fromisoformat(entry["title_next"]), due + timedelta(minutes=30))
            collision.unlink()
            library.refresh_titles([replace(episode, title="Nouveau")], due + timedelta(minutes=30))
            self.assertEqual(probe(collision)["tags"]["title"], "Nouveau")

    def test_title_changes_with_same_sanitized_filename_update_metadata(self) -> None:
        aired = datetime(2026, 11, 16, tzinfo=TORONTO)
        episode, = episodes(fixture("302", aired, [101]), "302")
        with tempfile.TemporaryDirectory() as directory:
            library = Library(Path(directory), "302")
            with patch("library.fetch", side_effect=audio):
                library.publish(episode, "2026-11-16", "05:30", 1)
            output, = library.output.glob("*.mp3")
            due = datetime.fromisoformat(library.state["entries"][episode.id]["title_next"])
            changed = replace(episode, title="Épisode complet / test")
            library.refresh_titles([changed], due)
            self.assertEqual(list(library.output.glob("*.mp3")), [output])
            self.assertEqual(probe(output)["tags"]["title"], changed.title)

    def test_case_only_rename_on_case_insensitive_filesystem(self) -> None:
        aired = datetime(2026, 11, 16, tzinfo=TORONTO)
        episode, = episodes(fixture("302", aired, [101]), "302")
        episode = replace(episode, title="Titre provisoire")
        with tempfile.TemporaryDirectory() as directory:
            library = Library(Path(directory), "302")
            with patch("library.fetch", side_effect=audio):
                library.publish(episode, "2026-11-16", "05:30", 1)
            old, = library.output.glob("*.mp3")
            target = old.with_name(old.name.replace("provisoire", "PROVISOIRE"))
            if not target.exists():
                self.skipTest("système de fichiers sensible à la casse")
            due = datetime.fromisoformat(library.state["entries"][episode.id]["title_next"])
            changed = replace(episode, title="Titre PROVISOIRE")
            library.refresh_titles([changed], due)
            output, = library.output.glob("*.mp3")
            self.assertEqual(output.name, target.name)
            self.assertEqual(probe(output)["tags"]["title"], changed.title)

    def test_partial_episode_keeps_original_deadline_after_completion(self) -> None:
        aired = datetime(2026, 11, 16, tzinfo=TORONTO)
        episode, = episodes(fixture("3858", aired, [101]), "3858")
        with tempfile.TemporaryDirectory() as directory:
            library = Library(Path(directory), "3858")
            with patch("library.fetch", side_effect=audio):
                self.assertFalse(library.publish(episode, "2026-11-16", "13:00", 2))
                entry = library.state["entries"][episode.id]
                due = entry["title_next"]
                until = entry["title_until"]
                self.assertTrue(library.publish(replace(episode, media=("101", "102")),
                                                "2026-11-16", "13:00", 2))
            entry = library.state["entries"][episode.id]
            self.assertEqual((entry["title_next"], entry["title_until"]), (due, until))

    def test_refresh_schedule_survives_midnight_and_stops_after_six_hours(self) -> None:
        start = datetime(2026, 11, 16, 23, 50, tzinfo=TORONTO)
        episode, = episodes(fixture("302", start, [101]), "302")

        class Clock(datetime):
            current = start

            @classmethod
            def now(cls, tz=None):
                return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)

        class SimulatedStop(Event):
            def wait(self, timeout=None):
                assert timeout is not None
                Clock.current = (Clock.current.astimezone(timezone.utc) +
                                 timedelta(seconds=timeout)).astimezone(TORONTO)
                if Clock.current >= start + timedelta(hours=6, minutes=1):
                    self.set()
                return self.is_set()

        checks = []

        def discover(show, radio):
            checks.append(Clock.current)
            return [replace(episode, title="Titre final" if len(checks) > 1 else episode.title)]

        with tempfile.TemporaryDirectory() as directory, \
             patch("downloader.datetime", Clock), patch("library.datetime", Clock), \
             patch("downloader.discover", side_effect=discover), patch("library.fetch", side_effect=audio):
            run("302", Path(directory), SimulatedStop(), False)
            for n in range(1, 25):
                self.assertIn(start + timedelta(minutes=15 * n), checks)
            self.assertFalse(any(value > start + timedelta(hours=6) for value in checks))
            output, = (Path(directory) / "Émission 302").glob("*.mp3")
            self.assertEqual(probe(output)["tags"]["title"], "Titre final")


if __name__ == "__main__":
    unittest.main()
