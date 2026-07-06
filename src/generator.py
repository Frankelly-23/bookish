import os
import sys
import json
import re
import time
import curses
import textwrap
from google import genai # generative AI
from google.genai import types

# Resolve absolute paths relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
ASSIGNMENTS_FILE = os.path.join(DATA_DIR, "assignments.json")
DRAFTS_DIR = os.path.join(DATA_DIR, "drafts")

def sanitize_filename(filename):
    """
    Cleans a string to make it safe for use as a file name.
    Replaces spaces with underscores and removes special characters.
    """
    # Keep only alphanumeric characters, spaces, hyphens, and underscores
    clean = re.sub(r'[^\w\s-]', '', filename)
    # Replace whitespace sequences with a single underscore
    clean = re.sub(r'[-\s]+', '_', clean)
    return clean.strip().lower()

def generate_assignment_draft(client, title, description, course_code, course_name, due_date, additional_info=""):
    """
    Formulates a prompt and sends the assignment details to the Gemini API.
    """
    # System instructions enforce natural student tone, formatting, and avoid lists for essays.
    system_instruction = (
        "Actúas como un estudiante universitario de término de ingeniería de software que escribe "
        "un trabajo académico de forma natural y personal. Aplica estas reglas a menos que te pongan una excepción:\n"
        "1. Usa un tono directo y ligeramente conversacional, como si explicaras el tema a un compañero de clase inteligente — no a un tribunal. Evita saludos inmaduros o informales infantiles como 'Hola profe', 'Hola profesor' o '¡Qué onda a todos!'. Mantén la seriedad e identidad de un joven estudiante universitario.\n"
        "2. Varía el largo de las oraciones deliberadamente: alterna frases cortas con otras más largas. Evita que todas las oraciones tengan una estructura similar.\n"
        "3. Empieza algunos párrafos con conectores poco formales o reflexivos (pero úsalos de forma medida, no en todos): 'Lo interesante aquí es...', 'Vale la pena notar que...', 'En la práctica, esto significa...', 'Dicho de otro modo...'.\n"
        "4. Incluye una opinión o perspectiva personal ocasional, enmarcada como tal: 'Desde mi punto de vista...', 'Me parece que...', 'Creo que esto es relevante porque...'.\n"
        "5. Evita palabras y frases de IA típicas como: 'en resumen', 'es importante destacar', 'en el ámbito de', 'cabe mencionar', 'sin lugar a dudas', 'en conclusión podemos afirmar', 'a lo largo de este trabajo', 'en conclusión'. Si las detectas, cámbialas por algo más natural.\n"
        "6. No sobreexpliques. Si algo es obvio en contexto, confía en que el lector lo entiende.\n"
        "7. Usa vocabulario apropiado para el nivel universitario, pero sin palabras rebuscadas que nadie usaría al hablar.\n"
        "8. Mantén la precisión técnica y académica del contenido — no sacrifiques exactitud por sonar humano.\n"
        "9. Evita el uso de listas (viñetas/bullet points o listas numeradas) cuando redactes explicaciones, investigaciones o ensayos. Los humanos normalmente estructuran sus explicaciones usando párrafos fluidos y conectados. Usa listas únicamente si la asignación las pide de forma explícita o para enumerar elementos técnicos muy específicos (como pasos de un algoritmo o ejemplos de código).\n"
        "10. PROFUNDIDAD Y EXTENSIÓN ACADÉMICA: Cuando se trate de tareas teóricas, investigaciones o ensayos. No te limites a resúmenes o respuestas de un solo párrafo. Desarrolla cada concepto explicando su trasfondo, la teoría en la que se apoya, comparaciones de ventajas y desventajas, ejemplos prácticos en la industria y perspectivas a futuro. El entregable final debe tener una extensión robusta equivalente a un reporte completo para (investigaciones teóricas)."
    )
    
    course_display = f"{course_code} {course_name}".strip() or "Unknown Course"
        
    prompt = (
        f"Desarrolla el entregable universitario basándote exactamente en las instrucciones de la asignación. "
        f"Para cada punto o pregunta solicitada en las instrucciones de Moodle, no te limites a una definición simple; "
        f"desarrolla explicaciones amplias de al menos 2 o 3 párrafos completos por punto, analizando sus fundamentos, "
        f"ejemplos de aplicación práctica y consideraciones técnicas. El objetivo es producir un reporte formal "
        f"Contexto del Entregable:\n"
        f"- Asignatura: {course_display}\n"
        f"- Fecha de Vencimiento: {due_date}\n\n"
        f"Título: {title}\n\n"
        f"Instrucciones de Moodle:\n{description}"
    )
    
    if additional_info:
        prompt += f"\n\nInstrucciones/Detalles Adicionales del Estudiante ( CRITICO ) la opinión del estudiante (si existe) pesa mas que todo lo demas:\n{additional_info}"
    
    # Retry logic for handling transient API errors (like 503/429)
    max_retries = 3
    base_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7, # 0.7 gives a balance between creativity and consistency
                )
            )
            return response.text
        except Exception as e:
            # We want to retry on 503 (UNAVAILABLE) or 429 (RESOURCE_EXHAUSTED / RATE_LIMIT)
            err_msg = str(e).upper()
            is_transient = "503" in err_msg or "429" in err_msg or "UNAVAILABLE" in err_msg or "RESOURCE_EXHAUSTED" in err_msg
            
            if is_transient and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # Exponential backoff: 2s, 4s, 8s...
                print(f"Warning: Model is busy/overloaded ({e}). Retrying in {delay} seconds (attempt {attempt + 1}/{max_retries})...", file=sys.stderr)
                time.sleep(delay)
            else:
                raise e


