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
    NSLinkAttributeName,
    NSCursor,
    NSTrackingArea,
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
    fm         = NSFontManager.sharedFontManager()
    f_ex_en    = fm.convertFont_toHaveTrait_(
                     NSFont.systemFontOfSize_(13), 1)  # italic, NSItalicFontMask=1
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
        return mas   # 错误状态由 MainWindowController 的 overlay 处理

    # ── Pronunciations ───────────────────────────────────────────────────────
    if pronunciations:
        for p in pronunciations:
            lbl       = p.get("label", "").strip()
            ipa       = p.get("ipa", "").strip()
            audio_url = p.get("audio", "").strip()
            if not ipa:
                continue
            para = _para(line=3)
            if audio_url:
                spk_attrs = {
                    NSFontAttributeName: NSFont.systemFontOfSize_(12),
                    NSForegroundColorAttributeName: c_pron_lbl,
                    NSParagraphStyleAttributeName: para,
                    NSLinkAttributeName: audio_url,
                }
                _append(mas, "🔊 ", spk_attrs)
            if lbl:
                lbl_a = _attrs(f_pron_lbl, c_pron_lbl, para)
                if audio_url:
                    lbl_a = dict(lbl_a)
                    lbl_a[NSLinkAttributeName] = audio_url
                _append(mas, lbl + " ", lbl_a)
            ipa_a = _attrs(f_pron, c_pron, para)
            if audio_url:
                ipa_a = dict(ipa_a)
                ipa_a[NSLinkAttributeName] = audio_url
            _append(mas, f"/{ipa}/  ", ipa_a)
        _append(mas, "\n", _attrs(f_pron, c_pron, _para(after=14)))

    # ── Entries ──────────────────────────────────────────────────────────────
    for i, entry in enumerate(entries):
        pos      = entry.get("pos", "")
        pos_gram = entry.get("pos_gram", "")
        source   = entry.get("source", "")
        defs     = entry.get("definitions", [])

        # Yellow divider — repeated ─ characters, clipped at line end
        _sep_ps = NSMutableParagraphStyle.alloc().init()
        _sep_ps.setParagraphSpacingBefore_(14.0 if i == 0 else 20.0)
        _sep_ps.setParagraphSpacing_(12.0)
        _sep_ps.setLineBreakMode_(2)   # NSLineBreakByClipping
        _sep_ps.setTailIndent_(-50.0)  # 右侧留边距（含滚动条宽度）
        _append(mas, "─" * 44 + "\n",
                {
                    NSFontAttributeName: NSFont.boldSystemFontOfSize_(15),
                    NSForegroundColorAttributeName: NSColor.systemYellowColor(),
                    NSParagraphStyleAttributeName: _sep_ps,
                })

        # Source bar: "word | Source Name" on full-width yellow background
        if source:
            _src_ps = NSMutableParagraphStyle.alloc().init()
            _src_ps.setParagraphSpacingBefore_(0)
            _src_ps.setParagraphSpacing_(10.0)
            _src_ps.setLineBreakMode_(2)   # NSLineBreakByClipping
            _src_ps.setTailIndent_(-50.0)
            _src_bg = NSColor.systemYellowColor()
            _src_fg = NSColor.colorWithWhite_alpha_(0.12, 1.0)  # near-black on yellow
            # Bold word portion
            _append(mas, f" {word} ",
                    {NSFontAttributeName: NSFont.boldSystemFontOfSize_(13),
                     NSForegroundColorAttributeName: _src_fg,
                     NSBackgroundColorAttributeName: _src_bg,
                     NSParagraphStyleAttributeName: _src_ps})
            # Separator + source name + trailing spaces to fill width
            _append(mas, f"| {source}" + " " * 120 + "\n",
                    {NSFontAttributeName: NSFont.systemFontOfSize_(13),
                     NSForegroundColorAttributeName: _src_fg,
                     NSBackgroundColorAttributeName: _src_bg,
                     NSParagraphStyleAttributeName: _src_ps})

        # POS badge(s) + optional pos-level grammar
        if pos:
            badge_para = _para(before=0, after=0)
            for part in [p.strip() for p in pos.split(",") if p.strip()]:
                _append(mas, f"{part.upper()} ",
                        _attrs(f_pos, c_pos_fg, badge_para, bg=c_pos_bg, kern=0.5))
                _append(mas, " ", _attrs(f_note, c_note, badge_para))
            if pos_gram:
                _append(mas, f" {pos_gram}",
                        _attrs(f_note, c_note, badge_para))
            _append(mas, "\n", _attrs(f_pos, c_pos_fg, _para(after=8)))

        single = len(defs) == 1

        for j, defn in enumerate(defs):
            en    = defn.get("en", "")
            zh    = defn.get("zh", "")
            gram  = defn.get("gram", "")
            label = defn.get("label", "")
            usage = defn.get("usage", "")
            exs   = defn.get("examples", [])

            # 只有一个含义时不缩进（无编号）
            h_indent = 0 if single else INDENT
            def_para = _para(
                line=3,
                before=6 if j > 0 else 0,
                after=2,
                head=h_indent,
                first=0,
            )
            # 编号（多含义才显示）
            if not single:
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

            # Usage note — 去重：已在内联 note 里出现的跳过
            note_lower = {p.lower() for p in note_parts}
            if usage and usage.lower() not in note_lower:
                usage_para = _para(line=2, after=2,
                                   head=h_indent, first=h_indent)
                _append(mas, f"▸ {usage}\n",
                        _attrs(f_note, c_note, usage_para))

            # Chinese definition
            if zh:
                zh_para = _para(line=2, after=3, head=h_indent, first=h_indent)
                _append(mas, zh + "\n", _attrs(f_zh, c_zh, zh_para))

            # Examples
            for ex in exs:
                ex_en = ex.get("en", "") if isinstance(ex, dict) else ex
                ex_zh = ex.get("zh", "") if isinstance(ex, dict) else ""

                ex_para = _para(line=2, after=1,
                                head=h_indent + 14, first=h_indent + 2)
                _append(mas, "• ", _attrs(f_ex_en, c_bullet, ex_para))
                _append(mas, ex_en + "\n", _attrs(f_ex_en, c_ex_en, ex_para))
                if ex_zh:
                    ez_para = _para(line=2, after=3,
                                    head=h_indent + 16, first=h_indent + 16)
                    _append(mas, ex_zh + "\n",
                            _attrs(f_ex_zh, c_ex_zh, ez_para))


    return mas


