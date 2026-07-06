import os
import sys
import glob
import re
import markdown  # pyright: ignore[reportMissingModuleSource]
from playwright.sync_api import sync_playwright

# Resolve absolute paths relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

DRAFTS_DIR = os.path.join(PROJECT_ROOT, "data", "drafts")
PDFS_DIR = os.path.join(PROJECT_ROOT, "data", "pdfs")

# HTML Template with styling for academic PDF look
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Times New Roman', Times, serif;
            font-size: 12pt;
            line-height: 1.5;
            color: #000000;
            margin: 0;
            padding: 0;
        }}

        @page {{
            size: letter;
            margin: 1.0in 1.0in 1.0in 1.0in;
        }}

        @page :first {{
            margin: 0px !important;
        }}

        /* Cover page */
        .cover-page {{
            page-break-after: always;
            break-after: page;
            text-align: center;
            padding-top: 1.7in;
            height: 10.5in;
            width: 8.5in;
            box-sizing: border-box;
            padding-left: 1.0in;
            padding-right: 1.0in;
        }}

        .cover-page img.cover-logo {{
            max-height: 1.7in;
            margin-bottom: 0.4in;
            display: inline-block;
        }}

        .cover-page h1 {{
            font-family: Arial, Helvetica, sans-serif;
            font-size: 22pt;
            font-weight: bold;
            color: #000000;
            margin: 0 0 0.1in 0;
        }}

        .cover-page h2 {{
            font-family: Arial, Helvetica, sans-serif;
            font-size: 13pt;
            font-weight: bold;
            color: #000000;
            margin: 0 0 0.05in 0;
        }}

        .cover-page h3 {{
            font-family: Arial, Helvetica, sans-serif;
            font-size: 11pt;
            font-weight: normal;
            color: #333333;
            margin: 0 0 1.2in 0;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        .cover-page p {{
            text-align: left;
            margin-left: auto;
            margin-right: auto;
            width: 4.5in;
            font-family: 'Times New Roman', Times, serif;
            font-size: 12pt;
            margin-top: 0.1in;
            margin-bottom: 0.1in;
            color: #000000;
            line-height: 1.4;
        }}

        .cover-page p strong {{
            color: #000000;
            display: inline-block;
            width: 1.4in;
            text-align: right;
            margin-right: 0.15in;
        }}

        .page-break {{
            page-break-after: always;
            break-after: page;
        }}

        /* Headings */
        h1, h2, h3, h4, h5, h6 {{
            font-family: Arial, Helvetica, sans-serif;
            color: #000000;
            font-weight: bold;
            page-break-after: avoid;
            break-after: avoid;
        }}

        h1 {{
            font-size: 16pt;
            margin-top: 0;
            margin-bottom: 0.2in;
        }}

        h2 {{
            font-size: 14pt;
            margin-top: 0.3in;
            margin-bottom: 0.1in;
        }}

        h3 {{
            font-size: 12pt;
            margin-top: 0.25in;
            margin-bottom: 0.08in;
        }}

        p {{
            margin-top: 0;
            margin-bottom: 0.15in;
            text-align: justify;
            text-justify: inter-word;
        }}

        /* Code blocks */
        pre {{
            background-color: #f5f5f5;
            border: 1px solid #cccccc;
            padding: 10px 14px;
            overflow-x: auto;
            margin: 0.15in 0;
            page-break-inside: avoid;
            break-inside: avoid;
        }}

        code {{
            font-family: 'Courier New', Courier, monospace;
            font-size: 10pt;
            color: #000000;
            padding: 1px 3px;
        }}

        pre code {{
            color: #000000;
            background-color: transparent;
            padding: 0;
            font-size: 9.5pt;
            display: block;
            line-height: 1.4;
        }}

        /* Tables */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 0.2in 0;
            page-break-inside: avoid;
            break-inside: avoid;
            font-size: 11pt;
        }}

        th, td {{
            border: 1px solid #000000;
            padding: 6px 10px;
            text-align: left;
        }}

        th {{
            font-weight: bold;
        }}

        /* Blockquotes */
        blockquote {{
            margin: 0.15in 0 0.15in 0.4in;
            padding: 0;
            border-left: none;
            color: #000000;
            font-style: italic;
        }}

        /* Lists */
        ul, ol {{
            margin-top: 0;
            margin-bottom: 0.15in;
            padding-left: 0.35in;
        }}

        li {{
            margin-bottom: 0.04in;
        }}
    </style>
</head>
<body>
    {content}
