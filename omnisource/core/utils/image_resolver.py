from __future__ import annotations

import httpx
from selectolax.parser import HTMLParser


async def resolve_image_url(input_value: str) -> str:
    """
    Si recibe una URL de página (ej: DeviantArt),
    intenta extraer la imagen real (og:image).
    """

    if not input_value.startswith("http"):
        return input_value

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(input_value, headers=headers)

        if "text/html" not in r.headers.get("content-type", ""):
            return input_value

        tree = HTMLParser(r.text)

        meta = tree.css_first('meta[property="og:image"]')
        if meta:
            return meta.attributes.get("content")

        return input_value

    except Exception:
        return input_value