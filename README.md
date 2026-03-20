# WYSIWYG HTML Editor

A lightweight Dreamweaver-style HTML editor for Windows 11, built with Python and PyQt6.

## Features

- **Split-pane layout** — raw HTML source on the left, live rendered preview on the right
- **Syntax highlighting** — Pygments-powered coloring for HTML tags, attributes, strings, and comments
- **Live preview** — auto-refreshes with a 500 ms debounce as you type; resolves relative assets via `file:///` base URL
- **Formatting toolbar** — Bold, Italic, Underline, Headings (H1–H4), Insert Link
- **Prettify HTML** — one-click reformat via BeautifulSoup
- **View modes** — toggle between Split, Code-only, and Preview-only
- **Dark / Light theme** — toggle from the toolbar
- **Line numbers** and cursor position in the status bar
- **Unsaved-changes guard** — warns before closing or opening a new file

## Keyboard Shortcuts

| Shortcut         | Action        |
|------------------|---------------|
| Ctrl+O           | Open file     |
| Ctrl+S           | Save          |
| Ctrl+Shift+S     | Save As       |
| Ctrl+Z           | Undo          |
| Ctrl+Y           | Redo          |
| Ctrl+B           | Bold          |
| Ctrl+I           | Italic        |
| Ctrl+U           | Underline     |
| Ctrl+K           | Insert Link   |

## Install & Run

Requires **Python 3.11+** on Windows 11.

```bash
pip install -r requirements.txt
python main.py
```

You can also open a file directly:

```bash
python main.py path/to/file.html
```

## Dependencies

- PyQt6 + PyQt6-WebEngine (GUI and embedded Chromium preview)
- Pygments (syntax highlighting)
- beautifulsoup4 + lxml (HTML prettifier)
