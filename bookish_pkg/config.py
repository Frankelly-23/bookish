"""
Centralized configuration and path constants for Bookish.

All paths, URLs, and shared settings live here so every module imports
from one place instead of recomputing them independently.
"""

import os
import logging

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# PROJECT_ROOT is the repo root (parent of bookish_pkg/)
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PACKAGE_DIR)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DRAFTS_DIR = os.path.join(DATA_DIR, "drafts")
ATTACHMENTS_DIR = os.path.join(DATA_DIR, "attachments")
HANDOFF_DIR = os.path.join(DATA_DIR, "agent_handoff")
ASSIGNMENTS_FILE = os.path.join(DATA_DIR, "assignments.json")
STATE_FILE = os.path.join(PROJECT_ROOT, "state.json")
CONVERTER_FORMAT_FILE = os.path.join(PROJECT_ROOT, "CONVERTER_FORMAT.md")

# Output directory -- configurable via BOOKISH_OUTPUT_DIR env var
_user_downloads = os.path.join(os.path.expanduser("~"), "Downloads", "bookish")
DEFAULT_OUTPUT_DIR = os.environ.get("BOOKISH_OUTPUT_DIR", _user_downloads)
PDFS_DIR = DEFAULT_OUTPUT_DIR
PRESENTATIONS_DIR = DEFAULT_OUTPUT_DIR

# ---------------------------------------------------------------------------
# Moodle URLs
# ---------------------------------------------------------------------------
BASE_URL = os.environ.get("BOOKISH_MOODLE_URL", "https://moodle.uce.edu.do")
LOGIN_URL = f"{BASE_URL}/login/index.php"
CALENDAR_URL = f"{BASE_URL}/calendar/view.php?view=month"

# ---------------------------------------------------------------------------
# Student defaults (configurable via env vars)
# ---------------------------------------------------------------------------
STUDENT_NAME = os.environ.get("BOOKISH_STUDENT_NAME", "Estudiante")
STUDENT_ENROLMENT = os.environ.get("BOOKISH_STUDENT_ENROLMENT", "2024-0000")

# ---------------------------------------------------------------------------
# Moodle overlay suppression JS (reused by login and scraper)
# ---------------------------------------------------------------------------
MOODLE_SESSION_STORAGE_JS = """() => {
    try {
        sessionStorage.setItem('qr_encuesta_visto', '1');
        sessionStorage.setItem('encuesta_visto', '1');
        sessionStorage.setItem('aviso_visto', '1');
        sessionStorage.setItem('cookie_accepted', '1');
    } catch(e) {}
}"""

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger for Bookish."""
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
    )
