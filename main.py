"""
WYSIWYG HTML Editor — a lightweight Dreamweaver-style tool for visually
editing and previewing local HTML files on Windows 11.

The RIGHT pane is the primary visual editor (contentEditable).  Formatting
toolbar buttons (Bold, Italic, etc.) act on the visual pane.  Changes made
visually are synced back to the source code on the left.  You can also edit
the raw HTML on the left and it will refresh the visual pane.

Usage:
    python main.py
    python main.py path/to/file.html
"""

import sys
import os
import json
import re
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QToolBar, QStatusBar,
    QFileDialog, QMessageBox, QVBoxLayout, QWidget, QComboBox,
    QHBoxLayout, QPushButton, QInputDialog, QPlainTextEdit, QLabel,
    QSpinBox,
)
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSlot, QObject
from PyQt6.QtGui import (
    QAction, QFont, QKeySequence, QTextCharFormat, QSyntaxHighlighter,
    QColor, QPainter, QTextFormat, QShortcut, QPalette,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel

from pygments.lexers import HtmlLexer
from pygments.token import Token
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# JavaScript injected into the visual editor page
# ---------------------------------------------------------------------------
EDITOR_JS = r"""
(function() {
    // ---- QWebChannel bridge ----
    var bridge = null;
    new QWebChannel(qt.webChannelTransport, function(channel) {
        bridge = channel.objects.bridge;
    });

    function sendHtmlToBridge() {
        if (!bridge) return;
        // Get the full document HTML (doctype + html tag)
        var html = document.documentElement.outerHTML;
        // Reconstruct with doctype if present
        var doctype = '';
        if (document.doctype) {
            doctype = new XMLSerializer().serializeToString(document.doctype) + '\n';
        }
        bridge.on_visual_change(doctype + html);
    }

    // ---- Make body editable ----
    document.body.setAttribute('contenteditable', 'true');
    document.body.style.outline = 'none';
    document.body.style.minHeight = '100%';

    // ---- Observe changes ----
    var debounceTimer = null;
    var observer = new MutationObserver(function() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(sendHtmlToBridge, 300);
    });
    observer.observe(document.body, {
        childList: true, subtree: true,
        attributes: true, characterData: true
    });
    // Also catch typing
    document.body.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(sendHtmlToBridge, 300);
    });

    // ---- Formatting commands (called from Python via runJavaScript) ----
    window.editorExecCommand = function(cmd, value) {
        document.execCommand(cmd, false, value || null);
        sendHtmlToBridge();
    };

    // ---- Image resize handles ----
    var resizing = null;

    document.body.addEventListener('mousedown', function(e) {
        if (e.target.tagName === 'IMG') {
            e.target.style.outline = '2px solid #007acc';
            e.target.style.cursor = 'nwse-resize';
        }
    });

    document.body.addEventListener('click', function(e) {
        // Clear outlines from all images first
        document.querySelectorAll('img').forEach(function(img) {
            if (img !== e.target) {
                img.style.outline = '';
                img.style.cursor = '';
            }
        });
        if (e.target.tagName === 'IMG') {
            e.target.style.outline = '2px solid #007acc';
        }
    });

    // Corner-drag resize for images
    document.body.addEventListener('mousedown', function(e) {
        if (e.target.tagName === 'IMG') {
            var img = e.target;
            var rect = img.getBoundingClientRect();
            // Only start resize if near bottom-right corner (within 20px)
            var nearRight = Math.abs(e.clientX - rect.right) < 20;
            var nearBottom = Math.abs(e.clientY - rect.bottom) < 20;
            if (nearRight && nearBottom) {
                e.preventDefault();
                resizing = {
                    img: img,
                    startX: e.clientX,
                    startY: e.clientY,
                    startW: img.offsetWidth,
                    startH: img.offsetHeight,
                    ratio: img.offsetWidth / img.offsetHeight
                };
            }
        }
    });

    document.addEventListener('mousemove', function(e) {
        if (resizing) {
            e.preventDefault();
            var dx = e.clientX - resizing.startX;
            var newW = Math.max(20, resizing.startW + dx);
            var newH = newW / resizing.ratio;
            resizing.img.style.width = newW + 'px';
            resizing.img.style.height = newH + 'px';
            // Also set the width/height attributes for HTML output
            resizing.img.setAttribute('width', Math.round(newW));
            resizing.img.setAttribute('height', Math.round(newH));
        }
    });

    document.addEventListener('mouseup', function(e) {
        if (resizing) {
            resizing = null;
            sendHtmlToBridge();
        }
    });

    // ---- Drag-to-reposition images ----
    document.body.addEventListener('dragstart', function(e) {
        if (e.target.tagName === 'IMG') {
            e.dataTransfer.setData('text/html', e.target.outerHTML);
            e.dataTransfer.effectAllowed = 'move';
            e.target._dragging = true;
        }
    });

    document.body.addEventListener('drop', function(e) {
        // If an image was being dragged internally, remove the original
        var imgs = document.querySelectorAll('img');
        imgs.forEach(function(img) {
            if (img._dragging) {
                img.remove();
                delete img._dragging;
            }
        });
        setTimeout(sendHtmlToBridge, 100);
    });

    // ---- Font size command ----
    window.editorSetFontSize = function(size) {
        // Use fontSize command (1-7 scale), then replace with inline style
        document.execCommand('fontSize', false, '7');
        var fontElements = document.querySelectorAll('font[size="7"]');
        fontElements.forEach(function(el) {
            var span = document.createElement('span');
            span.style.fontSize = size + 'px';
            span.innerHTML = el.innerHTML;
            el.parentNode.replaceChild(span, el);
        });
        sendHtmlToBridge();
    };

    // Notify Python that the editor JS is ready
    setTimeout(function() {
        if (bridge) bridge.on_editor_ready();
    }, 200);
})();
"""


# ---------------------------------------------------------------------------
# Syntax highlighter using Pygments token types
# ---------------------------------------------------------------------------
class HtmlSyntaxHighlighter(QSyntaxHighlighter):
    """Applies Pygments-based syntax highlighting to an HTML document."""

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
        offset = 0
        for tok_type, tok_value in self._lexer.get_tokens(text):
            length = len(tok_value)
            fmt = self._format_for(tok_type)
            if fmt:
                self.setFormat(offset, length, fmt)
            offset += length

    def _format_for(self, tok_type) -> QTextCharFormat | None:
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
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self._line_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self._update_line_area_width()

        self._highlighter: HtmlSyntaxHighlighter | None = None

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
        painter.setFont(self.font())

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

    def attach_highlighter(self, dark: bool):
        self._highlighter = HtmlSyntaxHighlighter(self.document(), dark)


# ---------------------------------------------------------------------------
# Bridge object exposed to JavaScript via QWebChannel
# ---------------------------------------------------------------------------
class WebBridge(QObject):
    """Python ↔ JavaScript bridge for the visual editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._callback = None  # function(html_str) called when visual editor changes
        self._ready_callback = None

    def set_change_callback(self, fn):
        self._callback = fn

    def set_ready_callback(self, fn):
        self._ready_callback = fn

    @pyqtSlot(str)
    def on_visual_change(self, html: str):
        """Called from JS when the visual editor content changes."""
        if self._callback:
            self._callback(html)

    @pyqtSlot()
    def on_editor_ready(self):
        """Called from JS when the editor script has fully initialized."""
        if self._ready_callback:
            self._ready_callback()


# ---------------------------------------------------------------------------
# Visual WYSIWYG pane — contentEditable web view
# ---------------------------------------------------------------------------
class VisualEditor(QWebEngineView):
    """
    Renders HTML in a contentEditable page.  The user edits visually here;
    changes are sent back to the source editor via QWebChannel.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Enable JS and local file access
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)

        # Set up the web channel bridge
        self._bridge = WebBridge(self)
        self._channel = QWebChannel(self)
        self._channel.registerObject("bridge", self._bridge)
        self.page().setWebChannel(self._channel)

        self._editor_ready = False

    @property
    def bridge(self) -> WebBridge:
        return self._bridge

    def load_html(self, html: str, base_dir: str | None):
        """Load HTML content and inject the editor script after load."""
        self._editor_ready = False
        if base_dir:
            base_url = QUrl.fromLocalFile(base_dir + "/")
        else:
            base_url = QUrl()

        # Inject the QWebChannel JS and our editor script into the HTML
        inject = self._build_inject_script()
        # Insert just before </body> or at end
        if "</body>" in html.lower():
            idx = html.lower().rfind("</body>")
            modified_html = html[:idx] + inject + html[idx:]
        elif "</html>" in html.lower():
            idx = html.lower().rfind("</html>")
            modified_html = html[:idx] + inject + html[idx:]
        else:
            modified_html = html + inject

        self.setHtml(modified_html, base_url)

    def _build_inject_script(self) -> str:
        """Build the <script> tags to inject QWebChannel + editor logic."""
        return (
            '\n<script src="qrc:///qtwebchannel/qwebchannel.js"></script>\n'
            f"<script>{EDITOR_JS}</script>\n"
        )

    def exec_command(self, command: str, value: str = ""):
        """Execute a formatting command in the visual editor."""
        escaped_val = json.dumps(value)
        self.page().runJavaScript(
            f"window.editorExecCommand({json.dumps(command)}, {escaped_val});"
        )

    def set_font_size(self, size_px: int):
        """Set font size of the current selection."""
        self.page().runJavaScript(f"window.editorSetFontSize({size_px});")

    def get_html(self, callback):
        """Retrieve the current HTML from the visual editor asynchronously."""
        self.page().runJavaScript(
            "(function(){ return document.documentElement.outerHTML; })()",
            callback,
        )


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    """Top-level window: toolbar, splitter (source editor + visual editor), status bar."""

    VIEW_SPLIT = 0
    VIEW_CODE = 1
    VIEW_VISUAL = 2

    def __init__(self):
        super().__init__()

        self._file_path: str | None = None
        self._modified = False
        self._dark = True
        self._view_mode = self.VIEW_SPLIT

        # Flags to prevent infinite sync loops between panes
        self._syncing_to_source = False
        self._syncing_to_visual = False

        self._init_ui()
        self._apply_theme()
        self._connect_signals()

        # Debounce timer: source → visual
        self._source_timer = QTimer(self)
        self._source_timer.setSingleShot(True)
        self._source_timer.setInterval(600)
        self._source_timer.timeout.connect(self._source_to_visual)

        self._update_title()

        # Center the window on screen
        self._center_on_screen()

        # Open file from command-line argument if provided
        if len(sys.argv) > 1:
            path = sys.argv[1]
            if os.path.isfile(path):
                self._open_file(path)

    def _center_on_screen(self):
        """Center the window on the primary screen."""
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            # Clamp window size to 90% of screen if needed
            w = min(self.width(), int(geom.width() * 0.9))
            h = min(self.height(), int(geom.height() * 0.9))
            self.resize(w, h)
            x = geom.x() + (geom.width() - w) // 2
            y = geom.y() + (geom.height() - h) // 2
            self.move(x, y)

    # -- UI setup -----------------------------------------------------------

    def _init_ui(self):
        self.setMinimumSize(900, 600)
        self.resize(1300, 800)

        # --- Toolbar -------------------------------------------------------
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # File operations
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

        # Formatting buttons — these act on the VISUAL editor
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

        # Font size spinner
        lbl = QLabel("  Size: ")
        toolbar.addWidget(lbl)
        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(8, 72)
        self._font_size_spin.setValue(16)
        self._font_size_spin.setSuffix("px")
        self._font_size_spin.setFixedWidth(80)
        toolbar.addWidget(self._font_size_spin)

        self._act_apply_size = QAction("Apply Size", self)
        toolbar.addAction(self._act_apply_size)

        self._act_link = QAction("Link", self)
        self._act_link.setShortcut(QKeySequence("Ctrl+K"))
        toolbar.addAction(self._act_link)

        self._act_insert_image = QAction("Insert Image", self)
        toolbar.addAction(self._act_insert_image)

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

        # --- Central splitter: source (left) + visual editor (right) -------
        self._editor = CodeEditor()
        self._visual = VisualEditor()

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._editor)
        self._splitter.addWidget(self._visual)
        self._splitter.setSizes([500, 700])
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
        # File actions
        self._act_open.triggered.connect(self._on_open)
        self._act_save.triggered.connect(self._on_save)
        self._act_save_as.triggered.connect(self._on_save_as)

        # Formatting — these go to the VISUAL editor (right pane)
        self._act_bold.triggered.connect(lambda: self._visual.exec_command("bold"))
        self._act_italic.triggered.connect(lambda: self._visual.exec_command("italic"))
        self._act_underline.triggered.connect(lambda: self._visual.exec_command("underline"))
        self._heading_combo.currentIndexChanged.connect(self._on_heading)
        self._act_apply_size.triggered.connect(self._on_apply_font_size)
        self._act_link.triggered.connect(self._on_insert_link)
        self._act_insert_image.triggered.connect(self._on_insert_image)

        self._act_prettify.triggered.connect(self._on_prettify)
        self._act_view.triggered.connect(self._toggle_view)
        self._act_theme.triggered.connect(self._toggle_theme)

        # Source editor changes → debounce → update visual pane
        self._editor.textChanged.connect(self._on_source_changed)
        self._editor.cursorPositionChanged.connect(self._update_cursor_status)

        # Visual editor changes → update source pane
        self._visual.bridge.set_change_callback(self._on_visual_changed)

    # -- Theme --------------------------------------------------------------

    def _apply_theme(self):
        if self._dark:
            qss = """
                QMainWindow, QWidget { background-color: #1e1e1e; color: #d4d4d4; }
                QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4; border: none; selection-background-color: #264f78; }
                QToolBar { background-color: #2d2d2d; border: none; spacing: 6px; padding: 4px; }
                QToolBar QToolButton { color: #d4d4d4; padding: 4px 8px; }
                QToolBar QToolButton:hover { background-color: #3e3e3e; }
                QComboBox, QSpinBox { background-color: #3c3c3c; color: #d4d4d4; border: 1px solid #555; padding: 2px 6px; }
                QComboBox QAbstractItemView { background-color: #2d2d2d; color: #d4d4d4; selection-background-color: #094771; }
                QStatusBar { background-color: #007acc; color: #ffffff; }
                QStatusBar QLabel { color: #ffffff; margin: 0 8px; }
                QSplitter::handle { background-color: #007acc; width: 3px; }
                QLabel { background: transparent; }
            """
        else:
            qss = """
                QMainWindow, QWidget { background-color: #ffffff; color: #1e1e1e; }
                QPlainTextEdit { background-color: #ffffff; color: #1e1e1e; border: none; selection-background-color: #add6ff; }
                QToolBar { background-color: #f3f3f3; border-bottom: 1px solid #ccc; spacing: 6px; padding: 4px; }
                QToolBar QToolButton { color: #1e1e1e; padding: 4px 8px; }
                QToolBar QToolButton:hover { background-color: #e0e0e0; }
                QComboBox, QSpinBox { background-color: #ffffff; color: #1e1e1e; border: 1px solid #ccc; padding: 2px 6px; }
                QComboBox QAbstractItemView { background-color: #ffffff; color: #1e1e1e; selection-background-color: #0060c0; selection-color: #fff; }
                QStatusBar { background-color: #0078d4; color: #ffffff; }
                QStatusBar QLabel { color: #ffffff; margin: 0 8px; }
                QSplitter::handle { background-color: #0078d4; width: 3px; }
                QLabel { background: transparent; }
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
        labels = {self.VIEW_SPLIT: "Split", self.VIEW_CODE: "Code", self.VIEW_VISUAL: "Visual"}
        self._act_view.setText(f"View: {labels[self._view_mode]}")
        self._editor.setVisible(self._view_mode != self.VIEW_VISUAL)
        self._visual.setVisible(self._view_mode != self.VIEW_CODE)

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
        # Load into source editor (which will trigger sync to visual)
        self._syncing_to_source = True
        self._editor.setPlainText(content)
        self._syncing_to_source = False
        # Directly load into visual editor too
        base_dir = os.path.dirname(self._file_path)
        self._visual.load_html(content, base_dir)
        self._modified = False
        self._update_title()
        self._update_status()

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
            return not self._modified
        return reply == QMessageBox.StandardButton.Discard

    def closeEvent(self, event):
        if self._check_unsaved():
            event.accept()
        else:
            event.ignore()

    # -- Sync: source editor ↔ visual editor --------------------------------

    def _on_source_changed(self):
        """Source code was edited by the user — schedule visual pane refresh."""
        if self._syncing_to_source:
            return  # ignore changes caused by syncing from visual
        self._modified = True
        self._update_title()
        self._lbl_modified.setText("*")
        self._source_timer.start()

    def _source_to_visual(self):
        """Push current source code into the visual editor."""
        if self._syncing_to_visual:
            return
        self._syncing_to_visual = True
        html = self._editor.toPlainText()
        base_dir = os.path.dirname(self._file_path) if self._file_path else None
        self._visual.load_html(html, base_dir)
        # Reset flag after a delay to let the page load
        QTimer.singleShot(800, self._clear_visual_sync_flag)

    def _clear_visual_sync_flag(self):
        self._syncing_to_visual = False

    def _on_visual_changed(self, html: str):
        """Visual editor content changed — update the source code pane."""
        if self._syncing_to_visual:
            return  # ignore changes caused by syncing from source

        # Strip our injected scripts before putting back in source
        html = self._strip_injected_scripts(html)

        self._syncing_to_source = True
        # Preserve scroll position
        scrollbar = self._editor.verticalScrollBar()
        scroll_pos = scrollbar.value()
        self._editor.setPlainText(html)
        scrollbar.setValue(scroll_pos)
        self._syncing_to_source = False

        self._modified = True
        self._update_title()
        self._lbl_modified.setText("*")

    def _strip_injected_scripts(self, html: str) -> str:
        """Remove the QWebChannel and editor JS we injected."""
        # Remove the qwebchannel.js script tag
        html = re.sub(
            r'\n?<script src="qrc:///qtwebchannel/qwebchannel\.js"></script>\n?',
            '', html
        )
        # Remove our editor JS block
        html = re.sub(
            r'\n?<script>\(function\(\)\{.*?// Notify Python that the editor JS is ready.*?}\)\(\);\s*</script>\n?',
            '', html, flags=re.DOTALL
        )
        # Also remove contenteditable attribute we added
        html = html.replace(' contenteditable="true"', '')
        # Remove inline outline styles we added for image selection
        html = re.sub(r' style="outline: 2px solid rgb\(0, 122, 204\);[^"]*"', '', html)
        return html

    # -- Formatting commands (sent to visual editor) ------------------------

    def _on_heading(self, index: int):
        if index == 0:
            return
        tag = f"h{index}"
        self._visual.exec_command("formatBlock", f"<{tag}>")
        self._heading_combo.setCurrentIndex(0)

    def _on_apply_font_size(self):
        size = self._font_size_spin.value()
        self._visual.set_font_size(size)

    def _on_insert_link(self):
        url, ok = QInputDialog.getText(self, "Insert Link", "URL:")
        if ok and url:
            self._visual.exec_command("createLink", url)

    def _on_insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert Image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.svg *.webp);;All Files (*)",
        )
        if path:
            # Convert to file:/// URL or relative path
            if self._file_path:
                try:
                    rel = os.path.relpath(path, os.path.dirname(self._file_path))
                    rel = rel.replace("\\", "/")
                    self._visual.exec_command("insertImage", rel)
                except ValueError:
                    # Different drives on Windows
                    file_url = QUrl.fromLocalFile(path).toString()
                    self._visual.exec_command("insertImage", file_url)
            else:
                file_url = QUrl.fromLocalFile(path).toString()
                self._visual.exec_command("insertImage", file_url)

    def _on_prettify(self):
        html = self._editor.toPlainText()
        try:
            soup = BeautifulSoup(html, "lxml")
            pretty = soup.prettify()
        except Exception as e:
            QMessageBox.warning(self, "Prettify Error", str(e))
            return
        self._editor.setPlainText(pretty)

    # -- Status helpers -----------------------------------------------------

    def _update_title(self):
        name = os.path.basename(self._file_path) if self._file_path else "Untitled"
        mod = " *" if self._modified else ""
        self.setWindowTitle(f"{name}{mod} — WYSIWYG HTML Editor")

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
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("WYSIWYG HTML Editor")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
