

"""
models.py

Core data models for the simple museum cue planner.

Includes:
- CueType, TriggerType, PlayType, StartMode enums
- MediaCue dataclass (one cue)
- RoomPlan / ShowPlan containers
- JSON (de)serialization helpers
- compute_schedule(...) to get effective cue start times
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any


class CueType(str, Enum):
    """
    High-level category for a cue.

    Covers both traditional AV media and visitor / staff actions,
    so we can describe the whole experience, not just devices.
    """
    AUDIO = "Audio"
    PROJECTION = "Projection"
    TV = "TV"
    LIGHTING = "Lighting"
    INTERACTIVE = "Interactive"
    ACTIVITY = "Activity"
    GROUP_MOVEMENT = "Group Movement"
    FACILITATOR_ACTION = "Facilitator Action"


class TriggerType(str, Enum):
    """
    How the cue is triggered logically.

    For now this is descriptive (no logic attached), but it gives us
    a clean place to later connect to sensors / external systems.
    """
    TIMELINE = "Timeline (auto)"
    SENSOR = "Sensor"
    MANUAL = "Manual (operator)"


class PlayType(str, Enum):
    """Playback behaviour for a cue."""
    PLAY_ONCE = "Play once"
    LOOP = "Loop"
    AMBIENT = "Ambient"


class StartMode(str, Enum):
    """
    How the cue's timing is defined.

    - AT_TIME:           Starts at a fixed offset in seconds.
    - AFTER_PREVIOUS:    Starts when the previous cue ends.
    - AFTER_CUE:         Starts when a specific earlier cue ends.
    """
    AT_TIME = "At fixed time (s)"
    AFTER_PREVIOUS = "After previous cue"
    AFTER_CUE = "After cue"


@dataclass
class MediaCue:
    """
    One cue in the room.

    Attributes:
        name: Human readable label, e.g. "Ocean intro audio".
        cue_type: Audio / Projection / Lighting / Activity / etc.
        trigger_type: Timeline / Sensor / Manual.
        play_type: Play once / Loop / Ambient.
        start_mode: At fixed time vs after previous vs after specific cue.
        start_time_s: Offset in seconds from room start
                      (only meaningful when start_mode == AT_TIME).
        duration_s: Estimated duration in seconds.
        dependency_name: Name of cue this one depends on (if AFTER_CUE).
        notes: Free-form notes for operators / integrators.
    """
    name: str
    cue_type: CueType = CueType.AUDIO
    trigger_type: TriggerType = TriggerType.TIMELINE
    play_type: PlayType = PlayType.PLAY_ONCE
    start_mode: StartMode = StartMode.AT_TIME
    start_time_s: float = 0.0
    duration_s: float = 0.0
    dependency_name: str | None = None
    notes: str = ""

    # ---------- JSON helpers ----------
    def to_dict(self) -> Dict[str, Any]:
        """Convert to a plain dict safe for JSON."""
        return {
            "name": self.name,
            "cue_type": self.cue_type.value,
            "trigger_type": self.trigger_type.value,
            "play_type": self.play_type.value,
            "start_mode": self.start_mode.value,
            "start_time_s": self.start_time_s,
            "duration_s": self.duration_s,
            "dependency_name": self.dependency_name,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MediaCue":
        """
        Create a MediaCue from a dict, with sensible defaults.

        Supports both new 'cue_type' key and legacy 'media_type' key so
        older JSON files still load.
        """
        # Backwards compatibility for older JSON that used "media_type"
        type_value = data.get("cue_type") or data.get("media_type") or CueType.AUDIO.value

        return cls(
            name=data.get("name", ""),
            cue_type=CueType(type_value),
            trigger_type=TriggerType(data.get("trigger_type", TriggerType.TIMELINE.value)),
            play_type=PlayType(data.get("play_type", PlayType.PLAY_ONCE.value)),
            start_mode=StartMode(data.get("start_mode", StartMode.AT_TIME.value)),
            start_time_s=float(data.get("start_time_s", 0.0)),
            duration_s=float(data.get("duration_s", 0.0)),
            dependency_name=data.get("dependency_name") or None,
            notes=data.get("notes", ""),
        )


@dataclass
class RoomPlan:
    """Represents the plan for one room."""
    name: str
    cues: List[MediaCue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "cues": [c.to_dict() for c in self.cues],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoomPlan":
        cues = [MediaCue.from_dict(c) for c in data.get("cues", [])]
        return cls(name=data.get("name", "Room"), cues=cues)


@dataclass
class ShowPlan:
    """Root object representing the entire show (multiple rooms)."""
    rooms: List[RoomPlan] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"rooms": [r.to_dict() for r in self.rooms]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShowPlan":
        rooms = [RoomPlan.from_dict(r) for r in data.get("rooms", [])]
        return cls(rooms=rooms)


# ----------------------------------------------------------------------
# Scheduling
# ----------------------------------------------------------------------
def compute_schedule(cues: List[MediaCue]) -> List[float]:
    """
    Compute effective start times for each cue, in seconds.

    Rules:
        - AT_TIME:
              start = max(start_time_s, 0)
        - AFTER_PREVIOUS:
              start = previous_start + previous_duration
              (for index 0, start = 0)
        - AFTER_CUE:
              start = start(dep_cue) + duration(dep_cue)
              dep_cue is found by name among *earlier* cues.

    Returns:
        List of start times (same ordering as input list).
    """
    start_times: List[float] = []
    current_time = 0.0

    for index, cue in enumerate(cues):
        if cue.start_mode == StartMode.AT_TIME:
            start = max(cue.start_time_s, 0.0)
            current_time = max(current_time, start)

        elif cue.start_mode == StartMode.AFTER_PREVIOUS:
            if index == 0:
                start = 0.0
            else:
                prev_start = start_times[index - 1]
                prev_duration = max(cues[index - 1].duration_s, 0.0)
                start = prev_start + prev_duration
            current_time = start

        elif cue.start_mode == StartMode.AFTER_CUE:
            start = 0.0
            if cue.dependency_name:
                # look for dependency among earlier cues
                for dep_index in range(index - 1, -1, -1):
                    if cues[dep_index].name == cue.dependency_name:
                        dep_start = start_times[dep_index]
                        dep_dur = max(cues[dep_index].duration_s, 0.0)
                        start = dep_start + dep_dur
                        break
            current_time = max(current_time, start)

        else:
            # Fallback: treat as AT_TIME = 0
            start = 0.0
            current_time = max(current_time, start)

        start_times.append(start)

    return start_times
