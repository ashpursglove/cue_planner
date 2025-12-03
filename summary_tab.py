
"""
summary_tab.py

SummaryTab aggregates all rooms and provides:

- A global timeline that flows room-to-room in show order.
- A very detailed textual analysis of all cues (per room + global).
- Export to a nicely formatted landscape PDF including:
    * Global timeline graph (as an image)
    * One per-room timeline graph per page
    * Full text report (stats + data dump)

Relies on:
    - models.MediaCue, CueType, TriggerType, PlayType, StartMode, compute_schedule
    - RoomTab-like objects that expose:
        * room_name: str
        * get_cues() -> List[MediaCue]
        * export_timeline_image(width, height) -> QImage
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from PyQt5 import QtCore, QtGui, QtWidgets

from models import (
    MediaCue,
    CueType,
    TriggerType,
    PlayType,
    StartMode,
    compute_schedule,
)


# ---------------------------------------------------------------------------
# Global timeline data structure
# ---------------------------------------------------------------------------

@dataclass
class GlobalTimelineItem:
    room_name: str
    cue: MediaCue
    start_time: float  # global start time (with room offsets)
    duration: float


# ---------------------------------------------------------------------------
# Global timeline view
# ---------------------------------------------------------------------------

class GlobalTimelineView(QtWidgets.QGraphicsView):
    """
    Global timeline across all rooms.

    - Each cue is placed according to a GLOBAL start time:
        start = cumulative_room_offset + room_local_start(cue)
    - Rooms are effectively stitched together in show order.
    - Same cue colour scheme as per-room timeline.
    - Zoomable with mouse wheel, pannable with mouse drag.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)

        self._scene.setBackgroundBrush(QtGui.QColor(15, 24, 38))

        self._items: List[GlobalTimelineItem] = []

        self._pixels_per_second: float = 6.0
        self._bar_height: float = 26.0
        self._lane_gap: float = 8.0
        self._top_margin: float = 40.0
        self._left_margin: float = 70.0
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.setMinimumHeight(260)

        # Zoom / pan
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
        self._has_manual_zoom: bool = False

    # -----------------------
    # Public API
    # -----------------------
    def set_items(self, items: List[GlobalTimelineItem]) -> None:
        """Replace global timeline items and redraw."""
        self._items = items
        self._redraw()

    def total_duration(self) -> float:
        """
        Return the total duration (end of last cue) in seconds,
        based on the global items list.
        """
        if not self._items:
            return 0.0
        max_end = 0.0
        for item in self._items:
            end = item.start_time + max(item.duration, 0.0)
            if end > max_end:
                max_end = end
        return max_end

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # type: ignore[override]
        """Mouse wheel to zoom in/out around the cursor."""
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return

        zoom_factor = 1.2 if delta > 0 else 1 / 1.2
        self._has_manual_zoom = True
        self.scale(zoom_factor, zoom_factor)
        event.accept()

    def render_to_image(self, width: int = 2000, height: int = 600) -> QtGui.QImage:
        """
        Render the current scene into a QImage for PDF export.

        This uses the scene directly (not the view), so it ignores the
        user's zoom level and always renders a full overview.
        """
        image = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor(15, 24, 38))  # dark background

        painter = QtGui.QPainter(image)
        target_rect = QtCore.QRectF(0, 0, width, height)
        source_rect = self._scene.sceneRect()
        if source_rect.width() <= 0 or source_rect.height() <= 0:
            source_rect = QtCore.QRectF(0, 0, width, height)
        self._scene.render(painter, target=target_rect, source=source_rect)
        painter.end()

        return image
    

    def export_for_pdf(self, width: int = 2500, height: int = 500) -> QtGui.QImage:
        """
        Render a PDF-friendly version of the GLOBAL timeline.

        We temporarily increase bar height and lane gap so the global overview
        is legible on A4, then restore the original values for normal GUI use.
        """
        # Save old visual settings
        old_bar_height = self._bar_height
        old_lane_gap = self._lane_gap

        # Make everything chunkier for print
        self._bar_height = 40
        self._lane_gap = 16
        self._redraw()

        image = self.render_to_image(width=width, height=height)

        # Restore original settings
        self._bar_height = old_bar_height
        self._lane_gap = old_lane_gap
        self._redraw()

        return image


    # -----------------------
    # Internal layout/drawing
    # -----------------------
    def _compute_lanes(self) -> List[int]:
        """
        Assign each item to a lane based on overlaps (greedy algorithm).
        """
        n = len(self._items)
        if n == 0:
            return []

        indices = list(range(n))
        indices.sort(key=lambda i: self._items[i].start_time)

        lane_end_times: List[float] = []
        item_lane = [0] * n

        for i in indices:
            start = self._items[i].start_time
            duration = max(self._items[i].duration, 0.0)
            end = start + duration

            placed = False
            for lane_idx, lane_end in enumerate(lane_end_times):
                if start >= lane_end:
                    item_lane[i] = lane_idx
                    lane_end_times[lane_idx] = end
                    placed = True
                    break

            if not placed:
                item_lane[i] = len(lane_end_times)
                lane_end_times.append(end)

        return item_lane

    def _redraw(self) -> None:
        self._scene.clear()
        self._scene.setBackgroundBrush(QtGui.QColor(15, 24, 38))

        if not self._items:
            return

        max_end = 0.0
        for item in self._items:
            end = item.start_time + max(item.duration, 0.0)
            max_end = max(max_end, end)
        max_end = max(max_end, 10.0)

        item_lanes = self._compute_lanes()
        num_lanes = max(item_lanes) + 1 if item_lanes else 1

        total_width = self._left_margin + max_end * self._pixels_per_second + 60.0
        total_height = (
            self._top_margin
            + num_lanes * (self._bar_height + self._lane_gap)
            + 100.0
        )
        self._scene.setSceneRect(0, 0, total_width, total_height)

        axis_color = QtGui.QColor(220, 230, 245)
        grid_color = QtGui.QColor(90, 105, 135)
        text_color = QtGui.QColor(230, 235, 245)

        # Time axis
        axis_y = self._top_margin + num_lanes * (self._bar_height + self._lane_gap)
        axis_pen = QtGui.QPen(axis_color)
        self._scene.addLine(
            self._left_margin,
            axis_y,
            self._left_margin + max_end * self._pixels_per_second,
            axis_y,
            axis_pen,
        )

        # Grid + labels
        grid_pen = QtGui.QPen(grid_color)
        grid_pen.setStyle(QtCore.Qt.DashLine)
        label_font = QtGui.QFont("Segoe UI", 8)

        tick_step = 10  # 10-second grid for global view
        num_ticks = int(max_end // tick_step) + 1
        for i in range(num_ticks + 1):
            t = i * tick_step
            x = self._left_margin + t * self._pixels_per_second
            self._scene.addLine(
                x,
                self._top_margin - 10.0,
                x,
                axis_y,
                grid_pen,
            )
            text_item = self._scene.addText(f"{t}s", label_font)
            text_item.setDefaultTextColor(text_color)
            text_rect = text_item.boundingRect()
            text_item.setPos(x - text_rect.width() / 2.0, axis_y + 4.0)

        # Bars
        bar_pen = QtGui.QPen(QtGui.QColor(10, 10, 10))
        label_font_cue = QtGui.QFont("Segoe UI", 8)

        for idx, item in enumerate(self._items):
            lane_idx = item_lanes[idx]
            cue = item.cue
            color = self._color_for_cue_type(cue.cue_type)
            brush = QtGui.QBrush(color)

            bar_x = self._left_margin + item.start_time * self._pixels_per_second
            bar_y = self._top_margin + lane_idx * (self._bar_height + self._lane_gap)
            bar_width = max(item.duration * self._pixels_per_second, 16.0)

            rect_item = self._scene.addRect(
                bar_x,
                bar_y,
                bar_width,
                self._bar_height,
                bar_pen,
                brush,
            )
            rect_item.setToolTip(
                f"[{item.room_name}] {cue.name}\n"
                f"{cue.cue_type.value} | {cue.trigger_type.value} | {cue.play_type.value}\n"
                f"Start: {item.start_time:.1f}s  Duration: {item.duration:.1f}s"
            )

            label = f"{item.room_name}: {cue.name}"
            text_item = self._scene.addText(label, label_font_cue)
            text_item.setDefaultTextColor(QtGui.QColor(10, 10, 10))
            text_rect = text_item.boundingRect()
            text_x = bar_x + 3.0
            text_y = bar_y + (self._bar_height - text_rect.height()) / 2.0
            text_item.setPos(text_x, text_y)

        # Same scaling strategy as the room timeline:
        # - Short global timelines: auto-fit.
        # - Long ones: keep text legible and use scrollbars.
        if not self._has_manual_zoom:
            self.resetTransform()
            if max_end <= 150.0:
                self.fitInView(self._scene.sceneRect(), QtCore.Qt.KeepAspectRatio)
            else:
                self.centerOn(
                    self._left_margin,
                    self._scene.sceneRect().center().y(),
                )

    @staticmethod
    def _color_for_cue_type(cue_type: CueType) -> QtGui.QColor:
        """Mirror the colours from the RoomTab timeline."""
        if cue_type == CueType.AUDIO:
            return QtGui.QColor(135, 206, 250)  # light blue
        if cue_type == CueType.PROJECTION:
            return QtGui.QColor(255, 228, 181)  # moccasin
        if cue_type == CueType.TV:
            return QtGui.QColor(152, 251, 152)  # pale green
        if cue_type == CueType.LIGHTING:
            return QtGui.QColor(255, 182, 193)  # light pink
        if cue_type == CueType.INTERACTIVE:
            return QtGui.QColor(221, 160, 221)  # plum
        if cue_type == CueType.ACTIVITY:
            return QtGui.QColor(255, 215, 0)    # gold / yellow
        if cue_type == CueType.GROUP_MOVEMENT:
            return QtGui.QColor(64, 224, 208)   # teal
        if cue_type == CueType.FACILITATOR_ACTION:
            return QtGui.QColor(255, 165, 0)    # orange
        return QtGui.QColor(211, 211, 211)      # fallback grey


# ---------------------------------------------------------------------------
# Summary tab
# ---------------------------------------------------------------------------

class SummaryTab(QtWidgets.QWidget):
    """
    Aggregates all RoomTabs:

    - Builds a global room-to-room timeline.
    - Computes rich statistics per room and overall.
    - Displays a huge text report.
    - Exports everything to a landscape PDF.
    """

    def __init__(self, room_tabs: List[Any], parent: QtWidgets.QWidget | None = None) -> None:
        """
        room_tabs: list of RoomTab-like objects exposing:
            - room_name: str
            - get_cues() -> List[MediaCue]
        """
        super().__init__(parent)
        self._room_tabs = room_tabs

        self._build_ui()
        self.refresh_summary()

    # -----------------------
    # UI
    # -----------------------
    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        # Buttons row
        btn_row = QtWidgets.QHBoxLayout()
        self.refresh_button = QtWidgets.QPushButton("Refresh summary")
        self.export_pdf_button = QtWidgets.QPushButton("Export PDF report")
        btn_row.addWidget(self.refresh_button)
        btn_row.addStretch()
        btn_row.addWidget(self.export_pdf_button)
        layout.addLayout(btn_row)

        # Global timeline
        self.timeline_view = GlobalTimelineView()
        timeline_group = QtWidgets.QGroupBox("Global Timeline (Reception → Mecca)")
        tl_layout = QtWidgets.QVBoxLayout(timeline_group)
        tl_layout.addWidget(self.timeline_view)
        layout.addWidget(timeline_group)

        # Text report
        self.summary_edit = QtWidgets.QTextEdit()
        self.summary_edit.setReadOnly(True)
        font = QtGui.QFont("Consolas", 9)
        self.summary_edit.setFont(font)

        summary_group = QtWidgets.QGroupBox("Detailed Report")
        sg_layout = QtWidgets.QVBoxLayout(summary_group)
        sg_layout.addWidget(self.summary_edit)
        layout.addWidget(summary_group)

        # Connect signals
        self.refresh_button.clicked.connect(self.refresh_summary)
        self.export_pdf_button.clicked.connect(self._export_pdf)

    # -----------------------
    # Core logic
    # -----------------------
    def refresh_summary(self) -> None:
        """
        Recompute everything from scratch:

        - Build global timeline items.
        - Compute per-room + global statistics.
        - Update timeline view + text report.
        """
        global_items, room_stats, global_stats = self._compute_all_stats()
        self.timeline_view.set_items(global_items)
        report_text = self._build_report_text(global_items, room_stats, global_stats)
        self.summary_edit.setPlainText(report_text)

    # ---- stats & analysis ----
    def _compute_all_stats(
        self,
    ) -> Tuple[List[GlobalTimelineItem], Dict[str, Dict[str, Any]], Dict[str, Any]]:
        """
        Returns:
            global_items: list of GlobalTimelineItem in show order
            room_stats:   dict[room_name] -> stats dict
            global_stats: aggregate stats
        """
        global_items: List[GlobalTimelineItem] = []
        room_stats: Dict[str, Dict[str, Any]] = {}

        # For global stats
        total_cues = 0
        total_duration = 0.0
        cue_type_counts: Dict[CueType, int] = {}
        trigger_counts: Dict[TriggerType, int] = {}
        play_counts: Dict[PlayType, int] = {}

        global_offset = 0.0  # accumulates room durations

        for tab in self._room_tabs:
            room_name = getattr(tab, "room_name", "Room")
            cues = tab.get_cues()
            if not cues:
                # Still record empty stats
                room_stats[room_name] = {
                    "num_cues": 0,
                    "room_duration": 0.0,
                    "by_cue_type": {},
                    "by_trigger": {},
                    "by_play": {},
                    "notes": [],
                    "timeline": [],
                }
                continue

            # Local schedule for room
            starts = compute_schedule(cues)
            room_end = 0.0

            by_cue_type: Dict[CueType, Dict[str, Any]] = {}
            by_trigger: Dict[TriggerType, Dict[str, Any]] = {}
            by_play: Dict[PlayType, Dict[str, Any]] = {}
            notes_list: List[Tuple[float, str, str]] = []  # (start, cue_name, note)
            timeline_entries: List[Tuple[float, MediaCue]] = []

            for cue, local_start in zip(cues, starts):
                duration = max(cue.duration_s, 0.0)
                end = local_start + duration
                room_end = max(room_end, end)

                # Global item
                global_items.append(
                    GlobalTimelineItem(
                        room_name=room_name,
                        cue=cue,
                        start_time=global_offset + local_start,
                        duration=duration,
                    )
                )

                # Per-room stats
                timeline_entries.append((local_start, cue))

                ct = cue.cue_type
                tt = cue.trigger_type
                pt = cue.play_type

                # Cue type stats
                ct_entry = by_cue_type.setdefault(ct, {"count": 0, "total_duration": 0.0})
                ct_entry["count"] += 1
                ct_entry["total_duration"] += duration

                # Trigger stats
                tt_entry = by_trigger.setdefault(tt, {"count": 0})
                tt_entry["count"] += 1

                # Play stats
                pt_entry = by_play.setdefault(pt, {"count": 0})
                pt_entry["count"] += 1

                # Notes
                if cue.notes:
                    notes_list.append((local_start, cue.name, cue.notes))

                # Global stats
                total_cues += 1
                total_duration += duration
                cue_type_counts[ct] = cue_type_counts.get(ct, 0) + 1
                trigger_counts[tt] = trigger_counts.get(tt, 0) + 1
                play_counts[pt] = play_counts.get(pt, 0) + 1

            room_stats[room_name] = {
                "num_cues": len(cues),
                "room_duration": room_end,
                "by_cue_type": by_cue_type,
                "by_trigger": by_trigger,
                "by_play": by_play,
                "notes": sorted(notes_list, key=lambda x: x[0]),
                "timeline": sorted(timeline_entries, key=lambda x: x[0]),
            }

            global_offset += room_end

        global_stats: Dict[str, Any] = {
            "total_cues": total_cues,
            "total_duration": total_duration,
            "cue_type_counts": cue_type_counts,
            "trigger_counts": trigger_counts,
            "play_counts": play_counts,
            "total_show_duration": global_offset,
        }

        return global_items, room_stats, global_stats

    def _build_report_text(
        self,
        global_items: List[GlobalTimelineItem],
        room_stats: Dict[str, Dict[str, Any]],
        global_stats: Dict[str, Any],
    ) -> str:
        """
        Build a human-readable text report:

        - Overall summary
        - Per-room breakdown in plain English
        - Global, room-to-room timeline in plain English
        """
        lines: List[str] = []

        # Overall header
        lines.append("ASH'S CUE PLANNER – FULL SUMMARY")
        lines.append("=" * 72)
        lines.append("")

        # Global overview
        total_cues = global_stats["total_cues"]
        total_duration = global_stats["total_duration"]
        total_show = global_stats["total_show_duration"]
        lines.append("OVERALL SHOW")
        lines.append("-" * 72)
        lines.append(f"Total number of rooms: {len(room_stats)}")
        lines.append(f"Total number of cues:  {total_cues}")
        lines.append(
            f"Total cue time (all rooms combined): {total_duration:.1f} s "
            f"({self._format_seconds(total_duration)})"
        )
        lines.append(
            f"End of the final room relative to the start of Reception: "
            f"{total_show:.1f} s ({self._format_seconds(total_show)})"
        )
        lines.append("")

        # By cue type
        lines.append("Cues by Cue Type (whole show):")
        cue_type_counts: Dict[CueType, int] = global_stats["cue_type_counts"]
        if cue_type_counts:
            for ct in sorted(cue_type_counts.keys(), key=lambda x: x.value):
                lines.append(f"  • {ct.value}: {cue_type_counts[ct]} cues")
        else:
            lines.append("  (no cues defined yet)")
        lines.append("")

        # By trigger
        lines.append("Cues by Trigger Type (whole show):")
        trig_counts: Dict[TriggerType, int] = global_stats["trigger_counts"]
        if trig_counts:
            for tt in sorted(trig_counts.keys(), key=lambda x: x.value):
                lines.append(f"  • {tt.value}: {trig_counts[tt]} cues")
        else:
            lines.append("  (no cues defined yet)")
        lines.append("")

        # By play type
        lines.append("Cues by Play Type (whole show):")
        play_counts: Dict[PlayType, int] = global_stats["play_counts"]
        if play_counts:
            for pt in sorted(play_counts.keys(), key=lambda x: x.value):
                lines.append(f"  • {pt.value}: {play_counts[pt]} cues")
        else:
            lines.append("  (no cues defined yet)")
        lines.append("")
        lines.append("")

        # Per-room breakdown
        lines.append("PER-ROOM BREAKDOWN")
        lines.append("=" * 72)
        lines.append("")

        for room_name, stats in room_stats.items():
            lines.append(f"ROOM: {room_name}")
            lines.append("-" * 72)
            num_cues = stats["num_cues"]
            room_dur = stats["room_duration"]
            lines.append(f"Number of cues in this room: {num_cues}")
            lines.append(
                f"Approximate duration of this room: {room_dur:.1f} s "
                f"({self._format_seconds(room_dur)})"
            )
            lines.append("")

            # By cue type
            lines.append("  By Cue Type (what kind of elements are used here):")
            by_ct: Dict[CueType, Dict[str, Any]] = stats["by_cue_type"]
            if by_ct:
                for ct in sorted(by_ct.keys(), key=lambda x: x.value):
                    entry = by_ct[ct]
                    count = entry["count"]
                    dur = entry["total_duration"]
                    avg = dur / count if count > 0 else 0.0
                    lines.append(
                        f"    • {ct.value}: {count} cue(s), total {dur:.1f} s, "
                        f"average {avg:.1f} s each"
                    )
            else:
                lines.append("    (no cues yet for this room)")
            lines.append("")

            # By trigger
            lines.append("  By Trigger (how things start):")
            by_tr: Dict[TriggerType, Dict[str, Any]] = stats["by_trigger"]
            if by_tr:
                for tt in sorted(by_tr.keys(), key=lambda x: x.value):
                    entry = by_tr[tt]
                    lines.append(
                        f"    • {tt.value}: {entry['count']} cue(s) in this room"
                    )
            else:
                lines.append("    (no triggers yet)")
            lines.append("")

            # By play type
            lines.append("  By Play Type (playback behaviour):")
            by_pl: Dict[PlayType, Dict[str, Any]] = stats["by_play"]
            if by_pl:
                for pt in sorted(by_pl.keys(), key=lambda x: x.value):
                    entry = by_pl[pt]
                    lines.append(
                        f"    • {pt.value}: {entry['count']} cue(s) in this room"
                    )
            else:
                lines.append("    (no playback modes defined)")
            lines.append("")

            # Notes
            notes_list: List[Tuple[float, str, str]] = stats["notes"]
            if notes_list:
                lines.append("  Operator / design notes for this room:")
                for start, cue_name, note in notes_list:
                    lines.append(
                        f"    • Around {start:.1f} s from the start of this room, "
                        f"for cue “{cue_name}”: {note}"
                    )
                lines.append("")
            else:
                lines.append("  Operator / design notes for this room: (none)")
                lines.append("")

            # Timeline dump for the room
            lines.append("  Timeline for this room (local times):")
            timeline_entries: List[Tuple[float, MediaCue]] = stats["timeline"]
            if timeline_entries:
                for start, cue in timeline_entries:
                    duration = cue.duration_s
                    dep = cue.dependency_name or "No specific dependency"
                    lines.append(
                        f"    • At {start:.1f} s from the start of this room "
                        f"(lasting {duration:.1f} s): cue “{cue.name}” "
                        f"[{cue.cue_type.value}] "
                        f"– Triggered by: {cue.trigger_type.value}; "
                        f"Play mode: {cue.play_type.value}; "
                        f"Start rule: {cue.start_mode.value}; "
                        f"Dependency: {dep}."
                    )
            else:
                lines.append("    (no cues yet for this room)")
            lines.append("")
            lines.append("")

        # Global timeline dump (room-to-room)
        lines.append("GLOBAL TIMELINE – RECEPTION TO MECCA")
        lines.append("=" * 72)
        lines.append(
            "This section shows how the experience flows if the visitor moves "
            "from room to room in the planned order. Times are measured from "
            "the very beginning of Reception."
        )
        lines.append("")
        if global_items:
            for item in sorted(global_items, key=lambda x: x.start_time):
                cue = item.cue
                dep = cue.dependency_name or "No specific dependency"
                start_str = (
                    f"{item.start_time:.1f} s "
                    f"({self._format_seconds(item.start_time)})"
                )
                dur_str = (
                    f"{item.duration:.1f} s "
                    f"({self._format_seconds(item.duration)})"
                )
                lines.append(
                    f"• At {start_str} from the very beginning, in room “{item.room_name}”, "
                    f"cue “{cue.name}” starts. It lasts for {dur_str} and is of type "
                    f"{cue.cue_type.value}. It is triggered by {cue.trigger_type.value}, "
                    f"uses play mode {cue.play_type.value}, and follows the start rule "
                    f"“{cue.start_mode.value}”. Dependency: {dep}."
                )
        else:
            lines.append("There are currently no cues defined in any room.")

        return "\n".join(lines)

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        s = int(round(seconds))
        h = s // 3600
        m = (s % 3600) // 60
        s2 = s % 60
        if h > 0:
            return f"{h:d}:{m:02d}:{s2:02d}"
        return f"{m:02d}:{s2:02d}"

    # -----------------------
    # PDF export
    # -----------------------



    # -----------------------
    # PDF export
    # -----------------------
    def _export_pdf(self) -> None:
        """
        Export a fresh, reportlab-drawn global Gantt + per-room Gantts + text report.

        Layout:
            - Page 1: global Gantt chart (Reception → Mecca), with
              multiple lanes per room so overlapping cues never obscure
              each other.
            - Pages 2..N: one page per room, showing that room's local
              timeline as a multi-lane Gantt.
            - Remaining pages: text report (same content as in the GUI).
        """
        # Make sure the text report and internal stats are up to date
        self.refresh_summary()

        path_str, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export PDF report",
            "",
            "PDF files (*.pdf);;All files (*.*)",
        )
        if not path_str:
            return

        # Lazy import so the app still runs if reportlab isn't installed.
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.pdfgen import canvas
        except Exception:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(
                self,
                "Missing dependency",
                "The 'reportlab' package is required to export PDFs.\n\n"
                "Install it with:\n\n"
                "    pip install reportlab",
            )
            return

        if not path_str.lower().endswith(".pdf"):
            path_str = path_str + ".pdf"

        # Recompute data so we have everything locally here
        global_items, room_stats, global_stats = self._compute_all_stats()

        page_size = landscape(A4)
        c = canvas.Canvas(path_str, pagesize=page_size)
        c.setTitle("Ash's Cue Planner")

        page_width, page_height = page_size
        margin = 40

        # ------------------------------------------------------
        # Shared helpers
        # ------------------------------------------------------
        def pdf_color_for_cue_type(cue_type: CueType) -> tuple[float, float, float]:
            """Colour palette for PDF bars (normalized 0–1)."""
            if cue_type == CueType.AUDIO:
                return (135 / 255.0, 206 / 255.0, 250 / 255.0)
            if cue_type == CueType.PROJECTION:
                return (255 / 255.0, 228 / 255.0, 181 / 255.0)
            if cue_type == CueType.TV:
                return (152 / 255.0, 251 / 255.0, 152 / 255.0)
            if cue_type == CueType.LIGHTING:
                return (255 / 255.0, 182 / 255.0, 193 / 255.0)
            if cue_type == CueType.INTERACTIVE:
                return (221 / 255.0, 160 / 255.0, 221 / 255.0)
            if cue_type == CueType.ACTIVITY:
                return (255 / 255.0, 215 / 255.0, 0 / 255.0)
            if cue_type == CueType.GROUP_MOVEMENT:
                return (64 / 255.0, 224 / 255.0, 208 / 255.0)
            if cue_type == CueType.FACILITATOR_ACTION:
                return (255 / 255.0, 165 / 255.0, 0 / 255.0)
            return (211 / 255.0, 211 / 255.0, 211 / 255.0)

        def compute_lanes(intervals: list[tuple[float, float]]) -> list[int]:
            """
            Generic greedy lane allocator.

            intervals: list of (start, end) times.
            Returns: lane index per interval.
            """
            n = len(intervals)
            if n == 0:
                return []

            indices = list(range(n))
            indices.sort(key=lambda i: intervals[i][0])

            lane_end_times: list[float] = []
            item_lane = [0] * n

            for i in indices:
                start, end = intervals[i]
                placed = False
                for lane_idx, lane_end in enumerate(lane_end_times):
                    if start >= lane_end:
                        item_lane[i] = lane_idx
                        lane_end_times[lane_idx] = end
                        placed = True
                        break

                if not placed:
                    item_lane[i] = len(lane_end_times)
                    lane_end_times.append(end)

            return item_lane

        # Rooms in show order (based on tab order)
        room_order: list[str] = [
            getattr(tab, "room_name", "Room")
            for tab in self._room_tabs
        ]

        # Map room -> its global items
        from collections import defaultdict
        items_by_room: dict[str, list[GlobalTimelineItem]] = defaultdict(list)
        for item in global_items:
            items_by_room[item.room_name].append(item)

        # Only rooms that actually have cues (but keep order)
        rooms_with_cues = [r for r in room_order if items_by_room.get(r)]
        if not rooms_with_cues:
            rooms_with_cues = room_order

        # ------------------------------------------------------
        # PAGE 1: title + GLOBAL GANTT (drawn from scratch)
        # ------------------------------------------------------
        if global_items:
            max_end = max(
                item.start_time + max(item.duration, 0.0) for item in global_items
            )
        else:
            max_end = 0.0

        y = page_height - margin
        c.setFont("Helvetica-Bold", 18)
        c.setFillColorRGB(0.08, 0.15, 0.30)
        c.drawString(margin, y, "Ash's Cue Planner – Global Timeline Overview")
        y -= 22

        c.setFont("Helvetica", 11)
        c.setFillColorRGB(0.18, 0.35, 0.65)
        c.drawString(
            margin,
            y,
            "Reception → Mecca – Combined Experience Gantt",
        )
        y -= 12

        c.setStrokeColorRGB(0.35, 0.45, 0.70)
        c.setLineWidth(1)
        c.line(margin, y, page_width - margin, y)
        y -= 20

        if not global_items or max_end <= 0.0:
            # No cues – just a message and move on to text pages
            c.setFont("Helvetica-Oblique", 12)
            c.setFillColorRGB(0.3, 0.3, 0.3)
            c.drawString(margin, y, "No cues defined – nothing to plot in the timeline.")
            c.showPage()
        else:
            # Chart geometry for global page
            chart_top = page_height - margin - 60
            chart_bottom = margin + 50
            chart_height = chart_top - chart_bottom

            chart_left = margin + 80   # room labels sit to the left of this
            chart_right = page_width - margin
            chart_width = chart_right - chart_left

            def x_for_time_global(t: float) -> float:
                """Map 0..max_end -> chart_left..chart_right for global page."""
                if max_end <= 0.0:
                    return chart_left
                t_clamped = max(0.0, min(t, max_end))
                return chart_left + (t_clamped / max_end) * chart_width

            # Per-room lanes for the global page
            room_lane_info: dict[str, tuple[list[int], int]] = {}
            total_lanes_global = 0
            for room_name in rooms_with_cues:
                items = items_by_room.get(room_name, [])
                if items:
                    intervals = [
                        (
                            it.start_time,
                            it.start_time + max(it.duration, 0.0),
                        )
                        for it in items
                    ]
                    lanes = compute_lanes(intervals)
                    num_lanes = max(lanes) + 1 if lanes else 1
                else:
                    lanes = []
                    num_lanes = 1
                room_lane_info[room_name] = (lanes, num_lanes)
                total_lanes_global += num_lanes

            # Vertical sizing for global page
            total_lanes_global = max(1, total_lanes_global)
            row_height = chart_height / float(total_lanes_global)
            bar_height = min(30.0, row_height * 0.65)

            c.setFont("Helvetica", 9)

            current_row_index = 0  # accumulates lanes vertically from the top

            for room_name in rooms_with_cues:
                items = items_by_room.get(room_name, [])
                lanes, num_lanes = room_lane_info[room_name]

                # Row range reserved for this room
                room_first_row = current_row_index
                room_last_row = current_row_index + max(1, num_lanes) - 1
                current_row_index += max(1, num_lanes)

                band_top_y = chart_top - row_height * room_first_row
                band_bottom_y = chart_top - row_height * (room_last_row + 1)

                # Room band background
                c.setFillColorRGB(0.96, 0.97, 0.99)
                c.setStrokeColorRGB(0.9, 0.92, 0.96)
                c.setLineWidth(0.3)
                c.rect(
                    chart_left,
                    band_bottom_y,
                    chart_width,
                    band_top_y - band_bottom_y,
                    stroke=0,
                    fill=1,
                )

                # Room name on left, centred over its band
                room_mid_row = (room_first_row + room_last_row) / 2.0
                room_label_center_y = chart_top - row_height * (room_mid_row + 0.5)
                c.setFillColorRGB(0.15, 0.2, 0.3)
                c.drawRightString(chart_left - 6, room_label_center_y - 3, room_name)

                # Separator at bottom of band
                c.setStrokeColorRGB(0.85, 0.88, 0.93)
                c.setLineWidth(0.3)
                c.line(chart_left, band_bottom_y, chart_right, band_bottom_y)

                if not items:
                    continue

                # Bars for this room
                for idx, item in enumerate(items):
                    lane_idx = lanes[idx] if idx < len(lanes) else 0
                    lane_row = room_first_row + lane_idx
                    lane_center_y = chart_top - row_height * (lane_row + 0.5)
                    bar_y = lane_center_y - bar_height / 2.0

                    cue = item.cue
                    start = item.start_time
                    end = start + max(item.duration, 0.0)
                    x0 = x_for_time_global(start)
                    x1 = x_for_time_global(end)
                    width = max(3.0, x1 - x0)

                    r, g, b = pdf_color_for_cue_type(cue.cue_type)
                    c.setFillColorRGB(r, g, b)
                    c.setStrokeColorRGB(0.1, 0.1, 0.1)
                    c.setLineWidth(0.3)
                    c.rect(x0, bar_y, width, bar_height, stroke=1, fill=1)

                    # Label inside the bar if there's room
                    if width > 40:
                        c.setFont("Helvetica", 7)
                        c.setFillColorRGB(0.05, 0.05, 0.05)
                        text_y = bar_y + bar_height / 2.0 - 3
                        label = cue.name
                        max_chars = int(width / 4.0)
                        if len(label) > max_chars:
                            label = label[: max_chars - 3] + "..."
                        c.drawString(x0 + 2, text_y, label)

            # Time axis
            axis_y = chart_bottom
            c.setStrokeColorRGB(0.35, 0.45, 0.70)
            c.setLineWidth(1.0)
            c.line(chart_left, axis_y, chart_right, axis_y)

            c.setFont("Helvetica", 8)
            c.setFillColorRGB(0.2, 0.2, 0.25)
            num_ticks = 10
            for i in range(num_ticks + 1):
                t = (max_end / num_ticks) * i
                x = x_for_time_global(t)
                c.setLineWidth(0.5)
                c.line(x, axis_y, x, axis_y + 4)
                label = self._format_seconds(t)
                c.drawCentredString(x, axis_y - 10, label)

            c.showPage()

        # ------------------------------------------------------
        # PER-ROOM PAGES: one local Gantt per room
        # ------------------------------------------------------
        for room_name in rooms_with_cues:
            stats = room_stats.get(room_name)
            if not stats:
                continue
            timeline_entries: list[tuple[float, MediaCue]] = stats.get("timeline", [])
            if not timeline_entries:
                continue

            # Compute local max end time
            max_room_end = 0.0
            intervals_room: list[tuple[float, float]] = []
            for start, cue in timeline_entries:
                dur = max(cue.duration_s, 0.0)
                end = start + dur
                intervals_room.append((start, end))
                max_room_end = max(max_room_end, end)

            if max_room_end <= 0.0:
                continue

            # Local lanes for this room
            room_lanes = compute_lanes(intervals_room)
            num_lanes_room = max(room_lanes) + 1 if room_lanes else 1

            # New page
            c.setPageSize(page_size)
            page_width, page_height = page_size
            y = page_height - margin

            c.setFont("Helvetica-Bold", 16)
            c.setFillColorRGB(0.12, 0.22, 0.40)
            c.drawString(margin, y, f"Room: {room_name} – Local Timeline")
            y -= 18

            c.setFont("Helvetica", 10)
            c.setFillColorRGB(0.25, 0.4, 0.7)
            c.drawString(
                margin,
                y,
                "Times measured from the start of this room only.",
            )
            y -= 12

            c.setStrokeColorRGB(0.35, 0.45, 0.70)
            c.setLineWidth(1)
            c.line(margin, y, page_width - margin, y)
            y -= 20

            # Chart geometry for room
            chart_top_r = page_height - margin - 60
            chart_bottom_r = margin + 45
            chart_height_r = chart_top_r - chart_bottom_r

            chart_left_r = margin + 30   # small left margin for y labels if needed
            chart_right_r = page_width - margin
            chart_width_r = chart_right_r - chart_left_r

            row_height_r = chart_height_r / float(max(1, num_lanes_room))
            bar_height_r = min(30.0, row_height_r * 0.7)

            def x_for_time_room(t: float) -> float:
                """Map 0..max_room_end -> chart_left_r..chart_right_r."""
                if max_room_end <= 0.0:
                    return chart_left_r
                t_clamped = max(0.0, min(t, max_room_end))
                return chart_left_r + (t_clamped / max_room_end) * chart_width_r

            # Draw bars
            c.setFont("Helvetica", 8)
            for idx, (start, cue) in enumerate(timeline_entries):
                lane_idx = room_lanes[idx] if idx < len(room_lanes) else 0
                lane_center_y = chart_top_r - row_height_r * (lane_idx + 0.5)
                bar_y = lane_center_y - bar_height_r / 2.0

                dur = max(cue.duration_s, 0.0)
                end = start + dur
                x0 = x_for_time_room(start)
                x1 = x_for_time_room(end)
                width = max(4.0, x1 - x0)

                r, g, b = pdf_color_for_cue_type(cue.cue_type)
                c.setFillColorRGB(r, g, b)
                c.setStrokeColorRGB(0.1, 0.1, 0.1)
                c.setLineWidth(0.4)
                c.rect(x0, bar_y, width, bar_height_r, stroke=1, fill=1)

                # Label inside bar
                if width > 40:
                    c.setFont("Helvetica", 7)
                    c.setFillColorRGB(0.05, 0.05, 0.05)
                    text_y = bar_y + bar_height_r / 2.0 - 3
                    label = cue.name
                    max_chars = int(width / 4.0)
                    if len(label) > max_chars:
                        label = label[: max_chars - 3] + "..."
                    c.drawString(x0 + 2, text_y, label)

            # Time axis for room
            axis_y_r = chart_bottom_r
            c.setStrokeColorRGB(0.35, 0.45, 0.70)
            c.setLineWidth(1.0)
            c.line(chart_left_r, axis_y_r, chart_right_r, axis_y_r)

            c.setFont("Helvetica", 8)
            c.setFillColorRGB(0.2, 0.2, 0.25)

            num_ticks_r = 8
            for i in range(num_ticks_r + 1):
                t = (max_room_end / num_ticks_r) * i
                x = x_for_time_room(t)
                c.setLineWidth(0.5)
                c.line(x, axis_y_r, x, axis_y_r + 4)
                label = self._format_seconds(t)
                c.drawCentredString(x, axis_y_r - 10, label)

            c.showPage()

        # ------------------------------------------------------
        # TEXT REPORT PAGES (reuse existing report text)
        # ------------------------------------------------------
        page_width, page_height = page_size
        y = page_height - margin

        report_text = self.summary_edit.toPlainText()
        lines = self._wrap_text(report_text, max_len=110)

        for raw in lines:
            line = raw.rstrip("\n")
            stripped = line.strip()

            if y < margin:
                c.showPage()
                page_width, page_height = page_size
                y = page_height - margin

            if not stripped:
                y -= 6
                continue

            is_top_heading = (
                stripped.isupper()
                and len(stripped) <= 70
            )

            is_room_heading = stripped.startswith("ROOM:")
            subheading_keywords = (
                "Cues by Cue Type",
                "Cues by Trigger Type",
                "Cues by Play Type",
                "By Cue Type",
                "By Trigger",
                "By Play Type",
                "Operator / design notes",
                "Timeline for this room",
            )
            is_subheading = any(
                stripped.lstrip().startswith(k) for k in subheading_keywords
            )

            if is_top_heading:
                c.setFont("Helvetica-Bold", 12)
                c.setFillColorRGB(0.18, 0.35, 0.65)
                c.drawString(margin, y, stripped)
                y -= 16
            elif is_room_heading:
                c.setFont("Helvetica-Bold", 11)
                c.setFillColorRGB(0.14, 0.30, 0.55)
                c.drawString(margin, y, stripped)
                y -= 14
            elif is_subheading:
                c.setFont("Helvetica-Bold", 9.5)
                c.setFillColorRGB(0.25, 0.40, 0.70)
                c.drawString(margin, y, stripped)
                y -= 12
            else:
                c.setFont("Helvetica", 9)
                c.setFillColorRGB(0.10, 0.10, 0.10)
                c.drawString(margin, y, line)
                y -= 11

        c.save()

        # Styled export-complete dialog
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("Export complete")
        msg.setIcon(QtWidgets.QMessageBox.Information)
        msg.setText(
            f"<span style='color:#0A0A0A; font-size:11pt;'>"
            f"PDF report exported to:<br>{path_str}"
            f"</span>"
        )
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #e6e6e6;
            }
            QMessageBox QLabel {
                color: #0A0A0A;
                font-size: 11pt;
            }
            QPushButton {
                background-color: #1f2f4a;
                color: #e6ebf5;
                border: 1px solid #283754;
                border-radius: 3px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #254064;
            }
            QPushButton:pressed {
                background-color: #1a2940;
            }
        """)
        msg.exec_()

















    @staticmethod
    def _wrap_text(text: str, max_len: int = 110) -> List[str]:
        """
        Simple word-wrapping for the PDF text output.

        Tries to preserve headings and indentation while wrapping long
        body lines to a reasonable width.
        """
        out_lines: List[str] = []
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()

            # Short lines (headings or bullets) are kept as-is.
            if len(stripped) <= max_len:
                out_lines.append(line)
                continue

            # Wrap only long lines, preserving leading indentation
            leading_spaces = len(line) - len(line.lstrip(" "))
            indent = " " * leading_spaces
            words = stripped.split(" ")

            current: List[str] = []
            current_len = 0
            for w in words:
                extra = len(w) + (1 if current else 0)
                if current_len + extra > max_len - leading_spaces:
                    out_lines.append(indent + " ".join(current))
                    current = [w]
                    current_len = len(w)
                else:
                    current.append(w)
                    current_len += extra
            if current:
                out_lines.append(indent + " ".join(current))

        return out_lines
