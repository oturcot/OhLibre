import json
import logging
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import NotRequired, TypedDict

from ohdio import Episode, manifest


class Entry(TypedDict):
    date: str
    media: list[str]
    complete: bool
    filename: NotRequired[str]


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
                entries[episode.id] = {"date": date, "media": ready.copy(), "complete": False,
                                       "filename": filename}
                self.save()
                logging.info("%s : partiel (1 segment)", output)
        complete = bool(ready) and len(ready) >= expected and len(ready) == len(episode.media)
        if not ready or len(ready) < len(previous):
            return False

        if ready != previous:
            publish_audio(output, self.work, episode, date, hour, ready)
            logging.info("%s : %s (%d segment(s))", output, "complet" if complete else "partiel", len(ready))

        entries[episode.id] = {"date": date, "media": ready, "complete": complete,
                               "filename": filename}
        self.save()
        if complete:
            for mid in ready:
                (self.work / f"{mid}.mp3").unlink(missing_ok=True)
        return complete