def wrap_text(text, width):
    """
    Wraps text paragraphs to fit the specified width for curses rendering.
    """
    wrapped_lines = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            wrapped_lines.append("")
        else:
            wrapped_lines.extend(textwrap.wrap(paragraph, width=width))
    return wrapped_lines

def curses_prompt_assignment(stdscr, item, index, total):
    """
    Renders a beautiful scrollable curses interface for a single assignment choice.
    """
    # Color support initialization
    try:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(2, curses.COLOR_CYAN, -1)
        curses.init_pair(3, curses.COLOR_GREEN, -1)
    except Exception:
        pass

    title = item.get("title", "Sin Título")
    description = item.get("description", "").strip()
    course_code = item.get("course_code", "")
    course_name = item.get("course_name", "")
    due_date = item.get("due_date", "Sin fecha límite")

    scroll_pos = 0
    curses.curs_set(0) # Hide cursor

    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        # Check minimal dimensions
        if height < 12 or width < 45:
            stdscr.addstr(0, 0, "Terminal demasiado pequeña.", curses.A_REVERSE)
            stdscr.addstr(1, 0, "Expanda la terminal o presione [Q] para salir.")
            stdscr.refresh()
            ch = stdscr.getch()
            if ch in [ord('q'), ord('Q')]:
                return "quit", ""
            continue

        # Draw header bar
        header_text = f" Bookish TUI | Tarea {index} de {total} "
        stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        stdscr.addstr(0, 0, header_text + " " * (width - len(header_text) - 1))
        stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

        # Draw details metadata
        stdscr.attron(curses.color_pair(2) | curses.A_BOLD)
        stdscr.addstr(2, 2, "Asignatura: ")
        stdscr.attroff(curses.color_pair(2) | curses.A_BOLD)
        stdscr.addstr(2, 14, f"{course_code} - {course_name}"[:width-16])

        stdscr.attron(curses.color_pair(2) | curses.A_BOLD)
        stdscr.addstr(3, 2, "Tarea: ")
        stdscr.attroff(curses.color_pair(2) | curses.A_BOLD)
        stdscr.addstr(3, 14, title[:width-16])

        stdscr.attron(curses.color_pair(2) | curses.A_BOLD)
        stdscr.addstr(4, 2, "Vencimiento: ")
        stdscr.attroff(curses.color_pair(2) | curses.A_BOLD)
        stdscr.addstr(4, 15, due_date[:width-17])

        stdscr.addstr(5, 2, "─" * (width - 4))
        stdscr.addstr(6, 2, "Instrucciones:", curses.A_BOLD)

        # Scrollable description box
        wrap_width = max(10, width - 6)
        wrapped_lines = wrap_text(description, wrap_width)
        
        # Max view height available for descriptions
        desc_height = height - 11
        if desc_height < 1:
            desc_height = 1

        max_scroll = max(0, len(wrapped_lines) - desc_height)
        if scroll_pos > max_scroll:
            scroll_pos = max_scroll

        # Render description lines within window bounds
        for i in range(desc_height):
            line_idx = scroll_pos + i
            if line_idx < len(wrapped_lines):
                stdscr.addstr(7 + i, 3, wrapped_lines[line_idx][:width-4])

        # Scroll indicator
        if len(wrapped_lines) > desc_height:
            indicator = f" [Líneas {scroll_pos+1}-{min(scroll_pos+desc_height, len(wrapped_lines))} de {len(wrapped_lines)}] [↑/↓ para subir/bajar] "
            stdscr.addstr(6, max(20, width - len(indicator) - 2), indicator, curses.A_DIM)

        # Draw action bar
        footer_y = height - 2
        stdscr.addstr(footer_y, 2, "─" * (width - 4))

        action_y = height - 1
        stdscr.addstr(action_y, 2, "[")
        stdscr.addstr("Y", curses.color_pair(3) | curses.A_BOLD)
        stdscr.addstr("] Generar Borrador   [")
        stdscr.addstr("N", curses.color_pair(3) | curses.A_BOLD)
        stdscr.addstr("] Omitir   [")
        stdscr.addstr("Q", curses.color_pair(3) | curses.A_BOLD)
        stdscr.addstr("] Salir")

        stdscr.refresh()
        ch = stdscr.getch()

        if ch in [curses.KEY_UP, ord('k')]:
            if scroll_pos > 0:
                scroll_pos -= 1
        elif ch in [curses.KEY_DOWN, ord('j')]:
            if scroll_pos < max_scroll:
                scroll_pos += 1
        elif ch == curses.KEY_PPAGE:
            scroll_pos = max(0, scroll_pos - desc_height)
        elif ch == curses.KEY_NPAGE:
            scroll_pos = min(max_scroll, scroll_pos + desc_height)
        elif ch in [ord('y'), ord('Y'), 10, 13]: # Y or Enter keys
            # Transition to input screen for optional notes
            curses.curs_set(1) # Show cursor
            stdscr.clear()

            stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
            stdscr.addstr(0, 0, " Bookish TUI | Detalles Adicionales " + " " * (width - 36))
            stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

            stdscr.addstr(2, 2, "Tarea: " + title[:width-10], curses.A_BOLD)
            stdscr.addstr(4, 2, "¿Desea agregar instrucciones o detalles adicionales para Gemini?")
            stdscr.addstr(5, 2, "(Presione Enter sin escribir nada para omitir)")
            stdscr.addstr(7, 2, "> ")
            stdscr.refresh()

            curses.echo()
            additional_info = ""
            try:
                user_bytes = stdscr.getstr(7, 4, max(10, width - 8))
                additional_info = user_bytes.decode('utf-8', errors='ignore').strip()
            except Exception:
                pass
            curses.noecho()
            curses.curs_set(0)

            return "yes", additional_info
        elif ch in [ord('n'), ord('N')]:
            return "no", ""
        elif ch in [ord('q'), ord('Q')]:
            return "quit", ""

