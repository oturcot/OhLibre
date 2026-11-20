import json
import os
import subprocess
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from downloader import SCHEDULES, TORONTO, next_balado, select_scheduled, sync_balado
from library import Library, episode_filename, ffmpeg
from ohdio import discover, episodes, manifest


def fixture(show: str, aired: datetime, media: list[int]) -> str:
    record = {
        "globalId": {"id": "305"}, "broadcastedFirstTimeAt": aired.isoformat(),
        "broadcastedLastTimeAt": aired.isoformat(), "isBroadcastedReplay": False,
        "mediaIds": media, "title": "Épisode complet&nbsp;: test", "summary": "<p>Résumé</p>",
    }
    data = {"typename": "ProgramPage", "program": {"globalId": {"id": show}, "title": f"Émission {show}"}, "episodes": [record]}
    return "<script>window._rcState_ = " + json.dumps({"pages": {"pages": {"/": {"data": data}}}}) + ";</script>"


def probe(path: Path) -> dict:
    return json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_format", "-of", "json", str(path)], text=True,
    ))["format"]


class DownloadTest(unittest.TestCase):
    def test_long_episode_title_fits_filesystem_limit(self) -> None:
        for title in ("a" * 300, "é" * 200):
            filename = episode_filename("2026-11-16", title)
            self.assertLessEqual(len(filename.encode("utf-8")), 255)
            self.assertLessEqual(len(f".{Path(filename).stem}.tmp".encode("utf-8")), 255)
            self.assertTrue(filename.startswith("2026-11-16_"))
            self.assertTrue(filename.endswith(".mp3"))

    def test_reuses_existing_unicode_show_directory_without_moving_old_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = Library(root, "302")
            old = root / "302" / "2026-11-16-305.mp3"
            old.parent.mkdir()
            old.write_bytes(b"existing audio")
            existing = root / "A\u0300 la une"
            existing.mkdir()
            library.set_show_title("À la une")
            self.assertEqual(library.output, existing)
            self.assertEqual(old.read_bytes(), b"existing audio")

    def test_existing_unindexed_episode_is_not_overwritten(self) -> None:
        aired = datetime(2026, 11, 16, tzinfo=TORONTO)
        episode, = episodes(fixture("302", aired, [101]), "302")
        with tempfile.TemporaryDirectory() as directory:
            library = Library(Path(directory), "302")
            output = Path(directory) / "Émission 302" / "2026-11-16_Épisode complet test.mp3"
            output.parent.mkdir()
            output.write_bytes(b"other")
            with self.assertRaises(FileExistsError):
                library.publish(episode, "2026-11-16", "05:30", 1)
            self.assertEqual(output.read_bytes(), b"other")

    def test_title_filename_preserves_original_id3_title(self) -> None:
        aired = datetime(2026, 11, 16, tzinfo=TORONTO)
        episode, = episodes(fixture("302", aired, [101]), "302")
        episode = replace(episode, title="Une histoire : de A à Z / suite")
        with tempfile.TemporaryDirectory() as directory:
            library = Library(Path(directory), "302")

            def fake_fetch(media_id: str, path: Path) -> bool:
                ffmpeg("-f", "lavfi", "-i", "sine=frequency=431", "-t", "1",
                       "-ac", "2", "-ar", "44100", "-b:a", "128k",
                       "-write_xing", "0", str(path))
                return True

            with patch("library.fetch", side_effect=fake_fetch):
                self.assertTrue(library.publish(episode, "2026-11-16", "05:30", 1))
            output, = library.output.glob("*.mp3")
            self.assertEqual(output.name, "2026-11-16_Une histoire de A à Z suite.mp3")
            self.assertEqual(probe(output)["tags"]["title"], episode.title)
            with patch("library.fetch") as fetch:
                self.assertTrue(library.publish(replace(episode, title="Titre modifié"),
                                                "2026-11-16", "05:30", 1))
                fetch.assert_not_called()
            self.assertEqual(list(library.output.glob("*.mp3")), [output])

    def test_first_segment_is_published_before_fetching_the_second(self) -> None:
        show = "3858"
        schedule = SCHEDULES[show]
        slot = schedule.next_start(datetime(2026, 11, 16, tzinfo=TORONTO))
        ep, = episodes(fixture(show, slot - timedelta(minutes=10), [101, 102]), show)
        with tempfile.TemporaryDirectory() as directory:
            library = Library(Path(directory), show)
            published_during_second_fetch: list[dict] = []

            def fake_fetch(media_id: str, path: Path) -> bool:
                if media_id == "102":
                    output, = library.output.glob("*.mp3")
                    published_during_second_fetch.append(probe(output))
                    return False
                ffmpeg("-f", "lavfi", "-i", "sine=frequency=431", "-t", "1",
                       "-ac", "2", "-ar", "44100", "-b:a", "128k",
                       "-write_xing", "0", str(path))
                return True

            day = slot.date().isoformat()
            with patch("library.fetch", side_effect=fake_fetch):
                self.assertFalse(library.publish(ep, day, schedule.tag_hour, schedule.parts))

            self.assertEqual(len(published_during_second_fetch), 1)
            self.assertAlmostEqual(float(published_during_second_fetch[0]["duration"]), 1, delta=0.1)
            output, = library.output.glob("*.mp3")
            self.assertAlmostEqual(float(probe(output)["duration"]), 1, delta=0.1)
            self.assertEqual(library.state["entries"][ep.id]["media"], ["101"])

    def test_six_shows_publish_once_and_replace_partial(self) -> None:
        for show, schedule in SCHEDULES.items():
            with self.subTest(show=show), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                library = Library(root, show)
                slot = schedule.next_start(datetime(2026, 11, 16, tzinfo=TORONTO))
                aired = slot - timedelta(minutes=10)
                ep, = episodes(fixture(show, aired, [101]), show)
                self.assertEqual(ep.title, "Épisode complet : test")
                self.assertEqual(ep.summary, "Résumé")
                self.assertIs(select_scheduled([ep], schedule, slot.date()), ep)
                fetches: list[str] = []

                def fake_fetch(media_id: str, path: Path) -> bool:
                    fetches.append(media_id)
                    ffmpeg("-f", "lavfi", "-i", f"sine=frequency={330 + int(media_id)}",
                           "-t", "1", "-ac", "2", "-ar", "44100", "-b:a", "128k",
                           "-write_xing", "0", str(path))
                    return True

                with patch("library.fetch", side_effect=fake_fetch):
                    day = slot.date().isoformat()
                    self.assertEqual(library.publish(ep, day, schedule.tag_hour, schedule.parts),
                                     schedule.parts == 1)
                    path, = list(library.output.glob("*.mp3"))
                    before = probe(path)
                    self.assertAlmostEqual(float(before["duration"]), 1, delta=0.1)
                    self.assertEqual(before["tags"]["date"], f"{day}T{schedule.tag_hour}")
                    if schedule.parts == 2:
                        library = Library(root, show)
                        ep, = episodes(fixture(show, aired, [101, 102, 102]), show)
                        with patch("library.fetch", return_value=False) as unavailable:
                            self.assertFalse(library.publish(ep, day, schedule.tag_hour, 2))
                            unavailable.assert_called_once_with("102", library.work / "102.mp3")
                        self.assertEqual(path, next(library.output.glob("*.mp3")))
                        self.assertEqual(probe(path), before)
                        self.assertTrue(library.publish(ep, day, schedule.tag_hour, 2))
                        self.assertAlmostEqual(float(probe(path)["duration"]), 2, delta=0.15)
                    library = Library(root, show)
                    self.assertTrue(library.publish(ep, day, schedule.tag_hour, schedule.parts))
                    self.assertTrue(library.publish(replace(ep, id="306"), day, schedule.tag_hour, 1))
                    self.assertTrue(library.publish(replace(ep, id="307", replay=True, media=("999",)),
                                                    day, schedule.tag_hour, 1))
                    self.assertEqual(fetches, ["101", "102"] if schedule.parts == 2 else ["101"])
                    self.assertEqual(list(library.output.glob("*.mp3")), [path])

    def test_replay_is_selected_by_last_airing_but_original_has_priority(self) -> None:
        schedule = SCHEDULES["3855"]
        slot = schedule.next_start(datetime(2026, 11, 16, tzinfo=TORONTO))
        ep, = episodes(fixture("3855", slot, [101]), "3855")
        replay = replace(ep, id="306", aired=slot - timedelta(days=14), replay=True)
        self.assertIs(select_scheduled([replay], schedule, slot.date()), replay)
        self.assertIs(select_scheduled([replay, ep], schedule, slot.date()), ep)

    def test_unlisted_show_uses_local_times_and_adopts_new_episodes(self) -> None:
        aired = datetime(2026, 3, 8, 1, 15, tzinfo=TORONTO)
        self.assertEqual(next_balado(aired).isoformat(), "2026-03-08T06:00:00-04:00")
        original, = episodes(fixture("789", aired, [101]), "789")
        older = replace(original, id="400", aired=aired - timedelta(days=1), media=("102",))
        newer = replace(original, id="401", aired=aired + timedelta(days=1), media=("103",))
        with tempfile.TemporaryDirectory() as directory:
            library = Library(Path(directory), "789")
            with patch.object(library, "publish", return_value=True) as publish:
                self.assertTrue(sync_balado([older, original, newer], library, aired))
                publish.assert_called_once_with(original, "2026-03-08", "01:15", 1)
                publish.reset_mock()
                self.assertTrue(sync_balado([older, newer], library, newer.aired))
                publish.assert_called_once_with(newer, "2026-03-09", "01:15", 1)


@unittest.skipUnless(os.environ.get("OHDIO_LIVE_TEST") == "1", "test réseau sur demande")
class PublicStreamsTest(unittest.TestCase):
    def test_public_audio_for_six_shows(self) -> None:
        for show, schedule in SCHEDULES.items():
            with self.subTest(show=show):
                for attempt in range(3):
                    try:
                        discovered = discover(show, schedule.radio)
                        latest = next(ep for ep in discovered if schedule.accepts(ep)
                                      and not ep.replay and len(ep.media) >= schedule.parts)
                        for media_id in latest.media:
                            url = manifest(media_id)
                            self.assertIsNotNone(url, f"{show}/{media_id}: aucun flux HLS")
                            assert url is not None
                            ffmpeg("-rw_timeout", "20000000", "-i", url, "-map", "0:a:0",
                                   "-t", "2", "-f", "null", "-")
                    except (URLError, subprocess.CalledProcessError) as error:
                        if attempt == 2:
                            raise error
                    else:
                        break
