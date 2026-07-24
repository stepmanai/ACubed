from __future__ import annotations

# infrastructure/logging.py
import logging
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_CONFIGURED = False
_CHAFA_HINT_SHOWN = False
_CHAFA_FAILURE_SHOWN = False

try:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.progress import (
        BarColumn,
        Progress,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
    )
except ImportError:  # pragma: no cover - exercised in lean runtimes.
    Console = None
    RichHandler = None
    Progress = None
    TextColumn = None
    BarColumn = None
    TaskProgressColumn = None
    TimeElapsedColumn = None


class _LiveProgressDisplay:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rendered = False
        self._status = ""
        self._progress = 0.0
        self._phase_start = 0.0
        self._phase_end = 1.0
        self._stream = sys.stderr
        self._console = Console(stderr=True) if Console is not None else None
        self._rich_progress = None
        self._task_id = None

    def status(self, status: str, progress: float) -> None:
        with self._lock:
            self._status = status
            self._progress = max(self._progress, min(max(progress, 0.0), 1.0))
            self._phase_start = self._progress
            self._phase_end = self._progress
            self._render()

    def message(self, status: str) -> None:
        with self._lock:
            self._status = status
            self._render()

    def phase(self, status: str, start: float, end: float) -> None:
        with self._lock:
            self._status = status
            self._phase_start = max(
                self._progress,
                min(max(start, 0.0), 1.0),
            )
            self._phase_end = min(max(end, self._phase_start), 1.0)
            self._progress = self._phase_start
            self._render()

    def step(self, status: str, step_progress: float) -> None:
        with self._lock:
            step_progress = min(max(step_progress, 0.0), 1.0)
            self._status = status
            span = self._phase_end - self._phase_start
            if span <= 0:
                next_progress = step_progress
            else:
                next_progress = self._phase_start + (span * step_progress)
            self._progress = max(self._progress, min(next_progress, 1.0))
            self._render()

    def close(self) -> None:
        with self._lock:
            if self._rich_progress is not None:
                self._rich_progress.stop()
                self._rich_progress = None
                self._task_id = None
                self._rendered = False
                return
            if not self._rendered:
                return
            if self._stream.isatty():
                self._stream.write("\r\x1b[2K\x1b[1A\r\x1b[2K")
            self._stream.flush()
            self._rendered = False

    def finish(self, status: str = "Ingestion complete") -> None:
        with self._lock:
            self._status = status
            self._progress = 1.0
            self._phase_start = 1.0
            self._phase_end = 1.0
            self._render()
            if self._rich_progress is not None:
                self._rich_progress.stop()
                self._rich_progress = None
                self._task_id = None
                self._rendered = False
                return
            if self._rendered and self._stream.isatty():
                self._stream.write("\n")
                self._stream.flush()
            self._rendered = False

    def write(self, message: str, stream=None) -> None:
        with self._lock:
            if self._rich_progress is not None and self._console is not None:
                self._console.print(message, markup=False, highlight=False)
                return

            stream = stream or self._stream
            was_rendered = self._rendered
            if was_rendered:
                self.close()
            stream.write(f"{message}\n")
            stream.flush()
            if was_rendered:
                self._render()

    def _render(self) -> None:
        if self._console is not None and Progress is not None:
            self._render_rich()
            return

        if not self._stream.isatty():
            return

        columns = shutil.get_terminal_size((100, 20)).columns
        percent = int(round(self._progress * 100))
        bar_width = max(min(columns - 12, 44), 20)
        filled = int(bar_width * self._progress)
        bar = "#" * filled + "-" * (bar_width - filled)
        status = self._status[: max(columns - 1, 1)]

        if self._rendered:
            self._stream.write("\r\x1b[2K\x1b[1A\r\x1b[2K")

        self._stream.write(f"{status}\n[{bar}] {percent:3d}%")
        self._stream.flush()
        self._rendered = True

    def _render_rich(self) -> None:
        if self._console is None or Progress is None:
            return

        if self._rich_progress is None:
            self._rich_progress = Progress(
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(bar_width=None),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=self._console,
                transient=False,
            )
            self._rich_progress.start()
            self._task_id = self._rich_progress.add_task(
                self._status or "Starting ingestion",
                total=100,
                completed=0,
            )

        assert self._task_id is not None
        self._rich_progress.update(
            self._task_id,
            description=self._status or "Working",
            completed=min(max(self._progress_value(), 0.0), 100.0),
        )
        self._rendered = True

    def _progress_value(self) -> float:
        return self._progress * 100.0


