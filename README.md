# Moodle Assignment Scraper & AI Assistant

A Python-based utility to scrape university course assignments from Moodle and generate drafts using Gemini.

## Setup Instructions

### 1. Create a Python Virtual Environment
It is highly recommended to isolate your dependencies using a virtual environment (`venv`).

```bash
# Create the virtual environment named '.venv'
python3 -m venv .venv

# Activate it (on Linux/macOS)
source .venv/bin/activate
```

### 2. Install the Dependencies
Install Playwright and other required libraries listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 3. Install Playwright Web Browsers
Playwright requires browser binaries to control Chromium, Firefox, or WebKit. For this scraper, we only need Chromium (the open-source engine behind Chrome):

```bash
playwright install chromium
```

---

## How to Use the Scraper

The scraper has two steps: **Authentication** (done once visually) and **Scraping** (done headlessly in the background).

### Step 1: Log in and Save your Session
Because Moodle is password-protected, the script needs your active login cookies. Run this command:

```bash
python src/scraper.py login
```

1. A visible Chrome-like browser window will open.
2. Enter your credentials on your university's Moodle login screen (including SSO/MFA if applicable).
3. Do **not** close the browser. Once you reach the dashboard page (and the URL is no longer `login/index.php`), the script will automatically detect it.
4. The script will save your active session cookies into a local file called `state.json` and close the browser.

### Step 2: Scrape Course Info
Once you have generated `state.json`, you can run the scraper in the background without needing to log in again:

```bash
python src/scraper.py scrape
```

This runs a headless browser (silently in the background), loads `state.json`, navigates to Moodle, and prints the list of courses it finds.

---

## Educational Concepts Covered in the Script

### 1. Context Managers (`with sync_playwright() as p`)
We use `with` blocks to ensure Playwright resources are cleanly opened and closed, even if the script crashes midway.

### 2. Headless vs. Headed Browser
*   `headless=False`: Opens a visible window. Perfect for debugging or manually logging in.
*   `headless=True`: Standard for automated scrapers. Runs in the background, consuming much less memory and CPU.

### 3. Browser Contexts (`browser.new_context()`)
Think of a context as an isolated "incognito" window. This allows us to load specific cookies or local storage settings (using `storage_state`) without interfering with other browser runs.

### 4. Page Navigations and Wait Conditions (`page.goto` & `page.wait_for_url`)
*   `page.goto(url)`: Directs the page to a URL.
*   `page.wait_for_url(lambda url: ...)`: Pauses execution until the URL matches our callback rule. This is critical for catching when you have finished logging in.

### 5. Locators (`page.locator('a[href*="..."]')`)
Playwright uses **Locators** to find elements. In this script, we use CSS Attribute Selectors:
*   `a`: Look for anchor (link) elements.
*   `[href*="course/view.php?id="]`: The `*=` means "contains". It will match any link that has that string in its destination URL.
