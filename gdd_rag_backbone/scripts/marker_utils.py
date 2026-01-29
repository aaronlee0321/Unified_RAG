"""
Shared utilities for running Marker (PDF → Markdown + images).

Used by index_pdf_with_marker and convert_pdf_to_markdown.
"""

import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
logger = logging.getLogger(__name__)


def run_marker(
    pdf_path: Path,
    output_dir: Path,
    debug: bool = False,
    progress_cb: Optional[Callable[[str], None]] = None,
    heartbeat_seconds: float = 5.0,
) -> Tuple[bool, str]:
    """
    Run Marker CLI: marker_single <pdf_path> --output_format markdown --output_dir <output_dir>.
    Image extraction is enabled by default (do not pass --disable_image_extraction).
    On success, output is output_dir/<stem>/<stem>.md and output_dir/<stem>/images/.
    If debug=True, passes --debug to Marker (saves per-page layout images and extra JSON).
    """
    exe = shutil.which("marker_single")
    if not exe:
        return False, "marker_single CLI not found (pip install marker-pdf)"
    try:
        cmd = [
            exe,
            str(pdf_path),
            "--output_format",
            "markdown",
            "--output_dir",
            str(output_dir),
        ]
        if debug:
            cmd.append("--debug")
        logger.info("Running: %s", " ".join(cmd))

        # Start Marker and stream output (when it exists). Some Marker runs emit little/no newline
        # output for long stretches; in that case, emit heartbeat messages to progress_cb so the UI
        # doesn't look frozen.
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(PROJECT_ROOT),
        )

        start = time.time()
        stop_event = threading.Event()

        def heartbeat() -> None:
            if not callable(progress_cb):
                return
            # Emit periodically until process exits.
            while not stop_event.wait(timeout=heartbeat_seconds):
                elapsed = int(time.time() - start)
                progress_cb(f"Marker still running… ({elapsed}s)")

        hb_thread = None
        if callable(progress_cb) and heartbeat_seconds and heartbeat_seconds > 0:
            hb_thread = threading.Thread(target=heartbeat, daemon=True)
            hb_thread.start()

        output_lines = []
        assert p.stdout is not None
        for raw_line in iter(p.stdout.readline, ""):
            line = raw_line.rstrip()
            if not line:
                continue
            output_lines.append(line)
            logger.info("[Marker] %s", line[:2000])
            if callable(progress_cb):
                # Also forward real lines (throttling not critical; UI should handle).
                progress_cb(f"Marker: {line[:160]}")

        try:
            p.wait(timeout=900)
        except subprocess.TimeoutExpired:
            p.kill()
            return False, "Marker timed out (900s)"
        finally:
            stop_event.set()

        if p.returncode != 0:
            tail = "\n".join(output_lines[-40:])
            return False, (tail or f"exit code {p.returncode}")

        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Marker timed out (900s)"
    except Exception as e:
        return False, str(e)


def find_marker_output_dir(output_dir: Path, pdf_stem: str) -> Optional[Path]:
    """
    Marker writes to output_dir/<name>/ where <name> is derived from the PDF.
    Return the single subfolder that contains a .md file, or the one matching pdf_stem.
    """
    if not output_dir.exists():
        return None
    subs = [p for p in output_dir.iterdir() if p.is_dir()]
    for sub in subs:
        md_candidates = list(sub.glob("*.md"))
        if md_candidates:
            return sub
    stem_dir = output_dir / pdf_stem
    if stem_dir.exists() and stem_dir.is_dir():
        return stem_dir
    return None
