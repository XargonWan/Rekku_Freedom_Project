import os
import sys

# Ensure the project root is on sys.path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.mention_utils import is_rekku_mentioned


def test_is_rekku_mentioned():
    assert is_rekku_mentioned("Hey Rekku!") is True
    assert is_rekku_mentioned("これはれっくたんへのメッセージです") is True
    assert is_rekku_mentioned("Привет, рекку!") is True
    assert is_rekku_mentioned("Ammiro la tanukina oggi") is True
    assert is_rekku_mentioned("@The_Official_Rekku sei viva?") is True
    assert is_rekku_mentioned("Buongiorno a tutti!") is False
