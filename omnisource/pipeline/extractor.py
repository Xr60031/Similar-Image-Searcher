# path: omnisource/pipeline/extractor.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List
from urllib.parse import urljoin

from selectolax.parser import HTMLParser


@dataclass
class ExtractedLink:
    url: str
    text: str
    has_image: bool
    score: float


@dataclass
class ExtractedImage:
    url: str
    alt: str


class ContentExtractor:
    MAX_NODES = 500

    def _is_visible(self, node) -> bool:
        style = node.attributes.get("style", "")
        if any(x in style for x in ["display:none", "visibility:hidden", "opacity:0"]):
            return False

        if node.attributes.get("width") == "0" or node.attributes.get("height") == "0":
            return False

        return True

    def extract_links(self, html: str, base_url: str) -> List[ExtractedLink]:
        tree = HTMLParser(html)
        results: List[ExtractedLink] = []

        count = 0

        for node in tree.css("a"):
            if count >= self.MAX_NODES:
                break
            count += 1

            if not self._is_visible(node):
                continue

            href = node.attributes.get("href")
            if not href:
                continue

            text = node.text(strip=True)
            has_img = bool(node.css("img"))

            if not text and not has_img:
                continue

            score = 1.0
            if has_img:
                score += 1.5

            full_url = urljoin(base_url, href)

            results.append(
                ExtractedLink(
                    url=full_url,
                    text=text,
                    has_image=has_img,
                    score=score,
                )
            )

        return results

    def extract_images(self, html: str, base_url: str) -> List[ExtractedImage]:
        tree = HTMLParser(html)
        results: List[ExtractedImage] = []

        count = 0

        for node in tree.css("img"):
            if count >= self.MAX_NODES:
                break
            count += 1

            if not self._is_visible(node):
                continue

            src = node.attributes.get("src")
            if not src:
                continue

            alt = node.attributes.get("alt", "")

            full_url = urljoin(base_url, src)

            results.append(ExtractedImage(url=full_url, alt=alt))

        return results