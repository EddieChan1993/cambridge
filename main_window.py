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
        self.setFont_(NSFont.systemFontOfSize_(20))
        self.setTitle_("☆")
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
            NSColor.colorWithWhite_alpha_(0.5, 0.12).setFill()
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                self.bounds(), 6, 6)
            path.fill()
        objc.super(_HoverFavButton, self).drawRect_(rect)


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

        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(8, 3, w - 34, 18))
        lbl.setBezeled_(False); lbl.setDrawsBackground_(False)
        lbl.setEditable_(False); lbl.setSelectable_(False)
        lbl.setFont_(NSFont.systemFontOfSize_(13))
        lbl.setAutoresizingMask_(2)
        self.addSubview_(lbl)
        self._lbl = lbl

        del_btn = NSButton.alloc().initWithFrame_(NSMakeRect(w - 26, 2, 20, 20))
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
        self._ov_icon        = None
        self._ov_title       = None
        self._ov_hint        = None
        self._table        = None
        self._seg          = None
        self._stat_label   = None
        self._clear_btn    = None
        self._export_btn   = None
        self._search_field = None
        self._fav_btn      = None
        self._content_tv   = None
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
        left = NSView.alloc().initWithFrame_(NSMakeRect(cw - LEFT_W, 0, LEFT_W, ch))
        left.setAutoresizingMask_(1 | 16)   # 左边距弹性 + 高度弹性 → 钉在右边

        # [历史][收藏] segment — 垂直居中在 RIGHT_HDR 头部区域
        _seg_h = 32
        _seg_y = ch - RIGHT_HDR + (RIGHT_HDR - _seg_h) // 2
        seg = NSSegmentedControl.alloc().initWithFrame_(
            NSMakeRect(8, _seg_y, LEFT_W - 16, _seg_h))
        seg.setSegmentCount_(2)
        seg.setLabel_forSegment_("历史", 0)
        seg.setLabel_forSegment_("收藏", 1)
        seg.setSelectedSegment_(0)
        seg.setFont_(NSFont.systemFontOfSize_(14))
        seg.setTarget_(self)
        seg.setAction_("segmentChanged:")
        seg.setAutoresizingMask_(2 | 8)
        left.addSubview_(seg)

        # Thin separator — aligned with right panel divider at ch-RIGHT_HDR-1
        sep_top = NSView.alloc().initWithFrame_(
            NSMakeRect(0, ch - RIGHT_HDR - 1, LEFT_W, 1))
        sep_top.setWantsLayer_(True)
        sep_top.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        sep_top.setAutoresizingMask_(2 | 8)
        left.addSubview_(sep_top)

        # Word list scroll + table — fills between top and bottom areas
        _BTN_H  = 36    # height reserved at bottom for action buttons
        _STAT_H = 20    # stat label band height above button area
        _LBL_H  = 13    # tight label height so text is vertically centred
        stat_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(0, _BTN_H + (_STAT_H - _LBL_H) // 2, LEFT_W, _LBL_H))
        stat_label.setEditable_(False)
        stat_label.setBezeled_(False)
        stat_label.setDrawsBackground_(False)
        stat_label.setAlignment_(1)   # NSTextAlignmentCenter
        stat_label.setFont_(NSFont.systemFontOfSize_(10))
        stat_label.setTextColor_(NSColor.tertiaryLabelColor())
        stat_label.setAutoresizingMask_(2 | 32)
        left.addSubview_(stat_label)

        list_scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(0, _BTN_H + _STAT_H, LEFT_W, ch - RIGHT_HDR - 1 - _BTN_H - _STAT_H))
        list_scroll.setHasVerticalScroller_(True)
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
        table.setUsesAlternatingRowBackgroundColors_(True)
        table.setRowHeight_(24)
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

        # 布局：[搜索框(弹性)] [查询] [★] [☰]，右侧三个按钮钉在右边
        # 右侧固定宽度：60(查询)+8+36(★)+8+36(☰)+8 = 156
        fld_w = right_w - 8 - 8 - 60 - 8 - 36 - 8 - 36 - 8   # = right_w - 172

        search_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(8, 15, fld_w, 36))
        search_field.setPlaceholderString_("输入单词… 回车或点击查询")
        search_field.setBezeled_(True)
        search_field.setBezelStyle_(1)
        search_field.setEditable_(True)
        search_field.setContinuous_(False)
        search_field.setTarget_(self)
        search_field.setAction_("searchEnter:")
        search_field.setFont_(NSFont.systemFontOfSize_(15))
        search_field.cell().setControlSize_(3)   # NSControlSizeLarge — 光标/渲染跟着变大
        search_field.setAutoresizingMask_(2)
        hdr.addSubview_(search_field)

        query_btn = _btn("查询", self, "searchBtnClick:",
                         NSMakeRect(right_w - 156, 17, 60, 32))
        query_btn.cell().setControlSize_(3)      # NSControlSizeLarge — 按钮渲染高度跟着变
        query_btn.setAutoresizingMask_(1 | 8)
        hdr.addSubview_(query_btn)

        _ICON_Y  = (RIGHT_HDR - 36) // 2   # 36px 按钮在 66px header 里垂直居中
        _ICON_SZ = 36
        _ICON_F  = NSFont.systemFontOfSize_(18)

        fav_btn = _HoverFavButton.alloc().initWithFrame_(
            NSMakeRect(right_w - 88, _ICON_Y, _ICON_SZ, _ICON_SZ))
        fav_btn.setFont_(_ICON_F)           # 与 sidebar_btn 字号统一
        fav_btn.setTarget_(self)
        fav_btn.setAction_("toggleFavorite:")
        fav_btn.setAutoresizingMask_(1 | 8)
        fav_btn.setToolTip_("收藏 / 取消收藏")
        hdr.addSubview_(fav_btn)

        sidebar_btn = _HoverFavButton.alloc().initWithFrame_(
            NSMakeRect(right_w - 44, _ICON_Y, _ICON_SZ, _ICON_SZ))
        sidebar_btn.setTitle_("☰")
        sidebar_btn.setFont_(_ICON_F)       # 与 fav_btn 字号相同
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

        inner_h = 130
        inner = NSView.alloc().initWithFrame_(
            NSMakeRect(0, (content_h - inner_h) / 2, right_w, inner_h))
        inner.setAutoresizingMask_(2 | 8 | 32)   # 宽度弹性 + 上下边距均弹性 → 垂直居中

        def _clbl(text, y, h, size=13, bold=False):
            f = NSTextField.alloc().initWithFrame_(NSMakeRect(0, y, right_w, h))
            f.setStringValue_(text)
            f.setBezeled_(False); f.setDrawsBackground_(False)
            f.setEditable_(False); f.setSelectable_(False)
            f.setAlignment_(1)   # NSTextAlignmentCenter
            f.setAutoresizingMask_(2)
            f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold
                       else NSFont.systemFontOfSize_(size))
            f.setTextColor_(NSColor.secondaryLabelColor())
            return f

        ov_icon  = _clbl("", inner_h - 50, 44, size=36)
        ov_title = _clbl("", inner_h - 86, 24, size=16, bold=True)
        ov_hint  = _clbl("", inner_h - 116, 20, size=13)
        ov_hint.setTextColor_(NSColor.tertiaryLabelColor())

        inner.addSubview_(ov_icon)
        inner.addSubview_(ov_title)
        inner.addSubview_(ov_hint)
        overlay.addSubview_(inner)
        right.addSubview_(overlay)

        self._scroll_content  = scroll_content
        self._overlay         = overlay
        self._overlay_inner   = inner
        self._overlay_inner_h = inner_h
        self._ov_icon         = ov_icon
        self._ov_title        = ov_title
        self._ov_hint         = ov_hint

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

        self._window       = win
        self._right_view   = right
        self._sep_main     = sep_main
        self._sidebar_view = left
        self._table        = table
        self._seg          = seg
        self._stat_label   = stat_label
        self._clear_btn    = clear_btn
        self._export_btn   = export_btn
        self._search_field = search_field
        self._fav_btn      = fav_btn
        self._content_tv   = tv


    # ── NSWindowDelegate ──────────────────────────────────────────────────────

    def windowShouldClose_(self, sender):
        self._window.orderOut_(None)
        return False

    def windowDidResize_(self, notification):
        self._repositionBottomButtons()

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
            rv = _HoverRowView.alloc().initWithFrame_(NSMakeRect(0, 0, LEFT_W, 24))
            rv.setIdentifier_("HR")
        return rv

    def tableView_viewForTableColumn_row_(self, tv, col, row):
        cell = tv.makeViewWithIdentifier_owner_("WR", self)
        if cell is None:
            cell = _WordRowView.alloc().initWithFrame_(NSMakeRect(0, 0, LEFT_W, 24))
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
    def segmentChanged_(self, sender):
        self._mode = "history" if sender.selectedSegment() == 0 else "favorites"
        self._repositionBottomButtons()
        self.refreshList()

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
        word = (sender.stringValue() or "").strip()
        if word and self._delegate:
            self._delegate.lookupWordInMainWindow_(word)
        elif not word:
            self._resetToWelcome()

    @objc.IBAction
    def searchBtnClick_(self, sender):
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
        self._showOverlay("📖", "输入单词开始查询", "支持英文单词 · 划词快捷键 · 历史收藏")

    @objc.IBAction
    def toggleFavorite_(self, sender):
        if not self._delegate or not self._current_word:
            return
        dm = self._delegate.data_manager
        is_fav = dm.toggle_favorite(self._current_word, self._current_data)
        self._updateFavBtn_(is_fav)
        self.refreshFavorites()

    @objc.IBAction
    def rowDoubleClicked_(self, sender):
        row = self._table.clickedRow()
        if 0 <= row < len(self._list_data) and self._delegate:
            self._delegate.lookupWordInMainWindow_(self._list_data[row])

    # ── Public API ────────────────────────────────────────────────────────────

    @objc.python_method
    def _updateFavBtn_(self, is_fav: bool):
        self._fav_btn.setTitle_("★" if is_fav else "☆")
        color = NSColor.systemYellowColor() if is_fav else NSColor.tertiaryLabelColor()
        self._fav_btn.setContentTintColor_(color)

    @objc.python_method
    def refreshList(self):
        if not self._delegate:
            return
        dm = self._delegate.data_manager
        self._list_data = (
            dm.get_history() if self._mode == "history" else dm.get_favorites()
        )
        self._reloading = True
        self._table.reloadData()
        self._reloading = False
        if self._stat_label:
            total = len(self._list_data)
            if self._mode == "history":
                today = dm.get_today_history_count()
                self._stat_label.setStringValue_(f"共 {total} 条 · 今日 {today} 条")
            else:
                self._stat_label.setStringValue_(f"共 {total} 个收藏")

    @objc.python_method
    def refreshHistory(self):
        if self._mode == "history":
            self.refreshList()

    @objc.python_method
    def refreshFavorites(self):
        if self._mode == "favorites":
            self.refreshList()

    @objc.python_method
    def _showOverlay(self, icon: str, title: str, hint: str):
        self._ov_icon.setStringValue_(icon)
        self._ov_title.setStringValue_(title)
        self._ov_hint.setStringValue_(hint)
        # 从父视图（right panel）实时读取尺寸，autoresizing 未必及时更新
        right_b = self._overlay.superview().bounds()
        ov_w = right_b.size.width
        ov_h = right_b.size.height - RIGHT_HDR - 1
        self._overlay.setFrame_(NSMakeRect(0, 0, ov_w, ov_h))
        ih = self._overlay_inner_h
        self._overlay_inner.setFrame_(
            NSMakeRect(0, (ov_h - ih) / 2, ov_w, ih))
        for lbl in (self._ov_icon, self._ov_title, self._ov_hint):
            f = lbl.frame()
            lbl.setFrame_(NSMakeRect(0, f.origin.y, ov_w, f.size.height))
        self._scroll_content.setHidden_(True)
        self._overlay.setHidden_(False)

    @objc.python_method
    def _hideOverlay(self):
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
        if self._delegate and self._current_word:
            is_fav = self._delegate.data_manager.is_favorite(self._current_word)
            self._updateFavBtn_(is_fav)

    @objc.python_method
    def rerenderFontSize(self, font_size: int):
        if self._current_data:
            update_word_view(self._content_tv, self._current_data, font_size)

    @objc.python_method
    def showLoadingForWord_(self, word: str):
        self._hideOverlay()
        self._search_field.setStringValue_(word)
        self._current_word = word
        self._current_data = None
        self._updateFavBtn_(False)
        from Foundation import NSAttributedString
        from AppKit import NSFontAttributeName, NSForegroundColorAttributeName
        ph = NSAttributedString.alloc().initWithString_attributes_(
            f'查询 "{word}"…',
            {
                NSFontAttributeName: NSFont.systemFontOfSize_(15),
                NSForegroundColorAttributeName: NSColor.tertiaryLabelColor(),
            },
        )
        self._content_tv.textStorage().setAttributedString_(ph)

    # ── NSTextViewDelegate — pronunciation link clicks ─────────────────────────

    def textView_clickedOnLink_atIndex_(self, tv, link, char_index):
        url = str(link)
        if url.startswith("http"):
            self._playAudio_(url)
            return True
        return False

    # ── 发音播放 ──────────────────────────────────────────────────────────────

    @objc.python_method
    def _playAudio_(self, url: str):
        if not url:
            return
        import threading, subprocess, tempfile, os, requests as _req
        def _run():
            try:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://dictionary.cambridge.org/",
                    "Accept": "audio/mpeg,audio/*;q=0.9,*/*;q=0.8",
                }
                r = _req.get(url, headers=headers, timeout=10)
                r.raise_for_status()
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    f.write(r.content)
                    tmp = f.name
                subprocess.run(["afplay", tmp], check=False)
                os.unlink(tmp)
            except Exception as e:
                print(f"[Audio] {e}")
        threading.Thread(target=_run, daemon=True).start()

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
