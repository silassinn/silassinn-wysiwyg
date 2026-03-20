"""
WYSIWYG HTML Editor — a lightweight Dreamweaver-style tool for editing
and previewing local HTML files on Windows 11.

Usage:
    python main.py
    python main.py path/to/file.html
"""

import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QToolBar, QStatusBar,
    QFileDialog, QMessageBox, QVBoxLayout, QWidget, QComboBox,
    QHBoxLayout, QPushButton, QInputDialog, QPlainTextEdit, QLabel,
)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QAction, QFont, QKeySequence, QTextCharFormat, QSyntaxHighlighter,
    QColor, QPainter, QTextFormat, QShortcut, QPalette,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

from pygments.lexers import HtmlLexer
from pygments.token import Token
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Syntax highlighter using Pygments token types
# ---------------------------------------------------------------------------
class HtmlSyntaxHighlighter(QSyntaxHighlighter):
    """Applies Pygments-based syntax highlighting to an HTML document."""

    # Map Pygments token types to (colour, bold) pairs
    TOKEN_STYLES = {
        Token.Name.Tag:              ("#569cd6", True),
        Token.Name.Attribute:        ("#9cdcfe", False),
        Token.Literal.String:        ("#ce9178", False),
        Token.Comment:               ("#6a9955", False),
        Token.Comment.Preproc:       ("#6a9955", False),
        Token.Keyword:               ("#c586c0", True),
        Token.Operator:              ("#d4d4d4", False),
        Token.Punctuation:           ("#808080", False),
        Token.Text:                  ("#d4d4d4", False),
    }

    def __init__(self, document, dark: bool = True):
        super().__init__(document)
        self._lexer = HtmlLexer()
        self._dark = dark

    def highlightBlock(self, text: str):
        """Re-lex the current block and apply formats."""
        offset = 0
        for tok_type, tok_value in self._lexer.get_tokens(text):
            length = len(tok_value)
            fmt = self._format_for(tok_type)
            if fmt:
                self.setFormat(offset, length, fmt)
            offset += length

    def _format_for(self, tok_type) -> QTextCharFormat | None:
        # Walk up the token hierarchy until we find a mapped style
        tt = tok_type
        while tt:
            if tt in self.TOKEN_STYLES:
                colour, bold = self.TOKEN_STYLES[tt]
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(colour))
                if bold:
                    fmt.setFontWeight(QFont.Weight.Bold)
                return fmt
            tt = tt.parent
        return None