_LIVE_PROGRESS = _LiveProgressDisplay()


class _TqdmLoggingHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            _LIVE_PROGRESS.write(message, self.stream)
            self.flush()
        except Exception:
            self.handleError(record)


def get_logger() -> logging.Logger:
    global _CONFIGURED

    if not _CONFIGURED:
        if RichHandler is not None:
            handler = RichHandler(
                console=_LIVE_PROGRESS._console,
                markup=False,
                rich_tracebacks=True,
                show_path=False,
                show_time=False,
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
        else:
            handler = _TqdmLoggingHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter("%(levelname)s %(message)s")
            )

        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(logging.WARNING)

        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

        _CONFIGURED = True

    return logging.getLogger("acubed")


def console_info(message: str, *args: Any) -> None:
    if args:
        message = message % args
    _LIVE_PROGRESS.write(message)


def console_svg_logo(
    svg_path: str | Path,
    *,
    title: str | None = None,
    width: int = 56,
    height: int | None = None,
    padding: int = 1,
    cell_aspect_ratio: float = 2.0,
) -> None:
    svg_path = Path(svg_path)
    terminal_width = shutil.get_terminal_size((100, 20)).columns
    art_width = max(24, min(width, terminal_width - 8))

    if not svg_path.exists():
        return

    if shutil.which("chafa") is None:
        _write_chafa_install_hint(terminal_width, padding=padding)
        return

    chafa_output = _chafa_logo_art(
        svg_path,
        width=art_width,
        height=height,
        cell_aspect_ratio=cell_aspect_ratio,
    )
    if not chafa_output:
        return

    lines = []
    lines.extend("" for _ in range(max(padding, 0)))
    if title:
        lines.append(_center_terminal_line(title, terminal_width))
        lines.append("")
    lines.append(
        _center_terminal_block(chafa_output, terminal_width, ansi=True)
    )
    lines.extend("" for _ in range(max(padding, 0)))
    _write_terminal_graphics("\n".join(lines))


def _write_chafa_install_hint(terminal_width: int, *, padding: int) -> None:
    global _CHAFA_HINT_SHOWN

    if _CHAFA_HINT_SHOWN:
        return

    _CHAFA_HINT_SHOWN = True
    lines = []
    lines.extend("" for _ in range(max(padding, 0)))
    lines.append(
        _center_terminal_line(
            "Install chafa for logo rendering: sudo apt install chafa",
            terminal_width,
        )
    )
    lines.extend("" for _ in range(max(padding, 0)))
    _LIVE_PROGRESS.write("\n".join(lines))


