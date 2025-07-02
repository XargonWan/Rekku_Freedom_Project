import html
import re


def make_clickable_links(msg: str) -> tuple[str, bool]:
    """Convert URLs in *msg* to HTML anchors.

    Returns the transformed string and whether any URL was found.
    """
    pattern = re.compile(r"https?://\S+")
    matches = list(pattern.finditer(msg or ""))
    if not matches:
        return msg, False
    parts = []
    last = 0
    for m in matches:
        parts.append(html.escape(msg[last:m.start()]))
        url = m.group(0)
        parts.append(f'<a href="{html.escape(url)}">{html.escape(url)}</a>')
        last = m.end()
    parts.append(html.escape(msg[last:]))
    return "".join(parts), True
