import os
import sys
import json
from playwright.sync_api import sync_playwright

# Resolve absolute paths relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

STATE_FILE = os.path.join(PROJECT_ROOT, "state.json")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
ASSIGNMENTS_FILE = os.path.join(DATA_DIR, "assignments.json")
BASE_URL = "https://moodle.uce.edu.do"
LOGIN_URL = f"{BASE_URL}/login/index.php"
CALENDAR_URL = f"{BASE_URL}/calendar/view.php?view=month"

def login_and_save_session(username: str, password: str):

    """
    Handles logging in.
    If username/password are provided, logs in programmatically (headless).
    Otherwise, launches a visible browser window for manual login.
    """
     
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(LOGIN_URL)
            
            page.fill("input#username", username)
            page.fill("input#password", password)
            
            page.click("#loginbtn")
            
            try:
                # Wait 15 seconds for successful login redirect
                page.wait_for_url(lambda url: "login/index.php" not in url, timeout=15000)

            except Exception:
                error_locator = page.locator(".alert-danger, .loginerrors, #loginerrormessage")
                if error_locator.count() > 0:
                    err_text = error_locator.first.inner_text().strip()
                    print(f"Error: Login failed. Moodle says: '{err_text}'", file=sys.stderr)
                else:
                    print("Error: Login timed out. Check your credentials or network.", file=sys.stderr)
                context.close()
                browser.close()
                sys.exit(1)

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
    page.goto(assignment_url)
    
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
            
            # Navigate directly to the calendar month view
            page.goto(CALENDAR_URL)
            
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
                            "student_name": "Frankelly Cordero",
                            "student_enrrolment": "2024-3153",
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
