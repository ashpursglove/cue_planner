

"""
room_tab.py

Defines RoomTab, a QWidget that manages the cues for a single room.

Layout:
    [ Cue Form ]
    [ Cue Table ]
    [ Timeline Graph ]

The timeline graph is a QGraphicsView (TimelineView) that draws:
    - Time axis in seconds.
    - Vertical grid lines.
    - One bar per cue, positioned according to its effective start time
      (via compute_schedule) and duration.

Features:
    - Bars use multiple "lanes" so overlapping cues don't overlap visually.
    - Dependency dropdown (AFTER_CUE: start after another cue ends).
    - PlayType dropdown (play once / loop / ambient).
    - StartMode dropdown:
        * At fixed time
        * After previous cue
        * After specific cue
    - Zoomable & scrollable timeline:
        * Mouse wheel = zoom in/out (under mouse)
        * Drag with left mouse = pan (scroll hand drag)
    - JSON save/load handled by main window (via get_cues / set_cues).
"""

from __future__ import annotations

from typing import List

from PyQt5 import QtCore, QtGui, QtWidgets

from models import (
    CueType,
    TriggerType,
    PlayType,
    StartMode,
    MediaCue,
    compute_schedule,
)


# ---------------------------------------------------------------------------
# Per-room timeline view
# ---------------------------------------------------------------------------

