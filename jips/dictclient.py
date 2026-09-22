from abc import ABC, abstractmethod
from pathlib import Path
import sqlite3
import json
from zipfile import ZipFile
from logging import getLogger
from dataclasses import dataclass
import subprocess
import io
import os
import re

from .exc import AmbiguityException
from .enums import AudioFormat

logger = getLogger(__name__)


@dataclass
class Utterance:
    source_dict: str
    source_dict_id: str
    audio_format: AudioFormat
    expression: str
    reading: str


class InvalidIDException(Exception):
    pass


class DictClient(ABC):
    name: str

    @abstractmethod
    def stats(self) -> dict:
        ...

    @abstractmethod
    def get_utterances(self, expression: str, reading: str) -> list[Utterance]:
        ...

    @abstractmethod
    def get_audio_by_id(self, internal_id: str):
        ...


class NHK16Client(DictClient):
    """This client is for the nhk16.zip format - with an "entries.json" file."""

    def __init__(self, zipfile_path: Path):
        self.name = "nhk16"
        self.zipfile_path = zipfile_path
        self.index_path = self.zipfile_path.parent / f"{self.zipfile_path.stem}.sqlite3"
        self._ensure_index()
        self.internal_id_regex = re.compile("^[0-9]+")

    def _ensure_index(self) -> None:
        if self.index_path.exists():
            logger.info("index found")
            return

        logger.info("index not found - building")
        stmt = "INSERT INTO entries (entry) VALUES (?);"
        create_table_stmt = """CREATE TABLE entries (
            entry JSON
        );"""

        index_1_stmt = (
            "CREATE INDEX idx_entries_kana ON entries (json_extract(entry, '$.kana'));"
        )

        with sqlite3.connect(self.index_path) as conn:
            conn.execute(create_table_stmt)
            with ZipFile(self.zipfile_path) as zipfile:
                with zipfile.open("nhk16/entries.json") as entries_f:
                    entries = [(json.dumps(e),) for e in json.load(entries_f)]
                    conn.executemany(stmt, entries)
            conn.execute(index_1_stmt)

    def stats(self) -> dict:
        stmt = """
        SELECT
          (
            SELECT
              COUNT(*)
            FROM
              (
                SELECT DISTINCT
                  json_extract(entry, '$.kana') AS kana,
                  kanji.value AS kanji
                FROM
                  entries,
                  json_each(json_extract(entry, '$.kanji')) AS kanji
              )
          ) AS distinct_words,
          (
            SELECT
              COUNT(DISTINCT json_extract(accents.value, '$.soundFile'))
            FROM
              entries,
              json_each(json_extract(entry, '$.accents')) AS accents
            WHERE
              json_extract(accents.value, '$.soundFile') IS NOT NULL
          ) AS distinct_sound_files;
        """
        with sqlite3.connect(self.index_path) as conn:
            cur = conn.execute(stmt)
            row = cur.fetchone()
        return {
            "words": row[0],
            "sounds": row[1],
        }

    def get_utterances(self, expression: str, reading: str) -> list[Utterance]:
        stmt = """
        SELECT *
        FROM entries
        WHERE
        json_extract(entry, '$.kana') = ?
        AND EXISTS (
        SELECT 1
        FROM json_each(json_extract(entry, '$.kanji'))
        WHERE json_each.value = ?
        );
        """
        with sqlite3.connect(self.index_path) as conn:
            cur = conn.execute(stmt, (reading, expression))
            entries = [json.loads(row[0]) for row in cur.fetchall()]

        if len(entries) == 0:
            return entries

        headwords = [e for e in entries if e.get("type") == "headword"]

        if len(headwords) > 1:
            raise AmbiguityException("part of speech needed to determine audio")

        utterances = []

        accents = headwords[0].get("accents", [])
        for accent in accents:
            if accent["notStandardButPermissible"]:
                logger.warning(
                    "notStandardButPermissible set for %s (%s)", expression, reading
                )
                continue
            else:
                internal_id = accent["soundFile"].removesuffix(".mp3")
                utterance = Utterance(
                    "nhk16", internal_id, AudioFormat.MP3, expression, reading
                )
                utterances.append(utterance)
        return utterances

    def get_audio_by_id(self, internal_id: str):
        if not self.internal_id_regex.match(internal_id):
            raise InvalidIDException("invalid id: %s", internal_id)

        # zipfile module is extremely slow for individual reads - so shell out
        # to `unzip` as an optimisation
        internal_path = f"nhk16/media/{internal_id}.mp3"
        command = ["unzip", "-p", self.zipfile_path, internal_path]
        result = subprocess.run(command, capture_output=True, check=True)
        return io.BytesIO(result.stdout)


