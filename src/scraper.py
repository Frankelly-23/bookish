import re
import os
import sys
import json
import time
from playwright.sync_api import sync_playwright

# Resolve absolute paths relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

STATE_FILE = os.path.join(PROJECT_ROOT, "state.json")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
ASSIGNMENTS_FILE = os.path.join(DATA_DIR, "assignments.json")
ATTACHMENTS_DIR = os.path.join(DATA_DIR, "attachments")
PROFILE_FILE = os.path.join(DATA_DIR, "user_profile.json")
BASE_URL = "https://moodle.uce.edu.do"
LOGIN_URL = f"{BASE_URL}/login/index.php"
CALENDAR_URL = f"{BASE_URL}/calendar/view.php?view=month"


def extract_attachment_text(file_path):
    """
    Extracts text from PDF or image files using PyMuPDF (fitz) with OCR fallback.
    """
    if not os.path.exists(file_path):
        return ""

    ext = os.path.splitext(file_path)[1].lower()
    text_content = []

    if ext == ".pdf":
        try:
            import pymupdf  # PyMuPDF
            doc = pymupdf.open(file_path)
            for page_num, page in enumerate(doc, 1):
                page_text = page.get_text("text").strip()
                # If page text is sparse (scanned image PDF), fallback to OCR
                if len(page_text) < 30:
                    try:
                        import pytesseract
                        from PIL import Image
                        pix = page.get_pixmap(dpi=150)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        ocr_text = pytesseract.image_to_string(img, lang="spa+eng").strip()
                        if ocr_text:
                            page_text = ocr_text
                    except Exception:
                        pass
                if page_text:
                    text_content.append(f"--- [Página {page_num}] ---\n{page_text}")
            doc.close()
        except Exception as e:
            print(f"Warning: Failed to extract PDF text from '{file_path}': {e}", file=sys.stderr)
    elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(file_path)
            ocr_text = pytesseract.image_to_string(img, lang="spa+eng").strip()
            if ocr_text:
                text_content.append(ocr_text)
        except Exception:
            pass

    return "\n\n".join(text_content).strip()


def dismiss_overlays(page):
    """
    Aggressively dismisses any modals, popups, survey banners, cookie consents,
    or other overlay elements that Moodle (or its admins) might inject.
    Designed to be safe to call on any page at any time.
    """
    # 1. JavaScript nuclear option: remove known blocking overlays and set flags
    #    so they don't reappear during this session.
    page.evaluate("""() => {
        // Known modal IDs that UCE Moodle has used
        const knownModals = [
            'qr-modal-aviso',
            'modal-aviso',
            'popup-encuesta',
            'survey-modal',
            'cookie-notice',
            'cookie-banner',
        ];
        for (const id of knownModals) {
            const el = document.getElementById(id);
            if (el) el.remove();
        }

        // Set sessionStorage flags that known modals check before showing
        try {
            sessionStorage.setItem('qr_encuesta_visto', '1');
            sessionStorage.setItem('encuesta_visto', '1');
            sessionStorage.setItem('aviso_visto', '1');
            sessionStorage.setItem('cookie_accepted', '1');
        } catch(e) {}

        // Generic: remove any fixed/absolute positioned element that covers >50% of viewport
        // and isn't a core Moodle container
        const dominated = ['page-wrapper', 'page', 'topofscroll', 'maincontent'];
        document.querySelectorAll('div[style*="position:fixed"], div[style*="position: fixed"], div[style*="z-index:99"]').forEach(el => {
            if (dominated.includes(el.id)) return;
            const rect = el.getBoundingClientRect();
            const viewArea = window.innerWidth * window.innerHeight;
            const elArea = rect.width * rect.height;
            if (elArea > viewArea * 0.3) {
                el.remove();
            }
        });
    }""")

    # 2. Try clicking known dismiss buttons (safe even if they don't exist)
    dismiss_selectors = [
        'button[onclick*="cerrarAviso"]',
        'button[onclick*="cerrar"]',
        '#qr-modal-aviso button',
        '.modal .close',
        '.modal .btn-close',
        '.modal [data-dismiss="modal"]',
        '.modal [data-bs-dismiss="modal"]',
        '[aria-label="Close"]',
        '.cookie-notice button',
        '.cc-dismiss',
    ]
    for selector in dismiss_selectors:
        try:
            btn = page.locator(selector)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=1000)
                time.sleep(0.3)
        except Exception:
            pass


