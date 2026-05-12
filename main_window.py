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
    NSSplitView,
    NSView,
    NSScrollView,
    NSTableView,
    NSTableColumn,
    NSTextField,
    NSButton,
    NSSegmentedControl,
    NSBezelStyleRounded,
    NSBezelStyleSmallSquare,
    NSBezelStyleTexturedRounded,
    NSBezelStyleInline,
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

LEFT_W    = 200
RIGHT_HDR = 50
MIN_WIN_W = 740
MIN_WIN_H = 480


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


def _btn(title, target, action, frame, small=False):
    b = NSButton.alloc().initWithFrame_(frame)
    b.setTitle_(title)
    b.setBezelStyle_(NSBezelStyleRounded)
    b.setButtonType_(NSButtonTypeMomentaryLight)
    b.setFont_(NSFont.systemFontOfSize_(12))
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
        self._window       = None
        self._table        = None
        self._seg          = None
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
        cw, ch = 920, 620
        x = sf.origin.x + (sf.size.width  - cw) / 2
        y = sf.origin.y + (sf.size.height - ch) / 2

        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
                 | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, cw, ch), style, NSBackingStoreBuffered, False)
        win.setTitle_("Cambridge")
        win.setMinSize_(NSMakeSize(MIN_WIN_W, MIN_WIN_H))
        win.setReleasedWhenClosed_(False)
        win.setDelegate_(self)

        content = win.contentView()

        # ── NSSplitView fills full content area ────────────────────────────
        split = NSSplitView.alloc().initWithFrame_(NSMakeRect(0, 0, cw, ch))
        split.setVertical_(True)
        split.setDividerStyle_(1)
        split.setDelegate_(self)
        split.setAutoresizingMask_(2 | 16)
        content.addSubview_(split)

        # ── Left panel ─────────────────────────────────────────────────────
        left = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, LEFT_W, ch))
        left.setAutoresizingMask_(16)

        # [历史][收藏] segment — pin to top
        seg = NSSegmentedControl.alloc().initWithFrame_(
            NSMakeRect(8, ch - 36, LEFT_W - 16, 28))
        seg.setSegmentCount_(2)
        seg.setLabel_forSegment_("历史", 0)
        seg.setLabel_forSegment_("收藏", 1)
        seg.setSelectedSegment_(0)
        seg.setTarget_(self)
        seg.setAction_("segmentChanged:")
        seg.setAutoresizingMask_(2 | 8)
        left.addSubview_(seg)

        # [清空] [导出] — small inline-style buttons, pin to top
        clear_btn = _btn("清空", self, "clearList:",
                         NSMakeRect(8, ch - 62, 52, 20))
        clear_btn.setFont_(NSFont.systemFontOfSize_(11))
        clear_btn.setAutoresizingMask_(8)
        left.addSubview_(clear_btn)

        export_btn = _btn("导出", self, "exportFavorites:",
                          NSMakeRect(64, ch - 62, 52, 20))
        export_btn.setFont_(NSFont.systemFontOfSize_(11))
        export_btn.setAutoresizingMask_(8)
        export_btn.setHidden_(True)
        left.addSubview_(export_btn)

        # Thin separator under buttons
        sep_left = NSView.alloc().initWithFrame_(NSMakeRect(0, ch - 68, LEFT_W, 1))
        sep_left.setWantsLayer_(True)
        sep_left.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        sep_left.setAutoresizingMask_(2 | 8)
        left.addSubview_(sep_left)

        # Word list scroll + table — fill remaining space
        list_scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(0, 0, LEFT_W, ch - 70))
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

        # ── Right panel ────────────────────────────────────────────────────
        right_w = cw - LEFT_W - 1
        right = NSView.alloc().initWithFrame_(
            NSMakeRect(LEFT_W + 1, 0, right_w, ch))
        right.setAutoresizingMask_(2 | 16)

        # Header: search field + [查询] + [★]  — pin to top
        hdr_y = ch - RIGHT_HDR
        hdr = NSView.alloc().initWithFrame_(NSMakeRect(0, hdr_y, right_w, RIGHT_HDR))
        hdr.setAutoresizingMask_(2 | 8)

        fld_w = right_w - 126
        search_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(12, 11, fld_w, 28))
        search_field.setPlaceholderString_("输入单词… 回车或点击查询")
        search_field.setBezeled_(True)
        search_field.setBezelStyle_(1)  # NSTextFieldRoundedBezel
        search_field.setEditable_(True)
        search_field.setContinuous_(False)
        search_field.setTarget_(self)
        search_field.setAction_("searchEnter:")
        search_field.setAutoresizingMask_(2)
        hdr.addSubview_(search_field)

        query_btn = _btn("查询", self, "searchBtnClick:",
                         NSMakeRect(fld_w + 18, 12, 52, 26))
        query_btn.setAutoresizingMask_(4 | 8)
        hdr.addSubview_(query_btn)

        fav_btn = _HoverFavButton.alloc().initWithFrame_(
            NSMakeRect(right_w - 44, 9, 32, 32))
        fav_btn.setTarget_(self)
        fav_btn.setAction_("toggleFavorite:")
        fav_btn.setAutoresizingMask_(4 | 8)
        fav_btn.setToolTip_("收藏 / 取消收藏")
        hdr.addSubview_(fav_btn)

        right.addSubview_(hdr)

        # Thin divider below header
        div = NSView.alloc().initWithFrame_(NSMakeRect(0, hdr_y - 1, right_w, 1))
        div.setWantsLayer_(True)
        div.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
        div.setAutoresizingMask_(2 | 8)
        right.addSubview_(div)

        # Content scroll view fills remaining space
        content_h = ch - RIGHT_HDR - 1
        scroll_content, tv = make_word_scroll_view(
            NSMakeRect(0, 0, right_w, content_h))
        scroll_content.setAutoresizingMask_(2 | 16)
        right.addSubview_(scroll_content)
        update_word_view(tv, None)

        # ── Assemble split ─────────────────────────────────────────────────
        split.addSubview_(left)
        split.addSubview_(right)

        self._window       = win
        self._table        = table
        self._seg          = seg
        self._clear_btn    = clear_btn
        self._export_btn   = export_btn
        self._search_field = search_field
        self._fav_btn      = fav_btn
        self._content_tv   = tv

    # ── NSWindowDelegate ──────────────────────────────────────────────────────

    def windowShouldClose_(self, sender):
        self._window.orderOut_(None)
        return False

    # ── NSSplitViewDelegate ───────────────────────────────────────────────────

    def splitView_constrainMinCoordinate_ofSubviewAt_(self, sv, proposed, idx):
        return 150 if idx == 0 else proposed

    def splitView_constrainMaxCoordinate_ofSubviewAt_(self, sv, proposed, idx):
        return 320 if idx == 0 else proposed

    # ── NSTableViewDataSource ─────────────────────────────────────────────────

    def numberOfRowsInTableView_(self, tv):
        return len(self._list_data)

    def tableView_objectValueForTableColumn_row_(self, tv, col, row):
        if 0 <= row < len(self._list_data):
            return self._list_data[row]
        return ""

    # ── NSTableViewDelegate ───────────────────────────────────────────────────

    def tableView_viewForTableColumn_row_(self, tv, col, row):
        cell = tv.makeViewWithIdentifier_owner_("WC", self)
        if cell is None:
            cell = _Cell.alloc().initWithFrame_(NSMakeRect(0, 0, LEFT_W, 24))
            cell.setIdentifier_("WC")
        if 0 <= row < len(self._list_data):
            cell.setStringValue_(self._list_data[row])
        return cell

    def tableViewSelectionDidChange_(self, notification):
        row = self._table.selectedRow()
        if 0 <= row < len(self._list_data) and self._delegate:
            self._delegate.lookupWordInMainWindow_(self._list_data[row])

    # ── Actions ───────────────────────────────────────────────────────────────

    @objc.IBAction
    def segmentChanged_(self, sender):
        self._mode = "history" if sender.selectedSegment() == 0 else "favorites"
        self._export_btn.setHidden_(self._mode != "favorites")
        self.refreshList()

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

    @objc.IBAction
    def searchBtnClick_(self, sender):
        word = (self._search_field.stringValue() or "").strip()
        if word and self._delegate:
            self._delegate.lookupWordInMainWindow_(word)

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
        self._table.reloadData()

    @objc.python_method
    def refreshHistory(self):
        if self._mode == "history":
            self.refreshList()

    @objc.python_method
    def refreshFavorites(self):
        if self._mode == "favorites":
            self.refreshList()

    @objc.python_method
    def showContent_(self, data: dict):
        self._current_data = data
        self._current_word = data.get("word", "") if data else ""
        update_word_view(self._content_tv, data)
        if self._delegate and self._current_word:
            is_fav = self._delegate.data_manager.is_favorite(self._current_word)
            self._updateFavBtn_(is_fav)

    @objc.python_method
    def showLoadingForWord_(self, word: str):
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

    @objc.python_method
    def showWindow(self):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self._window.orderFrontRegardless()
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
