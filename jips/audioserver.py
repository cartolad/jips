from pathlib import Path
from datetime import timedelta
from logging import getLogger

from jips.enums import AudioFormat
from jips.exc import AmbiguityException
from jips.dictclient import DictClient, NHK16Client

from flask import Flask, request, url_for, send_file, render_template

audioserver = Flask(__name__)

logger = getLogger(__name__)

ONE_YEAR_IN_SECONDS = int(timedelta(days=366).total_seconds())

dict_dir = (Path(__file__).parent.parent / "dicts").resolve()


def get_dict_client(path: Path) -> DictClient | None:
    if path.name == "nhk16.zip":
        return NHK16Client(path)
    else:
        return None


dicts = {}
for dict_path in dict_dir.glob("*.zip"):
    dict_client = get_dict_client(dict_path)
    if dict_client is not None:
        dicts[dict_path.stem] = dict_client


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
    dict_client = dicts["nhk16"]
    return dict_client.stats()


@audioserver.route("/audio.json")
def audio_json():
    term = request.args["term"]
    reading = request.args["reading"]

    dict_client = dicts["nhk16"]
    try:
        utterances = dict_client.get_utterances(term, reading)
    except AmbiguityException as e:
        return {"error": str(e)}, 500

    audio_sources = []
    for u in utterances:
        audio_sources.append(
            {
                "name": f"[{dict_client.name}] {u.expression}",
                "url": url_for(
                    "utterance_file",
                    dict_name=dict_client.name,
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
    audio = dict_client.get_audio_by_id(internal_id)
    return send_file(
        audio, mimetype=audio_format.mimetype(), max_age=ONE_YEAR_IN_SECONDS
    )