# ---------------------------------------------------------------------------
# Line-number area widget (gutter)
# ---------------------------------------------------------------------------
class LineNumberArea(QWidget):
    """Draws line numbers alongside the code editor."""

    def __init__(self, editor: "CodeEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return self._editor.line_number_area_size()

    def paintEvent(self, event):
        self._editor.line_number_area_paint(event)


# ---------------------------------------------------------------------------
# Code editor with line numbers
# ---------------------------------------------------------------------------
class CodeEditor(QPlainTextEdit):
    """Plain-text editor with line numbers and Pygments highlighting."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Monospace font
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        # Line-number gutter
        self._line_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self._update_line_area_width()

        # Syntax highlighter (attached later when theme is known)
        self._highlighter: HtmlSyntaxHighlighter | None = None

    # -- Line-number helpers ------------------------------------------------

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def line_number_area_size(self):
        from PyQt6.QtCore import QSize
        return QSize(self.line_number_area_width(), 0)

    def _update_line_area_width(self):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_area(self, rect, dy):
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(cr.left(), cr.top(), self.line_number_area_width(), cr.height())

    def line_number_area_paint(self, event):
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor("#1e1e1e") if self._is_dark() else QColor("#f0f0f0"))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        fg = QColor("#858585") if self._is_dark() else QColor("#999999")
        painter.setPen(fg)
        font = self.font()
        painter.setFont(font)

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0, top, self._line_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1
        painter.end()

    def _is_dark(self) -> bool:
        return self.palette().color(QPalette.ColorRole.Window).lightness() < 128

    # -- Highlight ----------------------------------------------------------

    def attach_highlighter(self, dark: bool):
        self._highlighter = HtmlSyntaxHighlighter(self.document(), dark)

    # -- Tag wrapping -------------------------------------------------------

    def wrap_selection(self, open_tag: str, close_tag: str):
        """Wraps the current selection with the given HTML tags."""
        cursor = self.textCursor()
        selected = cursor.selectedText()
        cursor.insertText(f"{open_tag}{selected}{close_tag}")
        self.setTextCursor(cursor)

    def insert_link(self):
        """Prompts for a URL and wraps the selection in an <a> tag."""
        url, ok = QInputDialog.getText(self, "Insert Link", "URL:")
        if ok and url:
            cursor = self.textCursor()
            selected = cursor.selectedText() or url
            cursor.insertText(f'<a href="{url}">{selected}</a>')
            self.setTextCursor(cursor)


# ---------------------------------------------------------------------------
# Preview pane — embedded Chromium via QtWebEngine
# ---------------------------------------------------------------------------
class PreviewPane(QWebEngineView):
    """Renders the HTML source with a file:/// base URL so local assets work."""

    def update_preview(self, html: str, base_dir: str | None):
        if base_dir:
            base_url = QUrl.fromLocalFile(base_dir + "/")
        else:
            base_url = QUrl()
        self.setHtml(html, base_url)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    """Top-level window: toolbar, splitter (editor + preview), status bar."""

    VIEW_SPLIT = 0
    VIEW_CODE = 1
    VIEW_PREVIEW = 2

    def __init__(self):
        super().__init__()

        self._file_path: str | None = None
        self._modified = False
        self._dark = True  # start in dark mode
        self._view_mode = self.VIEW_SPLIT

        self._init_ui()
        self._apply_theme()
        self._connect_signals()

        # Debounce timer for live preview
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(500)
        self._preview_timer.timeout.connect(self._refresh_preview)

        self._update_title()

        # Open file from command-line argument if provided
        if len(sys.argv) > 1:
            path = sys.argv[1]
            if os.path.isfile(path):
                self._open_file(path)

    # -- UI setup -----------------------------------------------------------

    def _init_ui(self):
        self.setMinimumSize(1100, 700)
        self.resize(1400, 850)

        # --- Toolbar -------------------------------------------------------
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._act_open = QAction("Open", self)
        self._act_open.setShortcut(QKeySequence("Ctrl+O"))
        toolbar.addAction(self._act_open)

        self._act_save = QAction("Save", self)
        self._act_save.setShortcut(QKeySequence("Ctrl+S"))
        toolbar.addAction(self._act_save)

        self._act_save_as = QAction("Save As", self)
        self._act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        toolbar.addAction(self._act_save_as)

        toolbar.addSeparator()

        # Formatting buttons
        self._act_bold = QAction("Bold", self)
        self._act_bold.setShortcut(QKeySequence("Ctrl+B"))
        toolbar.addAction(self._act_bold)

        self._act_italic = QAction("Italic", self)
        self._act_italic.setShortcut(QKeySequence("Ctrl+I"))
        toolbar.addAction(self._act_italic)

        self._act_underline = QAction("Underline", self)
        self._act_underline.setShortcut(QKeySequence("Ctrl+U"))
        toolbar.addAction(self._act_underline)

        # Heading dropdown
        self._heading_combo = QComboBox()
        self._heading_combo.addItems(["Heading...", "H1", "H2", "H3", "H4"])
        self._heading_combo.setFixedWidth(100)
        toolbar.addWidget(self._heading_combo)

        self._act_link = QAction("Link", self)
        self._act_link.setShortcut(QKeySequence("Ctrl+K"))
        toolbar.addAction(self._act_link)

        toolbar.addSeparator()

        self._act_prettify = QAction("Prettify HTML", self)
        toolbar.addAction(self._act_prettify)

        toolbar.addSeparator()

        # View toggle
        self._act_view = QAction("View: Split", self)
        toolbar.addAction(self._act_view)

        # Theme toggle
        self._act_theme = QAction("Theme: Dark", self)
        toolbar.addAction(self._act_theme)

        # --- Central splitter ----------------------------------------------
        self._editor = CodeEditor()
        self._preview = PreviewPane()

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._editor)
        self._splitter.addWidget(self._preview)
        self._splitter.setSizes([600, 600])
        self.setCentralWidget(self._splitter)

        # --- Status bar ----------------------------------------------------
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._lbl_cursor = QLabel("Ln 1, Col 1")
        self._lbl_modified = QLabel("")
        self._lbl_path = QLabel("No file open")

        self._status_bar.addWidget(self._lbl_cursor)
        self._status_bar.addWidget(self._lbl_modified)
        self._status_bar.addPermanentWidget(self._lbl_path)

    def _connect_signals(self):
        self._act_open.triggered.connect(self._on_open)
        self._act_save.triggered.connect(self._on_save)
        self._act_save_as.triggered.connect(self._on_save_as)

        self._act_bold.triggered.connect(lambda: self._editor.wrap_selection("<strong>", "</strong>"))
        self._act_italic.triggered.connect(lambda: self._editor.wrap_selection("<em>", "</em>"))
        self._act_underline.triggered.connect(lambda: self._editor.wrap_selection("<u>", "</u>"))
        self._heading_combo.currentIndexChanged.connect(self._on_heading)
        self._act_link.triggered.connect(self._editor.insert_link)

        self._act_prettify.triggered.connect(self._on_prettify)
        self._act_view.triggered.connect(self._toggle_view)
        self._act_theme.triggered.connect(self._toggle_theme)

        self._editor.textChanged.connect(self._on_text_changed)
        self._editor.cursorPositionChanged.connect(self._update_cursor_status)

    # -- Theme --------------------------------------------------------------

    def _apply_theme(self):
        if self._dark:
            qss = """
                QMainWindow, QWidget { background-color: #1e1e1e; color: #d4d4d4; }
                QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4; border: none; selection-background-color: #264f78; }
                QToolBar { background-color: #2d2d2d; border: none; spacing: 6px; padding: 4px; }
                QToolBar QToolButton { color: #d4d4d4; padding: 4px 8px; }
                QToolBar QToolButton:hover { background-color: #3e3e3e; }
                QComboBox { background-color: #3c3c3c; color: #d4d4d4; border: 1px solid #555; padding: 2px 6px; }
                QComboBox QAbstractItemView { background-color: #2d2d2d; color: #d4d4d4; selection-background-color: #094771; }
                QStatusBar { background-color: #007acc; color: #ffffff; }
                QStatusBar QLabel { color: #ffffff; margin: 0 8px; }
                QSplitter::handle { background-color: #007acc; width: 3px; }
            """
        else:
            qss = """
                QMainWindow, QWidget { background-color: #ffffff; color: #1e1e1e; }
                QPlainTextEdit { background-color: #ffffff; color: #1e1e1e; border: none; selection-background-color: #add6ff; }
                QToolBar { background-color: #f3f3f3; border-bottom: 1px solid #ccc; spacing: 6px; padding: 4px; }
                QToolBar QToolButton { color: #1e1e1e; padding: 4px 8px; }
                QToolBar QToolButton:hover { background-color: #e0e0e0; }
                QComboBox { background-color: #ffffff; color: #1e1e1e; border: 1px solid #ccc; padding: 2px 6px; }
                QComboBox QAbstractItemView { background-color: #ffffff; color: #1e1e1e; selection-background-color: #0060c0; selection-color: #fff; }
                QStatusBar { background-color: #0078d4; color: #ffffff; }
                QStatusBar QLabel { color: #ffffff; margin: 0 8px; }
                QSplitter::handle { background-color: #0078d4; width: 3px; }
            """
        self.setStyleSheet(qss)
        self._editor.attach_highlighter(self._dark)
        self._act_theme.setText(f"Theme: {'Dark' if self._dark else 'Light'}")

    def _toggle_theme(self):
        self._dark = not self._dark
        self._apply_theme()

    # -- View mode ----------------------------------------------------------

    def _toggle_view(self):
        self._view_mode = (self._view_mode + 1) % 3
        labels = {self.VIEW_SPLIT: "Split", self.VIEW_CODE: "Code", self.VIEW_PREVIEW: "Preview"}
        self._act_view.setText(f"View: {labels[self._view_mode]}")

        self._editor.setVisible(self._view_mode != self.VIEW_PREVIEW)
        self._preview.setVisible(self._view_mode != self.VIEW_CODE)

    # -- File operations ----------------------------------------------------

    def _on_open(self):
        if not self._check_unsaved():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open HTML File", "",
            "HTML Files (*.html *.htm);;All Files (*)",
        )
        if path:
            self._open_file(path)

    def _open_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Could not open file:\n{e}")
            return
        self._file_path = path
        self._editor.setPlainText(content)
        self._modified = False
        self._update_title()
        self._update_status()
        self._refresh_preview()

    def _on_save(self):
        if self._file_path:
            self._save_file(self._file_path)
        else:
            self._on_save_as()

    def _on_save_as(self):
        start_dir = os.path.dirname(self._file_path) if self._file_path else ""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save HTML File", start_dir,
            "HTML Files (*.html *.htm);;All Files (*)",
        )
        if path:
            self._save_file(path)

    def _save_file(self, path: str):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._editor.toPlainText())
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")
            return
        self._file_path = path
        self._modified = False
        self._update_title()
        self._update_status()

    def _check_unsaved(self) -> bool:
        """Returns True if it's safe to proceed (saved or discarded)."""
        if not self._modified:
            return True
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            "You have unsaved changes. Do you want to save before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Save:
            self._on_save()
            return not self._modified  # still modified means save was cancelled
        return reply == QMessageBox.StandardButton.Discard

    def closeEvent(self, event):
        if self._check_unsaved():
            event.accept()
        else:
            event.ignore()

    # -- Text editing -------------------------------------------------------

    def _on_text_changed(self):
        self._modified = True
        self._update_title()
        self._lbl_modified.setText("*")
        # Restart debounce timer for live preview
        self._preview_timer.start()

    def _on_heading(self, index: int):
        if index == 0:
            return
        tag = f"h{index}"
        self._editor.wrap_selection(f"<{tag}>", f"</{tag}>")
        self._heading_combo.setCurrentIndex(0)

    def _on_prettify(self):
        html = self._editor.toPlainText()
        try:
            soup = BeautifulSoup(html, "lxml")
            pretty = soup.prettify()
        except Exception as e:
            QMessageBox.warning(self, "Prettify Error", str(e))
            return
        self._editor.setPlainText(pretty)

    # -- Preview ------------------------------------------------------------

    def _refresh_preview(self):
        html = self._editor.toPlainText()
        base_dir = os.path.dirname(self._file_path) if self._file_path else None
        self._preview.update_preview(html, base_dir)

    # -- Status helpers -----------------------------------------------------

    def _update_title(self):
        name = os.path.basename(self._file_path) if self._file_path else "Untitled"
        mod = " *" if self._modified else ""
        self.setWindowTitle(f"{name}{mod} — HTML Editor")

    def _update_status(self):
        self._lbl_modified.setText("*" if self._modified else "")
        self._lbl_path.setText(self._file_path or "No file open")

    def _update_cursor_status(self):
        cursor = self._editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self._lbl_cursor.setText(f"Ln {line}, Col {col}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    # High-DPI scaling (default in Qt6, but be explicit)
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("HTML Editor")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
