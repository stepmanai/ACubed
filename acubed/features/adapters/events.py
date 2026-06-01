import narwhals as nw

from acubed.models.gameplay import Stepfile


def stepfile_to_events(stepfile: Stepfile) -> nw.DataFrame:
    return nw.from_dict(
        {
            "note_id": [idx for idx, _ in enumerate(stepfile.notes)],
            "lane": [note.lane for note in stepfile.notes],
            "time": [note.time for note in stepfile.notes],
        }
    )
