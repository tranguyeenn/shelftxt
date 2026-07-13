from __future__ import annotations

import json
from html.parser import HTMLParser
from typing import Any


class JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capture = False
        self._buffer: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attr_map = {name.lower(): value for name, value in attrs}
        if (attr_map.get("type") or "").lower() == "application/ld+json":
            self._capture = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture and tag.lower() == "script":
            self.blocks.append("".join(self._buffer).strip())
            self._capture = False
            self._buffer = []


def extract_jsonld_documents(html: str) -> tuple[list[Any], bool]:
    parser = JsonLdParser()
    parser.feed(html)
    documents: list[Any] = []
    malformed = False
    for block in parser.blocks:
        if not block:
            continue
        try:
            documents.append(json.loads(block))
        except json.JSONDecodeError:
            malformed = True
    return documents, malformed


def iter_jsonld_nodes(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from iter_jsonld_nodes(item)
    elif isinstance(value, dict):
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from iter_jsonld_nodes(item)
        yield value
