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
