# engine/ruleset.py

from dataclasses import dataclass

from acubed.engine.objective import Objective


@dataclass(frozen=True, slots=True)
class Ruleset:
    name: str
    objective: Objective
