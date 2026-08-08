# Bookish - Academic Automation Engine

Bookish is a CLI and TUI automation workflow designed to streamline university assignment scraping, draft generation, external AI agent handoff, and academic PDF/PNG compilation.

It handles authentication with Moodle platforms, parses calendar events, extracts text from embedded assignment attachments (including scanned image PDFs via OCR), presents interactive choices via a Curses terminal interface, and outputs standard academic PDF documents and cover pages directly to your downloads directory.

---

## One-Command Installation

To install dependencies, download Playwright Chromium, and configure `bookish` to run from anywhere in your terminal:

```bash
git clone https://github.com/Frankelly-23/bookish.git
cd bookish
./install.sh
```

`install.sh` performs the following setup automatically:
1. Creates a Python virtual environment in `.venv/`.
2. Installs required Python dependencies from `requirements.txt`.
3. Downloads the Playwright Chromium browser binary.
4. Symlinks the `bookish` launcher script to `$HOME/.local/bin/bookish`.

After running `install.sh`, you can execute `bookish` from any directory in your terminal.

---

## Complete Pipeline Architecture (Stages 1 through 7)

Bookish executes a 7-stage sequential pipeline managed by `src/bookish.py`:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Stage 1: Authentication & Overlay Suppression (scraper.py)              │
├─────────────────────────────────────────────────────────────────────────┤
│ Stage 2: Calendar Scraping & Attachment OCR (scraper.py)                 │
├─────────────────────────────────────────────────────────────────────────┤
│ Stage 3: Interactive TUI Questionnaire (generator.py)                    │
├─────────────────────────────────────────────────────────────────────────┤
│ Stage 4: External Editor Context Input ($EDITOR / vim)                  │
├─────────────────────────────────────────────────────────────────────────┤
│ Stage 5: Agent Context Export & Handoff (AGY / OpenCode)                │
├─────────────────────────────────────────────────────────────────────────┤
│ Stage 6: Presentation PNG & Gemini Draft Generation (converter.py)      │
├─────────────────────────────────────────────────────────────────────────┤
│ Stage 7: Session-Scoped PDF Compilation & Auto-Open (converter.py)      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Stage 1: Authentication & Overlay Suppression
- Verifies session tokens in `state.json` or uses environment credentials (`BOOKISH_USERNAME`, `BOOKISH_PASS`).
- Pre-injects `sessionStorage` flags and evaluates DOM cleanups (`dismiss_overlays`) to automatically dismiss Moodle survey modals (`#qr-modal-aviso`), cookie consent banners, and fixed-position blocking elements.

### Stage 2: Calendar Scraping & Attachment OCR
- Navigates directly to the Moodle monthly calendar (`/calendar/view.php?view=month`).
- Extracts pending assignment URLs, titles, course codes, and deadlines.
- Identifies attached instruction files (PDFs, images), downloads them into `data/attachments/`, and extracts text using PyMuPDF (`pymupdf`).
- Performs fallback Optical Character Recognition (OCR) using `pytesseract` and `Pillow` for scanned image PDFs.
- Appends extracted text blocks to the assignment description records.

### Stage 3: Interactive TUI Questionnaire
- Opens a Curses terminal interface displaying pending assignments one by one.
- Collapses long extracted PDF attachment blocks into compact indicator tags (`[📄 Adjunto: file.pdf (N líneas extraídas)]`) to keep the scrollable description clean while preserving full text for AI processing.
- Renders a single horizontal action bar:
  - `[Y] Borrador IA`: Selects Gemini API draft generation.
  - `[P] Presentación`: Selects presentation cover sheet PNG generation only.
  - `[A] AGY`: Selects AGY agent handoff.
  - `[O] OpenCode`: Selects OpenCode agent handoff.
  - `[N] Omitir`: Skips assignment.
  - `[Q] Salir`: Exits pipeline.

### Stage 4: External Editor Context Input
- If `[Y]`, `[A]`, or `[O]` is chosen, Bookish temporarily exits Curses and opens your system `$EDITOR` (or `vim`) with a clean temporary file.
- Allows pasting or writing multi-line text, code snippets, or custom instructions without terminal buffer limits or line-truncation issues.
- Reads the saved file content upon exit (`:wq`) and restores Curses.

### Stage 5: Agent Context Export & Handoff
- For `[A]` or `[O]`, constructs a Markdown handoff file in `data/agent_handoff/` containing assignment metadata, Moodle instructions, extracted PDF text, custom student instructions, and `CONVERTER_FORMAT.md` rules.
- Launches the selected agent CLI with automated permission flags:
  - **AGY**: `agy --dangerously-skip-permissions "<prompt>"`
  - **OpenCode**: `opencode run --auto "<prompt>"`
- Suspends Curses while you interact with the agent, resuming automatically upon agent exit.

### Stage 6: Presentation PNG & Gemini Draft Generation
- For `[P]`, renders an institutional cover sheet as a PNG image (`data/presentations/`).
- For `[Y]`, invokes Gemini API with structured prompts and writes the generated Markdown file to `data/drafts/`.

### Stage 7: Session-Scoped PDF Compilation & Auto-Open
- Tracks Markdown files created or modified during the current active session.
- Compiles session Markdown files into styled academic PDFs (Letter size, 1.0-inch margins, Times New Roman body, Arial section headings, cover page, Base64 image inlining).
- Outputs PDFs directly to `/mnt/c/Users/frank/Downloads/bookish` (or system Downloads) and opens them immediately using `wslview`, `xdg-open`, or `open`.

---

## Project Structure

```
bookish/
├── install.sh                 # One-click installation and symlink script
├── bookish                    # Executable launcher script
├── CONVERTER_FORMAT.md        # Formatted rulebook for Markdown PDF generation
├── README.md                  # Project documentation
├── requirements.txt           # Python dependency manifest
├── state.json                 # Saved Moodle authentication session (git-ignored)
├── data/                      # Data storage directory (git-ignored content)
│   ├── assignments.json       # Scraped assignment cache
│   ├── attachments/           # Downloaded Moodle file attachments
│   ├── agent_handoff/         # Generated context files for external agents
│   ├── drafts/                # Generated Markdown drafts
│   └── images/                # Image assets (includes institutional logo)
└── src/
    ├── bookish.py             # Main pipeline orchestrator and TUI runner
    ├── converter.py           # PDF and presentation PNG rendering engine
    ├── generator.py           # Curses TUI questionnaire & Gemini API client
    └── scraper.py             # Moodle web scraper & attachment text extractor
```

---

## Configuration & Environment Variables

Add the following environment variables to your shell profile (`~/.bashrc` or `~/.zshrc`):

```bash
export BOOKISH_USERNAME="your_moodle_username"
export BOOKISH_PASS="your_moodle_password"
export GEMINI_API_KEY="your_gemini_api_key"
export EDITOR="vim"
```

---

## Execution Commands

### Run Full Automation Pipeline
```bash
bookish
```

### Manual Moodle Login (Session Creation)
```bash
python3 src/scraper.py login
```

### Scrape Pending Assignments Only
```bash
python3 src/scraper.py scrape
```

### Standalone PDF Conversion
Convert a specific Markdown file to PDF:
```bash
python3 src/converter.py /path/to/assignment.md /path/to/output.pdf
```
