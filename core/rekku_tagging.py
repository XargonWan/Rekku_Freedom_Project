# core/rekku_tagging.py

from core.db import get_conn
import aiomysql

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

async def expand_tags(tags: list[str]) -> list[str]:
    """
    Expand the provided tags based on relationships defined in the `tag_links` table.
    Relationships are considered symmetrical (tag → related_tag and vice versa).
    """
    expanded = set(tags)

    if not tags:
        return list(expanded)

    placeholders = ",".join("%s" for _ in tags)
    query = f"""
        SELECT related_tag FROM tag_links WHERE tag IN ({placeholders})
        UNION
        SELECT tag FROM tag_links WHERE related_tag IN ({placeholders})
    """

    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(query, tags * 2)
            rows = await cur.fetchall()
            for row in rows:
                expanded.add(row[0])
    finally:
        conn.close()

    return list(expanded)
