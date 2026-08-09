import os
import sys
import json
import time
import curses
import subprocess
import logging

from bookish_pkg.config import (
    DRAFTS_DIR, PDFS_DIR, PRESENTATIONS_DIR, DEFAULT_OUTPUT_DIR,
    HANDOFF_DIR, CONVERTER_FORMAT_FILE, ASSIGNMENTS_FILE, PROJECT_ROOT,
    STUDENT_NAME, STUDENT_ENROLMENT,
)
from bookish_pkg.utils import sanitize_filename, build_cover_page_html
from bookish_pkg.scraper import login_and_save_session, load_session_and_scrape
from bookish_pkg.generator import curses_prompt_assignment, generate_assignment_draft
from bookish_pkg.converter import convert_md_to_pdf, render_presentation_png

log = logging.getLogger(__name__)

class BookishLogger:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.logs = []
        self.init_colors()

    def init_colors(self):
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(2, curses.COLOR_GREEN, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
            curses.init_pair(4, curses.COLOR_RED, -1)
            curses.init_pair(5, curses.COLOR_CYAN, -1)
        except Exception:
            pass

    def log(self, message, category="info"):
        timestamp = time.strftime("%H:%M:%S")
        self.logs.append((timestamp, message, category))
        log.info(f"[{category.upper()}] {message}")
        self.render()

    def render(self):
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        if height < 10 or width < 40:
            self.stdscr.addstr(0, 0, "Terminal demasiado pequeña.", curses.A_REVERSE)
            self.stdscr.refresh()
            return
        header = " Bookish TUI"
        self.stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.addstr(0, 0, header + " " * max(0, width - len(header) - 1))
        self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
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
        footer_y = height - 1
        self.stdscr.addstr(footer_y, 2, "Procesando tareas universitarias... Espere por favor.", curses.A_DIM)
        self.stdscr.refresh()

def ensure_directories():
    os.makedirs(os.path.join(PROJECT_ROOT, "data"), exist_ok=True)
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    os.makedirs(PDFS_DIR, exist_ok=True)
    os.makedirs(PRESENTATIONS_DIR, exist_ok=True)
    os.makedirs(HANDOFF_DIR, exist_ok=True)

def create_handoff_file(item):
    title = item.get("title", "Sin Título")
    course_code = item.get("course_code", "")
    due_date = item.get("due_date", "Sin fecha límite")
    description = item.get("description", "")
    student_name = item.get("student_name", STUDENT_NAME)
    student_enrrolment = item.get("student_enrrolment", STUDENT_ENROLMENT)
    additional_info = item.get("additional_info", "")
    safe_title = sanitize_filename(title)
    output_draft = os.path.join(DRAFTS_DIR, f"{safe_title}.md")
    format_rules = ""
    if os.path.exists(CONVERTER_FORMAT_FILE):
        with open(CONVERTER_FORMAT_FILE, "r", encoding="utf-8") as f:
            format_rules = f.read()
    additional_section = ""
    if additional_info:
        additional_section = f"## Contexto / Instrucciones Adicionales del Estudiante\n\n{additional_info}\n\n---\n\n"
    handoff_content = (
        f"# Contexto de Asignación — Handoff para Agente IA\n\n"
        f"> [!IMPORTANT]\n"
        f"> **DIRECTIVA DE EJECUCIÓN DEL AGENTE**:\n"
        f"> 1. NO escanees, busques ni leas otros archivos o carpetas del proyecto (como `src/`, `data/pdfs/`, `state.json`, `README.md` u otros borradores).\n"
        f"> 2. TODO el contexto de la tarea, metadatos, instrucciones de Moodle, texto de adjuntos/videos y las reglas de formato están 100% CONTENIDOS en este archivo.\n"
        f"> 3. Genera el borrador Markdown para esta tarea y guárdalo DIRECTAMENTE en: `{output_draft}`.\n\n"
        f"---\n\n"
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
    curses.endwin()
    print(f"\n{'=' * 60}")
    print(f"  Tarea: {title}")
    print(f"  Contexto guardado en: {handoff_path}")
    print(f"  Archivo de salida esperado: {output_draft}")
    print(f"  Lanzando {agent_cmd}...")
    print(f"{'=' * 60}\n")
    initial_prompt = (
        f"DIRECTIVA DE AGENTE: NO explores ni leas otros archivos o carpetas del proyecto (como src/, data/pdfs/, state.json). "
        f"Todo el contexto de la asignación, metadatos, texto de adjuntos/videos y reglas de formato están TOTALMENTE CONTENIDOS en @[{handoff_path}]. "
        f"Lee @[{handoff_path}] y escribe directamente el borrador de la asignación en {output_draft}. No analices el código del repositorio."
    )
    if agent_cmd == "opencode":
        cmd = [agent_cmd, "run", "--auto", initial_prompt]
    else:
        cmd = [agent_cmd, "--dangerously-skip-permissions", initial_prompt]
    try:
        subprocess.run(cmd, cwd=PROJECT_ROOT)
    except FileNotFoundError:
        print(f"\n  Error: '{agent_cmd}' no está instalado o no está en el PATH.")
        print(f"    Instálalo y vuelve a intentar.")
        input("\n  Presiona Enter para continuar...")
    except Exception as e:
        print(f"\n  Error lanzando {agent_cmd}: {e}")
        input("\n  Presiona Enter para continuar...")
    stdscr.refresh()

def run_bookish_pipeline(stdscr):
    logger = BookishLogger(stdscr)
    ensure_directories()
    logger.log("Iniciando pipeline de Bookish...", "step")
    
    # Step 1: Moodle Login
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
        
    # Step 3: TUI Questionnaire
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
    approved_markdown_only = []
    agent_handoffs = []
    session_generated_mds = []
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
        elif action == "markdown_only":
            item["additional_info"] = additional_info
            approved_markdown_only.append(item)
        elif action == "presentation":
            approved_presentations.append(item)
        elif action in ("agent_agy", "agent_opencode"):
            item["additional_info"] = additional_info
            agent_cmd = "agy" if action == "agent_agy" else "opencode"
            title = item.get("title", "Sin Título")
            logger.log(f"Preparando handoff para '{title}' -> {agent_cmd}...", "info")
            handoff_path, output_draft = create_handoff_file(item)
            launch_agent(stdscr, agent_cmd, handoff_path, output_draft, title)
            agent_handoffs.append(item)
            if os.path.exists(output_draft):
                session_generated_mds.append(output_draft)
                
    summary_parts = []
    if approved_drafts:
        summary_parts.append(f"{len(approved_drafts)} borradores (PDF)")
    if approved_markdown_only:
        summary_parts.append(f"{len(approved_markdown_only)} solo-Markdown")
    if approved_presentations:
        summary_parts.append(f"{len(approved_presentations)} presentaciones")
    if agent_handoffs:
        summary_parts.append(f"{len(agent_handoffs)} enviadas a agente externo")
        
    logger.log(f"Cuestionario completado: {', '.join(summary_parts) if summary_parts else 'ninguna tarea seleccionada'}.", "success")
    time.sleep(1)
    
    # Step 4: Presentations
    if approved_presentations:
        logger.log(f"[4/6] Renderizando {len(approved_presentations)} presentación(es) PNG...", "step")
        for item in approved_presentations:
            title = item.get("title", "Sin Título")
            logger.log(f"Renderizando hoja de presentación para '{title}'...", "info")
            try:
                png_out = render_presentation_png(item)
                logger.log(f"Guardada presentación PNG: {os.path.basename(png_out)}", "success")
            except Exception as e:
                logger.log(f"Error renderizando presentación para '{title}': {e}", "error")
                
    # Step 5: AI Drafts
    all_ai_items = approved_drafts + approved_markdown_only
    if all_ai_items:
        logger.log(f"[5/6] Generando {len(all_ai_items)} borrador(es) con IA...", "step")
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if not gemini_key:
            logger.log("Error: GEMINI_API_KEY no está configurada en el entorno.", "error")
            time.sleep(2)
        else:
            try:
                import google.genai as _genai
                client = _genai.Client()
                for item in all_ai_items:
                    is_pdf_target = item in approved_drafts
                    title = item.get("title", "Sin Título")
                    description = item.get("description", "")
                    course_code = item.get("course_code", "")
                    course_name = item.get("course_name", "")
                    due_date = item.get("due_date", "Sin fecha límite")
                    student_name = item.get("student_name", STUDENT_NAME)
                    student_enrrolment = item.get("student_enrrolment", STUDENT_ENROLMENT)
                    additional_info = item.get("additional_info", "")
                    output_file = item["md_file"]
                    tag = "Borrador PDF" if is_pdf_target else "Solo Markdown"
                    logger.log(f"Generando {tag} para '{title}'...", "info")
                    try:
                        draft_content = generate_assignment_draft(
                            client, title, description, course_code, course_name, due_date, additional_info
                        )
                        header = build_cover_page_html(
                            course_code=course_code,
                            title=title,
                            student_name=student_name,
                            student_enrolment=student_enrrolment,
                            due_date=due_date,
                        )
                        with open(output_file, "w", encoding="utf-8") as f:
                            f.write(header + "\n\n" + draft_content)
                        logger.log(f"Guardado borrador Markdown ({tag}): {os.path.basename(output_file)}", "success")
                        if is_pdf_target:
                            session_generated_mds.append(output_file)
                    except Exception as e:
                        logger.log(f"Error al generar borrador para '{title}': {e}", "error")
            except ImportError:
                logger.log("Error: google-genai no está instalado.", "error")
                time.sleep(2)
            except Exception as e:
                logger.log(f"Error inicializando cliente Gemini: {e}", "error")
                
    # Step 6: PDF Conversion
    if session_generated_mds:
        logger.log(f"[6/6] Convirtiendo {len(session_generated_mds)} borrador(es) de la sesión actual a PDF...", "step")
        for md_file in session_generated_mds:
            try:
                convert_md_to_pdf(target=md_file)
                logger.log(f"Guardado y abierto PDF: {os.path.basename(md_file).replace('.md', '.pdf')}", "success")
            except Exception as e:
                logger.log(f"Error convirtiendo '{os.path.basename(md_file)}': {e}", "error")
    else:
        logger.log("[6/6] No hay borradores generados en esta sesión para convertir a PDF.", "info")
        
    logger.log("=========================================", "info")
    logger.log("  Proceso completado!", "success")
    logger.log(f"  Archivos en: {DEFAULT_OUTPUT_DIR}", "info")
    logger.log("=========================================", "info")
    stdscr.addstr(stdscr.getmaxyx()[0] - 1, 2, "Presione cualquier tecla para cerrar...", curses.A_BOLD | curses.color_pair(2))
    stdscr.refresh()
    stdscr.getch()

def main():
    if len(sys.argv) > 1:
        if sys.argv[1] in ('--version', '-v'):
            try:
                from bookish_pkg import __version__
                print(f"bookish {__version__}")
            except ImportError:
                print("bookish (version unknown)")
            return
        elif sys.argv[1] in ('--help', '-h'):
            print("Usage: bookish [options]")
            print("")
            print("Academic automation engine for UCE Moodle.")
            print("")
            print("Options:")
            print("  --version, -v    Show version and exit")
            print("  --help, -h       Show this help and exit")
            print("")
            print("Environment variables:")
            print("  BOOKISH_USERNAME      Moodle username for auto-login")
            print("  BOOKISH_PASS          Moodle password for auto-login")
            print("  GEMINI_API_KEY        Google Gemini API key for draft generation")
            print("  BOOKISH_OUTPUT_DIR    Custom output directory (default: /mnt/c/Users/frank/Downloads/bookish)")
            return

    try:
        curses.wrapper(run_bookish_pipeline)
    except KeyboardInterrupt:
        print("\nEjecución cancelada por el usuario.", file=sys.stderr)
    except Exception as e:
        print(f"\nError durante la ejecución: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
