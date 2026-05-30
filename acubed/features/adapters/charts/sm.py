import re

from acubed.models.gameplay import (
    Note,
    Orientation,
    Stepfile,
)

LANES = (
    Orientation.LEFT,
    Orientation.DOWN,
    Orientation.UP,
    Orientation.RIGHT,
)


def _parse_offset(text: str) -> float:
    match = re.search(
        r"#OFFSET:([^;]+);",
        text,
        re.IGNORECASE,
    )

    return float(match.group(1))


def _parse_bpms(text: str) -> list[tuple[float, float]]:
    match = re.search(
        r"#BPMS:(.*?);",
        text,
        re.DOTALL | re.IGNORECASE,
    )

    entries = []

    for item in match.group(1).replace("\n", "").replace("\r", "").split(","):
        if not item:
            continue

        beat, bpm = item.split("=")

        entries.append(
            (
                float(beat),
                float(bpm),
            )
        )

    entries.sort()

    return entries


def _parse_measures(text: str) -> list[list[str]]:
    notes_section = text.split("#NOTES:", 1)[1]

    start = notes_section.find(":")
    start = notes_section.find(":", start + 1)
    start = notes_section.find(":", start + 1)
    start = notes_section.find(":", start + 1)
    start = notes_section.find(":", start + 1)

    data = notes_section[start + 1 :]
    data = data.split(";", 1)[0]

    measures = []

    current_measure = []

    for line in data.splitlines():
        line = line.split("//")[0].strip()

        if not line:
            continue

        if "," in line:
            line = line.replace(",", "").strip()

            if line:
                current_measure.append(line)

            measures.append(current_measure)
            current_measure = []

            continue

        current_measure.append(line)

    if current_measure:
        measures.append(current_measure)

    return measures


def beat_to_seconds(
    beat: float,
    bpms: list[tuple[float, float]],
) -> float:
    seconds = 0.0

    for i, (start_beat, bpm) in enumerate(bpms):
        end_beat = bpms[i + 1][0] if i + 1 < len(bpms) else beat

        if beat <= start_beat:
            break

        segment_end = min(beat, end_beat)

        beats_in_segment = segment_end - start_beat

        if beats_in_segment > 0:
            seconds += beats_in_segment * 60.0 / bpm

        if segment_end == beat:
            break

    return seconds


def sm_to_stepfile(chart: bytes) -> Stepfile:
    text = chart.decode("utf-8")

    offset = _parse_offset(text)
    bpms = _parse_bpms(text)
    measures = _parse_measures(text)

    notes: list[Note] = []

    current_beat = 0.0

    for measure in measures:
        rows = len(measure)

        for row_index, row in enumerate(measure):
            beat = current_beat + row_index * (4.0 / rows)

            timestamp_ms = (
                beat_to_seconds(
                    beat=beat,
                    bpms=bpms,
                )
                - offset
            ) * 1000.0

            for lane_index, char in enumerate(row):
                if char in {"1", "2", "4"}:
                    notes.append(
                        Note(
                            timestamp_ms=timestamp_ms,
                            lane=LANES[lane_index],
                        )
                    )

        current_beat += 4.0

    notes.sort(key=lambda note: note.timestamp_ms)

    if notes:
        start = min(note.timestamp_ms for note in notes)

        notes = [
            Note(
                timestamp_ms=note.timestamp_ms - start,
                lane=note.lane,
            )
            for note in notes
        ]

    return Stepfile(notes=notes)