class TimelineView(QtWidgets.QGraphicsView):
    """
    Timeline visualization for a list of MediaCue objects.

    It draws:
        - Horizontal time axis.
        - Vertical grid lines.
        - One bar per cue, positioned according to its effective start time
          and duration, with overlapping cues pushed onto separate "lanes".

    Interaction:
        - Mouse wheel: zoom in/out around the cursor.
        - Left mouse drag: pan/scroll the view (hand tool).
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)

        # Dark background to match the global theme
        self._scene.setBackgroundBrush(QtGui.QColor(15, 24, 38))

        # List of cues and their computed start times.
        self._cues: List[MediaCue] = []
        self._start_times: List[float] = []

        # Visual settings
        self._pixels_per_second: float = 8.0
        self._bar_height: float = 30.0
        self._lane_gap: float = 10.0
        self._top_margin: float = 40.0
        self._left_margin: float = 60.0
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.setMinimumHeight(220)

        # Interaction settings for zoom & pan
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)

        # Track whether the user has manually zoomed
        self._has_manual_zoom: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_cues(self, cues: List[MediaCue]) -> None:
        """
        Update the cues to be drawn and refresh the scene.

        This calls compute_schedule(cues) so that:
            - AT_TIME uses start_time_s
            - AFTER_PREVIOUS starts after the previous cue
            - AFTER_CUE starts after a named earlier cue
        """
        self._cues = cues
        self._start_times = compute_schedule(cues)
        self._redraw()

    def render_to_image(self, width: int = 2000, height: int = 400) -> QtGui.QImage:
        """
        Render the current per-room timeline scene into a QImage.

        Used for PDF export so we can draw one large, readable graph per room.
        This ignores the user's current zoom level and always renders the full
        sceneRect into the requested width/height.
        """
        image = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor(15, 24, 38))  # match the dark background

        painter = QtGui.QPainter(image)
        target_rect = QtCore.QRectF(0, 0, width, height)

        source_rect = self._scene.sceneRect()
        if source_rect.width() <= 0 or source_rect.height() <= 0:
            # Fallback in case the scene hasn't been laid out yet
            source_rect = QtCore.QRectF(0, 0, width, height)

        self._scene.render(painter, target=target_rect, source=source_rect)
        painter.end()

        return image

    # ------------------------------------------------------------------
    # Zoom handling
    # ------------------------------------------------------------------
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # type: ignore[override]
        """
        Use mouse wheel to zoom in/out around the cursor.

        Default behaviour is scrolling; we override to zoom which feels
        more natural for a timeline.
        """
        # AngleDelta is in eighths of a degree; y > 0 means scroll up (zoom in)
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return

        zoom_factor = 1.2 if delta > 0 else 1 / 1.2
        self._has_manual_zoom = True
        self.scale(zoom_factor, zoom_factor)
        event.accept()

    # ------------------------------------------------------------------
    # Internal layout / drawing
    # ------------------------------------------------------------------
    def _compute_lanes(self) -> List[int]:
        """
        Assign each cue to a "lane" (row) based on overlaps.

        Greedy interval-graph colouring:
            - Sort by start time.
            - For each cue, place it in the first lane that has finished
              before this cue starts; otherwise create a new lane.
        Returns:
            lane_index per cue (same ordering as self._cues).
        """
        n = len(self._cues)
        if n == 0:
            return []

        indices = list(range(n))
        indices.sort(key=lambda i: self._start_times[i])

        lane_end_times: List[float] = []  # end time per lane
        cue_lane = [0] * n

        for i in indices:
            start = self._start_times[i]
            duration = max(self._cues[i].duration_s, 0.0)
            end = start + duration

            placed = False
            for lane_idx, lane_end in enumerate(lane_end_times):
                if start >= lane_end:
                    cue_lane[i] = lane_idx
                    lane_end_times[lane_idx] = end
                    placed = True
                    break

            if not placed:
                cue_lane[i] = len(lane_end_times)
                lane_end_times.append(end)

        return cue_lane

    def _redraw(self) -> None:
        """Clear and redraw the entire timeline."""
        self._scene.clear()
        self._scene.setBackgroundBrush(QtGui.QColor(15, 24, 38))

        if not self._cues:
            return

        # Compute max time extent to size the view and axis.
        max_end = 0.0
        for cue, start in zip(self._cues, self._start_times):
            duration = max(cue.duration_s, 0.0)
            end = start + duration
            max_end = max(max_end, end)

        # Always show at least 10 seconds for some sense of scale
        max_end = max(max_end, 10.0)

        cue_lanes = self._compute_lanes()
        num_lanes = max(cue_lanes) + 1 if cue_lanes else 1

        total_width = self._left_margin + max_end * self._pixels_per_second + 40.0
        total_height = (
            self._top_margin
            + num_lanes * (self._bar_height + self._lane_gap)
            + 80.0
        )

        self._scene.setSceneRect(0, 0, total_width, total_height)

        # Colors used for axis/text
        axis_color = QtGui.QColor(220, 230, 245)
        grid_color = QtGui.QColor(90, 105, 135)
        text_color = QtGui.QColor(230, 235, 245)

        # Draw time axis
        axis_y = self._top_margin + num_lanes * (self._bar_height + self._lane_gap)
        axis_pen = QtGui.QPen(axis_color)
        self._scene.addLine(
            self._left_margin,
            axis_y,
            self._left_margin + max_end * self._pixels_per_second,
            axis_y,
            axis_pen,
        )

        # Draw grid and labels every 5 seconds.
        grid_pen = QtGui.QPen(grid_color)
        grid_pen.setStyle(QtCore.Qt.DashLine)
        label_font = QtGui.QFont("Segoe UI", 8)

        tick_step = 5
        num_ticks = int(max_end // tick_step) + 1
        for i in range(num_ticks + 1):
            t = i * tick_step
            x = self._left_margin + t * self._pixels_per_second

            # Vertical grid line
            self._scene.addLine(
                x,
                self._top_margin - 10.0,
                x,
                axis_y,
                grid_pen,
            )

            # Time label
            text_item = self._scene.addText(f"{t}s", label_font)
            text_item.setDefaultTextColor(text_color)
            text_rect = text_item.boundingRect()
            text_item.setPos(x - text_rect.width() / 2.0, axis_y + 4.0)

        # Draw cue bars
        bar_pen = QtGui.QPen(QtGui.QColor(10, 10, 10))
        label_font_cue = QtGui.QFont("Segoe UI", 9)

        for idx, (cue, start) in enumerate(zip(self._cues, self._start_times)):
            lane_idx = cue_lanes[idx]
            color = self._color_for_cue_type(cue.cue_type)
            brush = QtGui.QBrush(color)

            bar_x = self._left_margin + start * self._pixels_per_second
            bar_y = self._top_margin + lane_idx * (self._bar_height + self._lane_gap)
            bar_width = max(cue.duration_s * self._pixels_per_second, 20.0)

            rect_item = self._scene.addRect(
                bar_x,
                bar_y,
                bar_width,
                self._bar_height,
                bar_pen,
                brush,
            )
            rect_item.setToolTip(
                f"{cue.name}\n"
                f"{cue.cue_type.value} | {cue.trigger_type.value} | {cue.play_type.value}\n"
                f"Start: {start:.1f}s  Duration: {cue.duration_s:.1f}s"
            )

            # Cue label text (inside the bar if possible)
            label = f"{cue.name}"
            text_item = self._scene.addText(label, label_font_cue)
            text_item.setDefaultTextColor(QtGui.QColor(10, 10, 10))
            text_rect = text_item.boundingRect()
            text_x = bar_x + 4.0
            text_y = bar_y + (self._bar_height - text_rect.height()) / 2.0
            text_item.setPos(text_x, text_y)

        # Initial view / scaling behaviour:
        # - For relatively short timelines we auto-fit everything.
        # - For long timelines (>150 s) we keep a 1:1 scale so text stays
        #   readable and let the user scroll horizontally instead.
        if not self._has_manual_zoom:
            self.resetTransform()
            if max_end <= 150.0:
                self.fitInView(self._scene.sceneRect(), QtCore.Qt.KeepAspectRatio)
            else:
                # Show the start of the timeline by default
                self.centerOn(
                    self._left_margin,
                    self._scene.sceneRect().center().y(),
                )

    @staticmethod
    def _color_for_cue_type(cue_type: CueType) -> QtGui.QColor:
        """Return a stable color associated with each cue type."""
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
# RoomTab widget
# ---------------------------------------------------------------------------

class RoomTab(QtWidgets.QWidget):
    """
    RoomTab encapsulates the UI and logic for editing cues in one room.

    Exposes:
        - room_name: str
        - get_cues() -> List[MediaCue]
        - set_cues(cues: List[MediaCue]) -> None
        - export_timeline_image(width, height) -> QImage
    """

    def export_timeline_image(self, width: int = 2500, height: int = 600) -> QtGui.QImage:
        """
        Export THIS room's timeline as an image for PDF export.

        We temporarily increase bar height and lane gap so that in the PDF
        the bars and labels are much more readable, then restore them for
        normal GUI use.
        """
        tv = self.timeline_view

        # Save old sizes
        old_bar_height = tv._bar_height
        old_lane_gap = tv._lane_gap

        # Make everything chunkier for print
        tv._bar_height = 40
        tv._lane_gap = 16
        tv._redraw()

        image = tv.render_to_image(width=width, height=height)

        # Restore GUI sizes
        tv._bar_height = old_bar_height
        tv._lane_gap = old_lane_gap
        tv._redraw()

        return image

    def __init__(self, room_name: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.room_name = room_name

        # Internal list of cues
        self._cues: List[MediaCue] = []

        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)

        # ---------- Form for adding/editing cues ----------
        form_group = QtWidgets.QGroupBox(f"{self.room_name} – Cues")
        form_layout = QtWidgets.QGridLayout(form_group)

        # Name
        self.name_edit = QtWidgets.QLineEdit()
        form_layout.addWidget(QtWidgets.QLabel("Name:"), 0, 0)
        form_layout.addWidget(self.name_edit, 0, 1, 1, 5)

        # Cue type
        self.cue_type_combo = QtWidgets.QComboBox()
        for ct in CueType:
            self.cue_type_combo.addItem(ct.value, ct)
        form_layout.addWidget(QtWidgets.QLabel("Cue Type:"), 1, 0)
        form_layout.addWidget(self.cue_type_combo, 1, 1)

        # Trigger type
        self.trigger_type_combo = QtWidgets.QComboBox()
        for tt in TriggerType:
            self.trigger_type_combo.addItem(tt.value, tt)
        form_layout.addWidget(QtWidgets.QLabel("Trigger:"), 1, 2)
        form_layout.addWidget(self.trigger_type_combo, 1, 3)

        # Play type
        self.play_type_combo = QtWidgets.QComboBox()
        for pt in PlayType:
            self.play_type_combo.addItem(pt.value, pt)
        form_layout.addWidget(QtWidgets.QLabel("Play type:"), 1, 4)
        form_layout.addWidget(self.play_type_combo, 1, 5)

        # Start mode
        self.start_mode_combo = QtWidgets.QComboBox()
        for sm in StartMode:
            self.start_mode_combo.addItem(sm.value, sm)
        form_layout.addWidget(QtWidgets.QLabel("Start mode:"), 2, 0)
        form_layout.addWidget(self.start_mode_combo, 2, 1)

        # Start time (seconds)
        self.start_time_spin = QtWidgets.QDoubleSpinBox()
        self.start_time_spin.setRange(0.0, 36000.0)  # up to 10 hours
        self.start_time_spin.setDecimals(1)
        self.start_time_spin.setSingleStep(0.5)
        form_layout.addWidget(QtWidgets.QLabel("Start time (s):"), 2, 2)
        form_layout.addWidget(self.start_time_spin, 2, 3)

        # Dependency (for AFTER_CUE)
        self.dependency_combo = QtWidgets.QComboBox()
        self.dependency_combo.addItem("None", None)
        form_layout.addWidget(QtWidgets.QLabel("Depends on:"), 2, 4)
        form_layout.addWidget(self.dependency_combo, 2, 5)

        # Duration (seconds)
        self.duration_spin = QtWidgets.QDoubleSpinBox()
        self.duration_spin.setRange(0.0, 36000.0)
        self.duration_spin.setDecimals(1)
        self.duration_spin.setSingleStep(1.0)
        form_layout.addWidget(QtWidgets.QLabel("Duration (s):"), 3, 0)
        form_layout.addWidget(self.duration_spin, 3, 1)

        # Notes
        self.notes_edit = QtWidgets.QLineEdit()
        form_layout.addWidget(QtWidgets.QLabel("Notes:"), 3, 2)
        form_layout.addWidget(self.notes_edit, 3, 3, 1, 3)

        # Buttons
        self.add_button = QtWidgets.QPushButton("Add cue")
        self.remove_button = QtWidgets.QPushButton("Remove selected")

        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.addWidget(self.add_button)
        buttons_layout.addWidget(self.remove_button)
        buttons_layout.addStretch()

        form_layout.addLayout(buttons_layout, 4, 0, 1, 6)

        main_layout.addWidget(form_group)

        # ---------- Table ----------
        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "Name",
            "Cue Type",
            "Trigger",
            "Play type",
            "Start mode",
            "Depends on",
            "Start time (s)",
            "Duration (s)",
            "Notes",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        main_layout.addWidget(self.table)

        # ---------- Timeline ----------
        self.timeline_view = TimelineView()
        timeline_group = QtWidgets.QGroupBox("Timeline")
        timeline_layout = QtWidgets.QVBoxLayout(timeline_group)
        timeline_layout.addWidget(self.timeline_view)

        main_layout.addWidget(timeline_group)

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------
    def _connect_signals(self) -> None:
        self.add_button.clicked.connect(self._on_add_cue)
        self.remove_button.clicked.connect(self._on_remove_selected)
        self.start_mode_combo.currentIndexChanged.connect(self._on_start_mode_changed)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_start_mode_changed(self) -> None:
        """
        Enable/disable the start time and dependency fields based on
        the selected start mode.
        """
        sm = self._current_start_mode()
        is_at_time = sm == StartMode.AT_TIME
        is_after_cue = sm == StartMode.AFTER_CUE

        self.start_time_spin.setEnabled(is_at_time)
        self.dependency_combo.setEnabled(is_after_cue)

    def _on_add_cue(self) -> None:
        """Create a new MediaCue from the form and append it to the list."""
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing name", "Please enter a cue name.")
            return

        cue_type = self._current_cue_type()
        trigger_type = self._current_trigger_type()
        play_type = self._current_play_type()
        start_mode = self._current_start_mode()
        start_time_s = float(self.start_time_spin.value())
        duration_s = float(self.duration_spin.value())
        notes = self.notes_edit.text().strip()

        dependency_name = None
        if start_mode == StartMode.AFTER_CUE:
            dep_idx = self.dependency_combo.currentIndex()
            dependency_name = self.dependency_combo.itemData(dep_idx, QtCore.Qt.UserRole)

        cue = MediaCue(
            name=name,
            cue_type=cue_type,
            trigger_type=trigger_type,
            play_type=play_type,
            start_mode=start_mode,
            start_time_s=start_time_s,
            duration_s=duration_s,
            dependency_name=dependency_name,
            notes=notes,
        )
        self._cues.append(cue)

        self._refresh_table()
        self._refresh_dependency_combo()
        self._refresh_timeline()

    def _on_remove_selected(self) -> None:
        """Remove the currently selected cue from the list."""
        row = self.table.currentRow()
        if row < 0 or row >= len(self._cues):
            return
        del self._cues[row]
        self._refresh_table()
        self._refresh_dependency_combo()
        self._refresh_timeline()

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------
    def _current_cue_type(self) -> CueType:
        idx = self.cue_type_combo.currentIndex()
        return self.cue_type_combo.itemData(idx, QtCore.Qt.UserRole)

    def _current_trigger_type(self) -> TriggerType:
        idx = self.trigger_type_combo.currentIndex()
        return self.trigger_type_combo.itemData(idx, QtCore.Qt.UserRole)

    def _current_play_type(self) -> PlayType:
        idx = self.play_type_combo.currentIndex()
        return self.play_type_combo.itemData(idx, QtCore.Qt.UserRole)

    def _current_start_mode(self) -> StartMode:
        idx = self.start_mode_combo.currentIndex()
        return self.start_mode_combo.itemData(idx, QtCore.Qt.UserRole)

    def _refresh_table(self) -> None:
        """Rebuild the QTableWidget to reflect the internal cue list."""
        self.table.setRowCount(len(self._cues))
        for row, cue in enumerate(self._cues):
            dep_text = cue.dependency_name or ""
            data = [
                cue.name,
                cue.cue_type.value,
                cue.trigger_type.value,
                cue.play_type.value,
                cue.start_mode.value,
                dep_text,
                f"{cue.start_time_s:.1f}",
                f"{cue.duration_s:.1f}",
                cue.notes,
            ]
            for col, value in enumerate(data):
                item = QtWidgets.QTableWidgetItem(value)
                self.table.setItem(row, col, item)

    def _refresh_timeline(self) -> None:
        """Redraw the timeline view with the current cues."""
        self.timeline_view.set_cues(self._cues)

    def _refresh_dependency_combo(self) -> None:
        """
        Refresh the 'Depends on' dropdown to list all existing cues.

        Only cues that already exist can be chosen as dependencies.
        """
        current_name = self.dependency_combo.currentText()
        self.dependency_combo.blockSignals(True)
        self.dependency_combo.clear()
        self.dependency_combo.addItem("None", None)
        for cue in self._cues:
            self.dependency_combo.addItem(cue.name, cue.name)

        # Try to restore previous selection if it still exists
        idx = self.dependency_combo.findText(current_name)
        if idx >= 0:
            self.dependency_combo.setCurrentIndex(idx)
        self.dependency_combo.blockSignals(False)

    # Public API (for saving/loading)
    def get_cues(self) -> List[MediaCue]:
        """Return a copy of the cues list."""
        return list(self._cues)

    def set_cues(self, cues: List[MediaCue]) -> None:
        """Replace the cue list and refresh the UI."""
        self._cues = list(cues)
        self._refresh_table()
        self._refresh_dependency_combo()
        self._refresh_timeline()
