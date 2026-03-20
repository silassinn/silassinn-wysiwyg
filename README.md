# WYSIWYG HTML Editor

A lightweight Dreamweaver-style HTML editor for Windows 11, built with Python and PyQt6.

## Features

- **True WYSIWYG editing** — edit visually in the right pane (like Word/Publisher), and the HTML source updates automatically on the left
- **Split-pane layout** — raw HTML source on the left, visual editor on the right
- **Two-way sync** — edit in either pane; changes propagate to the other
- **Visual formatting** — select text in the visual pane and apply Bold, Italic, Underline, Headings, Font Size, or Links from the toolbar
- **Image support** — insert images, drag to reposition, resize by dragging the corner
- **Syntax highlighting** — Pygments-powered coloring for the source pane
- **Prettify HTML** — one-click reformat via BeautifulSoup
- **View modes** — toggle between Split, Code-only, and Visual-only
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

Or use the included installer script:

```bash
python install.py
python main.py
```

You can also open a file directly:

```bash
python main.py path/to/file.html
```

## Dependencies

- PyQt6 + PyQt6-WebEngine (GUI and embedded Chromium visual editor)
- Pygments (syntax highlighting)
- beautifulsoup4 + lxml (HTML prettifier)
