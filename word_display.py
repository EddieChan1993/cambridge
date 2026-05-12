"""
Reusable word-display widget built from NSScrollView + NSTextView.
Renders structured dictionary data as an NSAttributedString.
"""

import objc
from Foundation import NSMutableAttributedString, NSAttributedString
from AppKit import (
    NSScrollView,
    NSTextView,
    NSColor,
    NSFont,
    NSFontManager,
    NSMutableParagraphStyle,
    NSParagraphStyleAttributeName,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSBackgroundColorAttributeName,
    NSKernAttributeName,
)


# ── Paragraph style helpers ───────────────────────────────────────────────────

def _para(line=2, before=0, after=0, head=0.0, first=None):
    ps = NSMutableParagraphStyle.alloc().init()
    ps.setLineSpacing_(line)
    ps.setParagraphSpacingBefore_(before)
    ps.setParagraphSpacing_(after)
    ps.setHeadIndent_(head)
    ps.setFirstLineHeadIndent_(first if first is not None else head)
    return ps


def _attrs(font, color, para=None, bg=None, kern=None):
    d = {NSFontAttributeName: font, NSForegroundColorAttributeName: color}
    if para: d[NSParagraphStyleAttributeName] = para
    if bg   is not None: d[NSBackgroundColorAttributeName] = bg
    if kern is not None: d[NSKernAttributeName] = kern
    return d


def _append(mas, text, attrs):
    mas.appendAttributedString_(
        NSAttributedString.alloc().initWithString_attributes_(text, attrs))


# ── Public builder ────────────────────────────────────────────────────────────

def build_attributed_string(data: dict) -> NSMutableAttributedString:
    mas = NSMutableAttributedString.alloc().init()

    word           = data.get("word", "")
    error          = data.get("error", "")
    pronunciations = data.get("pronunciations", [])
    entries        = data.get("entries", [])

    # ── Fonts ────────────────────────────────────────────────────────────────
    f_word     = NSFont.boldSystemFontOfSize_(28)
    f_pron     = NSFont.fontWithName_size_("Menlo", 13) \
                 or NSFont.monospacedSystemFontOfSize_weight_(13, 0.0)
    f_pron_lbl = NSFont.boldSystemFontOfSize_(10)
    f_pos      = NSFont.boldSystemFontOfSize_(11)
    f_num      = NSFont.boldSystemFontOfSize_(14)
    f_en       = NSFont.boldSystemFontOfSize_(14)     # definition — bold, prominent
    f_note     = NSFont.systemFontOfSize_(11)         # gram/label/usage inline note
    f_zh       = NSFont.systemFontOfSize_(13)         # Chinese definition
    f_ex_en    = NSFont.systemFontOfSize_(13)         # example English — regular weight
    f_ex_zh    = NSFont.systemFontOfSize_(12)         # example Chinese — smaller
    f_err      = NSFont.systemFontOfSize_(14)

    # ── Colors ───────────────────────────────────────────────────────────────
    c_word     = NSColor.labelColor()
    c_pron     = NSColor.secondaryLabelColor()
    c_pron_lbl = NSColor.tertiaryLabelColor()
    c_pos_fg   = NSColor.whiteColor()
    c_pos_bg   = NSColor.systemBlueColor()
    c_num      = NSColor.systemBlueColor()
    c_en       = NSColor.labelColor()             # bold black/dark — definition
    c_note     = NSColor.secondaryLabelColor()    # inline gram/label note
    c_zh       = NSColor.secondaryLabelColor()    # Chinese definition
    c_ex_en    = NSColor.secondaryLabelColor()    # example sentence
    c_ex_zh    = NSColor.tertiaryLabelColor()     # example Chinese
    c_bullet   = NSColor.systemBlueColor()        # example bullet (distinct color)
    c_err      = NSColor.systemRedColor()

    INDENT = 22.0

    # ── Word heading ─────────────────────────────────────────────────────────
    _append(mas, word + "\n",
            _attrs(f_word, c_word, _para(line=4, after=6)))

    if error and not entries:
        _append(mas, error + "\n", _attrs(f_err, c_err, _para(before=4)))
        return mas

    # ── Pronunciations ───────────────────────────────────────────────────────
    if pronunciations:
        for p in pronunciations:
            lbl = p.get("label", "").strip()
            ipa = p.get("ipa", "").strip()
            if not ipa:
                continue
            if lbl:
                _append(mas, lbl + " ",
                        _attrs(f_pron_lbl, c_pron_lbl, _para(line=3)))
            _append(mas, f"/{ipa}/  ",
                    _attrs(f_pron, c_pron, _para(line=3)))
        _append(mas, "\n", _attrs(f_pron, c_pron, _para(after=14)))

    # ── Entries ──────────────────────────────────────────────────────────────
    for i, entry in enumerate(entries):
        pos      = entry.get("pos", "")
        pos_gram = entry.get("pos_gram", "")
        defs     = entry.get("definitions", [])

        # POS badge + optional pos-level grammar
        if pos:
            _append(mas, "\n", _attrs(f_pos, c_pos_fg,
                                      _para(before=2, after=4)))
            _append(mas, f" {pos.upper()} ",
                    _attrs(f_pos, c_pos_fg,
                           _para(before=0, after=0),
                           bg=c_pos_bg, kern=0.5))
            if pos_gram:
                _append(mas, f"  {pos_gram}",
                        _attrs(f_note, c_note, _para(before=0, after=0)))
            _append(mas, "\n", _attrs(f_pos, c_pos_fg, _para(after=8)))

        for j, defn in enumerate(defs):
            en    = defn.get("en", "")
            zh    = defn.get("zh", "")
            gram  = defn.get("gram", "")
            label = defn.get("label", "")
            usage = defn.get("usage", "")
            exs   = defn.get("examples", [])

            def_para = _para(
                line=3,
                before=6 if j > 0 else 0,
                after=2,
                head=INDENT,
                first=0,
            )
            # Number
            _append(mas, f"{j+1}. ", _attrs(f_num, c_num, def_para))
            # English definition (bold)
            if en:
                _append(mas, en, _attrs(f_en, c_en, def_para))
            # Inline grammar / label note
            note_parts = [p for p in [gram, label] if p]
            if note_parts:
                _append(mas, "  " + "  ".join(note_parts),
                        _attrs(f_note, c_note, def_para))
            _append(mas, "\n", _attrs(f_en, c_en, def_para))

            # Usage note on its own line (e.g. "not usually before noun")
            if usage:
                usage_para = _para(line=2, after=2,
                                   head=INDENT, first=INDENT)
                _append(mas, f"▸ {usage}\n",
                        _attrs(f_note, c_note, usage_para))

            # Chinese definition
            if zh:
                zh_para = _para(line=2, after=3, head=INDENT, first=INDENT)
                _append(mas, zh + "\n", _attrs(f_zh, c_zh, zh_para))

            # Examples
            for ex in exs:
                ex_en = ex.get("en", "") if isinstance(ex, dict) else ex
                ex_zh = ex.get("zh", "") if isinstance(ex, dict) else ""

                ex_para = _para(line=2, after=1,
                                head=INDENT + 14, first=INDENT + 2)
                _append(mas, "• ", _attrs(f_ex_en, c_bullet, ex_para))
                _append(mas, ex_en + "\n", _attrs(f_ex_en, c_ex_en, ex_para))
                if ex_zh:
                    ez_para = _para(line=2, after=3,
                                    head=INDENT + 16, first=INDENT + 16)
                    _append(mas, ex_zh + "\n",
                            _attrs(f_ex_zh, c_ex_zh, ez_para))

        if i < len(entries) - 1:
            _append(mas, "\n",
                    _attrs(f_en, NSColor.separatorColor(),
                           _para(before=4, after=4)))

    return mas