def process_assignments():
    """
    Reads assignments.json, requests drafts from Gemini, and saves them to the drafts/ folder.
    """
    # Ensure the API key is set in the environment
    if not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
        print("Please run: export GEMINI_API_KEY='your_api_key_here'", file=sys.stderr)
        sys.exit(1)
        
    if not os.path.exists(ASSIGNMENTS_FILE):
        print(f"Error: Assignments file not found at '{ASSIGNMENTS_FILE}'. Please run the scraper first.", file=sys.stderr)
        sys.exit(1)
        
    try:
        with open(ASSIGNMENTS_FILE, "r", encoding="utf-8") as f:
            assignments = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}", file=sys.stderr)
        sys.exit(1)
        
    if not assignments:
        return

    os.makedirs(DRAFTS_DIR, exist_ok=True)
    
    # Filter pending assignments
    to_prompt = []
    for item in assignments:
        title = item.get("title", "Unnamed_Assignment")
        description = item.get("description", "").strip()
        if not description:
            continue
            
        safe_title = sanitize_filename(title)
        output_file = os.path.join(DRAFTS_DIR, f"{safe_title}.md")
        
        # Skip if already generated
        if os.path.exists(output_file):
            continue
            
        item["output_file"] = output_file
        to_prompt.append(item)
        
    if not to_prompt:
        return

    approved_assignments = []
    
    # Run interactive curses loop
    def run_curses_tui(stdscr):
        total = len(to_prompt)
        for idx, item in enumerate(to_prompt, 1):
            action, additional_info = curses_prompt_assignment(stdscr, item, idx, total)
            if action == "quit":
                return "quit"
            elif action == "yes":
                item["additional_info"] = additional_info
                approved_assignments.append(item)
        return "done"

    try:
        tui_status = curses.wrapper(run_curses_tui)
        if tui_status == "quit":
            print("\nOperación cancelada por el usuario.", file=sys.stderr)
            sys.exit(0)
    except KeyboardInterrupt:
        print("\nOperación cancelada por el usuario.", file=sys.stderr)
        sys.exit(0)
        
    if not approved_assignments:
        return

    # Initialize Gemini client and process approved assignments
    client = genai.Client()
    
    for item in approved_assignments:
        title = item["title"]
        description = item["description"]
        course_code = item["course_code"]
        course_name = item["course_name"]
        due_date = item["due_date"]
        student_name = item.get("student_name", "")
        student_enrrolment = item.get("student_enrrolment", "")
        output_file = item["output_file"]
        additional_info = item.get("additional_info", "")
        
        try:
            print(f"Generando borrador para '{title}'...", file=sys.stderr)
            draft_content = generate_assignment_draft(client, title, description, course_code, course_name, due_date, additional_info)
            
            # Create a formal academic presentation/cover sheet block at the top of the file
            header = (
                f"<div class=\"cover-page\">\n"
                f"  <img src=\"logo.jpeg\" alt=\"Universidad Central del Este\" class=\"cover-logo\" />\n"
                f"  <h2>Facultad de Ciencias e Ingenierías</h2>\n"
                f"  <h3>Escuela de Ingeniería de Software</h3>\n\n"
                f"  <p><strong>Asignatura:</strong> {course_code}</p>\n"
                f"  <p><strong>Asignación:</strong> {title}</p>\n"
                f"  <p><strong>Estudiante:</strong> {student_name}</p>\n"
                f"  <p><strong>Matrícula:</strong> {student_enrrolment}</p>\n"
                f"  <p><strong>Fecha Límite:</strong> {due_date}</p>\n"
                f"</div>\n\n"
            )
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(header + draft_content)
                
        except Exception as e:
            print(f"Error generating draft for '{title}': {e}", file=sys.stderr)

if __name__ == "__main__":
    process_assignments()
