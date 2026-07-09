from __future__ import annotations

# infrastructure/logging.py
import logging
import math
import re
import shutil
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_CONFIGURED = False

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
                self._console.print(message)
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

    chafa_art = _chafa_logo_art(
        svg_path,
        width=art_width,
        height=height,
        cell_aspect_ratio=cell_aspect_ratio,
    )
    art = chafa_art or _svg_ascii_art(
        svg_path,
        width=art_width,
        height=height,
        cell_aspect_ratio=cell_aspect_ratio,
    )
    if not art:
        return

    lines = []
    lines.extend("" for _ in range(max(padding, 0)))
    if title:
        lines.append(_center_terminal_line(title, terminal_width))
        lines.append("")
    lines.extend(_center_terminal_line(line, terminal_width) for line in art)
    lines.extend("" for _ in range(max(padding, 0)))
    _LIVE_PROGRESS.write("\n".join(lines))


def _chafa_logo_art(
    path: Path,
    *,
    width: int,
    height: int | None,
    cell_aspect_ratio: float,
) -> list[str]:
    chafa = shutil.which("chafa")
    if not chafa or not path.exists():
        return []

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

    command = [
        chafa,
        "--size",
        f"{width}x{height}",
        "--center",
        "off",
        "--stretch",
        "off",
        "--animate",
        "off",
        "--polite",
        "on",
        str(path),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    if completed.returncode != 0:
        return []

    lines = [
        _strip_ansi(line).rstrip()
        for line in completed.stdout.splitlines()
        if line.strip()
    ]
    return _trim_ascii_canvas(lines)


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _strip_ansi(value: str) -> str:
    return _ANSI_RE.sub("", value)


def _svg_file_view_box(path: Path) -> tuple[float, float, float, float] | None:
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError, UnicodeDecodeError):
        return None
    return _svg_view_box(root)


def _svg_ascii_art(
    path: Path,
    *,
    width: int,
    height: int | None = None,
    cell_aspect_ratio: float = 2.0,
) -> list[str]:
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError, UnicodeDecodeError):
        return []

    view_box = _svg_view_box(root)
    if view_box is None:
        return []

    min_x, min_y, box_width, box_height = view_box
    if box_width <= 0 or box_height <= 0:
        return []

    if height is None:
        height = max(
            4,
            round(width * (box_height / box_width) / cell_aspect_ratio),
        )

    paths = []
    for element in root.iter():
        if not element.tag.endswith("path"):
            continue
        d = element.attrib.get("d")
        if not d:
            continue
        transform = _svg_transform(element.attrib.get("transform"))
        paths.extend(_path_polylines(d, transform))

    if not paths:
        return []

    canvas = []
    for row in range(height):
        upper_y = min_y + ((row + 0.25) / height) * box_height
        lower_y = min_y + ((row + 0.75) / height) * box_height
        cells = []
        for col in range(width):
            x = min_x + ((col + 0.5) / width) * box_width
            upper = _point_in_paths(x, upper_y, paths)
            lower = _point_in_paths(x, lower_y, paths)
            if upper and lower:
                cells.append("#")
            elif upper:
                cells.append("^")
            elif lower:
                cells.append("_")
            else:
                cells.append(" ")
        canvas.append("".join(cells).rstrip())

    return _trim_ascii_canvas(canvas)


