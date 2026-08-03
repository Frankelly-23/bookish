#!/usr/bin/env python3
import os
import sys
import json
import glob
import time
import shutil
import curses
import textwrap

# Resolve absolute paths relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.scraper import login_and_save_session, load_session_and_scrape, STATE_FILE
from src.generator import curses_prompt_assignment, generate_assignment_draft, sanitize_filename, ASSIGNMENTS_FILE, DRAFTS_DIR
from src.converter import convert_md_to_pdf, render_presentation_png, PDFS_DIR, PRESENTATIONS_DIR
from google import genai

EXPORT_DIR = "/mnt/c/Users/frank/Downloads/Homework"
EXPORT_FALLBACK = "/mnt/c/Users/frank/Downloads"

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
        header = " Bookish TUI | Flujo de Automatización Académica "
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
        self.stdscr.addstr(footer_y, 2, "Procesando tareas universitarias... Espere por favor.", curses.A_DIM)
        self.stdscr.refresh()

def open_file_async(file_path):
    import subprocess
    try:
        if shutil.which("wslview"):
            subprocess.Popen(["wslview", file_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", file_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("open"):
            subprocess.Popen(["open", file_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def ensure_directories():
    os.makedirs(os.path.join(PROJECT_ROOT, "data"), exist_ok=True)
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    os.makedirs(PDFS_DIR, exist_ok=True)
    os.makedirs(PRESENTATIONS_DIR, exist_ok=True)

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

    logger.log(f"Cuestionario completado: {len(approved_drafts)} borradores, {len(approved_presentations)} presentaciones solo-PNG.", "success")
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
                    student_name = item.get("student_name", "Frankelly Cordero")
                    student_enrrolment = item.get("student_enrrolment", "2024-3153")
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

                    except Exception as e:
                        logger.log(f"✗ Error al generar borrador para '{title}': {e}", "error")

            except Exception as e:
                logger.log(f"Error inicializando cliente Gemini: {e}", "error")

    # Step 6: Convert Markdown Drafts to PDF
    if glob.glob(os.path.join(DRAFTS_DIR, "*.md")):
        logger.log("[6/6] Convirtiendo borradores Markdown a PDF...", "step")
        try:
            convert_md_to_pdf()
            logger.log("✓ Conversión a PDF completada.", "success")
        except Exception as e:
            logger.log(f"✗ Error convirtiendo PDFs: {e}", "error")

    # Step 7: Export & Open files
    logger.log("Abriendo y moviendo archivos generados a Descargas...", "step")
    target_dir = EXPORT_DIR if os.path.exists(os.path.dirname(EXPORT_DIR)) else EXPORT_FALLBACK
    os.makedirs(target_dir, exist_ok=True)

    moved_count = 0

    # Handle PDFs
    pdf_files = glob.glob(os.path.join(PDFS_DIR, "*.pdf"))
    if pdf_files:
        for pdf_file in pdf_files:
            open_file_async(pdf_file)
            dest_file = os.path.join(target_dir, os.path.basename(pdf_file))
            try:
                shutil.move(pdf_file, dest_file)
                moved_count += 1
            except Exception as e:
                logger.log(f"Error moviendo {os.path.basename(pdf_file)}: {e}", "error")
    else:
        logger.log("No hay PDFs para mover.", "info")

    # Handle Presentations PNGs
    png_files = glob.glob(os.path.join(PRESENTATIONS_DIR, "*.png"))
    if png_files:
        for png_file in png_files:
            open_file_async(png_file)
            dest_file = os.path.join(target_dir, os.path.basename(png_file))
            try:
                shutil.move(png_file, dest_file)
                moved_count += 1
            except Exception as e:
                logger.log(f"Error moviendo {os.path.basename(png_file)}: {e}", "error")
    else:
        logger.log("No hay presentaciones PNG para mover.", "info")

    logger.log(f"✓ Movidos {moved_count} archivo(s) a '{target_dir}'.", "success")
    logger.log("=========================================", "info")
    logger.log("  ¡Proceso completado con éxito!", "success")
    logger.log("=========================================", "info")

    # Final Wait for exit
    stdscr.addstr(stdscr.getmaxyx()[0] - 1, 2, "Presione cualquier tecla para cerrar...", curses.A_BOLD | curses.color_pair(2))
    stdscr.refresh()
    stdscr.getch()

def main():
    try:
        curses.wrapper(run_bookish_pipeline)
    except KeyboardInterrupt:
        print("\nEjecución cancelada por el usuario.", file=sys.stderr)
    except Exception as e:
        print(f"\nError durante la ejecución del TUI de Bookish: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
