# jips

## Project Overview

jips is a local HTTP audio server that serves Japanese word pronunciations for use with [Yomitan](https://yomitan.wiki/) and similar immersion learning tools. It reads audio files from locally-stored dictionary ZIP files (currently NHK16 format) and exposes them over a simple Flask/Gunicorn HTTP API on port 1989.

## Architecture

- `jips/audioserver.py` — Flask app, routes, and request handling
- `jips/dictclient.py` — `DictClient` abstract base class + `NHK16Client` concrete implementation; `Utterance` dataclass
- `jips/enums.py` — `AudioFormat` enum (MP3/OGG)
- `jips/exc.py` — `AmbiguityException`
- `bin/audioserver` — bash script that launches gunicorn on port 1989

## Dictionary Data

The `dicts/` directory holds large binary ZIP files and is **not tracked in git**. Never read files there directly. The schema and access patterns can be inferred from `NHK16Client` in `dictclient.py`.

## Dev Commands

```sh
tox                          # canonical: runs ruff check + pytest
uv run --dev pytest          # run tests directly
.tox/py/bin/ruff check .     # lint directly (after tox has set up the env)
```

Docker is also available:

```sh
docker compose up --build -d  # runs on port 1989
```

## Permitted Bash Commands

Mirrors `.claude/settings.local.json`:

- `tox` / `tox *`
- `.tox/*/bin/python -m pytest *`
- `.tox/*/bin/mypy *`
- `.tox/*/bin/ruff *`

## Key Conventions

- Python 3.14, managed with `uv`
- Ruff for linting and formatting (defaults; no separate config file)
- pytest + pytest-flask for tests
- No CI/CD — test locally with tox

## Known TODOs / In-Progress Work

- **Part-of-speech disambiguation**: test marked `xfail` in `test_audioserver.py`
- **Additional dictionary formats**: support beyond NHK16 is in progress (see commit `a5e8b22`)
