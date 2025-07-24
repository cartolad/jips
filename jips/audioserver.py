from pathlib import Path
from datetime import timedelta
from logging import getLogger

from jips.enums import AudioFormat
from jips.exc import AmbiguityException
from jips.dictclient import DictClient

from flask import Flask, request, url_for, send_file

audioserver = Flask(__name__)

logger = getLogger(__name__)

ONE_YEAR_IN_SECONDS = int(timedelta(days=366).total_seconds())

def get_dicts() -> dict[str, Path]:
    dict_dir = (Path(__file__).parent.parent / "dicts").resolve()
    dicts = {f.stem: f for f in dict_dir.glob("*.zip")}
    logger.info("found dicts: %s", [dicts])
    return dicts


@audioserver.route("/ok")
def ok():
    return {"ok": True}


@audioserver.route("/audio.json")
def audio_json():
    term = request.args["term"]
    reading = request.args["reading"]

    dicts = get_dicts()

    dict_client = DictClient(dicts["nhk16"])
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
    dict_client = DictClient(get_dicts()[dict_name])
    audio = dict_client.get_audio_by_id(internal_id)
    return send_file(
        audio, mimetype=audio_format.mimetype(), max_age=ONE_YEAR_IN_SECONDS
    )