</body>
</html>
"""


def preprocess_markdown(md_content):
    """
    Cleans and preprocesses draft content.
    1. Removes any references to "Enlace Moodle" or Moodle URLs.
    2. Converts old markdown-style UCE headers to standard HTML cover-page format.
    3. Trims redundant second header separators if they exist in the body.
    """
    lines = md_content.splitlines()
    
    # Clean up Moodle links
    clean_lines = []
    for line in lines:
        if "Enlace Moodle" in line or "moodle.uce.edu.do" in line:
            continue
        clean_lines.append(line)
        
    content_no_moodle = "\n".join(clean_lines)
    
    # Remove any <div class="page-break"></div> that directly follows </div> of the cover page
    content_no_moodle = re.sub(
        r'</div>\s*<div\s+class=["\']page-break["\']>\s*</div>',
        '</div>',
        content_no_moodle,
        flags=re.IGNORECASE
    )
    
    # Replace existing text headers with the logo image for backwards compatibility
    content_no_moodle = content_no_moodle.replace(
        '<h1>UNIVERSIDAD CENTRAL DEL ESTE (UCE)</h1>',
        '<img src="logo.jpeg" alt="Universidad Central del Este" class="cover-logo" />'
    )
    
    # Check if we need to convert old markdown-style header to new HTML format
    has_html_cover = "<div class=\"cover-page\"" in content_no_moodle or "<div class='cover-page'" in content_no_moodle
    
    if not has_html_cover and content_no_moodle.strip().startswith("# UNIVERSIDAD CENTRAL DEL ESTE"):
        # Split old header from body at the first horizontal rule
        header_lines = []
        body_lines = []
        is_header = True
        
        for line in clean_lines:
            if is_header:
                if line.strip() == "---":
                    is_header = False
                    continue
                header_lines.append(line)
            else:
                body_lines.append(line)
                
        # Parse details
        details = {
            "Asignatura": "",
            "Asignación": "",
            "Estudiante": "",
            "Matrícula": "",
            "Fecha Límite": ""
        }
        
        for line in header_lines:
            line_str = line.strip()
            for key in details.keys():
                if f"**{key}:**" in line_str:
                    val = line_str.split(f"**{key}:**")[1].strip()
                    details[key] = val
                    break
                    
        # Construct cover page
        new_header = (
            f"<div class=\"cover-page\">\n"
            f"  <img src=\"logo.jpeg\" alt=\"Universidad Central del Este\" class=\"cover-logo\" />\n"
            f"  <h2>Facultad de Ciencias e Ingenierías</h2>\n"
            f"  <h3>Escuela de Ingeniería de Software</h3>\n\n"
            f"  <p><strong>Asignatura:</strong> {details['Asignatura']}</p>\n"
            f"  <p><strong>Asignación:</strong> {details['Asignación']}</p>\n"
            f"  <p><strong>Estudiante:</strong> {details['Estudiante']}</p>\n"
            f"  <p><strong>Matrícula:</strong> {details['Matrícula']}</p>\n"
            f"  <p><strong>Fecha Límite:</strong> {details['Fecha Límite']}</p>\n"
            f"</div>\n\n"
        )
        
        # Clean redundant headers in first few body lines
        clean_body = []
        for i, line in enumerate(body_lines):
            if i < 10 and ("**Asignatura:**" in line or "**Título:**" in line or "**Fecha:**" in line):
                continue
            if i < 10 and line.strip() == "---":
                continue
            clean_body.append(line)
            
        return new_header + "\n".join(clean_body)
        
    return content_no_moodle


def convert_md_to_pdf():
    """
    Finds all Markdown files in DRAFTS_DIR, converts them to HTML + CSS,
    and uses Playwright to render them as PDFs.
    """
    if not os.path.exists(DRAFTS_DIR):
        print(f"Error: Drafts directory not found at '{DRAFTS_DIR}'. Please run generator first.", file=sys.stderr)
        sys.exit(1)
        
    os.makedirs(PDFS_DIR, exist_ok=True)
    
    md_files = glob.glob(os.path.join(DRAFTS_DIR, "*.md"))
    
    if not md_files:
        print("No drafts found to convert.", file=sys.stderr)
        return

    print(f"Found {len(md_files)} drafts. Starting PDF conversion...", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        for md_path in md_files:
            file_name = os.path.basename(md_path)
            title = os.path.splitext(file_name)[0]
            pdf_path = os.path.join(PDFS_DIR, f"{title}.pdf")
            
            try:
                print(f"Converting '{file_name}' to PDF...", file=sys.stderr)
                
                with open(md_path, "r", encoding="utf-8") as f:
                    raw_content = f.read()
                
                # Preprocess content to sanitize links and standardise formatting
                md_content = preprocess_markdown(raw_content)
                
                # Write the clean markdown back to the file to keep them in sync
                if md_content != raw_content:
                    with open(md_path, "w", encoding="utf-8") as f:
                        f.write(md_content)
                
                # Convert markdown to html, enabling tables and code blocks
                html_body = markdown.markdown(md_content, extensions=['fenced_code', 'tables'])
                
                # Render inside our styled template
                full_html = HTML_TEMPLATE.format(title=title.replace("_", " ").title(), content=html_body)
                
                # Replace the logo relative reference with a base64 Data URI for inline rendering
                logo_path = os.path.join(PROJECT_ROOT, "data", "images", "Universidad_Central_del_Este.jpeg")
                if os.path.exists(logo_path):
                    import base64
                    with open(logo_path, "rb") as img_file:
                        b64_str = base64.b64encode(img_file.read()).decode('utf-8')
                    file_uri = f"data:image/jpeg;base64,{b64_str}"
                else:
                    file_uri = ""
                    print(f"Warning: Logo image not found at '{logo_path}'", file=sys.stderr)
                
                full_html = full_html.replace('src="logo.jpeg"', f'src="{file_uri}"')
                full_html = full_html.replace("src='logo.jpeg'", f"src='{file_uri}'")
                
                # Set page content
                page.set_content(full_html)
                
                # Render to PDF using Chromium's engine without header/footer overlays
                page.pdf(
                    path=pdf_path,
                    format="Letter",
                    print_background=True,
                    display_header_footer=False,
                    margin={"top": "1.0in", "bottom": "1.0in", "left": "1.0in", "right": "1.0in"}
                )
                print(f"✓ Saved PDF: {pdf_path}", file=sys.stderr)
                
            except Exception as e:
                print(f"✗ Error converting '{file_name}': {e}", file=sys.stderr)
                
        browser.close()
        print("PDF conversion completed successfully!", file=sys.stderr)

if __name__ == "__main__":
    convert_md_to_pdf()
