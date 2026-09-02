from pathlib import Path
from datetime import timedelta
from logging import getLogger
import hashlib
import random

from jips.enums import AudioFormat
from jips.exc import AmbiguityException
from jips.dictclient import DictClient, NHK16Client, IndexJsonClient, InvalidIDException

from flask import Flask, request, url_for, send_file, render_template

audioserver = Flask(__name__)

logger = getLogger(__name__)

ONE_YEAR_IN_SECONDS = int(timedelta(days=366).total_seconds())

dict_dir = (Path(__file__).parent.parent / "dicts").resolve()


def get_dict_client(path: Path) -> DictClient | None:
    if path.name == "nhk16.zip":
        return NHK16Client(path)
    elif path.name in ("shinmeikai8.zip", "daijisen.zip"):
        return IndexJsonClient(path)
    else:
        return None


dicts = {}
for dict_path in dict_dir.glob("*.zip"):
    dict_client = get_dict_client(dict_path)
    if dict_client is not None:
        dicts[dict_path.stem] = dict_client

# Tier 1 sources are the highest-quality audio (nhk16, daijisen). Yomitan
# plays the first source in the list by default, so tier-1 sources must always
# precede tier-2 (shinmeikai8). Within a tier the order is a deterministic
# shuffle seeded by the lookup, so no single tier-1 dict is always first.
SOURCE_TIERS = {"nhk16": 1, "daijisen": 1, "shinmeikai8": 2}


def _lookup_seed(term: str, reading: str) -> int:
    digest = hashlib.blake2b(f"{term}\0{reading}".encode(), digest_size=8)
    return int.from_bytes(digest.digest(), "big")


def _ordered_dict_clients(term: str, reading: str) -> list[DictClient]:
    by_tier: dict[int, list[DictClient]] = {}
    for client in sorted(dicts.values(), key=lambda c: c.name):
        by_tier.setdefault(SOURCE_TIERS.get(client.name, 99), []).append(client)

    rng = random.Random(_lookup_seed(term, reading))
    ordered = []
    for tier in sorted(by_tier):
        tier_clients = by_tier[tier]
        if len(tier_clients) > 1:
            rng.shuffle(tier_clients)
        ordered.extend(tier_clients)
    return ordered


@audioserver.route("/")
def index():
    return render_template(
        "index.html",
        dicts=dicts,
    )


@audioserver.route("/ok")
def ok():
    return {"ok": True}


@audioserver.route("/stats")
def stats():
    return {name: client.stats() for name, client in dicts.items()}


@audioserver.route("/audio.json")
def audio_json():
    term = request.args["term"]
    reading = request.args["reading"]

    audio_sources = []
    for dict_client in _ordered_dict_clients(term, reading):
        try:
            utterances = dict_client.get_utterances(term, reading)
        except AmbiguityException as e:
            logger.warning("ambiguity for %s (%s) in %s: %s", term, reading, dict_client.name, e)
            continue

        for u in utterances:
            audio_sources.append(
                {
                    "name": f"[{u.source_dict}] {u.expression}",
                    "url": url_for(
                        "utterance_file",
                        dict_name=u.source_dict,
                        internal_id=u.source_dict_id,
                        ext=u.audio_format.value,
                        _external=True,
                    ),
                }
            )
    return {"type": "audioSourceList", "audioSources": audio_sources}


@audioserver.route("/utterances/<dict_name>/<internal_id>.<ext>")
def utterance_file(dict_name: str, internal_id: str, ext: str):
    # FIXME: handle 404
    audio_format = AudioFormat(ext)
    # FIXME: handle unknown dict
    dict_client = dicts[dict_name]
    try:
        audio = dict_client.get_audio_by_id(internal_id)
    except InvalidIDException:
        return "invalid id", 400
    return send_file(
        audio, mimetype=audio_format.mimetype(), max_age=ONE_YEAR_IN_SECONDS
    )
