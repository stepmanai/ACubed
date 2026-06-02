# features/types.py

from collections.abc import Mapping
from typing import TypeAlias

from acubed.models.gameplay import Note

NoteFeature: TypeAlias = Mapping[Note, float]