def safe_goto(page, url, retries=2):
    """
    Navigates to a URL, waits for DOM ready, and dismisses any overlays.
    Retries on transient network failures.
    """
    for attempt in range(retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            dismiss_overlays(page)
            return
        except Exception as e:
            if attempt < retries:
                time.sleep(2)
            else:
                raise e


def save_user_profile(profile):
    """
    Persists the logged-in user's profile (full name and identification number)
    to data/user_profile.json so it survives across scraping runs.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)


def load_user_profile():
    """
    Loads the saved user profile (student_name / student_enrrolment).
    Returns empty strings when no profile has been saved yet.
    """
    profile = {"student_name": "", "student_enrrolment": ""}
    if os.path.exists(PROFILE_FILE):
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                profile.update(stored)
        except Exception:
            pass
    return profile


def extract_identification_number(page):
    """
    Locates the user's identification number (matrícula) on a Moodle profile page.
    """
    try:
        dt_locator = page.locator("dt")
        for i in range(dt_locator.count()):
            try:
                label = dt_locator.nth(i).inner_text().strip().lower()
            except Exception:
                continue
            if (
                "identificaci" in label
                or label in ("idnumber", "id number", "matrícula", "matricula", "expediente")
            ):
                try:
                    dd = dt_locator.nth(i).locator("xpath=following-sibling::dd[1]")
                    if dd.count() > 0:
                        value = dd.inner_text().strip()
                        if value:
                            return value
                except Exception:
                    pass
    except Exception:
        pass
    return ""


def derive_matricula_from_username(username):
    """
    Derives the student's institutional ID (matrícula) from the login username.
    UCE institutional IDs follow the pattern 'DDDD-DDDD' (e.g. '2024-0001') and
    are embedded in the institutional email login (e.g. 'hs2024-0441@uce.edu.do'
    -> '2024-0441'). Returns '' when the pattern cannot be found.
    """
    if not username:
        return ""
    local_part = username.split("@")[0]
    match = re.search(r"\d{4}-\d{3,4}", local_part)
    if not match:
        return ""
    return match.group(0)


def extract_user_profile(page, username=""):
    """
    Navigates to the logged-in user's Moodle profile page and extracts their
    full name and identification number (matrícula) automatically, so no
    personal data has to be hardcoded or configured manually.
    Returns a dict with 'student_name' and 'student_enrrolment' keys.
    """
    profile = {"student_name": "", "student_enrrolment": ""}

    # Locate the profile page URL from the navbar user menu.
    profile_url = ""
    try:
        links = page.locator('a[href*="user/profile.php?id="]')
        if links.count() > 0:
            profile_url = links.first.evaluate("el => el.href")
    except Exception:
        pass

    if not profile_url:
        try:
            toggle = page.locator("#user-menu-toggle")
            if toggle.count() > 0:
                profile_url = toggle.first.evaluate(
                    "el => { const root = el.closest('li') || el; "
                    "const a = root.querySelector('a[href*=profile.php]'); "
                    "return a ? a.href : ''; }"
                )
        except Exception:
            pass

    if not profile_url:
        profile["student_enrrolment"] = derive_matricula_from_username(username)
        return profile

    try:
        safe_goto(page, profile_url)

        # Full name from the page header.
        for selector in [
            "#page-header h1",
            ".page-heading h1",
            "#region-main h1",
            "h1",
            "h2",
        ]:
            loc = page.locator(selector)
            try:
                if loc.count() > 0 and loc.first.inner_text().strip():
                    profile["student_name"] = loc.first.inner_text().strip()
                    break
            except Exception:
                continue

        profile["student_enrrolment"] = extract_identification_number(page)

    except Exception as e:
        print(f"Warning: Could not extract user profile from Moodle: {e}", file=sys.stderr)

    if not profile["student_enrrolment"]:
        profile["student_enrrolment"] = derive_matricula_from_username(username)

    return profile


def login_and_save_session(username: str, password: str):
    """
    Handles logging in to Moodle programmatically.
    Dismisses any popups/modals before interacting with the login form.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            # Pre-set sessionStorage flags before navigating so modals never render
            page.add_init_script("""() => {
                try {
                    sessionStorage.setItem('qr_encuesta_visto', '1');
                    sessionStorage.setItem('encuesta_visto', '1');
                    sessionStorage.setItem('aviso_visto', '1');
                } catch(e) {}
            }""")

            safe_goto(page, LOGIN_URL)

            # Fill credentials and submit
            page.fill("input#username", username)
            page.fill("input#password", password)
            page.click("#loginbtn")

            try:
                page.wait_for_url(lambda url: "login/index.php" not in url, timeout=15000)
            except Exception:
                # Dismiss overlays in case a post-login popup appeared
                dismiss_overlays(page)

                error_locator = page.locator(".alert-danger, .loginerrors, #loginerrormessage")
                if error_locator.count() > 0:
                    err_text = error_locator.first.inner_text().strip()
                    print(f"Error: Login failed. Moodle says: '{err_text}'", file=sys.stderr)
                else:
                    print("Error: Login timed out. Check your credentials or network.", file=sys.stderr)
                context.close()
                browser.close()
                sys.exit(1)

            # Dismiss any post-login popups/modals before saving session
            dismiss_overlays(page)

            # Extract the student's full name and identification number from
            # the user's Moodle profile so no personal data is hardcoded.
            profile = extract_user_profile(page, username)
            if profile["student_name"] or profile["student_enrrolment"]:
                save_user_profile(profile)

            context.storage_state(path=STATE_FILE)
            context.close()
            browser.close()

    except Exception as e:
        print(f"Error during login flow: {e}", file=sys.stderr)
        sys.exit(1)


def get_assignment_details(page, assignment_url, fallback_title="Crea un titulo acorde a la asignación"):
    """
    Navigates to a specific assignment URL and extracts its title, description,
    course metadata, due date, and submission status.
    """
    safe_goto(page, assignment_url)

    # 1. Extract Title
    title = ""
    for selector in ["h1", "h2"]:
        locator = page.locator(selector)
        if locator.count() > 0:
            text = locator.first.inner_text().strip()
            if text:
                title = text
                break
    if not title:
        title = fallback_title

    # 2. Extract course code from breadcrumbs (e.g., "ECO-011-1.9332" -> "ECO-011-1")
    course_code = ""
    course_link = page.locator('ol.breadcrumb li.breadcrumb-item a[href*="course/view.php?id="]')
    if course_link.count() > 0:
        raw_course = course_link.first.inner_text().strip()
        course_code = raw_course.split(".")[0].split()[0]

    # 3. Extract due and open dates
    open_date = "Unknown Open Date"
    due_date = "Unknown Due Date"

    dates_locator = page.locator(".activity-dates")
    if dates_locator.count() > 0:
        lines = dates_locator.first.inner_text().strip().split("\n")
        for line in lines:
            if "Apertura" in line:
                open_date = line.split("Apertura:")[1].strip()
            elif "Cierre" in line:
                due_date = line.split("Cierre:")[1].strip()

    # Fallback to submission status table for due date if not found in .activity-dates
    if due_date == "Unknown Due Date":
        try:
            rows = page.locator("tr").all()
            for row in rows:
                cells = row.locator("td, th").all()
                if len(cells) >= 2:
                    label = cells[0].inner_text().strip().lower()
                    if "fecha de entrega" in label or "fecha límite" in label:
                        due_date = cells[1].inner_text().strip()
                        break
        except Exception:
            pass

    # 4. Extract description/instructions text
    description = ""
    for selector in ["#intro", ".activitydescription", ".no-overflow", ".generalbox"]:
        desc_locator = page.locator(selector)
        if desc_locator.count() > 0:
            text = desc_locator.first.inner_text().strip()
            if text:
                description = text
                break

    # 4.5 Extract & Download attached files (PDFs/Images)
    try:
        os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
        file_links = page.locator('a[href*="pluginfile.php"], a[href*="introattachment"], .fileuploadsubmission a, .introattachments a').all()
        downloaded_urls = set()

        for link in file_links:
            href = link.get_attribute("href")
            if not href or href in downloaded_urls or "forcedownload=0" in href or "portfolio" in href:
                continue

            file_name = link.inner_text().strip()
            if not file_name:
                file_name = href.split("/")[-1].split("?")[0]

            ext = os.path.splitext(file_name)[1].lower()
            if ext not in [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".docx", ".txt"]:
                continue

            downloaded_urls.add(href)

            clean_filename = re.sub(r'[^\w\s.-]', '', file_name).replace(" ", "_")
            attachment_file = os.path.join(ATTACHMENTS_DIR, clean_filename)

            # Download using Playwright context request (inherits session cookies)
            res = page.context.request.get(href)
            if res.status == 200:
                with open(attachment_file, "wb") as f:
                    f.write(res.body())

                extracted = extract_attachment_text(attachment_file)
                if extracted:
                    line_count = len(extracted.splitlines())
                    attachment_block = (
                        f"\n\n[INICIO ADJUNTO: {clean_filename} | {line_count} líneas]\n"
                        f"{extracted}\n"
                        f"[FIN ADJUNTO: {clean_filename}]\n"
                    )
                    description += attachment_block
    except Exception as e:
        print(f"Warning: Error extracting attachments for assignment: {e}", file=sys.stderr)

    # 5. Check if already submitted ("Enviado para calificar")
    is_submitted = False
    submission_status_loc = page.locator(".submissionstatussubmitted")
    if submission_status_loc.count() > 0:
        status_text = submission_status_loc.first.inner_text().strip().lower()
        if "enviado para calificar" in status_text:
            is_submitted = True
    else:
        # Fallback check on all table rows/cells if class is not present
        try:
            rows = page.locator("tr").all()
            for row in rows:
                cells = row.locator("td, th").all()
                if len(cells) >= 2:
                    label = cells[0].inner_text().strip().lower()
                    value = cells[1].inner_text().strip().lower()
                    if "estado de la entrega" in label:
                        if "enviado para calificar" in value:
                            is_submitted = True
                            break
        except Exception:
            pass

    return title, description, course_code, open_date, due_date, is_submitted


def load_session_and_scrape():
    """
    Loads the saved session from state.json, navigates to the monthly calendar page,
    extracts all unique assignment links, fetches their contents, and saves them to
    a JSON file. Standard output is silent; errors are logged to stderr.
    """
    if not os.path.exists(STATE_FILE):
        print(f"Error: Session file '{STATE_FILE}' not found. Please run the login command first.", file=sys.stderr)
        sys.exit(1)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=STATE_FILE)
            page = context.new_page()

            # Pre-set sessionStorage flags so modals never appear
            page.add_init_script("""() => {
                try {
                    sessionStorage.setItem('qr_encuesta_visto', '1');
                    sessionStorage.setItem('encuesta_visto', '1');
                    sessionStorage.setItem('aviso_visto', '1');
                } catch(e) {}
            }""")

            safe_goto(page, CALENDAR_URL)

            # Verify active session
            if "login/index.php" in page.url:
                print("Error: Session has expired! Please run the login command again.", file=sys.stderr)
                context.close()
                browser.close()
                sys.exit(1)

            # Find links that go to assignments
            assignment_links = page.locator('a[href*="mod/assign/view.php?id="]')
            all_links = assignment_links.all()

            # Deduplicate links using a dictionary
            unique_assignments = {}
            for link in all_links:
                href = link.get_attribute("href")
                if href:
                    clean_href = href.split("#")[0]

                    # Try to extract the title from the specific eventname element inside the link
                    eventname_locator = link.locator(".eventname")
                    if eventname_locator.count() > 0:
                        name = eventname_locator.first.inner_text().strip()
                    else:
                        name = link.inner_text().strip()

                    if clean_href not in unique_assignments or (name and not unique_assignments[clean_href]):
                        unique_assignments[clean_href] = name

            scraped_data = []

            # Personal data comes from the user's Moodle profile, not from
            # hardcoded values.
            profile = load_user_profile()

            # If no assignments are found, write an empty list to the JSON file
            if unique_assignments:
                for url, name in unique_assignments.items():
                    try:
                        title, description, course_code, open_date, due_date, is_submitted = get_assignment_details(page, url, fallback_title=name)
                        if is_submitted:
                            # Skip already submitted assignments
                            continue

                        scraped_data.append({
                            "title": title,
                            "url": url,
                            "course_code": course_code,
                            "open_date": open_date,
                            "due_date": due_date,
                            "description": description,
                            "student_name": profile.get("student_name", ""),
                            "student_enrrolment": profile.get("student_enrrolment", ""),
                        })
                    except Exception as e:
                        print(f"Error scraping assignment {url}: {e}", file=sys.stderr)

            # Ensure the output directory exists
            os.makedirs(DATA_DIR, exist_ok=True)

            # Save the scraped assignments to a formatted JSON file
            with open(ASSIGNMENTS_FILE, "w", encoding="utf-8") as f:
                json.dump(scraped_data, f, indent=2, ensure_ascii=False)

            context.close()
            browser.close()

    except Exception as e:
        print(f"Scraping failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        if len(sys.argv) >= 4:
            cli_user = sys.argv[2]
            cli_pass = sys.argv[3]
            login_and_save_session(cli_user, cli_pass)

    elif len(sys.argv) > 1 and sys.argv[1] == "scrape":
        load_session_and_scrape()
    else:
        print("Usage:", file=sys.stderr)
        print("  python src/scraper.py login [<username> <password>]  - Log in to Moodle and save session", file=sys.stderr)
        print("  python src/scraper.py scrape                         - Scrape assignments using saved session", file=sys.stderr)
        sys.exit(1)
