#!/usr/bin/env python3
import os
import sys
import json
import glob
import time
import shutil
import curses
import textwrap
import subprocess

# Resolve absolute paths relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.scraper import login_and_save_session, load_session_and_scrape, STATE_FILE
from src.generator import curses_prompt_assignment, generate_assignment_draft, sanitize_filename, ASSIGNMENTS_FILE, DRAFTS_DIR
from src.converter import convert_md_to_pdf, render_presentation_png, PDFS_DIR, PRESENTATIONS_DIR, DEFAULT_OUTPUT_DIR
from google import genai

HANDOFF_DIR = os.path.join(PROJECT_ROOT, "data", "agent_handoff")
CONVERTER_FORMAT_FILE = os.path.join(PROJECT_ROOT, "CONVERTER_FORMAT.md")

class BookishLogger:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.logs = []
        self.init_colors()

    def init_colors(self):
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)  # Header
            curses.init_pair(2, curses.COLOR_GREEN, -1)                # Success
            curses.init_pair(3, curses.COLOR_YELLOW, -1)               # Warning/Progress
            curses.init_pair(4, curses.COLOR_RED, -1)                  # Error
            curses.init_pair(5, curses.COLOR_CYAN, -1)                 # Info
        except Exception:
            pass

    def log(self, message, category="info"):
        timestamp = time.strftime("%H:%M:%S")
        self.logs.append((timestamp, message, category))
        self.render()

    def render(self):
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()

        if height < 10 or width < 40:
            self.stdscr.addstr(0, 0, "Terminal demasiado pequeña.", curses.A_REVERSE)
            self.stdscr.refresh()
            return

        # Header Bar
        header = " Bookish TUI"
        self.stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.addstr(0, 0, header + " " * max(0, width - len(header) - 1))
        self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

        # Draw log section
        self.stdscr.addstr(2, 2, "Registro de Ejecución en Tiempo Real:", curses.A_BOLD)
        self.stdscr.addstr(3, 2, "─" * max(10, width - 4))

        max_visible_logs = max(1, height - 7)
        visible_logs = self.logs[-max_visible_logs:]

        for idx, (t, msg, cat) in enumerate(visible_logs):
            y = 4 + idx
            if y >= height - 2:
                break
            
            color_pair = curses.color_pair(5)
            prefix = "[INFO]"
            if cat == "success":
                color_pair = curses.color_pair(2) | curses.A_BOLD
                prefix = "[  OK  ]"
            elif cat == "warn":
                color_pair = curses.color_pair(3) | curses.A_BOLD
                prefix = "[ WARN ]"
            elif cat == "error":
                color_pair = curses.color_pair(4) | curses.A_BOLD
                prefix = "[ERROR ]"
            elif cat == "step":
                color_pair = curses.color_pair(1) | curses.A_BOLD
                prefix = "[PASO ]"

            self.stdscr.attron(color_pair)
            self.stdscr.addstr(y, 2, f"{t} {prefix} ")
            self.stdscr.attroff(color_pair)

            max_text_w = max(10, width - 20)
            self.stdscr.addstr(y, 18, msg[:max_text_w])

        # Footer
        footer_y = height - 1
        self.stdscr.addstr(footer_y, 2, "Procesando tareas universitarias... Espere por favor."[:max(0, width - 4)], curses.A_DIM)
        self.stdscr.refresh()

    pass

def ensure_directories():
    os.makedirs(os.path.join(PROJECT_ROOT, "data"), exist_ok=True)
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    os.makedirs(PDFS_DIR, exist_ok=True)
    os.makedirs(PRESENTATIONS_DIR, exist_ok=True)
    os.makedirs(HANDOFF_DIR, exist_ok=True)


