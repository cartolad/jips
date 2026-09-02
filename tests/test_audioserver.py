import json

import pytest
from jsonschema import validate

from jips.audioserver import audioserver, dicts

from .conftest import random_string, test_data_path


@pytest.fixture
def app():
    audioserver.config["TESTING"] = True
    audioserver.config["DEBUG"] = False
    return audioserver


def test_ok(client):
    resp = client.get("/ok")
    assert resp.status_code == 200


def test_dicts_loaded():
    assert {"nhk16", "shinmeikai8", "daijisen"}.issubset(dicts.keys())


def test_index(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_stats(client):
    resp = client.get("/stats")
    assert resp.status_code == 200
    assert {"nhk16", "shinmeikai8", "daijisen"}.issubset(resp.json.keys())
    for stats in resp.json.values():
        assert isinstance(stats["words"], int)
        assert isinstance(stats["sounds"], int)


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
                "name": "[daijisen] 引く",
                "url": "http://localhost/utterances/daijisen/s00033728.mp3",
            },
            {
                "name": "[nhk16] 引く",
                "url": "http://localhost/utterances/nhk16/20171206152741.mp3",
            },
            {
                "name": "[shinmeikai8] 引く",
                "url": "http://localhost/utterances/shinmeikai8/00607.mp3",
            },
        ],
    }
    assert sorted(resp.json["audioSources"], key=lambda s: s["name"]) == sorted(
        expected["audioSources"], key=lambda s: s["name"]
    )

    url = sorted(resp.json["audioSources"], key=lambda s: s["name"])[0]["url"]
    assert url.startswith("http://localhost")

    mp3_resp = client.get(url)
    assert mp3_resp.status_code == 200
    assert mp3_resp.data[:3] == b"ID3", "doesn't look like an mp3 file!"


def test_audiojson__source_ordering_prefers_high_tiers(client):
    term = "引く"
    reading = "ひく"
    resp = client.get("/audio.json", query_string={"term": term, "reading": reading})
    assert resp.status_code == 200

    source_names = [s["name"] for s in resp.json["audioSources"]]
    # shinmeikai8 is tier 2: when nhk16 or daijisen also answer, every tier-1
    # source must come before the shinmeikai8 source
    tier2_idx = next(i for i, n in enumerate(source_names) if n.startswith("[shinmeikai8]"))
    tier1_idxs = [
        i for i, n in enumerate(source_names) if n.startswith("[nhk16]") or n.startswith("[daijisen]")
    ]
    assert tier1_idxs
    assert all(i < tier2_idx for i in tier1_idxs), "shinmeikai8 must be ordered after tier-1 sources"

    # ordering is deterministic for a given term/reading
    again = client.get("/audio.json", query_string={"term": term, "reading": reading})
    assert source_names == [s["name"] for s in again.json["audioSources"]]


def test_audiojson__shinmeikai8(client, audiojson_schema):
    term = "引く"
    reading = "ひく"
    resp = client.get("/audio.json", query_string={"term": term, "reading": reading})
    assert resp.status_code == 200
    validate(instance=resp.json, schema=audiojson_schema)

    sources = [s for s in resp.json["audioSources"] if s["name"] == "[shinmeikai8] 引く"]
    assert len(sources) == 1
    assert sources[0]["url"].endswith("/utterances/shinmeikai8/00607.mp3")

    mp3_resp = client.get(sources[0]["url"])
    assert mp3_resp.status_code == 200
    assert mp3_resp.data[:3] == b"ID3", "doesn't look like an mp3 file!"


def test_audiojson__daijisen(client, audiojson_schema):
    term = "引く"
    reading = "ひく"
    resp = client.get("/audio.json", query_string={"term": term, "reading": reading})
    assert resp.status_code == 200
    validate(instance=resp.json, schema=audiojson_schema)

    sources = [s for s in resp.json["audioSources"] if s["name"] == "[daijisen] 引く"]
    assert len(sources) == 1
    assert sources[0]["url"].endswith("/utterances/daijisen/s00033728.mp3")

    mp3_resp = client.get(sources[0]["url"])
    assert mp3_resp.status_code == 200
    assert mp3_resp.data[:3] == b"ID3", "doesn't look like an mp3 file!"


def test_audio__daijisen_combined_url(client):
    resp = client.get("/audio.json?term=%E9%83%A8&reading=%E3%81%B6")
    assert resp.status_code == 200
    sources = [
        s
        for s in resp.json["audioSources"]
        if s["url"].endswith("/utterances/daijisen/s00005446+s00019366.mp3")
    ]
    assert len(sources) == 1

    mp3_resp = client.get(sources[0]["url"])
    assert mp3_resp.status_code == 200
    assert mp3_resp.data[:3] == b"ID3", "doesn't look like an mp3 file!"


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


def test_audiojson__ambiguous_dict_does_not_break_response(client, audiojson_schema):
    # alternate examples:
    # /audio.json?term=%E6%9C%AC%E9%A4%A8&reading=%E3%81%BB%E3%82%93%E3%81%8B%E3%82%93
    # /audio.json?term=%E6%9E%9A&reading=%E3%81%BE%E3%81%84
    # /audio.json?term=%E4%BD%95%E5%9B%9E&reading=%E3%81%AA%E3%82%93%E3%81%8B%E3%81%84
    # NHK16 raises AmbiguityException for this term, but the other dictionaries
    # still answer, so the endpoint must not 500.
    resp = client.get(
        "/audio.json?term=%E5%A4%A7%E4%BA%8B&reading=%E3%81%A0%E3%81%84%E3%81%98"
    )
    assert resp.status_code == 200
    validate(instance=resp.json, schema=audiojson_schema)
    assert len(resp.json["audioSources"]) > 0


def test_audio(client):
    resp = client.get("/utterances/nhk16/20171115151714.mp3")
    assert resp.status_code == 200

    # check content type is correct
    assert resp.headers["Content-Type"] == "audio/mpeg"

    # check cache headers are there
    assert "Expires" in resp.headers
    assert "public" in resp.headers["Cache-Control"]


def test_audio_invalid_id(client):
    resp = client.get("/utterances/nhk16/ date .mp3")
    assert resp.status_code == 400