# ── Widget factory ────────────────────────────────────────────────────────────

class _WordTextView(NSTextView):
    """NSTextView without URL tooltips and with pointer cursor over links."""

    def addToolTipRect_owner_userData_(self, rect, owner, data):
        return 0  # block all tooltip rects (suppresses link URL tooltip)

    def updateTrackingAreas(self):
        for area in list(self.trackingAreas()):
            self.removeTrackingArea_(area)
        # NSTrackingMouseMoved=0x02 | NSTrackingActiveAlways=0x80
        opts = 0x02 | 0x80
        area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), opts, self, None)
        self.addTrackingArea_(area)

    def mouseMoved_(self, event):
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        idx = self.characterIndexForInsertionAtPoint_(point)
        ts = self.textStorage()
        if ts and idx < ts.length():
            result = ts.attribute_atIndex_effectiveRange_(
                NSLinkAttributeName, idx, None)
            link_val = result[0] if isinstance(result, (list, tuple)) else result
            if link_val:
                NSCursor.pointingHandCursor().set()
                return
        NSCursor.arrowCursor().set()

    def mouseExited_(self, event):
        NSCursor.arrowCursor().set()


def make_word_scroll_view(frame) -> tuple:
    """Returns (scroll_view, text_view)."""
    scroll = NSScrollView.alloc().initWithFrame_(frame)
    scroll.setHasVerticalScroller_(True)
    scroll.setHasHorizontalScroller_(False)
    scroll.setAutohidesScrollers_(True)
    scroll.setBorderType_(0)

    tv = _WordTextView.alloc().initWithFrame_(frame)
    tv.setEditable_(False)
    tv.setSelectable_(True)
    tv.setDrawsBackground_(False)
    tv.setTextContainerInset_((16, 20))
    tv.setLinkTextAttributes_({
        NSForegroundColorAttributeName: NSColor.secondaryLabelColor(),
    })
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