def create_handoff_file(item):
    """
    Writes a full-context markdown file for an AI agent to pick up.
    Includes assignment metadata, Moodle instructions, additional student instructions,
    and CONVERTER_FORMAT.md rules.
    Returns the absolute path to the handoff file.
    """
    title = item.get("title", "Sin Título")
    course_code = item.get("course_code", "")
    due_date = item.get("due_date", "Sin fecha límite")
    description = item.get("description", "")
    student_name = item.get("student_name", "")
    student_enrrolment = item.get("student_enrrolment", "")
    additional_info = item.get("additional_info", "")
    safe_title = sanitize_filename(title)
    output_draft = os.path.join(DRAFTS_DIR, f"{safe_title}.md")

    # Read CONVERTER_FORMAT.md rules
    format_rules = ""
    if os.path.exists(CONVERTER_FORMAT_FILE):
        with open(CONVERTER_FORMAT_FILE, "r", encoding="utf-8") as f:
            format_rules = f.read()

    additional_section = ""
    if additional_info:
        additional_section = f"## Contexto / Instrucciones Adicionales del Estudiante\n\n{additional_info}\n\n---\n\n"

    handoff_content = (
        f"# Contexto de Asignación — Handoff para Agente IA\n\n"
        f"## Metadatos\n"
        f"- **Asignatura:** {course_code}\n"
        f"- **Tarea:** {title}\n"
        f"- **Estudiante:** {student_name}\n"
        f"- **Matrícula:** {student_enrrolment}\n"
        f"- **Fecha Límite:** {due_date}\n\n"
        f"---\n\n"
        f"## Instrucciones de Moodle\n\n"
        f"{description}\n\n"
        f"---\n\n"
        f"{additional_section}"
        f"## Instrucciones para el Agente\n\n"
        f"Genera el borrador de esta asignación en formato Markdown.\n"
        f"Guarda el resultado en: `{output_draft}`\n\n"
        f"Sigue ESTRICTAMENTE las reglas de formato que están debajo (CONVERTER_FORMAT.md). "
        f"El archivo .md será convertido a PDF por el sistema Bookish.\n\n"
        f"---\n\n"
        f"## Reglas de Formato (CONVERTER_FORMAT.md)\n\n"
        f"{format_rules}\n"
    )

    handoff_path = os.path.join(HANDOFF_DIR, f"{safe_title}.md")
    with open(handoff_path, "w", encoding="utf-8") as f:
        f.write(handoff_content)

    return handoff_path, output_draft


def launch_agent(stdscr, agent_cmd, handoff_path, output_draft, title):
    """
    Exits curses, launches an AI agent CLI as a subprocess with the handoff file
    as initial context, then resumes curses when the agent exits.
    """
    curses.endwin()

    print(f"\n{'=' * 60}")
    print(f"  📄 Tarea: {title}")
    print(f"  📁 Contexto guardado en: {handoff_path}")
    print(f"  📝 Archivo de salida esperado: {output_draft}")
    print(f"  🚀 Lanzando {agent_cmd}...")
    print(f"{'=' * 60}\n")

    initial_prompt = (
        f"Lee el archivo @[{handoff_path}] y genera el borrador de la asignación "
        f"siguiendo las instrucciones y reglas de formato que contiene. "
        f"Guarda el resultado en {output_draft}"
    )

    # Build command per agent CLI interface:
    #   agy --dangerously-skip-permissions <prompt>  → auto-approves tool calls outside project root
    #   opencode run --auto <prompt>                 → auto-approves permissions in opencode
    if agent_cmd == "opencode":
        cmd = [agent_cmd, "run", "--auto", initial_prompt]
    else:
        cmd = [agent_cmd, "--dangerously-skip-permissions", initial_prompt]

    try:
        subprocess.run(cmd, cwd=PROJECT_ROOT)
    except FileNotFoundError:
        print(f"\n  ✗ Error: '{agent_cmd}' no está instalado o no está en el PATH.")
        print(f"    Instálalo y vuelve a intentar.")
        input("\n  Presiona Enter para continuar...")
    except Exception as e:
        print(f"\n  ✗ Error lanzando {agent_cmd}: {e}")
        input("\n  Presiona Enter para continuar...")

    # Resume curses
    stdscr.refresh()

