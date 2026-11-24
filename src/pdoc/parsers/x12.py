"""Minimal ANSI X12 tokenizer.

The ISA segment has a fixed width of 106 characters, which is how a receiver learns the
delimiters: character 4 is the element separator, character 105 the component separator
and character 106 the segment terminator.
"""
from __future__ import annotations

from dataclasses import dataclass


class X12ParseError(Exception):
    pass


@dataclass
class Segment:
    tag: str
    elements: list[str]  # elements[0] is the tag itself, so elements[1] == ISA01, BEG01 ...
    index: int  # 1-based position in the interchange

    def get(self, n: int, default: str = "") -> str:
        return self.elements[n] if n < len(self.elements) else default

    def __str__(self) -> str:
        return "*".join(self.elements)


@dataclass
class Interchange:
    element_sep: str
    component_sep: str
    segment_term: str
    segments: list[Segment]
    wrapped: bool  # line breaks found inside segments (file wrapped at a fixed width)

    def find(self, tag: str) -> list[Segment]:
        return [s for s in self.segments if s.tag == tag]


def parse(text: str) -> Interchange:
    text = text.lstrip("﻿")
    wrapped = False
    if "\r" in text[:105] or "\n" in text[:105]:
        # The fixed-width ISA header contains line breaks, so they cannot be the terminator:
        # the file was wrapped. Remove every line break and parse the unwrapped text.
        wrapped = True
        text = text.replace("\r", "").replace("\n", "")
    start = text.find("ISA")
    if start != 0:
        raise X12ParseError("file does not start with an ISA segment")
    if len(text) < 106:
        raise X12ParseError(f"ISA segment is only {len(text)} characters; it must be exactly 106")
    element_sep = text[3]
    component_sep = text[104]
    segment_term = text[105]
    if segment_term.isalnum() or segment_term == element_sep:
        raise X12ParseError(
            f"character 106 of ISA is {segment_term!r}, which cannot be a segment terminator; "
            "the ISA header is probably not padded to its fixed width")

    raw_segments = text.split(segment_term)
    segments: list[Segment] = []
    for raw in raw_segments:
        # Line breaks after the terminator are common and harmless; strip leading ones.
        cleaned = raw.lstrip("\r\n")
        if not cleaned.strip():
            continue
        if segment_term not in "\r\n" and ("\r" in cleaned or "\n" in cleaned):
            wrapped = True
            cleaned = cleaned.replace("\r", "").replace("\n", "")
        elements = cleaned.split(element_sep)
        segments.append(Segment(elements[0].strip(), elements, len(segments) + 1))
    return Interchange(element_sep, component_sep, segment_term, segments, wrapped)


TRANSACTION_NAMES = {
    "850": "Purchase Order",
    "855": "Purchase Order Acknowledgment",
    "856": "Advance Ship Notice",
    "810": "Invoice",
    "997": "Functional Acknowledgment",
}
