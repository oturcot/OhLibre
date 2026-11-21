import json
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


SITE = "https://ici.radio-canada.ca/ohdio"
VALIDATION = "https://services.radio-canada.ca/media/validation/v2/"


class Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain(value: str | None) -> str:
    parser = Text()
    parser.feed(value or "")
    return " ".join(" ".join(parser.parts).split())


def read(url: str) -> str:
    request = Request(url, headers={"User-Agent": "OhLibre/1.0"})
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


@dataclass(frozen=True)
class Episode:
    id: str
    title: str
    summary: str
    aired: datetime
    last_aired: datetime
    replay: bool
    media: tuple[str, ...]
    show_title: str


def episodes(html: str, show_id: str) -> list[Episode]:
    marker = re.search(r"window\._rcState_\s*=\s*", html)
    if marker is None:
        raise ValueError("état OHdio absent")
    state, _ = json.JSONDecoder().raw_decode(html, marker.end())
    for page in state["pages"]["pages"].values():
        data = page["data"]
        if data.get("typename") == "ProgramPage" and str(data["program"]["globalId"]["id"]) == show_id:
            break
    else:
        raise ValueError("page d'émission OHdio introuvable")

    show_title = plain(data["program"]["title"])
    if not show_title:
        raise ValueError("nom d'émission OHdio absent")
    result = []
    for item in data["episodes"]:
        episode_id = str(item["globalId"]["id"])
        aired = datetime.fromisoformat(item["broadcastedFirstTimeAt"])
        last = datetime.fromisoformat(item["broadcastedLastTimeAt"] or item["broadcastedFirstTimeAt"])
        media = tuple(dict.fromkeys(str(mid) for mid in item["mediaIds"] if mid))
        if not re.fullmatch(r"[0-9]+", episode_id) or any(not re.fullmatch(r"[0-9]+", mid) for mid in media):
            raise ValueError("identifiant d'épisode ou de média invalide")
        if aired.tzinfo is None or last.tzinfo is None:
            raise ValueError("horaire OHdio sans fuseau")
        result.append(Episode(episode_id, plain(item["title"]), plain(item["summary"]), aired,
                              last, item["isBroadcastedReplay"], media, show_title))
    return result


def discover(show_id: str, radio: bool) -> list[Episode]:
    kind = "premiere/emissions" if radio else "balados"
    return episodes(read(f"{SITE}/{kind}/{show_id}/-"), show_id)


def manifest(media_id: str) -> str | None:
    query = urlencode({
        "appCode": "medianet", "connectionType": "hd", "deviceType": "ipad",
        "idMedia": media_id, "multibitrate": "true", "output": "json",
        "tech": "hls", "manifestVersion": "2",
    })
    data = json.loads(read(f"{VALIDATION}?{query}"))
    url = data.get("urlSecureHls") or data.get("url")
    if not url:
        return None
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(f"{media_id}: adresse HLS inattendue")
    return url