def _chafa_logo_art(
    path: Path,
    *,
    width: int,
    height: int | None,
    cell_aspect_ratio: float,
) -> str:
    chafa = shutil.which("chafa")
    if not chafa or not path.exists():
        return ""

    if height is None:
        view_box = _svg_file_view_box(path)
        if view_box is None:
            height = max(4, round(width / cell_aspect_ratio))
        else:
            _min_x, _min_y, box_width, box_height = view_box
            height = max(
                4,
                round(width * (box_height / box_width) / cell_aspect_ratio),
            )

    input_path = path
    temp_png = _rasterize_svg_logo(path, width=width, height=height)
    if temp_png is not None:
        input_path = temp_png

    commands = [
        [
            chafa,
            "-f",
            "symbols",
            "-s",
            f"{width}x{height}",
            "--symbols",
            "block+space",
            "-c",
            _chafa_color_mode(),
            "--color-space",
            "rgb",
            "--dither",
            "diffusion",
            "-w",
            "9",
            str(input_path),
        ],
        [
            chafa,
            "-f",
            "symbols",
            "-s",
            f"{width}x{height}",
            "--symbols",
            "block+space",
            "-c",
            "16",
            str(input_path),
        ],
        [
            chafa,
            "-f",
            "symbols",
            "-s",
            f"{width}x{height}",
            "--symbols",
            "block+space",
            str(input_path),
        ],
        [
            chafa,
            "-s",
            f"{width}x{height}",
            str(input_path),
        ],
        [
            chafa,
            str(input_path),
        ],
    ]

    try:
        completed = subprocess.CompletedProcess(
            commands[-1],
            1,
            "",
            "chafa did not run",
        )
        for command in commands:
            completed = _run_chafa_command(command)
            if completed.returncode == 0 and completed.stdout:
                break

        if completed.returncode != 0:
            _write_chafa_failure_hint(
                _chafa_failure_reason(completed.stderr, path)
            )
            return ""

        if not completed.stdout:
            _write_chafa_failure_hint("chafa produced no terminal output")
            return ""

        return completed.stdout
    finally:
        if temp_png is not None:
            try:
                temp_png.unlink()
            except OSError:
                pass


def _write_terminal_graphics(output: str) -> None:
    _LIVE_PROGRESS.close()
    stream = getattr(sys, "stderr", None) or sys.stdout
    stream.write(f"{output.rstrip()}\n")
    stream.flush()


def _rasterize_svg_logo(path: Path, *, width: int, height: int) -> Path | None:
    if path.suffix.casefold() != ".svg":
        return None

    render_width = max(width * 12, 128)
    render_height = max(height * 24, 128)
    source = _terminal_svg_source(path)
    output = Path(
        tempfile.NamedTemporaryFile(
            prefix="acubed-logo-",
            suffix=".png",
            delete=False,
        ).name
    )

    commands = _svg_rasterizer_commands(
        source,
        output,
        width=render_width,
        height=render_height,
    )
    try:
        for command in commands:
            completed = _run_plain_command(command)
            if (
                completed.returncode == 0
                and output.exists()
                and output.stat().st_size
            ):
                return output
    finally:
        if source != path:
            try:
                source.unlink()
            except OSError:
                pass

    try:
        output.unlink()
    except OSError:
        pass
    return None


def _terminal_svg_source(path: Path) -> Path:
    try:
        svg = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return path

    svg = re.sub(r"fill\s*:\s*#(?:000|000000)\b", "fill:#ffffff", svg)
    svg = re.sub(r'fill=(["\'])#(?:000|000000)\1', r"fill=\1#ffffff\1", svg)
    svg = re.sub(r"rgb\(\s*0\s*,\s*0\s*,\s*0\s*\)", "rgb(255,255,255)", svg)
    svg = re.sub(r"(?i)\bblack\b", "#ffffff", svg)

    match = re.search(r"<svg\b[^>]*>", svg)
    if match is None:
        return path

    tag = match.group(0)
    if "style=" in tag:
        tag = re.sub(
            r'style=(["\'])(.*?)\1',
            lambda found: (
                f"style={found.group(1)}"
                f"color:#ffffff;fill:#ffffff;{found.group(2)}"
                f"{found.group(1)}"
            ),
            tag,
            count=1,
        )
    else:
        tag = tag[:-1] + ' style="color:#ffffff;fill:#ffffff">'
    svg = svg[: match.start()] + tag + svg[match.end() :]

    output = Path(
        tempfile.NamedTemporaryFile(
            prefix="acubed-logo-",
            suffix=".svg",
            delete=False,
        ).name
    )
    try:
        output.write_text(svg, encoding="utf-8")
    except OSError:
        try:
            output.unlink()
        except OSError:
            pass
        return path
    return output


