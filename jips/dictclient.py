from abc import ABC
from pathlib import Path
import sqlite3
import json
from zipfile import ZipFile
from logging import getLogger
from dataclasses import dataclass

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


class DictClient(ABC):
    pass


class NHK16Client(DictClient):
    """This client is for the nhk16.zip format - with an "entries.json" file."""

    def __init__(self, zipfile_path: Path):
        self.name = "nhk16"
        self.zipfile_path = zipfile_path
        self.index_path = self.zipfile_path.parent / f"{self.zipfile_path.stem}.sqlite3"
        self._ensure_index()

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
        with ZipFile(self.zipfile_path) as zipfile:
            return zipfile.open(f"nhk16/media/{internal_id}.mp3", "r")