def run_bookish_pipeline(stdscr):
    logger = BookishLogger(stdscr)
    ensure_directories()

    logger.log("Iniciando pipeline de Bookish...", "step")

    # Step 1: Moodle Login Check
    username = os.environ.get("BOOKISH_USERNAME")
    password = os.environ.get("BOOKISH_PASS")

    if username and password:
        logger.log(f"[1/6] Credenciales detectadas para {username}. Iniciando sesión Moodle...", "step")
        try:
            login_and_save_session(username, password)
            logger.log("Sesión de Moodle guardada exitosamente.", "success")
        except Exception as e:
            logger.log(f"Error al iniciar sesión en Moodle: {e}", "error")
            time.sleep(2)
    else:
        logger.log("[1/6] Omitiendo login automático (BOOKISH_USERNAME no configurado).", "info")

    # Step 2: Scraping
    logger.log("[2/6] Extrayendo asignaciones pendientes de Moodle...", "step")
    try:
        load_session_and_scrape()
        logger.log("Scraping de asignaciones completado.", "success")
    except Exception as e:
        logger.log(f"Advertencia en scraping: {e}", "warn")

    if not os.path.exists(ASSIGNMENTS_FILE):
        logger.log(f"No se encontró el archivo {ASSIGNMENTS_FILE}.", "error")
        time.sleep(2)
        return

    try:
        with open(ASSIGNMENTS_FILE, "r", encoding="utf-8") as f:
            assignments = json.load(f)
    except Exception as e:
        logger.log(f"Error al leer asignaciones: {e}", "error")
        time.sleep(2)
        return

    if not assignments:
        logger.log("No hay asignaciones encontradas o todas han sido enviadas.", "success")
        time.sleep(2)
        return

    # Step 3: Interactive Questionnaire (TUI)
    logger.log("[3/6] Iniciando cuestionario interactivo...", "step")
    time.sleep(1)

    pending_items = []
    for item in assignments:
        title = item.get("title", "")
        desc = item.get("description", "").strip()
        if not desc:
            continue

        safe_title = sanitize_filename(title)
        md_file = os.path.join(DRAFTS_DIR, f"{safe_title}.md")
        png_file = os.path.join(PRESENTATIONS_DIR, f"{safe_title}.png")

        item["md_file"] = md_file
        item["png_file"] = png_file

        pending_items.append(item)

    if not pending_items:
        logger.log("Todas las asignaciones ya tienen borrador o presentación generada.", "success")
        time.sleep(2)
        return

    approved_drafts = []
    approved_presentations = []
    agent_handoffs = []  # Items sent to external agents
    session_generated_mds = []  # Track Markdown files created/updated in THIS session

    total_pending = len(pending_items)
    for idx, item in enumerate(pending_items, 1):
        action, additional_info = curses_prompt_assignment(stdscr, item, idx, total_pending)
        if action == "quit":
            logger.log("Operación cancelada por el usuario.", "warn")
            time.sleep(1)
            return
        elif action == "yes":
            item["additional_info"] = additional_info
            approved_drafts.append(item)
        elif action == "presentation":
            approved_presentations.append(item)
        elif action in ("agent_agy", "agent_opencode"):
            item["additional_info"] = additional_info
            agent_cmd = "agy" if action == "agent_agy" else "opencode"
            title = item.get("title", "Sin Título")
            logger.log(f"Preparando handoff para '{title}' → {agent_cmd}...", "info")
            handoff_path, output_draft = create_handoff_file(item)
            launch_agent(stdscr, agent_cmd, handoff_path, output_draft, title)
            agent_handoffs.append(item)
            if os.path.exists(output_draft):
                session_generated_mds.append(output_draft)

    summary_parts = []
    if approved_drafts:
        summary_parts.append(f"{len(approved_drafts)} borradores")
    if approved_presentations:
        summary_parts.append(f"{len(approved_presentations)} presentaciones")
    if agent_handoffs:
        summary_parts.append(f"{len(agent_handoffs)} enviadas a agente externo")
    logger.log(f"Cuestionario completado: {', '.join(summary_parts) if summary_parts else 'ninguna tarea seleccionada'}.", "success")
    time.sleep(1)

    # Step 4: Generate Presentations Only (P)
    if approved_presentations:
        logger.log(f"[4/6] Renderizando {len(approved_presentations)} presentación(es) PNG...", "step")
        for item in approved_presentations:
            title = item.get("title", "Sin Título")
            logger.log(f"Renderizando hoja de presentación para '{title}'...", "info")
            try:
                png_out = render_presentation_png(item)
                logger.log(f"✓ Guardada presentación PNG: {os.path.basename(png_out)}", "success")
            except Exception as e:
                logger.log(f"✗ Error renderizando presentación para '{title}': {e}", "error")

    # Step 5: Generate AI Drafts (Y)
    if approved_drafts:
        logger.log(f"[5/6] Generando {len(approved_drafts)} borrador(es) con IA...", "step")
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if not gemini_key:
            logger.log("Error: GEMINI_API_KEY no está configurada en el entorno.", "error")
            time.sleep(2)
        else:
            try:
                client = genai.Client()
                for item in approved_drafts:
                    title = item.get("title", "Sin Título")
                    description = item.get("description", "")
                    course_code = item.get("course_code", "")
                    course_name = item.get("course_name", "")
                    due_date = item.get("due_date", "Sin fecha límite")
                    student_name = item.get("student_name", "")
                    student_enrrolment = item.get("student_enrrolment", "")
                    additional_info = item.get("additional_info", "")
                    output_file = item["md_file"]

                    logger.log(f"Generando borrador IA para '{title}'...", "info")
                    try:
                        draft_content = generate_assignment_draft(
                            client, title, description, course_code, course_name, due_date, additional_info
                        )

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

                        logger.log(f"✓ Guardado borrador Markdown: {os.path.basename(output_file)}", "success")
                        session_generated_mds.append(output_file)

                    except Exception as e:
                        logger.log(f"✗ Error al generar borrador para '{title}': {e}", "error")

            except Exception as e:
                logger.log(f"Error inicializando cliente Gemini: {e}", "error")

    # Step 6: Convert ONLY Markdown Drafts generated in this session to PDF
    if session_generated_mds:
        logger.log(f"[6/6] Convirtiendo {len(session_generated_mds)} borrador(es) de la sesión actual a PDF...", "step")
        for md_file in session_generated_mds:
            try:
                convert_md_to_pdf(target=md_file)
                logger.log(f"✓ Guardado y abierto PDF: {os.path.basename(md_file).replace('.md', '.pdf')}", "success")
            except Exception as e:
                logger.log(f"✗ Error convirtiendo '{os.path.basename(md_file)}': {e}", "error")
    else:
        logger.log("[6/6] No hay borradores generados en esta sesión para convertir a PDF.", "info")

    logger.log("=========================================", "info")
    logger.log("  ¡Proceso completado con éxito!", "success")
    logger.log(f"  Archivos en: {DEFAULT_OUTPUT_DIR}", "info")
    logger.log("=========================================", "info")

    # Final Wait for exit
    stdscr.addstr(stdscr.getmaxyx()[0] - 1, 2, "Presione cualquier tecla para cerrar...", curses.A_BOLD | curses.color_pair(2))
    stdscr.refresh()
    stdscr.getch()