def _svg_rasterizer_commands(
    source: Path,
    output: Path,
    *,
    width: int,
    height: int,
) -> list[list[str]]:
    commands = []
    rsvg_convert = shutil.which("rsvg-convert")
    if rsvg_convert:
        commands.append(
            [
                rsvg_convert,
                "-w",
                str(width),
                "-h",
                str(height),
                "-o",
                str(output),
                str(source),
            ]
        )

    inkscape = shutil.which("inkscape")
    if inkscape:
        commands.append(
            [
                inkscape,
                str(source),
                "--export-type=png",
                f"--export-filename={output}",
                f"--export-width={width}",
                f"--export-height={height}",
            ]
        )

    magick = shutil.which("magick")
    if magick:
        commands.append(
            [
                magick,
                "-background",
                "none",
                str(source),
                "-resize",
                f"{width}x{height}",
                str(output),
            ]
        )

    convert = shutil.which("convert")
    if convert:
        commands.append(
            [
                convert,
                "-background",
                "none",
                str(source),
                "-resize",
                f"{width}x{height}",
                str(output),
            ]
        )

    return commands


def _run_plain_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))


def _chafa_failure_reason(stderr: str | None, source: Path) -> str:
    reason = (stderr or "unknown Chafa error").strip()
    if source.suffix.casefold() == ".svg" and "Error loading" in reason:
        return (
            "Chafa could not load SVG; install SVG rasterizer: "
            "sudo apt install librsvg2-bin"
        )
    return reason


def _run_chafa_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))

    if completed.returncode == 0 and completed.stdout:
        return completed
    if os.name == "nt":
        return completed

    terminal_completed = _run_chafa_command_in_pty(command)
    if terminal_completed.stdout or terminal_completed.returncode != 0:
        return terminal_completed
    return completed


def _run_chafa_command_in_pty(
    command: list[str],
) -> subprocess.CompletedProcess[str]:
    try:
        import pty
    except ImportError:
        return subprocess.CompletedProcess(
            command, 1, "", "pty is unavailable"
        )

    master_fd: int | None = None
    slave_fd: int | None = None
    process = None
    chunks: list[bytes] = []

    try:
        master_fd, slave_fd = pty.openpty()
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLORTERM", "truecolor")
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=slave_fd,
            stderr=subprocess.PIPE,
            env=env,
            close_fds=True,
        )
        os.close(slave_fd)
        slave_fd = None

        while process.poll() is None:
            readable, _writable, _errors = select.select(
                [master_fd], [], [], 0.1
            )
            if not readable:
                continue
            try:
                chunk = os.read(master_fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)

        while True:
            readable, _writable, _errors = select.select(
                [master_fd], [], [], 0
            )
            if not readable:
                break
            try:
                chunk = os.read(master_fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)

        stderr = process.stderr.read() if process.stderr is not None else b""
        return subprocess.CompletedProcess(
            command,
            process.wait(timeout=1),
            b"".join(chunks).decode(errors="replace"),
            stderr.decode(errors="replace"),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))
    finally:
        if process is not None and process.poll() is None:
            process.kill()
        for fd in (slave_fd, master_fd):
            if fd is None:
                continue
            try:
                os.close(fd)
            except OSError:
                pass


def _write_chafa_failure_hint(reason: str | None) -> None:
    global _CHAFA_FAILURE_SHOWN

    if _CHAFA_FAILURE_SHOWN:
        return

    _CHAFA_FAILURE_SHOWN = True
    terminal_width = shutil.get_terminal_size((100, 20)).columns
    reason = (reason or "unknown Chafa error").strip().splitlines()[0]
    if len(reason) > 100:
        reason = f"{reason[:97]}..."
    lines = [
        "",
        _center_terminal_line(
            f"Chafa logo rendering failed: {reason}",
            terminal_width,
        ),
        _center_terminal_line(
            "Try reinstalling Chafa: sudo apt install chafa",
            terminal_width,
        ),
        "",
    ]
    _LIVE_PROGRESS.write("\n".join(lines))


