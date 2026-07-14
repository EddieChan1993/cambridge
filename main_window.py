# Copyright © 2026 EddieChan1993. All rights reserved.
# Unauthorized commercial use is strictly prohibited.
"""
Main application window.
Layout:
  NSSplitView (fills full content view):
    Left panel:  [历史][收藏]  /  [清空][导出]  /  word list
    Right panel: [search field] [查询] [★]  /  word display
"""

import objc
from Foundation import NSObject, NSMakeRect, NSMakeSize, NSIndexSet
from AppKit import (
    NSWindow,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSBackingStoreBuffered,
    NSView,
    NSScrollView,
    NSTableView,
    NSTableColumn,
    NSTableRowView,
    NSTextField,
    NSButton,
    NSSegmentedControl,
    NSBezelStyleRounded,
    NSColor,
    NSFont,
    NSScreen,
    NSApplication,
    NSButtonTypeMomentaryLight,
    NSButtonTypeToggle,
    NSMenu,
    NSMenuItem,
    NSTrackingArea,
    NSBezierPath,
    NSSearchField,
    NSTextAlignmentLeft,
    NSTextAlignmentCenter,
    NSTextAlignmentRight,
    NSSpellChecker,
    NSPasteboard,
    NSStringPboardType,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSVisualEffectView,
    NSImageView,
    NSImage,
    NSProgressIndicator,
)

from word_display import make_word_scroll_view, update_word_view

LEFT_W     = 200
RIGHT_HDR  = 66
MIN_WIN_W  = 740
MIN_WIN_H  = 480


# ── Helpers ───────────────────────────────────────────────────────────────────

class _Cell(NSTextField):
    """Read-only word-list cell."""
    def initWithFrame_(self, frame):
        self = objc.super(_Cell, self).initWithFrame_(frame)
        if self is None:
            return None
        self.setBezeled_(False)
        self.setDrawsBackground_(False)
        self.setEditable_(False)
        self.setSelectable_(False)
        self.setFont_(NSFont.systemFontOfSize_(13))
        return self


class _VScrollView(NSScrollView):
    """NSScrollView that blocks horizontal scrolling."""

    def scrollWheel_(self, event):
        if abs(event.scrollingDeltaY()) >= abs(event.scrollingDeltaX()):
            objc.super(_VScrollView, self).scrollWheel_(event)
        else:
            self.nextResponder().scrollWheel_(event)


class _WordTable(NSTableView):
    """NSTableView with right-click delete menu."""

    def menuForEvent_(self, event):
        pt = self.convertPoint_fromView_(event.locationInWindow(), None)
        row = self.rowAtPoint_(pt)
        if row < 0:
            return None
        self.selectRowIndexes_byExtendingSelection_(
            NSIndexSet.indexSetWithIndex_(row), False)
        menu = NSMenu.alloc().init()
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "删除", "deleteSelectedWord:", "")
        item.setTarget_(self.delegate())
        item.setTag_(row)
        menu.addItem_(item)
        return menu

    def keyDown_(self, event):
        # Delete / Backspace key removes selected word
        if event.keyCode() in (51, 117):  # backspace=51, delete=117
            row = self.selectedRow()
            if row >= 0 and self.delegate() and hasattr(self.delegate(), "deleteWordAtRow_"):
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", "", "")
                item.setTag_(row)
                self.delegate().deleteWordAtRow_(item)
                return
        objc.super(_WordTable, self).keyDown_(event)


class _HoverFavButton(NSButton):
    """Borderless ★/☆ button with hover background."""

    def initWithFrame_(self, frame):
        self = objc.super(_HoverFavButton, self).initWithFrame_(frame)
        if self is None:
            return None
        self._hovered = False
        self.setBordered_(False)
        self.setButtonType_(NSButtonTypeMomentaryLight)
        self.setFont_(NSFont.systemFontOfSize_(24))
        self.setTitle_("☆︎")
        self.setContentTintColor_(NSColor.tertiaryLabelColor())
        opts = 0x01 | 0x80  # NSTrackingMouseEnteredAndExited | NSTrackingActiveAlways
        ta = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), opts, self, None)
        self.addTrackingArea_(ta)
        return self

    def mouseEntered_(self, event):
        self._hovered = True
        self.setNeedsDisplay_(True)

    def mouseExited_(self, event):
        self._hovered = False
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        if self._hovered:
            NSColor.colorWithWhite_alpha_(0.5, 0.08).setFill()
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                self.bounds(), 6, 6)
            path.fill()
        from Foundation import NSString
        b = self.bounds()
        ns = NSString.stringWithString_(self.title())
        attrs = {
            NSFontAttributeName: self.font(),
            NSForegroundColorAttributeName: self.contentTintColor() or NSColor.labelColor(),
        }
        sz = ns.sizeWithAttributes_(attrs)
        ns.drawAtPoint_withAttributes_(
            (b.origin.x + (b.size.width  - sz.width)  / 2,
             b.origin.y + (b.size.height - sz.height) / 2),
            attrs
        )


class _EmojiView(NSView):
    """NSView that draws a single emoji/text perfectly centered (H+V)."""

    def initWithFrame_(self, frame):
        self = objc.super(_EmojiView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._text = ""
        self._font_size = 46
        return self

    @objc.python_method
    def set_text(self, text):
        self._text = text
        self.setNeedsDisplay_(True)


    def drawRect_(self, rect):
        if not self._text:
            return
        from Foundation import NSString
        b = self.bounds()
        attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(self._font_size)}
        ns = NSString.stringWithString_(self._text)
        sz = ns.sizeWithAttributes_(attrs)
        ns.drawAtPoint_withAttributes_(
            (b.origin.x + (b.size.width  - sz.width)  / 2,
             b.origin.y + (b.size.height - sz.height) / 2),
            attrs,
        )


class _HoverBtn(NSButton):
    """NSButton with subtle hover background."""
    def initWithFrame_(self, frame):
        self = objc.super(_HoverBtn, self).initWithFrame_(frame)
        if self is None:
            return None
        self.setWantsLayer_(True)
        self.layer().setCornerRadius_(6)
        ta = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), 0x01 | 0x80, self, None)
        self.addTrackingArea_(ta)
        return self

    def mouseEntered_(self, event):
        self.layer().setBackgroundColor_(
            NSColor.colorWithWhite_alpha_(0.5, 0.10).CGColor())

    def mouseExited_(self, event):
        self.layer().setBackgroundColor_(
            NSColor.colorWithWhite_alpha_(0, 0).CGColor())


