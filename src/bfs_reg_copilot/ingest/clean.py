"""Cleaning: turn a stored raw HTML page into headed sections of plain text.

Only the page's main content is kept. Menus, scripts, forms and the "In this section" link lists
are dropped. Headings become a breadcrumb path (`h1 > h2 > h3`) that the chunker later uses as
metadata. Nothing is summarised or reworded: the text is the publisher's, whitespace-normalised.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Final

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString, PageElement
from pydantic import BaseModel, ConfigDict

CLEANER_VERSION: Final = "1"

# Never contains corpus text.
_DROP_TAGS: Final = frozenset(
    {"script", "style", "noscript", "nav", "form", "template", "svg", "button", "iframe", "head"}
)
_HEADINGS: Final = {f"h{n}": n for n in range(1, 7)}
# Link-list headings that every Canada.ca / WET page carries; their lists are navigation only.
_NAV_HEADINGS: Final = frozenset(
    {"in this guidance", "in this section", "in this annex", "related links", "on this page"}
)
_CONTAINERS: Final = frozenset(
    {"div", "section", "article", "main", "ul", "ol", "dl", "table", "thead", "tbody", "tfoot",
     "details", "figure", "fieldset", "span", "body", "html"}
)  # fmt: skip
_WS: Final = re.compile("[ \t\r\f\v\u00a0]+")  # includes the non-breaking space


class Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    level: int
    heading: str
    path: tuple[str, ...]
    anchor: str | None
    text: str


class CleanedPage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    page_title: str
    date_modified: str | None
    sections: tuple[Section, ...]


class CleaningError(Exception):
    """The page does not have the structure we rely on."""


def _norm(text: str) -> str:
    lines = (_WS.sub(" ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def _text_of(tag: Tag) -> str:
    for br in tag.find_all("br"):
        br.replace_with("\n")
    return _norm(tag.get_text())


class _Builder:
    def __init__(self) -> None:
        self.sections: list[Section] = []
        self._stack: list[tuple[int, str]] = []
        self._current: tuple[int, str, str | None] | None = None
        self._blocks: list[str] = []
        self._skipping = False

    def heading(self, level: int, text: str, anchor: str | None) -> None:
        self._flush()
        if text.lower().rstrip(":") in _NAV_HEADINGS:
            self._skipping, self._current = True, None
            return
        self._skipping = False
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()
        self._stack.append((level, text))
        self._current = (level, text, anchor)

    def block(self, text: str) -> None:
        if text and not self._skipping:
            self._blocks.append(text)

    def finish(self) -> tuple[Section, ...]:
        self._flush()
        return tuple(self.sections)

    def _flush(self) -> None:
        if self._current is not None and self._blocks:
            level, heading, anchor = self._current
            path = tuple(name for _, name in self._stack)
            self.sections.append(
                Section(
                    index=len(self.sections),
                    level=level,
                    heading=heading,
                    path=path,
                    anchor=anchor,
                    text="\n".join(self._blocks),
                )
            )
        self._blocks = []


def _children(tag: Tag) -> Iterator[PageElement]:
    yield from tag.children


def _walk(node: PageElement, out: _Builder, depth: int = 0) -> None:
    if isinstance(node, NavigableString):
        # Stray text directly inside a container (rare); keep it.
        out.block(_norm(str(node))) if type(node) is NavigableString else None
        return
    if not isinstance(node, Tag) or node.name in _DROP_TAGS:
        return
    name = node.name
    if name in _HEADINGS:
        anchor = node.get("id")
        out.heading(_HEADINGS[name], _text_of(node), anchor if isinstance(anchor, str) else None)
    elif name == "tr":
        cells = (_text_of(c).replace("\n", " ") for c in node.find_all(["th", "td"]))
        out.block(" | ".join(c for c in cells if c))
    elif name in {"li", "dd"} and node.find(["ul", "ol", "p", "dl", "table"]):
        own = [c for c in _children(node) if not (isinstance(c, Tag) and c.name in _CONTAINERS)]
        prefix = "  " * max(depth - 1, 0) + ("- " if name == "li" else "")
        text = _norm(" ".join(c.get_text() for c in own if not isinstance(c, Tag) or c.name != "p"))
        out.block(prefix + text if text else "")
        for child in _children(node):
            if isinstance(child, Tag) and (child.name in _CONTAINERS or child.name == "p"):
                _walk(child, out, depth)
    elif name in {"li", "dd", "dt", "p", "caption", "summary", "blockquote", "pre", "legend"}:
        text = _text_of(node)
        if name == "li":
            text = "  " * max(depth - 1, 0) + "- " + text
        out.block(text)
    else:
        # Unknown or container tag: descend. (Handles ul/ol/div/table/details, etc.)
        nested = depth + 1 if name in {"ul", "ol"} else depth
        for child in _children(node):
            _walk(child, out, nested)


def _take_date_modified(main: Tag) -> str | None:
    """Pull the page's "Date modified" out as metadata, then remove the page footer block.

    Both OSFI and FINTRAC wrap it, with a "Report a problem" button, in `div.pagedetails`.
    """
    stamp = main.select_one("#wb-dtmd dd")
    date_modified = _norm(stamp.get_text()) if stamp else None
    for footer in main.select(".pagedetails, #wb-dtmd"):
        footer.decompose()
    return date_modified or None


def clean_html(html: str | bytes) -> CleanedPage:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main")
    if not isinstance(main, Tag):
        raise CleaningError("page has no <main> element")
    title = _norm(soup.title.get_text()) if soup.title else ""
    date_modified = _take_date_modified(main)
    out = _Builder()
    for child in _children(main):
        _walk(child, out)
    sections = out.finish()
    if not sections:
        raise CleaningError("no text sections found in <main>")
    return CleanedPage(page_title=title, date_modified=date_modified, sections=sections)
