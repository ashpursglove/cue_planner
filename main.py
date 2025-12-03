

"""
main.py

Entry point for the Ash's cue planner (multi-room version).

Features:
    - Tabs for each room:
        * Reception
        * Aljuhfa Path
        * Immersive Room
        * Road to Yemen
        * Yemen Market
        * Road to North
        * Levant Souq
        * Fabric Room
        * Mecca
    - Each room tab is a RoomTab with:
        * Cue Type, Trigger, Play type, Start mode, dependency, duration, notes.
        * Multi-lane timeline with zoom/pan.
    - Summary tab:
        * Global timeline (Reception → Mecca)
        * Extremely detailed report
        * PDF export (landscape, with colours and graph)
    - File menu:
        * New      -> clears all rooms
        * Open     -> loads all rooms from JSON (by name)
        * Save     -> saves all rooms to JSON
        * Save As  -> same, but prompts for path
"""

import json
import sys
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

from room_tab import RoomTab
from summary_tab import SummaryTab
from models import ShowPlan, RoomPlan


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Ash's Cue Planner")
        self.resize(1200, 750)

        self.current_path: Path | None = None

        # Central widget: tabbed interface for all rooms + summary
        self.tab_widget = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tab_widget)

        # Keep references to all RoomTab instances for saving/loading
        self.room_tabs: list[RoomTab] = []
        self.summary_tab: SummaryTab | None = None

        self._create_tabs()
        self._create_menus()
        self._apply_basic_theme()

        # Refresh summary when switching to the summary tab
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    # ------------------------------------------------------------------
    # Tabs / Rooms
    # ------------------------------------------------------------------
    def _create_tabs(self) -> None:
        """
        Create a RoomTab for each room in the show, plus a Summary tab.

        Order is important and matches the physical flow:
            Reception
            Aljuhfa Path
            Immersive Room
            Road to Yemen
            Yemen Market
            Road to North
            Levant Souq
            Fabric Room
            Mecca
        """
        room_names = [
            "Reception",
            "Aljuhfa Path",
            "Immersive Room",
            "Road to Yemen",
            "Yemen Market",
            "Road to North",
            "Levant Souq",
            "Fabric Room",
            "Mecca",
        ]

        for name in room_names:
            tab = RoomTab(name, self)
            self.tab_widget.addTab(tab, name)
            self.room_tabs.append(tab)

        # Summary tab at the end
        self.summary_tab = SummaryTab(self.room_tabs, self)
        self.tab_widget.addTab(self.summary_tab, "Summary")

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------
    def _create_menus(self) -> None:
        """Set up the File and About menus."""
        menubar = self.menuBar()

        # ----- FILE MENU -----
        file_menu = menubar.addMenu("&File")

        new_action = QtWidgets.QAction("&New", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._new_file)

        open_action = QtWidgets.QAction("&Open...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_file)

        save_action = QtWidgets.QAction("&Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_file)

        save_as_action = QtWidgets.QAction("Save &As...", self)
        save_as_action.triggered.connect(self._save_file_as)

        exit_action = QtWidgets.QAction("E&xit", self)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        # ----- ABOUT MENU -----
        about_menu = menubar.addMenu("&About")

        about_action = QtWidgets.QAction("About Ash's Program", self)
        about_action.triggered.connect(self._show_about_dialog)

        about_menu.addAction(about_action)
    

    def _show_about_dialog(self) -> None:
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("About Ash's Cue Planner")

        # Use a dark readable colour for body text
        text = (
            "<span style='color:#0A0A0A; font-size:12pt;'>"
            "Written by Ash for Lina because Ocubo are SHIT!!!\n\n"
            "V1.0 -- 2/12/2025\n\n --  "
            "Ashley Pursglove"
            "</span>"
        )
        msg.setText(text)

        # Force the popup to have a decent readable style
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #e6e6e6;      /* light grey popup */
            }
            QMessageBox QLabel {
                color: #0A0A0A;                 /* dark text */
                font-size: 12pt;
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


    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def _apply_basic_theme(self) -> None:
        """
        Apply a dark-blue theme similar to the other tools.
        """
        app = QtWidgets.QApplication.instance()
        if app is None:
            return

        palette = QtGui.QPalette()

        # Dark navy base colors
        window_color = QtGui.QColor(10, 18, 30)      # main window background
        base_color = QtGui.QColor(15, 24, 38)        # text entry / tables
        alt_base_color = QtGui.QColor(22, 34, 52)    # alternating rows
        button_color = QtGui.QColor(25, 40, 65)      # buttons, group boxes
        text_color = QtGui.QColor(230, 235, 245)     # almost white, but softer

        palette.setColor(QtGui.QPalette.Window, window_color)
        palette.setColor(QtGui.QPalette.WindowText, text_color)
        palette.setColor(QtGui.QPalette.Base, base_color)
        palette.setColor(QtGui.QPalette.AlternateBase, alt_base_color)
        palette.setColor(QtGui.QPalette.ToolTipBase, base_color)
        palette.setColor(QtGui.QPalette.ToolTipText, text_color)
        palette.setColor(QtGui.QPalette.Text, text_color)
        palette.setColor(QtGui.QPalette.Button, button_color)
        palette.setColor(QtGui.QPalette.ButtonText, text_color)
        palette.setColor(QtGui.QPalette.BrightText, QtCore.Qt.red)

        # Highlights in a clean blue
        highlight = QtGui.QColor(0, 122, 204)
        palette.setColor(QtGui.QPalette.Highlight, highlight)
        palette.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.white)

        # Disabled-state colors
        disabled_text = QtGui.QColor(140, 150, 170)
        palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, disabled_text)
        palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, disabled_text)
        palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, disabled_text)

        app.setPalette(palette)

        # Slightly tweak menus, table header, group boxes, etc. via stylesheet
        self.setStyleSheet("""
        QMainWindow {
            background-color: #0a121e;
        }
        QMenuBar {
            background-color: #0a121e;
            color: #e6ebf5;
        }
        QMenuBar::item {
            background: transparent;
            color: #e6ebf5;
        }
        QMenuBar::item:selected {
            background: #1f2f4a;
        }
        QMenu {
            background-color: #0f1826;
            color: #e6ebf5;
            border: 1px solid #283754;
        }
        QMenu::item:selected {
            background-color: #254064;
        }
        QTabWidget::pane {
            border: 1px solid #1f2a3e;
        }
        QTabBar::tab {
            background: #182338;
            color: #e6ebf5;
            padding: 6px 10px;
        }
        QTabBar::tab:selected {
            background: #1f2f4a;
        }
        QHeaderView::section {
            background-color: #1f2f4a;
            color: #e6ebf5;
            padding: 4px;
            border: 1px solid #141c2b;
        }
        QGroupBox {
            border: 1px solid #1f2a3e;
            border-radius: 4px;
            margin-top: 8px;
            background-color: #111a29;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 3px 0 3px;
        }
        QTableWidget {
            gridline-color: #283754;
            background-color: #0f1826;
            alternate-background-color: #182338;
            color: #e6ebf5;
            selection-background-color: #005a9e;
            selection-color: #ffffff;
        }
        QLineEdit, QDoubleSpinBox, QComboBox {
            background-color: #0f1826;
            color: #e6ebf5;
            border: 1px solid #283754;
            border-radius: 2px;
            padding: 2px 4px;
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

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------
    def _new_file(self) -> None:
        """Clear all cues in all rooms and reset current path."""
        for tab in self.room_tabs:
            tab.set_cues([])
        if self.summary_tab is not None:
            self.summary_tab.refresh_summary()
        self.current_path = None
        self._update_window_title()

    def _open_file(self) -> None:
        """Open a JSON show file and populate all room tabs."""
        path_str, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open show file",
            "",
            "JSON files (*.json);;All files (*.*)",
        )
        if not path_str:
            return

        path = Path(path_str)
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            plan = ShowPlan.from_dict(data)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to open file:\n{exc}")
            return

        # Map room names to their tabs
        tab_by_name = {tab.room_name: tab for tab in self.room_tabs}

        # First clear everything
        for tab in self.room_tabs:
            tab.set_cues([])

        # Then populate any matching rooms from the file
        for room_plan in plan.rooms:
            tab = tab_by_name.get(room_plan.name)
            if tab is not None:
                tab.set_cues(room_plan.cues)

        if self.summary_tab is not None:
            self.summary_tab.refresh_summary()

        self.current_path = path
        self._update_window_title()

    def _save_file(self) -> None:
        """Save to the current path, or prompt for a path if none."""
        if self.current_path is None:
            self._save_file_as()
            return

        self._write_to_path(self.current_path)

    def _save_file_as(self) -> None:
        """Prompt the user for a path and save there."""
        path_str, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save show file",
            "",
            "JSON files (*.json);;All files (*.*)",
        )
        if not path_str:
            return

        path = Path(path_str)
        # Ensure .json extension
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")

        self._write_to_path(path)
        self.current_path = path
        self._update_window_title()

    def _write_to_path(self, path: Path) -> None:
        """Serialize current state (all rooms) to JSON and write to disk."""
        rooms: list[RoomPlan] = []
        for tab in self.room_tabs:
            rooms.append(RoomPlan(name=tab.room_name, cues=tab.get_cues()))

        plan = ShowPlan(rooms=rooms)

        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(plan.to_dict(), f, indent=2)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save file:\n{exc}")

    def _update_window_title(self) -> None:
        """Update the window title to include the current file name, if any."""
        base = "Ash's Cue Planner – Simple"
        if self.current_path is None:
            self.setWindowTitle(base)
        else:
            self.setWindowTitle(f"{base} [{self.current_path.name}]")

    # ------------------------------------------------------------------
    # Tab change handler
    # ------------------------------------------------------------------
    def _on_tab_changed(self, index: int) -> None:
        """
        When switching to the Summary tab, refresh it so it always reflects
        the latest room data.
        """
        widget = self.tab_widget.widget(index)
        if self.summary_tab is not None and widget is self.summary_tab:
            self.summary_tab.refresh_summary()


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Ash's Cue Planner")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
