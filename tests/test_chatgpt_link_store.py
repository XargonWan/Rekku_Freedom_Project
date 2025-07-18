import os
import sys
from importlib import reload
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import core.db as db_module


def test_chatlink_store(tmp_path):
    db_path = tmp_path / "links.db"
    os.environ["MEMORY_DB"] = str(db_path)
    reload(db_module)

    from core.chatgpt_link_store import ChatLinkStore  # import after DB reload

    store = ChatLinkStore()

    assert store.get_link(1, None) is None

    store.save_link(1, None, "chat123")
    assert store.get_link(1, None) == "chat123"
    assert not store.is_full("chat123")

    store.mark_full("chat123")
    assert store.is_full("chat123")
    assert store.get_link(1, None) is None

    store.save_link(2, None, "chat456")
    assert store.get_link(2, None) == "chat456"
    store.remove_chat_link(2, None)
    assert store.get_link(2, None) is None

    os.environ.pop("MEMORY_DB")