def _center_terminal_line(line: str, terminal_width: int) -> str:
    visible = len(line)
    if visible >= terminal_width:
        return line
    return (" " * ((terminal_width - visible) // 2)) + line


def _trim_ascii_canvas(canvas: list[str]) -> list[str]:
    rows = [line.rstrip() for line in canvas]
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    if not rows:
        return []

    left = min(
        len(line) - len(line.lstrip(" ")) for line in rows if line.strip()
    )
    return [line[left:] for line in rows]


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


def _svg_transform(value: str | None):
    if not value:
        return lambda x, y: (x, y)
    matrix = re.search(r"matrix\(([^)]+)\)", value)
    if not matrix:
        return lambda x, y: (x, y)

    parts = [
        float(part) for part in re.split(r"[\s,]+", matrix.group(1).strip())
    ]
    if len(parts) != 6:
        return lambda x, y: (x, y)
    a, b, c, d, e, f = parts
    return lambda x, y: (a * x + c * y + e, b * x + d * y + f)


_PATH_TOKEN_RE = re.compile(
    r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"
)


def _path_polylines(d: str, transform) -> list[list[tuple[float, float]]]:
    tokens = _PATH_TOKEN_RE.findall(d)
    paths: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    index = 0
    command = ""
    x = y = 0.0
    start_x = start_y = 0.0
    last_cubic: tuple[float, float] | None = None
    last_quad: tuple[float, float] | None = None

    def is_cmd(token: str) -> bool:
        return len(token) == 1 and token.isalpha()

    def num() -> float:
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    def point(px: float, py: float) -> tuple[float, float]:
        return transform(px, py)

    def add(px: float, py: float) -> None:
        current.append(point(px, py))

    def close_path() -> None:
        nonlocal current
        if current:
            current.append(point(start_x, start_y))
            paths.append(current)
            current = []

    while index < len(tokens):
        if is_cmd(tokens[index]):
            command = tokens[index]
            index += 1
        if not command:
            break

        absolute = command.isupper()
        cmd = command.upper()

        if cmd == "M":
            if current:
                paths.append(current)
                current = []
            nx, ny = num(), num()
            x, y = (nx, ny) if absolute else (x + nx, y + ny)
            start_x, start_y = x, y
            add(x, y)
            command = "L" if absolute else "l"
        elif cmd == "L":
            while index < len(tokens) and not is_cmd(tokens[index]):
                nx, ny = num(), num()
                x, y = (nx, ny) if absolute else (x + nx, y + ny)
                add(x, y)
            last_cubic = last_quad = None
        elif cmd == "H":
            while index < len(tokens) and not is_cmd(tokens[index]):
                nx = num()
                x = nx if absolute else x + nx
                add(x, y)
            last_cubic = last_quad = None
        elif cmd == "V":
            while index < len(tokens) and not is_cmd(tokens[index]):
                ny = num()
                y = ny if absolute else y + ny
                add(x, y)
            last_cubic = last_quad = None
        elif cmd == "C":
            while index < len(tokens) and not is_cmd(tokens[index]):
                x1, y1, x2, y2, x3, y3 = (
                    num(),
                    num(),
                    num(),
                    num(),
                    num(),
                    num(),
                )
                if not absolute:
                    x1, y1, x2, y2, x3, y3 = (
                        x + x1,
                        y + y1,
                        x + x2,
                        y + y2,
                        x + x3,
                        y + y3,
                    )
                for step in range(1, 9):
                    t = step / 8
                    px = _cubic(x, x1, x2, x3, t)
                    py = _cubic(y, y1, y2, y3, t)
                    add(px, py)
                x, y = x3, y3
                last_cubic = (x2, y2)
                last_quad = None
        elif cmd == "S":
            while index < len(tokens) and not is_cmd(tokens[index]):
                x1, y1 = (
                    (2 * x - last_cubic[0], 2 * y - last_cubic[1])
                    if last_cubic
                    else (x, y)
                )
                x2, y2, x3, y3 = num(), num(), num(), num()
                if not absolute:
                    x2, y2, x3, y3 = x + x2, y + y2, x + x3, y + y3
                for step in range(1, 9):
                    t = step / 8
                    add(_cubic(x, x1, x2, x3, t), _cubic(y, y1, y2, y3, t))
                x, y = x3, y3
                last_cubic = (x2, y2)
                last_quad = None
        elif cmd == "Q":
            while index < len(tokens) and not is_cmd(tokens[index]):
                x1, y1, x2, y2 = num(), num(), num(), num()
                if not absolute:
                    x1, y1, x2, y2 = x + x1, y + y1, x + x2, y + y2
                for step in range(1, 9):
                    t = step / 8
                    add(_quad(x, x1, x2, t), _quad(y, y1, y2, t))
                x, y = x2, y2
                last_quad = (x1, y1)
                last_cubic = None
        elif cmd == "T":
            while index < len(tokens) and not is_cmd(tokens[index]):
                x1, y1 = (
                    (2 * x - last_quad[0], 2 * y - last_quad[1])
                    if last_quad
                    else (x, y)
                )
                x2, y2 = num(), num()
                if not absolute:
                    x2, y2 = x + x2, y + y2
                for step in range(1, 9):
                    t = step / 8
                    add(_quad(x, x1, x2, t), _quad(y, y1, y2, t))
                x, y = x2, y2
                last_quad = (x1, y1)
                last_cubic = None
        elif cmd == "Z":
            close_path()
            x, y = start_x, start_y
            last_cubic = last_quad = None
        else:
            # Arc support is intentionally coarse; consume parameters and mark
            # the endpoint so logos with arcs still produce a recognizable map.
            while index + 6 < len(tokens) and not is_cmd(tokens[index]):
                _rx, _ry, _rot, _large, _sweep = (
                    num(),
                    num(),
                    num(),
                    num(),
                    num(),
                )
                nx, ny = num(), num()
                x, y = (nx, ny) if absolute else (x + nx, y + ny)
                add(x, y)

    if current:
        paths.append(current)
    return paths


def _cubic(a: float, b: float, c: float, d: float, t: float) -> float:
    u = 1 - t
    return (u**3 * a) + (3 * u * u * t * b) + (3 * u * t * t * c) + (t**3 * d)


def _quad(a: float, b: float, c: float, t: float) -> float:
    u = 1 - t
    return (u * u * a) + (2 * u * t * b) + (t * t * c)


def _point_in_paths(
    x: float,
    y: float,
    paths: list[list[tuple[float, float]]],
) -> bool:
    inside = False
    for path in paths:
        for index, point in enumerate(path):
            x1, y1 = point
            x2, y2 = path[(index + 1) % len(path)]
            if math.isclose(y1, y2):
                continue
            crosses = (y1 > y) != (y2 > y)
            if not crosses:
                continue
            intersect_x = x1 + ((y - y1) * (x2 - x1) / (y2 - y1))
            if intersect_x > x:
                inside = not inside
    return inside


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