def _chafa_color_mode() -> str:
    color_term_value = os.environ.get("COLORTERM", "").casefold()
    if "truecolor" in color_term_value or "24bit" in color_term_value:
        return "full"
    if "256color" in os.environ.get("TERM", "").casefold():
        return "256"
    return "16"


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _strip_ansi(value: str) -> str:
    return _ANSI_RE.sub("", value)


def _svg_file_view_box(path: Path) -> tuple[float, float, float, float] | None:
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError, UnicodeDecodeError):
        return None
    return _svg_view_box(root)


def _center_terminal_line(
    line: str,
    terminal_width: int,
    *,
    ansi: bool = False,
) -> str:
    visible = len(_strip_ansi(line)) if ansi else len(line)
    if visible >= terminal_width:
        return line
    return (" " * ((terminal_width - visible) // 2)) + line


def _center_terminal_block(
    block: str,
    terminal_width: int,
    *,
    ansi: bool = False,
) -> str:
    return "\n".join(
        _center_terminal_line(line, terminal_width, ansi=ansi)
        for line in block.rstrip("\n").splitlines()
    )


def _svg_view_box(
    root: ET.Element,
) -> tuple[float, float, float, float] | None:
    value = root.attrib.get("viewBox")
    if value:
        numbers = [float(part) for part in re.split(r"[\s,]+", value.strip())]
        if len(numbers) == 4:
            return tuple(numbers)  # type: ignore[return-value]

    width = _svg_number(root.attrib.get("width"))
    height = _svg_number(root.attrib.get("height"))
    if width is None or height is None:
        return None
    return 0.0, 0.0, width, height


def _svg_number(value: str | None) -> float | None:
    if not value:
        return None
    match = re.match(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", value)
    return float(match.group(0)) if match else None


class _ProgressBar:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._iterable = args[0] if args else None
        self._total = kwargs.get("total")
        if self._total is None and self._iterable is not None:
            try:
                self._total = len(self._iterable)
            except TypeError:
                self._total = None
        self._count = 0
        self._desc = str(kwargs.get("desc") or "Working")
        self._closed = False
        self._render()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __iter__(self):
        if self._iterable is None:
            return iter(())
        for item in self._iterable:
            yield item
            self.update(1)

    def update(self, n: int = 1) -> None:
        if self._closed:
            return
        self._count += n
        self._render()

    def close(self) -> None:
        self._closed = True

    def _render(self) -> None:
        progress = 0.0
        step_percent = 0
        if self._total:
            progress = min(self._count / self._total, 1.0)
            step_percent = int(round(progress * 100))

        _LIVE_PROGRESS.step(f"{self._desc} ({step_percent}%)", progress)


def progress_bar(*args: Any, **kwargs: Any):
    for option in ("dynamic_ncols", "leave", "smoothing", "bar_format"):
        kwargs.pop(option, None)
    return _ProgressBar(*args, **kwargs)


def close_progress() -> None:
    _LIVE_PROGRESS.close()


def finish_progress(status: str = "Ingestion complete") -> None:
    _LIVE_PROGRESS.finish(status)


def set_progress_status(status: str, progress: float = 0.0) -> None:
    _LIVE_PROGRESS.status(status, progress)


def set_progress_message(status: str) -> None:
    _LIVE_PROGRESS.message(status)


def set_progress_phase(status: str, start: float, end: float) -> None:
    _LIVE_PROGRESS.phase(status, start, end)


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "null"

    text = str(value)
    if any(char.isspace() for char in text):
        return repr(text)
    return text


def log_event(
    logger: logging.Logger,
    event: str,
    /,
    **fields: Any,
) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return

    parts = [f"event={event}"]
    parts.extend(
        f"{key}={_format_value(value)}"
        for key, value in fields.items()
        if value is not None
    )
    logger.debug(" ".join(parts))


def log_warning_event(
    logger: logging.Logger,
    event: str,
    /,
    **fields: Any,
) -> None:
    parts = [f"event={event}"]
    parts.extend(
        f"{key}={_format_value(value)}"
        for key, value in fields.items()
        if value is not None
    )
    logger.warning(" ".join(parts))