def _explain_curses_failure():
    reasons = []
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        reasons.append(
            "La entrada/salida no es una terminal interactiva (sin TTY). "
            "Ejecuta `bookish` desde tu terminal y no desde un IDE/tool."
        )
    if not os.environ.get("TERM"):
        reasons.append(
            "La variable TERM no está definida. Ejecuta con: TERM=xterm-256color bookish"
        )
    try:
        lines, cols = os.get_terminal_size()
        if lines < 12 or cols < 45:
            reasons.append(
                f"La ventana del terminal es demasiado pequeña ({cols}x{lines}). "
                "Expándela y vuelve a intentar."
            )
    except OSError:
        pass

    print("Esto suele ocurrir cuando:", file=sys.stderr)
    for reason in reasons:
        print(f"  - {reason}", file=sys.stderr)
    if not reasons:
        print("  - Su terminal tiene soporte limitado o inestable para la interfaz curses.", file=sys.stderr)


def main():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("\nError: Bookish requiere una terminal interactiva (TTY) para mostrar su interfaz.\n", file=sys.stderr)
        sys.exit(1)

    try:
        curses.wrapper(run_bookish_pipeline)
    except KeyboardInterrupt:
        print("\nEjecución cancelada por el usuario.", file=sys.stderr)
    except curses.error as e:
        msg = str(e).lower()
        if "nocbreak" in msg or "cbreak" in msg or "initscr" in msg or "setupterm" in msg:
            print(f"\nError al inicializar la interfaz de terminal (curses): {e}", file=sys.stderr)
            _explain_curses_failure()
        else:
            print(f"\nError durante la ejecución del TUI de Bookish: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nError durante la ejecución del TUI de Bookish: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
