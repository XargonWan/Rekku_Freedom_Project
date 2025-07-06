# core/rekku_tagging.py

from core.db import get_db

def extract_tags(text: str) -> list[str]:
    text = text.lower()
    tags = []
    if "jay" in text:
        tags.append("jay")
    if "retrodeck" in text:
        tags.append("retrodeck")
    if "amore" in text or "affetto" in text:
        tags.append("emozioni")
    return tags

def expand_tags(tags: list[str]) -> list[str]:
    """
    Estende i tag forniti basandosi sulle relazioni definite nella tabella `tag_links`.
    Le relazioni sono considerate simmetriche (tag → related_tag e viceversa).
    """
    expanded = set(tags)

    if not tags:
        return list(expanded)

    placeholders = ",".join("?" for _ in tags)
    query = f"""
        SELECT related_tag FROM tag_links WHERE tag IN ({placeholders})
        UNION
        SELECT tag FROM tag_links WHERE related_tag IN ({placeholders})
    """

    with get_db() as db:
        rows = db.execute(query, tags * 2).fetchall()
        for row in rows:
            expanded.add(row[0])

    return list(expanded)
