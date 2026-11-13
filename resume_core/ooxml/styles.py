"""Effective paragraph / run formatting (style chain + document defaults).

Only what the analyser needs to recognise headings, bold labels and body text:
font size, bold, capitals, bottom borders and list membership.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from docx.oxml.ns import qn

from resume_core.ooxml.xmlutil import PPR, RPR, paragraph_text, text_items


def _on(element, tag: str) -> Optional[bool]:
    """Value of a toggle property (``w:b``): None if absent."""
    node = element.find(qn(tag)) if element is not None else None
    if node is None:
        return None
    value = node.get(qn("w:val"))
    return value not in ("0", "false", "off")


def _val(element, tag: str) -> Optional[str]:
    node = element.find(qn(tag)) if element is not None else None
    return None if node is None else node.get(qn("w:val"))


@dataclass(frozen=True)
class RunFormat:
    bold: bool = False
    italic: bool = False
    caps: bool = False
    size_half_pts: int = 0
    color: str = ""
    font: str = ""


# Word's built-in size when no run, style or document default sets one: 10 pt.
IMPLICIT_SIZE_HALF_POINTS = 20


def _theme_fonts(document) -> dict[str, str]:
    """Latin typefaces of the theme: {"major": ..., "minor": ...} (empty when there is no theme)."""
    fonts: dict[str, str] = {}
    try:
        for part in document.part.package.iter_parts():
            if str(part.partname).lower().startswith("/word/theme/"):
                from lxml import etree

                root = etree.fromstring(part.blob)
                ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
                for kind in ("major", "minor"):
                    latin = root.find(f".//a:{kind}Font/a:latin", ns)
                    if latin is not None and latin.get("typeface"):
                        fonts[kind] = latin.get("typeface")
                break
    except Exception:  # noqa: BLE001 - a broken theme must not stop the analysis
        return {}
    return fonts


class StyleSheet:
    def __init__(self, document) -> None:
        self._theme = _theme_fonts(document)
        self._styles: dict[str, object] = {}
        self._doc_defaults_rpr = None
        self._default_paragraph_style = ""
        styles_el = document.styles.element
        for style in styles_el.findall(qn("w:style")):
            style_id = style.get(qn("w:styleId"))
            if style_id:
                self._styles[style_id] = style
            if style.get(qn("w:type")) == "paragraph" and style.get(qn("w:default")) in ("1", "true"):
                self._default_paragraph_style = style_id or ""
        defaults = styles_el.find(qn("w:docDefaults"))
        if defaults is not None:
            rpr_default = defaults.find(qn("w:rPrDefault"))
            if rpr_default is not None:
                self._doc_defaults_rpr = rpr_default.find(RPR)

    # -- style chain ----------------------------------------------------
    def chain(self, style_id: str) -> list[object]:
        out: list[object] = []
        seen: set[str] = set()
        current = style_id or self._default_paragraph_style
        while current and current not in seen and current in self._styles:
            seen.add(current)
            style = self._styles[current]
            out.append(style)
            current = _val(style, "w:basedOn") or ""
        return out  # most specific first

    def style_name(self, style_id: str) -> str:
        style = self._styles.get(style_id)
        return (_val(style, "w:name") or "") if style is not None else ""

    # -- formatting -------------------------------------------------------
    def _resolve(self, rprs: list[object]) -> RunFormat:
        """``rprs`` are rPr elements from most to least specific."""
        def first(getter):
            for rpr in rprs:
                value = getter(rpr)
                if value is not None:
                    return value
            return None

        size = first(lambda r: _val(r, "w:sz"))
        def font_of(rpr):
            fonts = rpr.find(qn("w:rFonts"))
            if fonts is None:
                return None
            name = fonts.get(qn("w:ascii")) or fonts.get(qn("w:hAnsi"))
            if name:
                return name
            theme = fonts.get(qn("w:asciiTheme")) or fonts.get(qn("w:hAnsiTheme")) or ""
            if theme:
                return self._theme.get("major" if theme.startswith("major") else "minor")
            return None

        font = first(font_of)
        return RunFormat(
            bold=bool(first(lambda r: _on(r, "w:b"))),
            italic=bool(first(lambda r: _on(r, "w:i"))),
            caps=bool(first(lambda r: _on(r, "w:caps"))),
            size_half_pts=int(size) if size and size.isdigit() else IMPLICIT_SIZE_HALF_POINTS,
            color=first(lambda r: _val(r, "w:color")) or "",
            font=font or "",
        )

    def paragraph_rprs(self, paragraph) -> list[object]:
        ppr = paragraph.find(PPR)
        style_id = _val(ppr, "w:pStyle") if ppr is not None else None
        rprs = []
        for style in self.chain(style_id or ""):
            rpr = style.find(RPR)
            if rpr is not None:
                rprs.append(rpr)
        if self._doc_defaults_rpr is not None:
            rprs.append(self._doc_defaults_rpr)
        return rprs

    def run_format(self, run, paragraph) -> RunFormat:
        rprs: list[object] = []
        direct = run.find(RPR)
        if direct is not None:
            rprs.append(direct)
            char_style = _val(direct, "w:rStyle")
            if char_style:
                for style in self.chain(char_style):
                    rpr = style.find(RPR)
                    if rpr is not None:
                        rprs.append(rpr)
        rprs.extend(self.paragraph_rprs(paragraph))
        return self._resolve(rprs)

    def paragraph_style_id(self, paragraph) -> str:
        ppr = paragraph.find(PPR)
        return (_val(ppr, "w:pStyle") if ppr is not None else None) or ""

    def dominant_format(self, paragraph) -> RunFormat:
        """Formatting of the characters that make up most of the paragraph's text."""
        weights: dict[RunFormat, int] = {}
        for item in text_items(paragraph):
            if item.kind != "t" or not (item.element.text or "").strip():
                continue
            fmt = self.run_format(item.run, paragraph)
            weights[fmt] = weights.get(fmt, 0) + len(item.element.text)
        if not weights:
            rprs = self.paragraph_rprs(paragraph)
            return self._resolve(rprs)
        return max(weights, key=weights.get)

    def first_run_bold(self, paragraph) -> bool:
        for item in text_items(paragraph):
            if item.kind == "t" and (item.element.text or "").strip():
                return self.run_format(item.run, paragraph).bold
        return False

    def all_bold(self, paragraph) -> bool:
        seen = False
        for item in text_items(paragraph):
            if item.kind == "t" and (item.element.text or "").strip():
                seen = True
                if not self.run_format(item.run, paragraph).bold:
                    return False
        return seen

    # -- paragraph properties -------------------------------------------
    def has_bottom_border(self, paragraph) -> bool:
        ppr = paragraph.find(PPR)
        sources = [ppr] if ppr is not None else []
        sources += [s.find(PPR) for s in self.chain(self.paragraph_style_id(paragraph)) if s.find(PPR) is not None]
        for source in sources:
            borders = source.find(qn("w:pBdr"))
            if borders is not None:
                bottom = borders.find(qn("w:bottom"))
                if bottom is not None and bottom.get(qn("w:val")) not in (None, "", "nil", "none"):
                    return True
        return False

    def has_numbering(self, paragraph) -> bool:
        ppr = paragraph.find(PPR)
        sources = [ppr] if ppr is not None else []
        sources += [s.find(PPR) for s in self.chain(self.paragraph_style_id(paragraph)) if s.find(PPR) is not None]
        for source in sources:
            num = source.find(qn("w:numPr"))
            if num is not None:
                num_id = num.find(qn("w:numId"))
                return not (num_id is not None and num_id.get(qn("w:val")) == "0")
        return False

    def right_tab_stops(self, paragraph) -> list[int]:
        ppr = paragraph.find(PPR)
        stops: list[int] = []
        sources = [ppr] if ppr is not None else []
        sources += [s.find(PPR) for s in self.chain(self.paragraph_style_id(paragraph)) if s.find(PPR) is not None]
        for source in sources:
            tabs = source.find(qn("w:tabs"))
            if tabs is None:
                continue
            for tab in tabs.findall(qn("w:tab")):
                if tab.get(qn("w:val")) in ("right", "end"):
                    try:
                        stops.append(int(tab.get(qn("w:pos"))))
                    except (TypeError, ValueError):
                        pass
        return stops

    def justification(self, paragraph) -> str:
        ppr = paragraph.find(PPR)
        sources = [ppr] if ppr is not None else []
        sources += [s.find(PPR) for s in self.chain(self.paragraph_style_id(paragraph)) if s.find(PPR) is not None]
        for source in sources:
            value = _val(source, "w:jc")
            if value:
                return value
        return ""

    def paragraph_has_text(self, paragraph) -> bool:
        return bool(paragraph_text(paragraph).strip())

