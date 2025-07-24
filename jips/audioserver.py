from datetime import timedelta
from logging import getLogger

from jips.exc import AmbiguityException
from jips.enums import AudioFormat
from jips.dictclient import DictClient

from flask import Flask, request, url_for, send_file

audioserver = Flask(__name__)

logger = getLogger(__name__)

ONE_YEAR_IN_SECONDS = int(timedelta(days=366).total_seconds())


@audioserver.route("/ok")
def ok():
    return {"ok": True}


@audioserver.route("/audio.json")
def audio_json():
    term = request.args["term"]
    reading = request.args["reading"]

    dict_client = DictClient()
    try:
        utterances = dict_client.get_utterances(term, reading)
    except AmbiguityException as e:
        return {"error": str(e)}, 500

    audio_sources = []
    for u in utterances:
        audio_sources.append(
            {
                "name": f"{u.expression} ({u.reading})",
                "url": url_for(
                    "utterance_file",
                    udb_id=u.utterance_id,
                    ext=u.audio_format.value,
                    _external=True,
                ),
            }
        )
    return {"type": "audioSourceList", "audioSources": audio_sources}
