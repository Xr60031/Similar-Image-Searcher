from __future__ import annotations

import httpx
from PIL import Image
import imagehash
from io import BytesIO


async def compute_image_hash(image_url: str):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(image_url)

    img = Image.open(BytesIO(r.content))

    img = img.convert("RGB").resize((256, 256))

    phash = imagehash.phash(img)
    dhash = imagehash.dhash(img)

    return {
        "phash": phash,
        "dhash": dhash,
    }