# ── Widget factory ────────────────────────────────────────────────────────────

def make_word_scroll_view(frame) -> tuple:
    """Returns (scroll_view, text_view)."""
    scroll = NSScrollView.alloc().initWithFrame_(frame)
    scroll.setHasVerticalScroller_(True)
    scroll.setHasHorizontalScroller_(False)
    scroll.setAutohidesScrollers_(True)
    scroll.setBorderType_(0)

    tv = NSTextView.alloc().initWithFrame_(frame)
    tv.setEditable_(False)
    tv.setSelectable_(True)
    tv.setDrawsBackground_(False)
    tv.setTextContainerInset_((16, 20))
    tv.textContainer().setWidthTracksTextView_(True)
    tv.textContainer().setHeightTracksTextView_(False)
    tv.setAutoresizingMask_(2)
    tv.setVerticallyResizable_(True)

    scroll.setDocumentView_(tv)
    scroll.setAutoresizingMask_(2 | 16)
    return scroll, tv


def update_word_view(tv, data: dict | None):
    """Render *data* into *tv*. Pass None for placeholder."""
    if data is None:
        ph = NSAttributedString.alloc().initWithString_attributes_(
            "输入单词，或划词后按全局快捷键查询",
            {
                NSFontAttributeName: NSFont.systemFontOfSize_(15),
                NSForegroundColorAttributeName: NSColor.tertiaryLabelColor(),
                NSParagraphStyleAttributeName: _para(),
            },
        )
        tv.textStorage().setAttributedString_(ph)
        return

    mas = build_attributed_string(data)
    tv.textStorage().setAttributedString_(mas)
    tv.scrollRangeToVisible_((0, 0))
