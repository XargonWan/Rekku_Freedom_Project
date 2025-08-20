import ast
from pathlib import Path


def test_send_message_uses_markdown_parse_mode():
    tree = ast.parse(Path("interface/telegram_bot.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "send_message":
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and getattr(getattr(call, "func", None), "id", "") == "send_with_thread_fallback":
                    for kw in call.keywords:
                        if kw.arg == "parse_mode" and isinstance(kw.value, ast.Constant):
                            assert kw.value.value == "Markdown"
                            return
    assert False, "parse_mode='Markdown' not found in send_with_thread_fallback call"