class IndexJsonClient(DictClient):
    """Client for the version-2 "index.json" dictionary format (daijisen,
    shinmeikai8) - a per-dict media directory plus headword lookups."""

    # Bump when the on-disk index schema changes so stale caches rebuild.
    _SCHEMA_VERSION = 2

    def __init__(self, zipfile_path: Path):
        self.name = zipfile_path.stem
        self.zipfile_path = zipfile_path
        self.index_path = zipfile_path.parent / f"{zipfile_path.stem}.sqlite3"
        self.internal_id_regex = re.compile(r"^[A-Za-z0-9]+(\+[A-Za-z0-9]+)*$")
        self.media_dir = "media"
        self._ensure_index()

    def _ensure_index(self) -> None:
        if (
            self.index_path.exists()
            and self._index_schema_version() == self._SCHEMA_VERSION
        ):
            logger.info("index found for %s", self.name)
            return

        logger.info("index not found or outdated for %s - building", self.name)

        # This index caches media-file resolution (daijisen refs are written
        # `.ogg` but the ZIP ships `.mp3`). Replacing a dictionary ZIP requires
        # deleting its sibling <stem>.sqlite3 index.
        temp_index_path = Path(f"{self.index_path}.{os.getpid()}")

        with ZipFile(self.zipfile_path) as zipfile:
            index_json = json.load(zipfile.open(f"{self.name}/index.json"))
            meta = index_json.get("meta", {})
            if meta.get("media_dir") != self.media_dir:
                logger.warning(
                    "index.json meta.media_dir %r differs from expected %r for %s",
                    meta.get("media_dir"),
                    self.media_dir,
                    self.name,
                )
            media_dir_prefix = f"{self.name}/{self.media_dir}/"
            media_files = {
                name.removeprefix(media_dir_prefix)
                for name in zipfile.namelist()
                if name.startswith(media_dir_prefix)
            }

            files = index_json.get("files", {})
            rows = []
            for headword, refs in index_json.get("headwords", {}).items():
                for ref in refs:
                    resolved = self._resolve_ref(ref, media_files)
                    if resolved is None:
                        logger.warning(
                            "unresolvable media ref %r for headword %r in %s",
                            ref,
                            headword,
                            self.name,
                        )
                        continue
                    media_file, internal_id, ext = resolved
                    # The reading disambiguates headwords shared by multiple
                    # readings (e.g. 柱: はしら / ちゅう / じゅう).
                    reading = (files.get(ref) or {}).get("kana_reading")
                    rows.append((headword, internal_id, ext, reading))

        with sqlite3.connect(temp_index_path) as conn:
            conn.execute(
                "CREATE TABLE headwords (headword TEXT NOT NULL, id TEXT NOT NULL, "
                "ext TEXT NOT NULL, reading TEXT)"
            )
            conn.execute("CREATE INDEX idx_headwords_headword ON headwords (headword)")
            conn.execute(
                "CREATE INDEX idx_headwords_headword_reading "
                "ON headwords (headword, reading)"
            )
            conn.executemany(
                "INSERT INTO headwords (headword, id, ext, reading) VALUES (?, ?, ?, ?)",
                set(rows),
            )
            conn.execute(f"PRAGMA user_version = {self._SCHEMA_VERSION}")
        os.replace(temp_index_path, self.index_path)

    def _index_schema_version(self) -> int | None:
        try:
            with sqlite3.connect(self.index_path) as conn:
                row = conn.execute("PRAGMA user_version").fetchone()
        except sqlite3.DatabaseError:
            return None
        return row[0] if row else None

    def _resolve_ref(
        self, ref: str, media_files: set[str]
    ) -> tuple[str, str, str] | None:
        """Resolve an index.json media ref to an actual ZIP media file.

        Tries the ref basename as-is first, then with the extension swapped to
        each known AudioFormat value (daijisen refs are `.ogg` but the media
        files shipped are `.mp3`). Returns (media_file, internal_id, ext) or
        None if nothing in the ZIP matches.
        """
        candidates = [ref]
        base, _, _ = ref.rpartition(".")
        candidates.extend(f"{base}.{fmt.value}" for fmt in AudioFormat)

        for media_file in candidates:
            if media_file in media_files:
                internal_id, ext = media_file.rsplit(".", 1)
                return media_file, internal_id, ext
        return None

    def stats(self) -> dict:
        with sqlite3.connect(self.index_path) as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT headword), COUNT(DISTINCT id) FROM headwords"
            ).fetchone()
        return {"words": row[0], "sounds": row[1]}

    def get_utterances(self, expression: str, reading: str) -> list[Utterance]:
        # Match on both term and reading to disambiguate homographs that share
        # a headword but have different readings (e.g. 柱: はしら / ちゅう /
        # じゅう). The reading-only lookup covers kana-only headword keys.
        rows = self._lookup_headword(expression, reading)
        if not rows:
            rows = self._lookup_headword(reading, reading)

        utterances = []
        for internal_id, ext in rows:
            # AudioFormat enum values are lowercase, so use NAME lookup
            try:
                audio_format = AudioFormat[ext.upper()]
            except KeyError:
                logger.warning(
                    "unknown audio extension %r for %s (%s)", ext, expression, reading
                )
                continue
            utterances.append(
                Utterance(self.name, internal_id, audio_format, expression, reading)
            )
        return utterances

    def _lookup_headword(self, headword: str, reading: str) -> list[tuple[str, str]]:
        stmt = (
            "SELECT DISTINCT id, ext FROM headwords "
            "WHERE headword = ? AND reading = ? ORDER BY id"
        )
        with sqlite3.connect(self.index_path) as conn:
            rows = conn.execute(stmt, (headword, reading)).fetchall()
        return [(row[0], row[1]) for row in rows]

    def get_audio_by_id(self, internal_id: str):
        if not self.internal_id_regex.match(internal_id):
            raise InvalidIDException(f"invalid id: {internal_id}")

        # zipfile module is extremely slow for individual reads - so shell out
        # to `unzip` as an optimisation
        for ext in ("mp3", "ogg"):
            internal_path = f"{self.name}/{self.media_dir}/{internal_id}.{ext}"
            command = ["unzip", "-p", str(self.zipfile_path), internal_path]
            result = subprocess.run(command, capture_output=True, check=False)
            if result.returncode == 0:
                return io.BytesIO(result.stdout)
        raise InvalidIDException(f"no audio file found for id: {internal_id}")
