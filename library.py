import ctypes
import errno
import json
import logging
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from threading import Lock
from typing import TypedDict

from ohdio import Episode, manifest


DIRECTORY_LOCK = Lock()


def move_no_replace(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except FileExistsError:
        if not os.path.samefile(source, destination):
            raise FileExistsError(f"Migration refusée : {destination} existe déjà")
    except OSError as error:
        if sys.platform != "linux" or error.errno not in {
            errno.EPERM, errno.ENOSYS, errno.ENOTSUP, errno.EXDEV,
        }:
            raise
        libc = ctypes.CDLL(None, use_errno=True)
        try:
            rename = libc.renameat2
        except AttributeError as unavailable:
            raise OSError(errno.ENOTSUP, "Renommage exclusif indisponible", str(source)) from unavailable
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        at_fdcwd, rename_noreplace = -100, 1
        if rename(at_fdcwd, os.fsencode(source), at_fdcwd, os.fsencode(destination), rename_noreplace) != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(destination))
        return
    source.unlink()


class Entry(TypedDict):
    date: str
    media: list[str]
    complete: bool


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
    temp = path.with_suffix(".tmp")
    try:
        ffmpeg("-rw_timeout", "20000000", "-i", url, "-map", "0:a:0", "-map_metadata", "-1",
               "-ac", "2", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "128k",
               "-write_xing", "0", "-f", "mp3", str(temp))
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return True


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
        self.show = show
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
        with DIRECTORY_LOCK:
            markers = self.root / ".ohdio"
            for marker in markers.glob("*/directory"):
                if marker.parent != self.work and unicodedata.normalize(
                    "NFC", marker.read_text(encoding="utf-8")
                ) == name:
                    raise ValueError(f"Le dossier {name!r} appartient déjà à une autre émission")
            matches = [path for path in self.root.iterdir()
                       if unicodedata.normalize("NFC", path.name) == name]
            if len(matches) > 1:
                raise ValueError(f"Plusieurs dossiers correspondent à {name!r}")
            output = matches[0] if matches else self.root / name
            output.mkdir(parents=True, exist_ok=True)
            marker = self.work / "directory"
            if marker.exists() and unicodedata.normalize("NFC", marker.read_text(encoding="utf-8")) != name:
                raise ValueError(f"Le nom de l'émission {self.show} a changé; migration manuelle requise")
            marker.write_text(name, encoding="utf-8")
            legacy = self.root / self.show
            if legacy != output:
                for episode_id, entry in self.state["entries"].items():
                    old = legacy / f'{entry["date"]}-{episode_id}.mp3'
                    new = output / old.name
                    if not old.is_file():
                        continue
                    move_no_replace(old, new)
            self.output = output

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
        output = self.output / f"{date}-{episode.id}.mp3"
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
                entries[episode.id] = {"date": date, "media": ready.copy(), "complete": False}
                self.save()
                logging.info("%s : partiel (1 segment)", output)
        complete = bool(ready) and len(ready) >= expected and len(ready) == len(episode.media)
        if not ready or len(ready) < len(previous):
            return False

        if ready != previous:
            publish_audio(output, self.work, episode, date, hour, ready)
            logging.info("%s : %s (%d segment(s))", output, "complet" if complete else "partiel", len(ready))

        entries[episode.id] = {"date": date, "media": ready, "complete": complete}
        self.save()
        if complete:
            for mid in ready:
                (self.work / f"{mid}.mp3").unlink(missing_ok=True)
        return complete