class _WordRowView(NSView):
    """Cell view: word label + × delete button (visibility driven by _HoverRowView)."""

    def initWithFrame_(self, frame):
        self = objc.super(_WordRowView, self).initWithFrame_(frame)
        if self is None:
            return None
        w = frame.size.width

        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(10, 5, w - 36, 18))
        lbl.setBezeled_(False); lbl.setDrawsBackground_(False)
        lbl.setEditable_(False); lbl.setSelectable_(False)
        lbl.setFont_(NSFont.systemFontOfSize_(13))
        lbl.setAutoresizingMask_(2)
        self.addSubview_(lbl)
        self._lbl = lbl

        del_btn = NSButton.alloc().initWithFrame_(NSMakeRect(w - 26, 4, 20, 20))
        del_btn.setTitle_("×")
        del_btn.setBordered_(False)
        del_btn.setFont_(NSFont.systemFontOfSize_(15))
        del_btn.setContentTintColor_(NSColor.secondaryLabelColor())
        del_btn.setHidden_(True)
        del_btn.setAutoresizingMask_(1 | 4)
        self.addSubview_(del_btn)
        self._del_btn = del_btn
        return self

    @objc.python_method
    def configure(self, word, row, target):
        self._lbl.setStringValue_(word)
        self._del_btn.setTag_(row)
        self._del_btn.setTarget_(target)
        self._del_btn.setAction_("deleteSelectedWord:")


class _HoverRowView(NSTableRowView):
    """NSTableRowView — NSTableView updates mouseHover automatically."""

    def setMouseHover_(self, hovered):
        objc.super(_HoverRowView, self).setMouseHover_(hovered)
        try:
            cell = self.viewAtColumn_(0)
            if cell and hasattr(cell, "_del_btn"):
                cell._del_btn.setHidden_(not hovered)
        except Exception:
            pass


def _btn(title, target, action, frame):
    b = _HoverBtn.alloc().initWithFrame_(frame)
    b.setTitle_(title)
    b.setBezelStyle_(NSBezelStyleRounded)
    b.setButtonType_(NSButtonTypeMomentaryLight)
    b.setFont_(NSFont.systemFontOfSize_(14))
    b.setTarget_(target)
    b.setAction_(action)
    return b


# ── Autocomplete suggestion panel ─────────────────────────────────────────────

class _SuggestOverlay(NSObject):
    """Autocomplete dropdown embedded in the main window's content view.

    Avoids separate-window issues in py2app full builds by living as a plain
    NSView subview of the window's contentView, always on top via re-ordering.
    """

    ROW_H   = 24
    MAX_VIS = 8

    def init(self):
        self = objc.super(_SuggestOverlay, self).init()
        if self is None:
            return None
        self._words    = []
        self._callback = None
        self._bg       = None
        self._tv       = None
        self._sv       = None
        return self

    @objc.python_method
    def attach(self, content_view):
        """Create the overlay NSView and add it (hidden) to content_view."""
        from AppKit import NSTextFieldCell
        bg = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 300, 200))
        bg.setWantsLayer_(True)
        bg.layer().setBackgroundColor_(NSColor.windowBackgroundColor().CGColor())
        bg.layer().setBorderColor_(NSColor.separatorColor().CGColor())
        bg.layer().setBorderWidth_(0.5)
        bg.layer().setCornerRadius_(6.0)
        bg.setHidden_(True)
        content_view.addSubview_(bg)

        sv = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, 300, 200))
        sv.setBorderType_(0)
        sv.setHasVerticalScroller_(False)
        sv.setDrawsBackground_(False)
        bg.addSubview_(sv)

        tv = NSTableView.alloc().initWithFrame_(NSMakeRect(0, 0, 300, 200))
        tv.setHeaderView_(None)
        tv.setRowHeight_(self.ROW_H)
        tv.setGridStyleMask_(0)
        tv.setIntercellSpacing_(NSMakeSize(0, 0))
        tv.setSelectionHighlightStyle_(1)
        tv.setBackgroundColor_(NSColor.windowBackgroundColor())
        tv.setDataSource_(self)
        tv.setDelegate_(self)
        tv.setTarget_(self)
        tv.setAction_("rowClicked:")

        col = NSTableColumn.alloc().initWithIdentifier_("word")
        col.setWidth_(296)
        col.setResizingMask_(1)
        data_cell = NSTextFieldCell.alloc().init()
        data_cell.setFont_(NSFont.systemFontOfSize_(13))
        data_cell.setEditable_(False)
        data_cell.setSelectable_(False)
        col.setDataCell_(data_cell)
        tv.addTableColumn_(col)
        sv.setDocumentView_(tv)

        self._bg = bg
        self._tv = tv
        self._sv = sv

    @objc.python_method
    def update(self, words, search_field, on_click):
        """Reposition below search_field and show. Empty words → hide."""
        if not words or self._bg is None:
            self.hide()
            return
        self._words    = list(words)
        self._callback = on_click

        content_view = self._bg.superview()
        n = min(len(words), self.MAX_VIS)
        w = max(search_field.frame().size.width, 200.0)
        h = float(n * self.ROW_H + 2)

        # Convert search field origin to content view coordinate space
        field_in_cv = search_field.convertRect_toView_(search_field.bounds(), content_view)
        x = field_in_cv.origin.x
        y = field_in_cv.origin.y - h   # macOS y-up: subtract = visually below

        self._bg.setFrame_(NSMakeRect(x, y, w, h))
        inner = NSMakeRect(0, 0, w, h)
        self._sv.setFrame_(inner)
        self._tv.setFrame_(inner)
        self._tv.tableColumns()[0].setWidth_(w - 4)

        self._tv.reloadData()
        self._tv.deselectAll_(None)
        self._bg.setHidden_(False)
        # Re-order to front so it draws above all other subviews
        content_view.addSubview_positioned_relativeTo_(self._bg, 1, None)

    @objc.python_method
    def hide(self):
        if self._bg:
            self._bg.setHidden_(True)
        self._words    = []
        self._callback = None

    @objc.python_method
    def is_visible(self):
        return bool(self._bg and not self._bg.isHidden())

    @objc.python_method
    def move_selection(self, delta):
        n = len(self._words)
        if not n:
            return None
        row = self._tv.selectedRow()
        new = row + delta
        if new < -1:
            new = n - 1
        elif new >= n:
            new = -1
        if new < 0:
            self._tv.deselectAll_(None)
            return None
        idx = NSIndexSet.indexSetWithIndex_(new)
        self._tv.selectRowIndexes_byExtendingSelection_(idx, False)
        self._tv.scrollRowToVisible_(new)
        return self._words[new]

    @objc.python_method
    def selected_word(self):
        row = self._tv.selectedRow()
        if 0 <= row < len(self._words):
            return self._words[row]
        return None

    # NSTableViewDataSource — cell-based
    def numberOfRowsInTableView_(self, tv):
        return len(self._words)

    def tableView_objectValueForTableColumn_row_(self, tv, col, row):
        if row < len(self._words):
            return self._words[row]
        return ""

    @objc.IBAction
    def rowClicked_(self, sender):
        row = sender.selectedRow()
        if 0 <= row < len(self._words) and self._callback:
            word = self._words[row]
            cb   = self._callback
            self.hide()
            cb(word)


# ── Controller ────────────────────────────────────────────────────────────────

