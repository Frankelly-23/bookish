# Bookish - Academic Automation Engine

Bookish is a CLI/TUI automation pipeline for university assignment management. It handles Moodle authentication, scrapes pending assignments from the calendar, extracts text from attachments (PDF/image OCR) and YouTube transcripts, generates Markdown drafts via Gemini AI or external agents, and compiles them into formatted academic PDFs with cover pages.

---

## Installation

```bash
git clone https://github.com/Frankelly-23/bookish.git
cd bookish
./install.sh
```

`install.sh` performs the following:
1. Creates a Python virtual environment in `.venv/`.
2. Installs the project as an editable package via `pip install -e .` (all deps defined in `pyproject.toml`).
3. Downloads the Playwright Chromium browser binary.
4. Checks for `tesseract` OCR binary (required for PDF/image text extraction).
5. Symlinks the `bookish` wrapper to `$HOME/.local/bin/bookish`.

After installation, run `bookish` from anywhere in your terminal.

### System Dependencies

- Python 3.10+
- Tesseract OCR (optional, for PDF/image text extraction): `sudo apt install tesseract-ocr tesseract-ocr-spa`

---

## Usage

```bash
# Run the full pipeline
bookish

# Show version
bookish --version

# Show help
bookish --help
```

### Environment Variables

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key for AI draft generation |
| `BOOKISH_USERNAME` | Moodle username for automatic login |
| `BOOKISH_PASS` | Moodle password for automatic login |
| `BOOKISH_OUTPUT_DIR` | Custom output directory (default: `/mnt/c/Users/frank/Downloads/bookish`) |

---

## Pipeline Architecture (7 Stages)

Bookish executes a sequential pipeline managed by `bookish_pkg/pipeline.py`:

```
Stage 1  Authentication & Overlay Suppression      (scraper.py)
Stage 2  Calendar Scraping & Attachment OCR         (scraper.py)
Stage 3  Interactive TUI Questionnaire              (generator.py)
Stage 4  External Editor Context Input              ($EDITOR / vim)
Stage 5  Agent Handoff / Gemini Draft Generation    (pipeline.py / generator.py)
Stage 6  Presentation PNG Rendering                 (converter.py)
Stage 7  Session-Scoped PDF Compilation & Auto-Open (converter.py)
```

### Stage 1 -- Authentication & Overlay Suppression

When `BOOKISH_USERNAME` and `BOOKISH_PASS` are set, launches a visible Chromium browser via Playwright, fills the Moodle login form, handles post-login modal popups and survey overlays (UCE-specific elements like `#qr-modal-aviso`, cookie banners, and viewport-blocking fixed elements), then saves the authenticated session cookies to `state.json` for reuse.

### Stage 2 -- Calendar Scraping & Attachment OCR

Loads the saved session, navigates to the Moodle monthly calendar, and extracts all unique assignment links (`mod/assign/view.php`). For each unsubmitted assignment, extracts:

- Title, course code (from breadcrumbs), open/due dates
- Assignment instructions/description from the page body
- File attachments (PDFs, images) downloaded via authenticated session cookies, with text extracted using PyMuPDF; falls back to Tesseract OCR for scanned/image-based PDFs
- YouTube video transcripts via `youtube-transcript-api` (Spanish/English auto-generated captions)

Results are serialized to `data/assignments.json`.

### Stage 3 -- Interactive TUI Questionnaire

Presents each pending assignment in a scrollable Curses interface showing course code, title, due date, and instructions. Long attachment blocks are collapsed into compact summary tags. The user selects one action per assignment:

| Key | Action |
|---|---|
| `Y` / Enter | Generate AI draft (with PDF conversion) |
| `M` | Generate AI draft (Markdown only, no PDF) |
| `P` | Render presentation cover sheet (PNG) |
| `A` | Handoff to AGY agent |
| `O` | Handoff to OpenCode agent |
| `N` | Skip |
| `Q` | Quit |

### Stage 4 -- External Editor Context Input

For actions `Y`, `M`, `A`, `O`, the TUI exits curses and opens `$EDITOR` (or `vim`) with a blank temporary `.md` file. The student writes any additional context, instructions, or corrections. This text is appended to the AI prompt or agent handoff file as high-priority student instructions.

### Stage 5 -- Agent Handoff / Gemini Draft Generation

**AI Draft Generation (Y/M):** Sends the assignment metadata, Moodle instructions, extracted attachment text, and student context to Gemini (`gemini-2.5-flash`) with system instructions that enforce academic tone, paragraph flow, and anti-AI-detection writing patterns. Includes exponential backoff retry for transient API errors.

**Agent Handoff (A/O):** Generates a self-contained Markdown context file in `data/agent_handoff/` containing all assignment metadata, Moodle instructions, extracted text, student context, and `CONVERTER_FORMAT.md` rules. Launches `agy` or `opencode` with strict directives to read ONLY the handoff file and write the draft directly to `data/drafts/`.

### Stage 6 -- Presentation PNG Rendering

For assignments marked `P`, renders a standard UCE cover page (logo, faculty, student details) as a PNG screenshot using Playwright headless Chromium at 816x1056 viewport.

### Stage 7 -- Session-Scoped PDF Compilation & Auto-Open

Converts only Markdown files generated during the current session to PDF. Each `.md` file is preprocessed (Moodle link cleanup, legacy header normalization), converted to HTML via `markdown` with fenced code and table extensions, styled with the academic CSS template (Times New Roman, Letter format, 1-inch margins), images are inlined as Base64 data URIs, and rendered to PDF via Playwright Chromium. Each PDF is automatically opened with the system viewer.

---

## Project Structure

```
bookish/
  bookish_pkg/           Python package (all source code)
    __init__.py           Package marker + version
    config.py             Centralized paths, URLs, constants, logging setup
    utils.py              Shared utilities (sanitize_filename, cover page HTML, image inlining)
    scraper.py            Moodle authentication, assignment scraping, OCR, YouTube transcripts
    generator.py          Curses TUI questionnaire, Gemini API draft generation
    converter.py          Markdown preprocessing, PDF/PNG rendering via Playwright
    pipeline.py           Main 7-stage orchestrator, BookishLogger, agent handoff, CLI entry
  data/                   Runtime data (gitignored)
    drafts/               Generated Markdown drafts
    attachments/           Downloaded assignment files
    agent_handoff/         Context files for external AI agents
    images/               Logo and image assets
  CONVERTER_FORMAT.md     Formatting specification for Markdown-to-PDF conversion
  pyproject.toml          Project metadata, dependencies, entry points
  install.sh              One-command setup script
  bookish                 Shell wrapper for global execution
```

---

## Standalone Module Usage

### Converter (direct Markdown to PDF)

```bash
# Convert all drafts in data/drafts/
.venv/bin/python3 -m bookish_pkg.converter

# Convert a specific file
.venv/bin/python3 -m bookish_pkg.converter /path/to/file.md

# Convert a specific file to a specific output
.venv/bin/python3 -m bookish_pkg.converter /path/to/file.md /path/to/output.pdf
```
