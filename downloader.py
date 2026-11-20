import argparse
import fcntl
import logging
import os
import re
import signal
import subprocess
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from threading import Event
from zoneinfo import ZoneInfo

from library import Library
from ohdio import Episode, discover


TORONTO = ZoneInfo("America/Toronto")
FIVE_MINUTES = timedelta(minutes=5)


@dataclass(frozen=True)
class Schedule:
    days: range | tuple[int, ...]
    first_end: time
    tag_hour: str
    parts: int = 1
    radio: bool = True
    title_prefix: str = ""

    def accepts(self, episode: Episode) -> bool:
        return episode.title.casefold().startswith(self.title_prefix)

    def next_start(self, now: datetime) -> datetime:
        for offset in range(8):
            day = now.date() + timedelta(days=offset)
            candidate = datetime.combine(day, self.first_end, TORONTO)
            if day.weekday() in self.days and candidate > now:
                return candidate
        raise RuntimeError("Horaire sans jour de diffusion")

    def latest_start(self, now: datetime) -> datetime:
        for offset in range(8):
            day = now.date() - timedelta(days=offset)
            candidate = datetime.combine(day, self.first_end, TORONTO)
            if day.weekday() in self.days and candidate <= now:
                return candidate
        raise RuntimeError("Horaire sans jour de diffusion")


SCHEDULES = {
    "6056": Schedule(range(4), time(20), "20:00"),
    "12879": Schedule((4,), time(19, 30), "19:30", radio=False, title_prefix="épisode complet"),
    "3858": Schedule(range(5), time(12, 10), "13:00", parts=2),
    "302": Schedule(range(5), time(5, 30), "05:30"),
    "3855": Schedule(range(4), time(18, 55), "20:30"),
    "52": Schedule((6,), time(13, 6), "14:00", parts=2),
}


def select_scheduled(items: list[Episode], schedule: Schedule, day: date) -> Episode | None:
    candidates = [ep for ep in items if schedule.accepts(ep) and
                  (ep.last_aired if ep.replay else ep.aired).astimezone(TORONTO).date() == day]
    return max(candidates, key=lambda ep: (not ep.replay, ep.aired), default=None)


def sync_balado(items: list[Episode], library: Library, now: datetime) -> bool:
    originals = [ep for ep in items if not ep.replay and ep.aired <= now]
    if not originals:
        return True
    state = library.state
    if not state["floor"]:
        state["floor"] = max(ep.aired for ep in originals).isoformat()
        library.save()
    floor = datetime.fromisoformat(state["floor"])
    complete = True
    for ep in sorted(originals, key=lambda e: e.aired):
        if ep.aired >= floor:
            local = ep.aired.astimezone(TORONTO)
            complete = library.publish(ep, local.date().isoformat(), local.strftime("%H:%M"), 1) and complete
    return complete


def next_balado(now: datetime) -> datetime:
    return now.replace(hour=now.hour // 6 * 6, minute=0, second=0, microsecond=0) + timedelta(hours=6)


def run(show: str, root: Path, stop: Event, once: bool) -> None:
    schedule = SCHEDULES.get(show)
    library = Library(root, show)
    startup = True
    while not stop.is_set():
        now = datetime.now(TORONTO)
        slot = schedule.latest_start(now) if schedule else None
        active = slot is not None and slot.date() == now.date()
        next_check = schedule.next_start(now) if schedule else next_balado(now)
        title_check = library.next_title_check(now)
        title_due = title_check is not None and title_check <= now
        if startup or active or schedule is None or title_due:
            items = None
            try:
                logging.info("Vérification de l'émission %s", show)
                items = discover(show, schedule.radio if schedule else False)
                if schedule and slot:
                    episode = select_scheduled(items, schedule, slot.date())
                    complete = episode is not None and library.publish(
                        episode, episode.aired.astimezone(TORONTO).date().isoformat(),
                        schedule.tag_hour, schedule.parts,
                    )
                else:
                    complete = sync_balado(items, library, now)
            except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as error:
                if once:
                    raise
                logging.warning("Émission %s : %s", show, error)
                complete = False
            library.refresh_titles(items, datetime.now(TORONTO))
            if active and not complete:
                midnight = datetime.combine(now.date() + timedelta(days=1), time(), TORONTO)
                next_check = min(next_check, midnight, now + FIVE_MINUTES, key=datetime.timestamp)
        title_check = library.next_title_check(datetime.now(TORONTO))
        if title_check is not None:
            next_check = min(next_check, title_check, key=datetime.timestamp)
        if once:
            return
        startup = False
        stop.wait(max(0, next_check.timestamp() - datetime.now(TORONTO).timestamp()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Bibliothèque de rattrapage OHdio")
    parser.add_argument("--once", action="store_true", help="faire une vérification puis quitter")
    args = parser.parse_args()
    shows = [value.strip() for value in os.environ.get("OHDIO_SHOWS", "").split(",")]
    if any(not re.fullmatch(r"[1-9][0-9]*", show) for show in shows):
        parser.error("OHDIO_SHOWS doit contenir des identifiants séparés par des virgules")
    if len(set(shows)) != len(shows):
        parser.error("OHDIO_SHOWS contient des identifiants en double")
    root = Path(os.environ.get("OHDIO_OUTPUT", "/podcasts")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    with (root / ".ohdio.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, f"Un autre téléchargeur utilise déjà {root}\n")
        logging.info("Démarrage du téléchargeur OHdio — version %s",
                     os.environ.get("OHDIO_VERSION", "développement"))
        with ThreadPoolExecutor(max_workers=len(shows)) as workers:
            futures = [workers.submit(run, show, root, stop, args.once) for show in shows]
            try:
                wait(futures, return_when=FIRST_EXCEPTION)
                for future in futures:
                    if future.done():
                        future.result()
            finally:
                stop.set()


if __name__ == "__main__":
    main()