class MainWindowController(NSObject):

    def init(self):
        self = objc.super(MainWindowController, self).init()
        if self is None:
            return None
        self._delegate     = None
        self._mode         = "history"
        self._list_data    = []
        self._current_word = ""
        self._current_data = None
        self._reloading    = False
        self._window         = None
        self._right_view     = None
        self._sidebar_view   = None
        self._sep_main       = None
        self._scroll_content = None
        self._overlay        = None
        self._ov_icon_bg     = None
        self._ov_icon        = None
        self._ov_title       = None
        self._ov_hint        = None
        self._ov_spinner     = None
        self._table          = None
        self._tab_pill       = None
        self._tab_hist       = None
        self._tab_fav        = None
        self._tab_seg_w      = 0
        self._stat_label     = None
        self._clear_btn      = None
        self._export_btn     = None
        self._sidebar_search = None
        self._sidebar_filter = ""
        self._search_field   = None
        self._fav_btn      = None
        self._copy_btn     = None
        self._content_tv   = None
        self._suggest      = None
        self._build()
        return self

    # ── Build ─────────────────────────────────────────────────────────────────

    @objc.python_method
    def _build(self):
        screen = NSScreen.mainScreen()
        sf  = screen.visibleFrame() if screen else NSMakeRect(0, 0, 1280, 800)
        cw, ch = MIN_WIN_W, MIN_WIN_H
        x = sf.origin.x + (sf.size.width  - cw) / 2
        y = sf.origin.y + (sf.size.height - ch) / 2

        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
                 | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, cw, ch), style, NSBackingStoreBuffered, False)
        win.setTitle_("HotDict")
        win.setMinSize_(NSMakeSize(MIN_WIN_W, MIN_WIN_H))
        win.setReleasedWhenClosed_(False)
        win.setRestorable_(False)
        win.setDelegate_(self)

        content = win.contentView()

        # ── 侧边栏（右侧固定宽度）─────────────────────────────────────────
        left = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(cw - LEFT_W, 0, LEFT_W, ch))
        left.setMaterial_(7)        # NSVisualEffectMaterialSidebar
        left.setBlendingMode_(1)    # NSVisualEffectBlendingModeWithinWindow
        left.setState_(0)           # NSVisualEffectStateFollowsWindowActiveState
        left.setAutoresizingMask_(1 | 16)

        # ── Pill tab bar（历史 / 收藏）──────────────────────────────────────
        _tab_h   = 32
        _tab_w   = LEFT_W - 16
        _tab_y   = ch - RIGHT_HDR + (RIGHT_HDR - _tab_h) // 2
        _seg_w   = (_tab_w - 4) / 2
        _seg_h   = _tab_h - 4

        tab_container = NSView.alloc().initWithFrame_(
            NSMakeRect(8, _tab_y, _tab_w, _tab_h))
        tab_container.setWantsLayer_(True)
        tab_container.layer().setBackgroundColor_(
            NSColor.colorWithWhite_alpha_(0.5, 0.09).CGColor())
        tab_container.layer().setCornerRadius_(9)
        tab_container.setAutoresizingMask_(2 | 8)
        left.addSubview_(tab_container)

        # 白色胶囊（活跃指示器）
        tab_pill = NSView.alloc().initWithFrame_(NSMakeRect(2, 2, _seg_w, _seg_h))
        tab_pill.setWantsLayer_(True)
        tab_pill.layer().setBackgroundColor_(NSColor.controlBackgroundColor().CGColor())
        tab_pill.layer().setCornerRadius_(7)
        tab_pill.layer().setShadowColor_(NSColor.blackColor().CGColor())
        tab_pill.layer().setShadowOpacity_(0.12)
        tab_pill.layer().setShadowOffset_((0, -1))
        tab_pill.layer().setShadowRadius_(2)
        tab_container.addSubview_(tab_pill)

        def _tab_btn(title, x, action):
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, 2, _seg_w, _seg_h))
            btn.setTitle_(title)
            btn.setBordered_(False)
            btn.setButtonType_(NSButtonTypeMomentaryLight)
            btn.setFocusRingType_(1)   # NSFocusRingTypeNone
            btn.setTarget_(self)
            btn.setAction_(action)
            return btn

        tab_hist = _tab_btn("历史", 2, "tabHistClick:")
        tab_hist.setFont_(NSFont.boldSystemFontOfSize_(13))
        tab_hist.setContentTintColor_(NSColor.labelColor())
        tab_container.addSubview_(tab_hist)

        tab_fav = _tab_btn("收藏", 2 + _seg_w, "tabFavClick:")
        tab_fav.setFont_(NSFont.systemFontOfSize_(13))
        tab_fav.setContentTintColor_(NSColor.secondaryLabelColor())
        tab_container.addSubview_(tab_fav)

        # Thin separator — aligned with right panel divider at ch-RIGHT_HDR-1
        sep_top = NSView.alloc().initWithFrame_(
            NSMakeRect(0, ch - RIGHT_HDR - 1, LEFT_W, 1))
        sep_top.setWantsLayer_(True)
        sep_top.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        sep_top.setAutoresizingMask_(2 | 8)
        left.addSubview_(sep_top)

        # Sidebar search field — sits between top separator and word list
        _SRCH_H    = 28   # field height
        _SRCH_ZONE = 38   # total vertical zone reserved for the field
        srch = NSSearchField.alloc().initWithFrame_(
            NSMakeRect(8, ch - RIGHT_HDR - 1 - _SRCH_ZONE + 5, LEFT_W - 16, _SRCH_H))
        srch.setPlaceholderString_("搜索")
        srch.setAutoresizingMask_(2 | 8)   # width-sizable + pin to top
        srch.setDelegate_(self)
        left.addSubview_(srch)

        # Thin separator below search field
        sep_srch = NSView.alloc().initWithFrame_(
            NSMakeRect(0, ch - RIGHT_HDR - 1 - _SRCH_ZONE, LEFT_W, 1))
        sep_srch.setWantsLayer_(True)
        sep_srch.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        sep_srch.setAutoresizingMask_(2 | 8)
        left.addSubview_(sep_srch)

        # Word list scroll + table — fills between top and bottom areas
        _BTN_H  = 36    # height reserved at bottom for action buttons
        _STAT_H = 20    # stat label band height above button area
        _LBL_H  = 13    # tight label height so text is vertically centred
        stat_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(0, _BTN_H + (_STAT_H - _LBL_H) // 2, LEFT_W, _LBL_H))
        stat_label.setEditable_(False)
        stat_label.setBezeled_(False)
        stat_label.setDrawsBackground_(False)
        stat_label.setAlignment_(NSTextAlignmentCenter)
        stat_label.setFont_(NSFont.systemFontOfSize_(10))
        stat_label.setTextColor_(NSColor.tertiaryLabelColor())
        stat_label.setAutoresizingMask_(2 | 32)
        left.addSubview_(stat_label)

        list_scroll = _VScrollView.alloc().initWithFrame_(
            NSMakeRect(0, _BTN_H + _STAT_H, LEFT_W,
                       ch - RIGHT_HDR - 1 - _SRCH_ZONE - _BTN_H - _STAT_H))
        list_scroll.setHasVerticalScroller_(True)
        list_scroll.setHasHorizontalScroller_(False)
        list_scroll.setAutohidesScrollers_(True)
        list_scroll.setBorderType_(0)
        list_scroll.setAutoresizingMask_(2 | 16)

        table = _WordTable.alloc().initWithFrame_(NSMakeRect(0, 0, LEFT_W, ch - 70))
        col = NSTableColumn.alloc().initWithIdentifier_("word")
        col.setTitle_("")
        col.setWidth_(LEFT_W - 4)
        col.setResizingMask_(1)
        table.addTableColumn_(col)
        table.setHeaderView_(None)
        table.setDataSource_(self)
        table.setDelegate_(self)
        table.setTarget_(self)
        table.setDoubleAction_("rowDoubleClicked:")
        table.setUsesAlternatingRowBackgroundColors_(False)
        table.setRowHeight_(28)
        table.setAutoresizingMask_(2 | 16)
        list_scroll.setDocumentView_(table)
        left.addSubview_(list_scroll)

        # Thin separator above button area — pin to bottom
        sep_bottom = NSView.alloc().initWithFrame_(NSMakeRect(0, _BTN_H - 1, LEFT_W, 1))
        sep_bottom.setWantsLayer_(True)
        sep_bottom.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        sep_bottom.setAutoresizingMask_(2 | 32)   # 32 = MaxYMargin = pin to bottom
        left.addSubview_(sep_bottom)

        # [清空] centered at bottom — pin to bottom
        _BW = 54
        clear_btn = _btn("清空", self, "clearList:",
                         NSMakeRect((LEFT_W - _BW) / 2, 8, _BW, 22))
        clear_btn.setFont_(NSFont.systemFontOfSize_(11))
        clear_btn.setAutoresizingMask_(1 | 4 | 32)   # left+right flex + pin to bottom
        left.addSubview_(clear_btn)

        # [导出] — only visible in favorites mode, starts hidden
        export_btn = _btn("导出", self, "exportFavorites:",
                          NSMakeRect((LEFT_W + _BW + 6) / 2, 8, _BW, 22))
        export_btn.setFont_(NSFont.systemFontOfSize_(11))
        export_btn.setAutoresizingMask_(1 | 4 | 32)
        export_btn.setHidden_(True)
        left.addSubview_(export_btn)

        # ── 内容区（左侧，宽度弹性填满剩余空间）──────────────────────────
        right_w = cw - LEFT_W - 1
        right = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, right_w, ch))
        right.setAutoresizingMask_(2 | 16)  # 宽度弹性 + 高度弹性

        # Header: search field + [查询] + [★]  — pin to top
        hdr_y = ch - RIGHT_HDR
        hdr = NSView.alloc().initWithFrame_(NSMakeRect(0, hdr_y, right_w, RIGHT_HDR))
        hdr.setAutoresizingMask_(2 | 8)

        # 布局（从右到左，间距4px，右边距4px）：
        # [☰ 34px] 4 [★ 34px] 4 [⎘ 34px] 6 [查询 60px] 8 [搜索框] 8 [logo 42px] 10
        _LOGO_SZ   = 36
        _LOGO_X    = 10
        _FLD_LEFT  = _LOGO_X + _LOGO_SZ + 8   # 搜索框左起点 = 54

        _ICON_SZ = 34
        _ICON_F  = NSFont.systemFontOfSize_(22)
        _ICON_Y  = (RIGHT_HDR - _ICON_SZ) // 2
        _x_sidebar = right_w - 4 - _ICON_SZ
        _x_fav     = _x_sidebar - 4 - _ICON_SZ
        _x_copy    = _x_fav - 4 - _ICON_SZ
        _x_query   = _x_copy - 6 - 60
        fld_w      = _x_query - _FLD_LEFT - 8

        # Logo 图片
        from Foundation import NSBundle
        import os as _os
        _icon_path = NSBundle.mainBundle().pathForResource_ofType_("icon", "png")
        if not _icon_path:
            _icon_path = _os.path.join(
                _os.path.dirname(_os.path.abspath(__file__)), "icon.png")
        _logo_img = NSImage.alloc().initWithContentsOfFile_(_icon_path) if _icon_path else None

        logo_iv = NSImageView.alloc().initWithFrame_(
            NSMakeRect(_LOGO_X, 15, _LOGO_SZ, _LOGO_SZ))
        if _logo_img:
            logo_iv.setImage_(_logo_img)
        logo_iv.setImageScaling_(3)   # NSImageScaleProportionallyUpOrDown
        logo_iv.setImageAlignment_(0) # NSImageAlignCenter
        logo_iv.setWantsLayer_(True)
        logo_iv.layer().setCornerRadius_(10)
        logo_iv.layer().setMasksToBounds_(True)
        logo_iv.setAutoresizingMask_(8)   # pin to top
        hdr.addSubview_(logo_iv)

        search_field = NSSearchField.alloc().initWithFrame_(
            NSMakeRect(_FLD_LEFT, 15, fld_w, 36))
        search_field.setPlaceholderString_("输入单词…")
        search_field.setTarget_(self)
        search_field.setAction_("searchEnter:")
        search_field.setFont_(NSFont.systemFontOfSize_(15))
        search_field.cell().setControlSize_(3)
        search_field.setSendsWholeSearchString_(True)
        search_field.setSendsSearchStringImmediately_(False)
        search_field.setDelegate_(self)
        search_field.setAutoresizingMask_(2)
        hdr.addSubview_(search_field)

        query_btn = _btn("查询", self, "searchBtnClick:",
                         NSMakeRect(_x_query, 17, 60, 32))
        query_btn.cell().setControlSize_(3)      # NSControlSizeLarge — 按钮渲染高度跟着变
        query_btn.setAutoresizingMask_(1 | 8)
        hdr.addSubview_(query_btn)

        copy_btn = _HoverFavButton.alloc().initWithFrame_(
            NSMakeRect(_x_copy, _ICON_Y, _ICON_SZ, _ICON_SZ))
        copy_btn.setTitle_("⎘")
        copy_btn.setFont_(NSFont.systemFontOfSize_(28))
        copy_btn.setAlignment_(NSTextAlignmentCenter)
        copy_btn.setContentTintColor_(NSColor.secondaryLabelColor())
        copy_btn.setToolTip_("复制内容")
        copy_btn.setTarget_(self)
        copy_btn.setAction_("copyCurrent:")
        copy_btn.setAutoresizingMask_(1 | 8)
        hdr.addSubview_(copy_btn)

        fav_btn = _HoverFavButton.alloc().initWithFrame_(
            NSMakeRect(_x_fav, _ICON_Y, _ICON_SZ, _ICON_SZ))
        fav_btn.setFont_(_ICON_F)
        fav_btn.setAlignment_(NSTextAlignmentCenter)
        fav_btn.setTarget_(self)
        fav_btn.setAction_("toggleFavorite:")
        fav_btn.setAutoresizingMask_(1 | 8)
        fav_btn.setToolTip_("收藏 / 取消收藏")
        hdr.addSubview_(fav_btn)

        sidebar_btn = _HoverFavButton.alloc().initWithFrame_(
            NSMakeRect(_x_sidebar, _ICON_Y, _ICON_SZ, _ICON_SZ))
        sidebar_btn.setTitle_("☰")
        sidebar_btn.setFont_(_ICON_F)
        sidebar_btn.setAlignment_(NSTextAlignmentCenter)
        sidebar_btn.setContentTintColor_(NSColor.secondaryLabelColor())
        sidebar_btn.setToolTip_("显示/隐藏侧边栏")
        sidebar_btn.setTarget_(self)
        sidebar_btn.setAction_("toggleSidebar:")
        sidebar_btn.setAutoresizingMask_(1 | 8)
        hdr.addSubview_(sidebar_btn)

        right.addSubview_(hdr)

        # Thin divider below header
        div = NSView.alloc().initWithFrame_(NSMakeRect(0, hdr_y - 1, right_w, 1))
        div.setWantsLayer_(True)
        div.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        div.setAutoresizingMask_(2 | 8)
        right.addSubview_(div)

        # Content scroll view fills all space below the divider
        content_h = ch - RIGHT_HDR - 1
        scroll_content, tv = make_word_scroll_view(
            NSMakeRect(0, 0, right_w, content_h))
        scroll_content.setAutoresizingMask_(2 | 16)
        tv.setDelegate_(self)
        right.addSubview_(scroll_content)
        update_word_view(tv, None)

        # 居中浮层：用于"未找到"/"网络错误"/"空白"状态的垂直居中显示
        overlay = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, right_w, content_h))
        overlay.setAutoresizingMask_(2 | 16)
        overlay.setHidden_(True)

        # 布局常量（从上到下）
        _BG   = 90    # 圆形背景直径
        _GAP1 = 16    # 圆圈 → 标题
        _TH   = 26    # 标题高度
        _GAP2 = 8     # 标题 → 副标题
        _HH   = 20    # 副标题高度
        _PAD  = 24    # 上下留白
        inner_h = _PAD + _BG + _GAP1 + _TH + _GAP2 + _HH + _PAD   # = 208

        inner = NSView.alloc().initWithFrame_(
            NSMakeRect(0, (content_h - inner_h) / 2, right_w, inner_h))
        inner.setAutoresizingMask_(2 | 8 | 32)

        def _clbl(text, y, h, size=13, bold=False):
            f = NSTextField.alloc().initWithFrame_(NSMakeRect(0, y, right_w, h))
            f.setStringValue_(text)
            f.setBezeled_(False); f.setDrawsBackground_(False)
            f.setEditable_(False); f.setSelectable_(False)
            f.setAlignment_(NSTextAlignmentCenter)
            f.setAutoresizingMask_(2)
            f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold
                       else NSFont.systemFontOfSize_(size))
            f.setTextColor_(NSColor.secondaryLabelColor())
            return f

        # 各元素 y（从 inner 底部算起）
        _y_hint  = _PAD
        _y_title = _y_hint  + _HH  + _GAP2
        _y_icon  = _y_title + _TH  + _GAP1
        _y_bg    = _y_icon                    # 圆圈与 icon 对齐

        # 圆形背景（x 在 _showOverlay 里动态居中）
        icon_bg = NSView.alloc().initWithFrame_(
            NSMakeRect((right_w - _BG) / 2, _y_bg, _BG, _BG))
        icon_bg.setWantsLayer_(True)
        icon_bg.layer().setCornerRadius_(_BG / 2)
        icon_bg.layer().setBackgroundColor_(
            NSColor.colorWithWhite_alpha_(0.5, 0.07).CGColor())
        icon_bg.setAutoresizingMask_(1 | 4)
        inner.addSubview_(icon_bg)

        ov_icon = _EmojiView.alloc().initWithFrame_(NSMakeRect(0, _y_icon, right_w, _BG))
        ov_icon.setAutoresizingMask_(2)
        ov_title = _clbl("", _y_title, _TH,  size=17, bold=True)
        ov_hint  = _clbl("", _y_hint,  _HH,  size=12)
        ov_hint.setTextColor_(NSColor.tertiaryLabelColor())

        # Spinner（loading 状态用，默认隐藏）
        _SP = 36
        ov_spinner = NSProgressIndicator.alloc().initWithFrame_(
            NSMakeRect(0, _y_icon + (_BG - _SP) / 2, right_w, _SP))
        ov_spinner.setStyle_(1)          # NSProgressIndicatorStyleSpinning
        ov_spinner.setControlSize_(1)    # NSControlSizeRegular
        ov_spinner.setIndeterminate_(True)
        ov_spinner.setDisplayedWhenStopped_(False)
        ov_spinner.setAutoresizingMask_(2)
        inner.addSubview_(ov_spinner)

        inner.addSubview_(ov_icon)
        inner.addSubview_(ov_title)
        inner.addSubview_(ov_hint)
        overlay.addSubview_(inner)
        right.addSubview_(overlay)

        self._scroll_content  = scroll_content
        self._overlay         = overlay
        self._overlay_inner   = inner
        self._overlay_inner_h = inner_h
        self._ov_icon_bg      = icon_bg
        self._ov_icon         = ov_icon
        self._ov_title        = ov_title
        self._ov_hint         = ov_hint
        self._ov_spinner      = ov_spinner

        # ── 竖向分隔线（内容区右边缘，钉在右侧）──────────────────────────
        sep_main = NSView.alloc().initWithFrame_(
            NSMakeRect(cw - LEFT_W - 1, 0, 1, ch))
        sep_main.setWantsLayer_(True)
        sep_main.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        sep_main.setAutoresizingMask_(1 | 16)   # 左边距弹性 + 高度弹性

        # 默认隐藏侧边栏，内容区撑满全宽
        sep_main.setHidden_(True)
        left.setHidden_(True)
        right.setFrame_(NSMakeRect(0, 0, cw, ch))

        # ── 直接拼入 content view ─────────────────────────────────────────
        content.addSubview_(right)
        content.addSubview_(sep_main)
        content.addSubview_(left)

        self._window         = win
        self._right_view     = right
        self._sep_main       = sep_main
        self._sidebar_view   = left
        self._table          = table
        self._tab_pill       = tab_pill
        self._tab_hist       = tab_hist
        self._tab_fav        = tab_fav
        self._tab_seg_w      = _seg_w
        self._stat_label     = stat_label
        self._clear_btn      = clear_btn
        self._export_btn     = export_btn
        self._sidebar_search = srch
        self._search_field = search_field
        self._fav_btn      = fav_btn
        self._copy_btn     = copy_btn
        self._content_tv   = tv

        search_field.setDelegate_(self)
        self._suggest = _SuggestOverlay.alloc().init()
        self._suggest.attach(self._window.contentView())


    # ── NSWindowDelegate ──────────────────────────────────────────────────────

    def windowShouldClose_(self, sender):
        self._window.orderOut_(None)
        return False

    def windowDidResize_(self, notification):
        self._repositionBottomButtons()
        if self._suggest:
            self._suggest.hide()

    def windowDidMove_(self, notification):
        if self._suggest:
            self._suggest.hide()

    def windowDidResignKey_(self, notification):
        if self._suggest:
            self._suggest.hide()

    # ── NSTableViewDataSource ─────────────────────────────────────────────────

    def numberOfRowsInTableView_(self, tv):
        return len(self._list_data)

    def tableView_objectValueForTableColumn_row_(self, tv, col, row):
        if 0 <= row < len(self._list_data):
            return self._list_data[row]
        return ""

    # ── NSTableViewDelegate ───────────────────────────────────────────────────

    def tableView_rowViewForRow_(self, tv, row):
        rv = tv.makeViewWithIdentifier_owner_("HR", self)
        if rv is None:
            rv = _HoverRowView.alloc().initWithFrame_(NSMakeRect(0, 0, LEFT_W, 28))
            rv.setIdentifier_("HR")
        return rv

    def tableView_viewForTableColumn_row_(self, tv, col, row):
        cell = tv.makeViewWithIdentifier_owner_("WR", self)
        if cell is None:
            cell = _WordRowView.alloc().initWithFrame_(NSMakeRect(0, 0, LEFT_W, 28))
            cell.setIdentifier_("WR")
        if 0 <= row < len(self._list_data):
            cell.configure(self._list_data[row], row, self)
        return cell

    def tableViewSelectionDidChange_(self, notification):
        if self._reloading:
            return
        row = self._table.selectedRow()
        if 0 <= row < len(self._list_data) and self._delegate:
            word = self._list_data[row]
            self._search_field.setStringValue_(word)
            self._delegate.lookupWordInMainWindow_(word)

    # ── Actions ───────────────────────────────────────────────────────────────

    @objc.IBAction
    def toggleSidebar_(self, sender):
        win_w = self._window.contentView().frame().size.width
        if self._sidebar_view.isHidden():
            new_right_w = win_w - LEFT_W - 1
            r = self._right_view.frame()
            self._right_view.setFrame_(NSMakeRect(0, 0, new_right_w, r.size.height))
            self._sep_main.setHidden_(False)
            self._sidebar_view.setHidden_(False)
        else:
            r = self._right_view.frame()
            self._right_view.setFrame_(NSMakeRect(0, 0, win_w, r.size.height))
            self._sep_main.setHidden_(True)
            self._sidebar_view.setHidden_(True)

    @objc.IBAction
    def tabHistClick_(self, sender):
        self._switchTab("history")

    @objc.IBAction
    def tabFavClick_(self, sender):
        self._switchTab("favorites")

    @objc.python_method
    def _switchTab(self, mode):
        self._mode = mode
        # 移动白色胶囊
        f = self._tab_pill.frame()
        pill_x = 2 if mode == "history" else 2 + self._tab_seg_w
        self._tab_pill.setFrame_(NSMakeRect(pill_x, f.origin.y, f.size.width, f.size.height))
        # 更新按钮字重和颜色
        if mode == "history":
            self._tab_hist.setFont_(NSFont.boldSystemFontOfSize_(13))
            self._tab_hist.setContentTintColor_(NSColor.labelColor())
            self._tab_fav.setFont_(NSFont.systemFontOfSize_(13))
            self._tab_fav.setContentTintColor_(NSColor.secondaryLabelColor())
        else:
            self._tab_fav.setFont_(NSFont.boldSystemFontOfSize_(13))
            self._tab_fav.setContentTintColor_(NSColor.labelColor())
            self._tab_hist.setFont_(NSFont.systemFontOfSize_(13))
            self._tab_hist.setContentTintColor_(NSColor.secondaryLabelColor())
        self._repositionBottomButtons()
        self._sidebar_filter = ""
        if self._sidebar_search is not None:
            self._sidebar_search.setStringValue_("")
        self.refreshList()

    def controlTextDidChange_(self, notification):
        field = notification.object()
        if self._sidebar_search is not None and field == self._sidebar_search:
            self._sidebar_filter = self._sidebar_search.stringValue() or ""
            self.refreshList()
        elif self._search_field is not None and field == self._search_field:
            self._updateSuggestions_(self._search_field.stringValue() or "")

    @objc.python_method
    def _repositionBottomButtons(self):
        if self._clear_btn is None:
            return
        bw, gap, y, h = 54, 6, 8, 22
        panel_w = self._clear_btn.superview().frame().size.width
        show_export = self._mode == "favorites"
        if show_export:
            x0 = (panel_w - 2 * bw - gap) / 2
            self._clear_btn.setFrame_(NSMakeRect(x0, y, bw, h))
            self._export_btn.setFrame_(NSMakeRect(x0 + bw + gap, y, bw, h))
            self._export_btn.setHidden_(False)
        else:
            self._clear_btn.setFrame_(NSMakeRect((panel_w - bw) / 2, y, bw, h))
            self._export_btn.setHidden_(True)

    @objc.IBAction
    def clearList_(self, sender):
        if not self._delegate:
            return
        label = "历史记录" if self._mode == "history" else "收藏"
        from AppKit import NSAlert
        alert = NSAlert.alloc().init()
        alert.setMessageText_(f"确认清空{label}？")
        alert.setInformativeText_("此操作不可撤销。")
        alert.addButtonWithTitle_("清空")
        alert.addButtonWithTitle_("取消")
        if alert.runModal() != 1000:  # NSAlertFirstButtonReturn
            return
        dm = self._delegate.data_manager
        if self._mode == "history":
            dm.clear_history()
        else:
            dm.clear_favorites()
        self.refreshList()

    @objc.IBAction
    def deleteSelectedWord_(self, sender):
        row = sender.tag()
        if 0 <= row < len(self._list_data) and self._delegate:
            word = self._list_data[row]
            dm = self._delegate.data_manager
            if self._mode == "history":
                dm.remove_history(word)
            else:
                dm.remove_favorite(word)
            dm.remove_cached(word)
            self.refreshList()

    # alias used by _WordTable keyDown_
    @objc.IBAction
    def deleteWordAtRow_(self, sender):
        self.deleteSelectedWord_(sender)

    @objc.IBAction
    def exportFavorites_(self, sender):
        if not self._delegate:
            return
        from AppKit import NSSavePanel, NSModalResponseOK
        panel = NSSavePanel.savePanel()
        panel.setTitle_("导出收藏")
        panel.setNameFieldStringValue_("cambridge_favorites.xlsx")
        panel.setAllowedFileTypes_(["xlsx"])
        if panel.runModal() == NSModalResponseOK:
            path = panel.URL().path()
            try:
                self._delegate.data_manager.export_favorites_xlsx(path)
            except Exception as e:
                from AppKit import NSAlert
                a = NSAlert.alloc().init()
                a.setMessageText_("导出失败")
                a.setInformativeText_(str(e))
                a.runModal()

    @objc.IBAction
    def searchEnter_(self, sender):
        if self._suggest:
            self._suggest.hide()
        word = (sender.stringValue() or "").strip()
        if word and self._delegate:
            self._delegate.lookupWordInMainWindow_(word)
        elif not word:
            self._resetToWelcome()

    @objc.IBAction
    def searchBtnClick_(self, sender):
        if self._suggest:
            self._suggest.hide()
        word = (self._search_field.stringValue() or "").strip()
        if word and self._delegate:
            self._delegate.lookupWordInMainWindow_(word)
        elif not word:
            self._resetToWelcome()

    @objc.python_method
    def _resetToWelcome(self):
        self._current_word = None
        self._current_data = None
        self._updateFavBtn_(False)
        self._showOverlay("🧀", "输入单词开始查询", "支持英文单词 · 划词快捷键 · 历史收藏")

    # ── Autocomplete ──────────────────────────────────────────────────────────

    @objc.python_method
    def _updateSuggestions_(self, prefix):
        if not self._suggest or not self._delegate:
            return
        prefix = prefix.strip()
        if len(prefix) < 2:
            self._suggest.hide()
            return

        # 系统词典补全（支持任意英语单词）
        checker     = NSSpellChecker.sharedSpellChecker()
        completions = checker.completionsForPartialWordRange_inString_language_inSpellDocumentWithTag_(
            (0, len(prefix)), prefix, "en", 0
        ) or []
        prefix_l  = prefix.lower()
        sys_words = [w for w in completions if w.lower() != prefix_l]

        # 历史/收藏中的匹配词优先置顶
        dm       = self._delegate.data_manager
        seen     = set()
        personal = []
        for entry in dm.history:
            w = entry.get("word", "") if isinstance(entry, dict) else str(entry)
            wl = w.lower()
            if w and wl.startswith(prefix_l) and wl != prefix_l and w not in seen:
                seen.add(w)
                personal.append(w)
        for w in dm.favorites:
            wl = w.lower()
            if w and wl.startswith(prefix_l) and wl != prefix_l and w not in seen:
                seen.add(w)
                personal.append(w)

        personal_lower = {w.lower() for w in personal}
        extra      = [w for w in sys_words if w.lower() not in personal_lower]
        candidates = (personal + extra)[: self._suggest.MAX_VIS]

        if not candidates:
            self._suggest.hide()
            return
        self._suggest.update(candidates, self._search_field, self._applySuggestion_)

    @objc.python_method
    def _applySuggestion_(self, word):
        self._search_field.setStringValue_(word)
        if self._delegate:
            self._delegate.lookupWordInMainWindow_(word)

    # NSControlTextEditingDelegate — keyboard navigation in the search field
    def control_textView_doCommandBySelector_(self, control, tv, sel):
        if control is not self._search_field:
            return False
        if not self._suggest or not self._suggest.is_visible():
            return False
        sel_str = str(sel)
        if sel_str == "moveDown:":
            word = self._suggest.move_selection(1)
            if word is not None:
                self._search_field.setStringValue_(word)
            return True
        if sel_str == "moveUp:":
            word = self._suggest.move_selection(-1)
            if word is not None:
                self._search_field.setStringValue_(word)
            return True
        if sel_str == "cancelOperation:":   # Escape
            self._suggest.hide()
            return True
        if sel_str in ("insertNewline:", "insertNewlineIgnoringFieldEditor:"):
            word = self._suggest.selected_word()
            if word:
                self._suggest.hide()
                self._search_field.setStringValue_(word)
                if self._delegate:
                    self._delegate.lookupWordInMainWindow_(word)
                return True
        return False

    @objc.IBAction
    def toggleFavorite_(self, sender):
        if not self._delegate or not self._current_word:
            return
        dm = self._delegate.data_manager
        is_fav = dm.toggle_favorite(self._current_word, self._current_data)
        self._updateFavBtn_(is_fav)
        self.refreshFavorites()

    @objc.IBAction
    def copyCurrent_(self, sender):
        text = self._content_tv.string()
        if not text or not text.strip():
            return
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSStringPboardType)
        self._copy_btn.setTitle_("✓")
        self._copy_btn.setContentTintColor_(NSColor.systemGreenColor())
        import threading
        from utils import run_on_main_thread
        def _restore():
            def _do():
                self._copy_btn.setTitle_("⎘")
                self._copy_btn.setContentTintColor_(NSColor.secondaryLabelColor())
            run_on_main_thread(_do)
        threading.Timer(1.5, _restore).start()

    @objc.IBAction
    def rowDoubleClicked_(self, sender):
        row = self._table.clickedRow()
        if 0 <= row < len(self._list_data) and self._delegate:
            self._delegate.lookupWordInMainWindow_(self._list_data[row])

    # ── Public API ────────────────────────────────────────────────────────────

    @objc.python_method
    def _updateFavBtn_(self, is_fav: bool):
        self._fav_btn.setTitle_("★︎" if is_fav else "☆︎")
        color = NSColor.systemYellowColor() if is_fav else NSColor.tertiaryLabelColor()
        self._fav_btn.setContentTintColor_(color)

    @objc.python_method
    def refreshList(self):
        if not self._delegate:
            return
        dm = self._delegate.data_manager
        all_words = (
            dm.get_history() if self._mode == "history" else dm.get_favorites()
        )
        q = self._sidebar_filter.lower().strip()
        if q:
            self._list_data = [w for w in all_words if q in w.lower()]
        else:
            self._list_data = all_words
        self._reloading = True
        self._table.reloadData()
        self._reloading = False
        if self._stat_label:
            total = len(all_words)
            shown = len(self._list_data)
            if self._mode == "history":
                today = dm.get_today_history_count()
                base = f"共 {total} 条 · 今日 {today} 条"
            else:
                base = f"共 {total} 个收藏"
            if q and shown != total:
                self._stat_label.setStringValue_(f"{base} · 匹配 {shown}")
            else:
                self._stat_label.setStringValue_(base)

    @objc.python_method
    def refreshHistory(self):
        if self._mode == "history":
            self.refreshList()

    @objc.python_method
    def refreshFavorites(self):
        if self._mode == "favorites":
            self.refreshList()

    @objc.python_method
    def _layoutOverlay(self, ov_w, ov_h):
        """共用：调整 overlay inner + 各子视图宽度居中。"""
        self._overlay.setFrame_(NSMakeRect(0, 0, ov_w, ov_h))
        ih = self._overlay_inner_h
        self._overlay_inner.setFrame_(
            NSMakeRect(0, (ov_h - ih) / 2, ov_w, ih))
        for v in (self._ov_icon, self._ov_title, self._ov_hint, self._ov_spinner):
            f = v.frame()
            v.setFrame_(NSMakeRect(0, f.origin.y, ov_w, f.size.height))
        bg_f = self._ov_icon_bg.frame()
        self._ov_icon_bg.setFrame_(
            NSMakeRect((ov_w - bg_f.size.width) / 2,
                       bg_f.origin.y,
                       bg_f.size.width, bg_f.size.height))

    @objc.python_method
    def _showOverlay(self, icon: str, title: str, hint: str):
        self._ov_spinner.stopAnimation_(None)
        self._ov_icon_bg.setHidden_(False)
        self._ov_icon.set_text(icon)
        self._ov_title.setStringValue_(title)
        self._ov_hint.setStringValue_(hint)
        right_b = self._overlay.superview().bounds()
        ov_w = right_b.size.width
        ov_h = right_b.size.height - RIGHT_HDR - 1
        self._layoutOverlay(ov_w, ov_h)
        self._scroll_content.setHidden_(True)
        self._overlay.setHidden_(False)

    @objc.python_method
    def _showLoadingOverlay(self, word: str):
        # 隐藏 emoji，只显示 spinner + 文字
        self._ov_icon.set_text("")
        self._ov_icon_bg.setHidden_(True)
        self._ov_title.setStringValue_("正在查询")
        self._ov_hint.setStringValue_(word)
        right_b = self._overlay.superview().bounds()
        ov_w = right_b.size.width
        ov_h = right_b.size.height - RIGHT_HDR - 1
        self._layoutOverlay(ov_w, ov_h)
        self._scroll_content.setHidden_(True)
        self._overlay.setHidden_(False)
        self._ov_spinner.startAnimation_(None)

    @objc.python_method
    def _hideOverlay(self):
        self._ov_spinner.stopAnimation_(None)
        self._overlay.setHidden_(True)
        self._scroll_content.setHidden_(False)

    @objc.python_method
    def showContent_(self, data: dict):
        self._current_data = data
        self._current_word = data.get("word", "") if data else ""
        error   = (data or {}).get("error", "")
        entries = (data or {}).get("entries", [])
        if error and not entries:
            is_net = any(k in error for k in ("SSL", "retries", "timed out", "timeout"))
            if is_net:
                self._showOverlay("📡", "网络连接失败", "请检查网络后重试")
            else:
                self._showOverlay("🔍", "未找到该词条", "请检查拼写，或尝试其他词形")
        else:
            self._hideOverlay()
            fs = self._delegate.settings.font_size if self._delegate else 14
            update_word_view(self._content_tv, data, fs)
            self._prefetchAudio(data)   # pre-download audio so clicks are instant
        if self._delegate and self._current_word:
            is_fav = self._delegate.data_manager.is_favorite(self._current_word)
            self._updateFavBtn_(is_fav)

    @objc.python_method
    def rerenderFontSize(self, font_size: int):
        if self._current_data:
            update_word_view(self._content_tv, self._current_data, font_size)

    @objc.python_method
    def showLoadingForWord_(self, word: str):
        self._search_field.setStringValue_(word)
        self._current_word = word
        self._current_data = None
        self._updateFavBtn_(False)
        self._showLoadingOverlay(word)

    # ── NSTextViewDelegate — pronunciation link clicks ─────────────────────────

    def textView_clickedOnLink_atIndex_(self, tv, link, char_index):
        url = str(link)
        if url.startswith("http"):
            self._playAudio_(url)
            return True
        if url.startswith("lookup://"):
            word = url[len("lookup://"):]
            if word and self._delegate:
                self._search_field.setStringValue_(word)
                self._delegate.lookupWordInMainWindow_(word)
            return True
        return False

    # ── 发音播放 ──────────────────────────────────────────────────────────────

    _AUDIO_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://dictionary.cambridge.org/",
        "Accept": "audio/mpeg,audio/*;q=0.9,*/*;q=0.8",
    }

    @objc.python_method
    def _playAudio_(self, url: str):
        """Play audio from URL. Uses DataManager.audio_cache to skip re-downloading."""
        if not url:
            return
        dm = self._delegate.data_manager if self._delegate else None
        import threading, subprocess, tempfile, os, requests as _req
        ac = dm.audio_cache if dm else {}

        def _play(data: bytes):
            try:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    f.write(data)
                    tmp = f.name
                subprocess.Popen(["afplay", tmp])
            except Exception as e:
                print(f"[Audio] play error: {e}")

        def _run():
            try:
                if url in ac:
                    _play(ac[url])
                    return
                # Check if prefetch is already downloading this URL
                should_fetch, event = (dm.claim_audio_fetch(url) if dm
                                       else (True, None))
                if not should_fetch:
                    if event is not None:
                        event.wait(timeout=12)   # join the in-flight prefetch
                    if url in ac:
                        _play(ac[url])
                    return
                # We claimed the slot — do the download
                try:
                    r = _req.get(url, headers=self._AUDIO_HEADERS, timeout=10)
                    r.raise_for_status()
                    if dm:
                        dm.put_audio_cache(url, r.content)
                finally:
                    if dm:
                        dm.release_audio_fetch(url)
                if url in ac:
                    _play(ac[url])
            except Exception as e:
                print(f"[Audio] {e}")

        threading.Thread(target=_run, daemon=True).start()

    @objc.python_method
    def _prefetchAudio(self, data: dict):
        """Pre-download pronunciation audio into DataManager.audio_cache."""
        dm = self._delegate.data_manager if self._delegate else None
        if not dm:
            return
        import threading, requests as _req
        ac = dm.audio_cache
        urls = [
            p.get("audio", "")
            for p in (data or {}).get("pronunciations", [])
            if p.get("audio")
        ]
        if not urls:
            return

        def _fetch(url):
            should_fetch, _ = dm.claim_audio_fetch(url)
            if not should_fetch:
                return   # already cached or another thread is downloading
            try:
                r = _req.get(url, headers=self._AUDIO_HEADERS, timeout=10)
                if r.ok:
                    dm.put_audio_cache(url, r.content)
            except Exception:
                pass
            finally:
                dm.release_audio_fetch(url)

        for url in urls:
            threading.Thread(target=_fetch, args=(url,), daemon=True).start()

    @objc.python_method
    def showWindow(self):
        if not getattr(self, "_first_shown", False):
            self._first_shown = True
            self._resetToWelcome()
            if (self._delegate and hasattr(self._delegate, "settings")
                    and self._delegate.settings.sidebar_open_on_start):
                self.toggleSidebar_(None)
        app = NSApplication.sharedApplication()
        app.activateIgnoringOtherApps_(True)
        self._window.orderFrontRegardless()
        self._window.makeKeyAndOrderFront_(None)
        self._window.makeFirstResponder_(self._search_field)

    @objc.python_method
    def toggleVisible(self):
        if self._window.isVisible():
            self._window.orderOut_(None)
        else:
            self.showWindow()

    @objc.python_method
    def window(self):
        return self._window
