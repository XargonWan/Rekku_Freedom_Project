import sys
import os
from types import SimpleNamespace
from datetime import datetime, timezone
import asyncio
import types

class DummyPytz:
    @staticmethod
    def timezone(name):
        return timezone.utc

sys.modules.setdefault('pytz', DummyPytz())

# Ensure the project root is on sys.path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.prompt_engine import build_json_prompt


def make_user(name="Alice", username="alice"):
    return SimpleNamespace(full_name=name, username=username)


def make_message(text="", **kwargs):
    now = datetime.now(timezone.utc)
    msg = SimpleNamespace(
        chat_id=123,
        text=text,
        caption=None,
        from_user=make_user(),
        date=now,
        reply_to_message=None,
        photo=None,
        voice=None,
        audio=None,
        video=None,
        document=None,
        sticker=None,
        animation=None,
    )
    for k, v in kwargs.items():
        setattr(msg, k, v)
    return msg


def test_reply_photo_label():
    reply = make_message(text=None, photo=[SimpleNamespace()])
    message = make_message("hi", reply_to_message=reply)
    prompt = asyncio.run(build_json_prompt(message, {}))
    assert prompt["message"]["reply_to"]["text"] == "\U0001F4F7 [Image]"


def test_reply_voice_label():
    reply = make_message(text=None, voice=SimpleNamespace())
    message = make_message("hi", reply_to_message=reply)
    prompt = asyncio.run(build_json_prompt(message, {}))
    assert prompt["message"]["reply_to"]["text"] == "\U0001F3B5 [Voice]"


def test_reply_audio_label():
    reply = make_message(text=None, audio=SimpleNamespace())
    message = make_message("hi", reply_to_message=reply)
    prompt = asyncio.run(build_json_prompt(message, {}))
    assert prompt["message"]["reply_to"]["text"] == "\U0001F3A7 [Audio]"


def test_reply_video_label():
    reply = make_message(text=None, video=SimpleNamespace())
    message = make_message("hi", reply_to_message=reply)
    prompt = asyncio.run(build_json_prompt(message, {}))
    assert prompt["message"]["reply_to"]["text"] == "\U0001F39E\ufe0f [Video]"


def test_reply_audio_document_label():
    doc = SimpleNamespace(mime_type="audio/mpeg", file_name="sound.mp3")
    reply = make_message(text=None, document=doc)
    message = make_message("hi", reply_to_message=reply)
    prompt = asyncio.run(build_json_prompt(message, {}))
    assert prompt["message"]["reply_to"]["text"] == "\U0001F3A7 [Audio (Document)]"


def test_reply_document_label():
    doc = SimpleNamespace(mime_type="application/pdf", file_name="file.pdf")
    reply = make_message(text=None, document=doc)
    message = make_message("hi", reply_to_message=reply)
    prompt = asyncio.run(build_json_prompt(message, {}))
    assert prompt["message"]["reply_to"]["text"] == "\U0001F5C2\ufe0f [Document]"


def test_reply_sticker_label_with_emoji():
    sticker = SimpleNamespace(is_animated=False, is_video=False, emoji="😀")
    reply = make_message(text=None, sticker=sticker)
    message = make_message("hi", reply_to_message=reply)
    prompt = asyncio.run(build_json_prompt(message, {}))
    assert prompt["message"]["reply_to"]["text"] == "\U0001F5BC\ufe0f [Sticker: 😀]"


def test_reply_sticker_gif_label():
    sticker = SimpleNamespace(is_animated=True, is_video=False, emoji="😎")
    reply = make_message(text=None, sticker=sticker)
    message = make_message("hi", reply_to_message=reply)
    prompt = asyncio.run(build_json_prompt(message, {}))
    assert prompt["message"]["reply_to"]["text"] == "\U0001F3AC [GIF Sticker: 😎]"


def test_reply_sticker_video_label():
    sticker = SimpleNamespace(is_animated=False, is_video=True, emoji="😅")
    reply = make_message(text=None, sticker=sticker)
    message = make_message("hi", reply_to_message=reply)
    prompt = asyncio.run(build_json_prompt(message, {}))
    assert prompt["message"]["reply_to"]["text"] == "\U0001F3AC [Video Sticker: 😅]"


def test_reply_unknown_fallback():
    reply = make_message(text=None)
    message = make_message("hi", reply_to_message=reply)
    prompt = asyncio.run(build_json_prompt(message, {}))
    assert prompt["message"]["reply_to"]["text"] == "[Contenuto non testuale]"

