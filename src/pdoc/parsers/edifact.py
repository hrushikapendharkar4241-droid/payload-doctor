"""Minimal UN/EDIFACT tokenizer with UNA service-string and release-character support."""
from __future__ import annotations

from dataclasses import dataclass


class EdifactParseError(Exception):
    pass


@dataclass
class Segment:
    tag: str
    elements: list[list[str]]  # elements[0] == [tag]; each element is a list of components
    index: int

    def el(self, n: int, comp: int = 0, default: str = "") -> str:
        if n < len(self.elements) and comp < len(self.elements[n]):
            return self.elements[n][comp]
        return default

    def __str__(self) -> str:
        return "+".join(":".join(c) for c in self.elements)


@dataclass
class Interchange:
    segments: list[Segment]
    has_una: bool

    def find(self, tag: str) -> list[Segment]:
        return [s for s in self.segments if s.tag == tag]


def parse(text: str) -> Interchange:
    text = text.lstrip("﻿").lstrip()
    comp, elem, release, term = ":", "+", "?", "'"
    has_una = text.startswith("UNA")
    if has_una:
        if len(text) < 9:
            raise EdifactParseError("UNA service string is shorter than 9 characters")
        comp, elem, release, term = text[3], text[4], text[6], text[8]
        text = text[9:]
    if not text.lstrip().startswith("UNB"):
        raise EdifactParseError("interchange does not start with UNB (after the optional UNA)")

    segments: list[Segment] = []
    elements: list[list[str]] = []
    components: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == release and i + 1 < len(text):
            buf.append(text[i + 1])
            i += 2
            continue
        if ch == comp:
            components.append("".join(buf)); buf = []
        elif ch == elem:
            components.append("".join(buf)); buf = []
            elements.append(components); components = []
        elif ch == term:
            components.append("".join(buf)); buf = []
            elements.append(components); components = []
            tag = elements[0][0].strip()
            if tag:
                elements[0] = [tag]
                segments.append(Segment(tag, elements, len(segments) + 1))
            elements = []
        elif ch in "\r\n" and not buf and not components and not elements:
            pass  # line breaks between segments
        else:
            buf.append(ch)
        i += 1
    if "".join(buf).strip() or elements:
        raise EdifactParseError("last segment is not terminated; the file may be truncated")
    return Interchange(segments, has_una)


MESSAGE_NAMES = {
    "ORDERS": "Purchase Order",
    "DESADV": "Despatch Advice",
    "INVOIC": "Invoice",
    "CONTRL": "Syntax and Service Report",
    "ORDRSP": "Purchase Order Response",
}
