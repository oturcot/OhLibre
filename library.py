import json
import logging
import re
import subprocess
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NotRequired, TypedDict

from ohdio import Episode, manifest


class Entry(TypedDict):
    date: str
    media: list[str]
    complete: bool
    filename: NotRequired[str]
    title: NotRequired[str]
    title_next: NotRequired[str]
    title_until: NotRequired[str]


class State(TypedDict):
    floor: str
    entries: dict[str, Entry]


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror",
                    "-y", *args], check=True, timeout=900)


def fetch(media_id: str, path: Path) -> bool:
    url = manifest(media_id)
    if url is None:
        logging.info("Média %s pas encore accessible", media_id)
        return False
    logging.info("Téléchargement du média %s", media_id)
    temp = path.with_suffix(".tmp")
    try:
        ffmpeg("-rw_timeout", "20000000", "-i", url, "-map", "0:a:0", "-map_metadata", "-1",
               "-ac", "2", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "128k",
               "-write_xing", "0", "-f", "mp3", str(temp))
        temp.replace(path)
        logging.info("Média %s téléchargé", media_id)
    finally:
        temp.unlink(missing_ok=True)
    return True


def episode_filename(date: str, title: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError(f"Date de fichier invalide : {date!r}")
    title = unicodedata.normalize("NFC", re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", title))
    title = " ".join(title.split()).strip(" .")
    title = title.encode("utf-8")[:239].decode("utf-8", errors="ignore").rstrip(" .")
    if not title:
        raise ValueError("Titre d'épisode inutilisable comme nom de fichier")
    return f"{date}_{title}.mp3"


def publish_audio(output: Path, work: Path, episode: Episode, date: str, hour: str,
                  media: list[str]) -> None:
    playlist = work / "concat.txt"
    playlist.write_text("".join(f"file '{mid}.mp3'\n" for mid in media), encoding="ascii")
    temp = output.with_name(f".{output.stem}.tmp")
    try:
        date_tag = f"{date}T{hour}"
        ffmpeg("-f", "concat", "-safe", "1", "-i", str(playlist), "-c", "copy",
               "-id3v2_version", "4", "-metadata", f"title={episode.title}",
               "-metadata", f"date={date_tag}", "-metadata", f"comment={episode.summary}",
               "-f", "mp3", str(temp))
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)
        playlist.unlink(missing_ok=True)


class Library:
    def __init__(self, root: Path, show: str) -> None:
        self.root = root
        self.output = root / show
        self.work = root / ".ohdio" / show
        self.work.mkdir(parents=True, exist_ok=True)
        self.index = self.work / "index.json"
        self.state: State = (json.loads(self.index.read_text(encoding="utf-8"))
                             if self.index.exists() else {"floor": "", "entries": {}})

    def set_show_title(self, title: str) -> None:
        name = unicodedata.normalize("NFC", re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", title)).strip(" .")
        if not name or name in {".ohdio", ".ohdio.lock"}:
            raise ValueError(f"Nom d'émission invalide : {title!r}")
        matches = [path for path in self.root.iterdir()
                   if unicodedata.normalize("NFC", path.name) == name]
        if len(matches) > 1:
            raise ValueError(f"Plusieurs dossiers correspondent à {name!r}")
        self.output = matches[0] if matches else self.root / name
        self.output.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        temp = self.index.with_suffix(".tmp")
        temp.write_text(json.dumps(self.state), encoding="utf-8")
        temp.replace(self.index)

    def record(self, episode: Episode, date: str, media: list[str], complete: bool,
               filename: str) -> None:
        entry = self.state["entries"].get(episode.id)
        if entry is None:
            now = datetime.now(timezone.utc)
            entry = {"date": date, "media": media, "complete": complete,
                     "filename": filename, "title": episode.title,
                     "title_next": (now + timedelta(minutes=15)).isoformat(),
                     "title_until": (now + timedelta(hours=6)).isoformat()}
        else:
            entry.update(date=date, media=media, complete=complete, filename=filename)
        self.state["entries"][episode.id] = entry
        self.save()

    def next_title_check(self, now: datetime) -> datetime | None:
        checks = [datetime.fromisoformat(entry["title_next"])
                  for entry in self.state["entries"].values()
                  if "title_next" in entry and "title_until" in entry
                  and now <= datetime.fromisoformat(entry["title_until"])]
        return min(checks, default=None)

    def refresh_titles(self, items: list[Episode] | None, now: datetime) -> None:
        episodes = {episode.id: episode for episode in items or [] if not episode.replay}
        for episode_id, entry in self.state["entries"].items():
            if "title_next" not in entry or "title_until" not in entry:
                continue
            due = datetime.fromisoformat(entry["title_next"])
            until = datetime.fromisoformat(entry["title_until"])
            if now > until or now < due:
                continue
            entry["title_next"] = min(now + timedelta(minutes=15), until).isoformat()
            if now >= until:
                del entry["title_next"]
            self.save()
            if items is None:
                continue
            episode = episodes.get(episode_id)
            if episode is None:
                logging.warning("Épisode %s absent de la page OHdio pendant le suivi du titre", episode_id)
                continue
            if episode.title == entry.get("title"):
                continue
            try:
                self.update_title(episode, entry)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                logging.warning("Épisode %s : mise à jour du titre impossible : %s", episode_id, error)

    def update_title(self, episode: Episode, entry: Entry) -> None:
        self.set_show_title(episode.show_title)
        filename = entry["filename"]
        if Path(filename).name != filename or "\\" in filename:
            raise ValueError(f"Nom de fichier indexé invalide : {filename!r}")
        source = self.output / filename
        destination = self.output / episode_filename(entry["date"], episode.title)
        temp = source.with_name(f".{source.stem}.tmp")
        same_file = destination == source
        if not same_file and destination.exists() and source.samefile(destination):
            names = {unicodedata.normalize("NFC", path.name) for path in self.output.iterdir()}
            same_file = unicodedata.normalize("NFC", destination.name) not in names
        try:
            ffmpeg("-i", str(source), "-map", "0", "-map_metadata", "0", "-c", "copy",
                   "-id3v2_version", "4", "-metadata", f"title={episode.title}",
                   "-f", "mp3", str(temp))
            if not same_file:
                with destination.open("xb"):
                    pass
                old_title = entry.get("title")
                try:
                    temp.replace(destination)
                    entry["filename"] = destination.name
                    entry["title"] = episode.title
                    self.save()
                except (OSError, ValueError):
                    entry["filename"] = filename
                    if old_title is None:
                        entry.pop("title", None)
                    else:
                        entry["title"] = old_title
                    destination.unlink(missing_ok=True)
                    raise
                source.unlink()
            else:
                temp.replace(source)
                if destination != source:
                    staging = self.work / f".title-{episode.id}.tmp"
                    with staging.open("xb"):
                        pass
                    moved = False
                    try:
                        source.replace(staging)
                        moved = True
                        try:
                            with destination.open("xb"):
                                pass
                        except OSError:
                            logging.error("Épisode %s : fichier conservé dans %s", episode.id, staging)
                            raise
                        try:
                            staging.replace(destination)
                        except OSError:
                            destination.unlink(missing_ok=True)
                            staging.replace(source)
                            raise
                    except OSError:
                        if not moved:
                            staging.unlink(missing_ok=True)
                        raise
                    entry["filename"] = destination.name
                entry["title"] = episode.title
                self.save()
        finally:
            temp.unlink(missing_ok=True)
        logging.info("Épisode %s : titre mis à jour : %s", episode.id, episode.title)

    def publish(self, episode: Episode, date: str, hour: str, expected: int) -> bool:
        entries = self.state["entries"]
        entry = entries.get(episode.id)
        if episode.replay:
            return True
        self.set_show_title(episode.show_title)
        if any(set(episode.media).intersection(other["media"])
               for key, other in entries.items() if key != episode.id):
            logging.info("Épisode %s ignoré : média déjà publié", episode.id)
            return True

        if entry:
            date = entry["date"]
        filename = entry.get("filename") if entry else None
        if filename is not None and (Path(filename).name != filename or "\\" in filename):
            raise ValueError(f"Nom de fichier indexé invalide : {filename!r}")
        old = self.output / f"{date}-{episode.id}.mp3"
        if entry and filename is None and old.is_file():
            filename = old.name
        if filename is None:
            filename = episode_filename(date, episode.title)
            output = self.output / filename
            if output.exists():
                raise FileExistsError(f"Publication refusée : {output} existe déjà sans index")
        output = self.output / filename
        if not entry and output.exists():
            raise FileExistsError(f"Publication refusée : {output} existe déjà sans index")
        previous = entry["media"] if entry and output.is_file() else []
        if entry and entry["complete"] and output.is_file() and list(episode.media) == previous:
            return True
        if previous and tuple(previous) != episode.media[:len(previous)]:
            logging.warning("Épisode %s : liste audio incomplète ou modifiée, fichier conservé", episode.id)
            return False

        ready: list[str] = []
        for mid in episode.media:
            path = self.work / f"{mid}.mp3"
            if not path.is_file():
                try:
                    if not fetch(mid, path):
                        break
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    logging.warning("Média %s indisponible : %s", mid, error)
                    break
            ready.append(mid)
            if len(ready) == 1 and len(episode.media) > 1 and not previous:
                publish_audio(output, self.work, episode, date, hour, ready)
                previous = ready.copy()
                self.record(episode, date, ready.copy(), False, filename)
                logging.info("%s : partiel (1 segment)", output)
        complete = bool(ready) and len(ready) >= expected and len(ready) == len(episode.media)
        if not ready or len(ready) < len(previous):
            return False

        if ready != previous:
            publish_audio(output, self.work, episode, date, hour, ready)
            logging.info("%s : %s (%d segment(s))", output, "complet" if complete else "partiel", len(ready))

        self.record(episode, date, ready, complete, filename)
        if complete:
            for mid in ready:
                (self.work / f"{mid}.mp3").unlink(missing_ok=True)
        return complete
