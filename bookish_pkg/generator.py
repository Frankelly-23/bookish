import os
import sys
import json
import re
import time
import curses
import textwrap
import tempfile
import subprocess
import logging

from bookish_pkg.config import ASSIGNMENTS_FILE, DRAFTS_DIR
from bookish_pkg.utils import sanitize_filename

log = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


def generate_assignment_draft(client, title, description, course_code, course_name, due_date, additional_info=""):
    from google import genai
    from google.genai import types

    system_instruction = (
        "Actúas como un estudiante universitario de ingeniería de software que escribe "
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
    
    max_retries = 3
    base_delay = 2
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                )
            )
            return response.text
        except Exception as e:
            err_msg = str(e).upper()
            is_transient = "503" in err_msg or "429" in err_msg or "UNAVAILABLE" in err_msg or "RESOURCE_EXHAUSTED" in err_msg
            if is_transient and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                log.warning(f"Warning: Model is busy/overloaded ({e}). Retrying in {delay} seconds (attempt {attempt + 1}/{max_retries})...")
                time.sleep(delay)
            else:
                raise e


def wrap_text(text, width):
    wrapped_lines = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            wrapped_lines.append("")
        else:
            wrapped_lines.extend(textwrap.wrap(paragraph, width=width))
    return wrapped_lines


def open_external_editor(stdscr, title):
    curses.endwin()
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vim"
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w+", delete=False, encoding="utf-8") as tf:
        temp_path = tf.name
    try:
        subprocess.run([editor, temp_path])
        with open(temp_path, "r", encoding="utf-8") as f:
            result = f.read().strip()
    except Exception as e:
        log.error(f"Error opening editor: {e}")
        result = ""
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    stdscr.refresh()
    return result


def format_description_for_tui(raw_description):
    pattern = r'\[INICIO ADJUNTO:\s*([^\]]+?)\s*\|\s*(\d+)\s*líneas\][\s\S]*?\[FIN ADJUNTO:[^\]]*\]'
    def _replace(match):
        filename = match.group(1).strip()
        lines = match.group(2).strip()
        return f"\n[Adjunto: {filename} ({lines} líneas extraídas) -- Texto completo incluido en borrador]\n"
    return re.sub(pattern, _replace, raw_description)


def curses_prompt_assignment(stdscr, item, index, total):
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
    curses.curs_set(0)
    
    # Precompute description format outside loop for performance
    tui_description = format_description_for_tui(description)
    prev_width = -1
    wrapped_lines = []

    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        
        if height < 12 or width < 45:
            stdscr.addstr(0, 0, "Terminal demasiado pequeña.", curses.A_REVERSE)
            stdscr.addstr(1, 0, "Expanda la terminal o presione [Q] para salir.")
            stdscr.refresh()
            ch = stdscr.getch()
            if ch in [ord('q'), ord('Q')]:
                return "quit", ""
            continue

        wrap_width = max(10, width - 6)
        
        # Only recompute wrap_text when terminal width changes
        if width != prev_width:
            wrapped_lines = wrap_text(tui_description, wrap_width)
            prev_width = width
            
        header_text = f" Bookish TUI | Tarea {index} de {total} "
        stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        stdscr.addstr(0, 0, header_text + " " * (width - len(header_text) - 1))
        stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
        
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
        
        desc_height = height - 10
        if desc_height < 1:
            desc_height = 1
            
        max_scroll = max(0, len(wrapped_lines) - desc_height)
        if scroll_pos > max_scroll:
            scroll_pos = max_scroll
            
        for i in range(desc_height):
            line_idx = scroll_pos + i
            if line_idx < len(wrapped_lines):
                stdscr.addstr(7 + i, 3, wrapped_lines[line_idx][:width-4])
                
        if len(wrapped_lines) > desc_height:
            indicator = f" [Líneas {scroll_pos+1}-{min(scroll_pos+desc_height, len(wrapped_lines))} de {len(wrapped_lines)}] [up/down para subir/bajar] "
            stdscr.addstr(6, max(20, width - len(indicator) - 2), indicator, curses.A_DIM)
            
        footer_y = height - 2
        stdscr.addstr(footer_y, 2, "─" * (width - 4))
        
        action_y = height - 1
        stdscr.addstr(action_y, 2, "[")
        stdscr.addstr("Y", curses.color_pair(3) | curses.A_BOLD)
        stdscr.addstr("] Borrador IA  [")
        stdscr.addstr("M", curses.color_pair(3) | curses.A_BOLD)
        stdscr.addstr("] Solo MD  [")
        stdscr.addstr("P", curses.color_pair(3) | curses.A_BOLD)
        stdscr.addstr("] Presentación  [")
        stdscr.addstr("A", curses.color_pair(3) | curses.A_BOLD)
        stdscr.addstr("] AGY  [")
        stdscr.addstr("O", curses.color_pair(3) | curses.A_BOLD)
        stdscr.addstr("] OpenCode  [")
        stdscr.addstr("N", curses.color_pair(3) | curses.A_BOLD)
        stdscr.addstr("] Omitir  [")
        stdscr.addstr("Q", curses.color_pair(3) | curses.A_BOLD)
        stdscr.addstr("] Salir")
        
        stdscr.refresh()
        ch = stdscr.getch()
        
        if ch in [curses.KEY_UP, ord('k')]:
            if scroll_pos > 0: scroll_pos -= 1
        elif ch in [curses.KEY_DOWN, ord('j')]:
            if scroll_pos < max_scroll: scroll_pos += 1
        elif ch == curses.KEY_PPAGE:
            scroll_pos = max(0, scroll_pos - desc_height)
        elif ch == curses.KEY_NPAGE:
            scroll_pos = min(max_scroll, scroll_pos + desc_height)
        elif ch in [ord('y'), ord('Y'), 10, 13]:
            additional_info = open_external_editor(stdscr, title)
            return "yes", additional_info
        elif ch in [ord('m'), ord('M')]:
            additional_info = open_external_editor(stdscr, title)
            return "markdown_only", additional_info
        elif ch in [ord('p'), ord('P')]:
            return "presentation", ""
        elif ch in [ord('a'), ord('A')]:
            additional_info = open_external_editor(stdscr, title)
            return "agent_agy", additional_info
        elif ch in [ord('o'), ord('O')]:
            additional_info = open_external_editor(stdscr, title)
            return "agent_opencode", additional_info
        elif ch in [ord('n'), ord('N')]:
            return "no", ""
        elif ch in [ord('q'), ord('Q')]:
            return "quit", ""


def process_assignments():
    # This function is NOT used in the new architecture -- pipeline.py handles orchestration
    # Keep it for standalone/backward compat but it should work correctly
    pass
