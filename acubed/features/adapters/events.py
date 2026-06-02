import subprocess
import sys

from acubed.models.gameplay import Stepfile

try:
    import narwhals as nw
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "narwhals"])
    import narwhals as nw


def stepfile_to_events(stepfile: Stepfile) -> nw.DataFrame:
    return nw.from_dict(
        {
            "note_id": [idx for idx, _ in enumerate(stepfile.notes)],
            "lane": [note.lane for note in stepfile.notes],
            "time": [note.time for note in stepfile.notes],
        }
    )
