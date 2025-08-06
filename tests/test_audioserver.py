import json

import pytest
from jsonschema import validate

from jips.audioserver import audioserver

from .conftest import random_string, test_data_path


@pytest.fixture
def app():
    audioserver.config["TESTING"] = True
    audioserver.config["DEBUG"] = False
    return audioserver


def test_ok(client):
    resp = client.get("/ok")
    assert resp.status_code == 200


def test_index(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_stats(client):
    resp = client.get("/stats")
    assert resp.status_code == 200


def test_audiojson__invalid_request(client):
    resp = client.get("/audio.json")
    assert resp.status_code == 400


@pytest.fixture(scope="session")
def audiojson_schema():
    with open(
        test_data_path / "yomitan-custom-audio-list-schema.json", "r"
    ) as schema_f:
        return json.load(schema_f)


def test_audiojson__noaudio(client, audiojson_schema):
    term = random_string()
    reading = random_string()
    resp = client.get("/audio.json", query_string={"term": term, "reading": reading})
    assert resp.status_code == 200
    validate(instance=resp.json, schema=audiojson_schema)


def test_audio__success(client, audiojson_schema):
    """Test that audio is found correctly when present"""
    term = "引く"
    reading = "ひく"
    resp = client.get("/audio.json", query_string={"term": term, "reading": reading})
    assert resp.status_code == 200
    validate(instance=resp.json, schema=audiojson_schema)

    expected = {
        "type": "audioSourceList",
        "audioSources": [
            {
                "name": "[nhk16] 引く",
                "url": "http://localhost/utterances/nhk16/20171206152741.mp3",
            }
        ],
    }
    assert expected == resp.json

    url = resp.json["audioSources"][0]["url"]
    assert url.startswith("http://localhost")

    mp3_resp = client.get(url)
    assert mp3_resp.status_code == 200


def test_audio__repeat(client, audiojson_schema):
    term = "引く"
    reading = "ひく"
    resp = client.get("/audio.json", query_string={"term": term, "reading": reading})
    assert resp.status_code == 200
    resp = client.get("/audio.json", query_string={"term": term, "reading": reading})
    assert resp.status_code == 200


def test_audio__headword_and_counter(client, audiojson_schema):
    resp = client.get("/audio.json?term=%E9%83%A8&reading=%E3%81%B6")
    assert resp.status_code == 200
    validate(instance=resp.json, schema=audiojson_schema)


@pytest.mark.xfail(reason="part of speech not supported")
def test_audiojson__ambigious_without_part_of_speech(client, audiojson_schema):
    # alternate examples:
    # /audio.json?term=%E6%9C%AC%E9%A4%A8&reading=%E3%81%BB%E3%82%93%E3%81%8B%E3%82%93
    # /audio.json?term=%E6%9E%9A&reading=%E3%81%BE%E3%81%84
    # /audio.json?term=%E4%BD%95%E5%9B%9E&reading=%E3%81%AA%E3%82%93%E3%81%8B%E3%81%84
    resp = client.get(
        "/audio.json?term=%E5%A4%A7%E4%BA%8B&reading=%E3%81%A0%E3%81%84%E3%81%98"
    )
    assert resp.status_code == 200
    validate(instance=resp.json, schema=audiojson_schema)
