import json
import logging
import subprocess
from pathlib import Path
from typing import TypedDict

from ohdio import Episode, manifest


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


class Library:
    def __init__(self, root: Path, show: str) -> None:
        self.output = root / show
        self.work = root / ".ohdio" / show
        self.output.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)
        self.index = self.work / "index.json"
        self.state: State = (json.loads(self.index.read_text(encoding="utf-8"))
                             if self.index.exists() else {"floor": "", "entries": {}})

    def save(self) -> None:
        temp = self.index.with_suffix(".tmp")
        temp.write_text(json.dumps(self.state), encoding="utf-8")
        temp.replace(self.index)

    def publish(self, episode: Episode, date: str, hour: str, expected: int) -> bool:
        entries = self.state["entries"]
        entry = entries.get(episode.id)
        if episode.replay:
            return True
        if any(set(episode.media).intersection(other["media"])
               for key, other in entries.items() if key != episode.id):
            logging.info("Épisode %s ignoré : média déjà publié", episode.id)
            return True

        if entry:
            date = entry["date"]
        output = self.output / f"{date}-{episode.id}.mp3"
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
        complete = bool(ready) and len(ready) >= expected and len(ready) == len(episode.media)
        if not ready or len(ready) < len(previous):
            return False

        if ready != previous:
            playlist = self.work / "concat.txt"
            playlist.write_text("".join(f"file '{mid}.mp3'\n" for mid in ready), encoding="ascii")
            temp = self.output / f".{output.stem}.tmp"
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
            logging.info("%s : %s (%d segment(s))", output, "complet" if complete else "partiel", len(ready))

        entries[episode.id] = {"date": date, "media": ready, "complete": complete}
        self.save()
        if complete:
            for mid in ready:
                (self.work / f"{mid}.mp3").unlink(missing_ok=True)
        return complete
