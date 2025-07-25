import os
import sys
from importlib import reload
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import core.db as db_module


def _load(tmp_path):
    db_path = tmp_path / "bio.db"
    os.environ["MEMORY_DB"] = str(db_path)
    reload(db_module)
    db_module.init_db()
    import core.bio_manager as bio_manager
    reload(bio_manager)
    return bio_manager


def test_update_and_get(tmp_path):
    bm = _load(tmp_path)
    bm.update_bio_fields(
        "u1",
        {
            "known_as": ["Alice"],
            "likes": ["pizza"],
            "contacts": {"telegram": ["@alice"]},
            "information": "hello",
        },
    )
    light = bm.get_bio_light("u1")
    assert light["likes"] == ["pizza"]
    full = bm.get_bio_full("u1")
    assert full["contacts"]["telegram"] == ["@alice"]

    bm.update_bio_fields(
        "u1",
        {
            "known_as": ["Al"],
            "likes": ["tea"],
            "contacts": {"discord": ["al#1"]},
        },
    )
    full = bm.get_bio_full("u1")
    assert set(full["known_as"]) == {"Alice", "Al"}
    assert full["likes"] == ["pizza", "tea"]
    assert full["contacts"]["discord"] == ["al#1"]
    os.environ.pop("MEMORY_DB")


def test_append_and_feelings(tmp_path):
    bm = _load(tmp_path)
    bm.append_to_bio_list("u2", "likes", "apples")
    bm.append_to_bio_list("u2", "likes", "apples")
    bm.append_to_bio_list("u2", "contacts.telegram", "@u2")
    bm.add_past_event("u2", "Wake", datetime(2023, 1, 1, 8, 0))
    bm.alter_feeling("u2", "LOVE", 5)
    bm.alter_feeling("u2", "love", 8)

    full = bm.get_bio_full("u2")
    assert full["likes"] == ["apples"]
    assert full["contacts"]["telegram"] == ["@u2"]
    assert full["past_events"][0]["summary"] == "Wake"
    assert full["feelings"] == [{"type": "love", "intensity": 8}]
    os.environ.pop("MEMORY_DB")


def test_light_missing(tmp_path):
    bm = _load(tmp_path)
    assert bm.get_bio_light("missing") == {}
    os.environ.pop("MEMORY_DB")
