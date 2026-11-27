"""PySide6 Desktop GUI for Interactive Process Mining Exploration."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Set

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
import pandas as pd

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    QThread,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from bpic17_app.analyzer import (
    AnalysisBundle,
    analyze_fast_slow,
    export_dataframe_csv,
    export_summary_csv,
    filter_by_activity_rule,
    filter_rework_and_resource,
    filter_sequence_relation,
    get_case_trace,
    get_environment_info,
    run_full_analysis,
)
from bpic17_app.discovery import DiscoveryResult, discover_process_model
from bpic17_app.graph_view import ProcessGraphView


APP_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0f172a;
    color: #e2e8f0;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}
QFrame#Card {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 8px;
}
QFrame#FilterBar {
    background-color: #172554;
    border: 1px solid #1d4ed8;
    border-radius: 8px;
    padding: 8px;
}
QLabel#CardTitle {
    color: #94a3b8;
    font-size: 11px;
    font-weight: 600;
}
QLabel#CardValue {
    color: #f8fafc;
    font-size: 20px;
    font-weight: 700;
}
QLabel#CardSub {
    color: #38bdf8;
    font-size: 11px;
}
QPushButton {
    background-color: #2563eb;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #1d4ed8;
}
QPushButton:disabled {
    background-color: #334155;
    color: #64748b;
}
QPushButton#SecondaryBtn {
    background-color: #334155;
    color: #e2e8f0;
}
QPushButton#SecondaryBtn:hover {
    background-color: #475569;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #475569;
    border-radius: 5px;
    padding: 5px 8px;
}
QCheckBox {
    color: #e2e8f0;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #334155;
    border-radius: 6px;
    background-color: #0f172a;
}
QTabBar::tab {
    background-color: #1e293b;
    color: #94a3b8;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background-color: #2563eb;
    color: #ffffff;
}
QTableView {
    background-color: #1e293b;
    alternate-background-color: #162032;
    color: #e2e8f0;
    gridline-color: #334155;
    border: 1px solid #334155;
    border-radius: 6px;
    selection-background-color: #1d4ed8;
    selection-color: #ffffff;
}
QHeaderView::section {
    background-color: #0f172a;
    color: #94a3b8;
    padding: 6px;
    border: 1px solid #334155;
    font-weight: 700;
}
QProgressBar {
    border: 1px solid #334155;
    border-radius: 5px;
    text-align: center;
    background-color: #1e293b;
    color: #f8fafc;
}
QProgressBar::chunk {
    background-color: #2563eb;
    border-radius: 4px;
}
"""


DEFAULT_HIGHLIGHT_ACTIVITIES = {
    "O_Accepted",
    "O_Refused",
    "O_Cancelled",
    "W_Assess Potential Fraud",
    "W_Assess potential fraud",
}


class PandasTableModel(QAbstractTableModel):
    """Virtualized table model backed by a pandas DataFrame."""

    def __init__(
        self,
        df: Optional[pd.DataFrame] = None,
        highlight_activities: Optional[Set[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()
        self._highlight = highlight_activities or set()

    def set_dataframe(
        self,
        df: pd.DataFrame,
        highlight_activities: Optional[Set[str]] = None,
    ) -> None:
        self.beginResetModel()
        self._df = df.reset_index(drop=True) if df is not None else pd.DataFrame()
        if highlight_activities is not None:
            self._highlight = highlight_activities
        self.endResetModel()

    def dataframe(self) -> pd.DataFrame:
        return self._df

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        val = self._df.iat[row, col]

        if role == Qt.DisplayRole:
            if pd.isna(val):
                return ""
            if isinstance(val, (float, np.floating)):
                return f"{float(val):,.2f}"
            if isinstance(val, (int, np.integer)):
                return f"{int(val):,}"
            return str(val)

        if role == Qt.EditRole:
            if pd.isna(val):
                return ""
            if isinstance(val, (float, np.floating)):
                return float(val)
            if isinstance(val, (int, np.integer)):
                return int(val)
            return str(val)

        if role == Qt.BackgroundRole and self._highlight:
            if "activity" in self._df.columns:
                act_val = str(self._df.iloc[row]["activity"])
                if act_val in self._highlight:
                    if act_val == "O_Accepted":
                        return QColor("#064e3b")
                    if act_val == "O_Cancelled":
                        return QColor("#7f1d1d")
                    if act_val == "O_Refused":
                        return QColor("#78350f")
                    return QColor("#1e3a8a")
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ) -> Any:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and section < len(self._df.columns):
            return str(self._df.columns[section])
        if orientation == Qt.Vertical:
            return str(section + 1)
        return None


class AnalysisWorker(QThread):
    """Background worker thread so XES parsing never freezes the desktop UI."""

    progress = Signal(str, int)
    finished_bundle = Signal(object)
    failed = Signal(str)

    def __init__(self, file_path: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.file_path = file_path

    def run(self) -> None:
        try:
            bundle = run_full_analysis(
                self.file_path,
                progress_cb=lambda msg, pct: self.progress.emit(msg, pct),
            )
            self.finished_bundle.emit(bundle)
        except Exception as exc:
            self.failed.emit(str(exc))


class DiscoveryWorker(QThread):
    """Background worker for running PM4Py discovery algorithms without blocking UI."""

    finished_result = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        df: pd.DataFrame,
        algorithm: str,
        lifecycle: str,
        top_k_variants: int,
        min_edge_freq: int,
        dependency_threshold: float,
        noise_threshold: float,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._df = df
        self._algorithm = algorithm
        self._lifecycle = lifecycle
        self._top_k = top_k_variants
        self._min_freq = min_edge_freq
        self._dep = dependency_threshold
        self._noise = noise_threshold

    def run(self) -> None:
        try:
            res = discover_process_model(
                self._df,
                algorithm=self._algorithm,
                lifecycle=self._lifecycle,
                top_k_variants=self._top_k,
                min_edge_freq=self._min_freq,
                dependency_threshold=self._dep,
                noise_threshold=self._noise,
            )
            self.finished_result.emit(res)
        except Exception as exc:
            self.failed.emit(str(exc))


class KpiCard(QFrame):
    """Compact metric card displaying title, primary value, and subtitle."""

    def __init__(
        self,
        title: str,
        value: str = "-",
        subtitle: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("CardTitle")
        self.value_lbl = QLabel(value)
        self.value_lbl.setObjectName("CardValue")
        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setObjectName("CardSub")
        self.sub_lbl.setWordWrap(True)

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.value_lbl)
        layout.addWidget(self.sub_lbl)

    def set_metrics(self, value: str, subtitle: str = "") -> None:
        self.value_lbl.setText(value)
        self.sub_lbl.setText(subtitle)


class SearchableTableWidget(QWidget):
    """Reusable table view with instant search filter, row count label, and CSV export."""

    case_selected = Signal(str)

    def __init__(
        self,
        title: str,
        enable_inspect_btn: bool = False,
        highlight_activities: Optional[Set[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        self.title_lbl = QLabel(f"<b>{title}</b>")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search rows...")
        self.count_lbl = QLabel("0 rows")

        header_row.addWidget(self.title_lbl)
        header_row.addStretch()
        header_row.addWidget(self.search_input)
        header_row.addWidget(self.count_lbl)

        if enable_inspect_btn:
            self.inspect_btn = QPushButton("Inspect Case in Explorer")
            self.inspect_btn.clicked.connect(self._emit_selected_case)
            header_row.addWidget(self.inspect_btn)
        else:
            self.inspect_btn = None

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("SecondaryBtn")
        self.export_btn.clicked.connect(self._export_csv)
        header_row.addWidget(self.export_btn)

        layout.addLayout(header_row)

        self.model = PandasTableModel(highlight_activities=highlight_activities)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setSortRole(Qt.EditRole)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True)
        self.proxy.sort(-1)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.doubleClicked.connect(self._on_double_click)

        self.search_input.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.table)

    def set_dataframe(
        self,
        df: pd.DataFrame,
        highlight_activities: Optional[Set[str]] = None,
    ) -> None:
        self.proxy.sort(-1)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self.model.set_dataframe(df, highlight_activities=highlight_activities)
        self._resize_columns_fast(df)
        self._update_count()

    def _resize_columns_fast(self, df: Optional[pd.DataFrame]) -> None:
        """Size columns from header + first 50 rows in O(1) instead of scanning 31k+ rows."""
        if df is None or df.empty:
            return
        fm = QFontMetrics(self.table.font())
        sample = df.head(50)
        for col_idx, col_name in enumerate(df.columns):
            max_w = fm.horizontalAdvance(str(col_name)) + 28
            for val in sample.iloc[:, col_idx]:
                if pd.isna(val):
                    continue
                s = f"{float(val):,.2f}" if isinstance(val, (float, np.floating)) else (
                    f"{int(val):,}" if isinstance(val, (int, np.integer)) else str(val)
                )
                w = fm.horizontalAdvance(s[:48]) + 24
                if w > max_w:
                    max_w = w
            self.table.setColumnWidth(col_idx, max(80, min(320, max_w)))

    def _on_search_changed(self, text: str) -> None:
        self.proxy.setFilterFixedString(text)
        self._update_count()

    def _update_count(self) -> None:
        shown = self.proxy.rowCount()
        total = self.model.rowCount()
        self.count_lbl.setText(f"{shown:,} / {total:,} rows")

    def get_selected_case_id(self) -> Optional[str]:
        df = self.model.dataframe()
        if df.empty or "case_id" not in df.columns:
            return None
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            if self.proxy.rowCount() > 0:
                src_idx = self.proxy.mapToSource(self.proxy.index(0, 0))
                return str(df.iloc[src_idx.row()]["case_id"])
            return None
        src_idx = self.proxy.mapToSource(indexes[0])
        return str(df.iloc[src_idx.row()]["case_id"])

    def _emit_selected_case(self) -> None:
        cid = self.get_selected_case_id()
        if cid:
            self.case_selected.emit(cid)

    def _on_double_click(self, proxy_index: QModelIndex) -> None:
        df = self.model.dataframe()
        if "case_id" in df.columns and proxy_index.isValid():
            src_idx = self.proxy.mapToSource(proxy_index)
            cid = str(df.iloc[src_idx.row()]["case_id"])
            self.case_selected.emit(cid)

    def _export_csv(self) -> None:
        df = self.model.dataframe()
        if df.empty:
            QMessageBox.information(self, "Export CSV", "No table data to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Table to CSV", "analysis_table.csv", "CSV Files (*.csv)"
        )
        if path:
            export_dataframe_csv(df, path)
            QMessageBox.information(
                self, "Export CSV", f"Saved {len(df):,} rows to:\n{path}"
            )


class MainWindow(QMainWindow):
    """Main Process Mining Explorer window with interactive, user-driven filter tabs."""

    def __init__(self, initial_xes: Optional[str] = None) -> None:
        super().__init__()
        self.setWindowTitle("PM4Py Process Mining & Event Log Explorer")
        self.resize(1380, 860)
        self.setStyleSheet(APP_STYLESHEET)

        self.bundle: Optional[AnalysisBundle] = None
        self.worker: Optional[AnalysisWorker] = None
        self.discovery_worker: Optional[DiscoveryWorker] = None
        self.pinned_outcome_rows: List[Dict[str, Any]] = []
        self.current_outcome_result: Optional[Dict[str, Any]] = None

        self._build_menu()
        self._build_ui()

        if initial_xes and os.path.isfile(initial_xes):
            self.start_analysis(initial_xes)

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")

        open_act = QAction("Open XES Event Log...", self)
        open_act.triggered.connect(self.prompt_open_xes)
        file_menu.addAction(open_act)

        export_all_act = QAction("Export Summary Snapshot (CSV)...", self)
        export_all_act.triggered.connect(self.export_all_summary)
        file_menu.addAction(export_all_act)

        file_menu.addSeparator()
        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        help_menu = menubar.addMenu("&Help")
        about_act = QAction("About & Runtime Info", self)
        about_act.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_act)

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 10, 12, 10)
        root_layout.setSpacing(8)

        # Top control bar
        top_frame = QFrame()
        top_frame.setObjectName("Card")
        top_bar = QHBoxLayout(top_frame)
        top_bar.setContentsMargins(10, 6, 10, 6)

        self.open_btn = QPushButton("Open XES File...")
        self.open_btn.clicked.connect(self.prompt_open_xes)

        self.rerun_btn = QPushButton("Reload / Reset Filters")
        self.rerun_btn.setObjectName("SecondaryBtn")
        self.rerun_btn.setEnabled(False)
        self.rerun_btn.clicked.connect(self.rerun_current_file)

        self.export_summary_btn = QPushButton("Export Summary (CSV)")
        self.export_summary_btn.setObjectName("SecondaryBtn")
        self.export_summary_btn.setEnabled(False)
        self.export_summary_btn.clicked.connect(self.export_all_summary)

        self.about_btn = QPushButton("About")
        self.about_btn.setObjectName("SecondaryBtn")
        self.about_btn.clicked.connect(self.show_about_dialog)

        self.file_lbl = QLabel("<b>Dataset:</b> No XES loaded")
        self.status_lbl = QLabel("Ready — Open a .xes event log to explore.")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setValue(0)

        top_bar.addWidget(self.open_btn)
        top_bar.addWidget(self.rerun_btn)
        top_bar.addWidget(self.export_summary_btn)
        top_bar.addWidget(self.file_lbl, stretch=1)
        top_bar.addWidget(self.status_lbl)
        top_bar.addWidget(self.progress_bar)
        top_bar.addWidget(self.about_btn)

        root_layout.addWidget(top_frame)

        # Main Tabs (Clean, capability-oriented names)
        self.tabs = QTabWidget()
        root_layout.addWidget(self.tabs, stretch=1)

        self._build_tab_overview()
        self._build_tab_outcome_filter()
        self._build_tab_rework_filter()
        self._build_tab_sequence_filter()
        self._build_tab_fast_slow()
        self._build_tab_case_explorer()
        self._build_tab_discovery()

    # ------------------------------------------------------------------
    # Tab 1: Log Overview
    # ------------------------------------------------------------------
    def _build_tab_overview(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.validation_banner = QLabel(
            "<b>Dataset Metadata:</b> Load an XES event log to view detected attributes, lifecycle states, activity coverage, and case durations."
        )
        self.validation_banner.setObjectName("FilterBar")
        self.validation_banner.setWordWrap(True)
        layout.addWidget(self.validation_banner)

        cards_row = QHBoxLayout()
        self.ov_card_cases = KpiCard("TOTAL CASES", "-", "Unique process instances")
        self.ov_card_events = KpiCard("TOTAL EVENTS", "-", "Events across log")
        self.ov_card_mean_ct = KpiCard("MEAN CYCLE TIME", "-", "Days (unfiltered traces)")
        self.ov_card_median_ct = KpiCard("MEDIAN / MAX DURATION", "-", "Days")
        self.ov_card_timerange = KpiCard("LOG TIME SPAN", "-", "First to last timestamp")
        for c in (
            self.ov_card_cases,
            self.ov_card_events,
            self.ov_card_mean_ct,
            self.ov_card_median_ct,
            self.ov_card_timerange,
        ):
            cards_row.addWidget(c)
        layout.addLayout(cards_row)

        splitter = QSplitter(Qt.Horizontal)
        self.ov_activity_table = SearchableTableWidget(
            "Activity Frequency & Case Coverage"
        )
        self.ov_cases_table = SearchableTableWidget(
            "All Cases & Cycle Time Duration (Double-click to Inspect Trace)",
            enable_inspect_btn=True,
        )
        self.ov_cases_table.case_selected.connect(self.open_case_in_explorer)

        splitter.addWidget(self.ov_activity_table)
        splitter.addWidget(self.ov_cases_table)
        splitter.setSizes([560, 760])
        layout.addWidget(splitter, stretch=1)

        self.tabs.addTab(tab, "Log Overview")

    # ------------------------------------------------------------------
    # Tab 2: Activity & Endpoint Filter
    # ------------------------------------------------------------------
    def _build_tab_outcome_filter(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        fbar = QFrame()
        fbar.setObjectName("FilterBar")
        flayout = QHBoxLayout(fbar)
        flayout.setContentsMargins(10, 6, 10, 6)

        flayout.addWidget(QLabel("<b>Filter Rule:</b>"))
        self.out_mode_combo = QComboBox()
        self.out_mode_combo.addItem("Contains Activity (≥ 1 in trace)", "contains")
        self.out_mode_combo.addItem("Ends With Activity (Last event in trace)", "ends_with")
        self.out_mode_combo.addItem("Starts With Activity (First event in trace)", "starts_with")
        self.out_mode_combo.addItem("Does Not Contain Activity", "not_contains")
        flayout.addWidget(self.out_mode_combo)

        flayout.addWidget(QLabel("<b>Activity:</b>"))
        self.out_activity_combo = QComboBox()
        self.out_activity_combo.setMinimumWidth(220)
        flayout.addWidget(self.out_activity_combo)

        flayout.addWidget(QLabel("<b>Lifecycle:</b>"))
        self.out_lifecycle_combo = QComboBox()
        self.out_lifecycle_combo.addItem("All")
        flayout.addWidget(self.out_lifecycle_combo)

        self.out_apply_btn = QPushButton("Apply Filter")
        self.out_apply_btn.clicked.connect(self.apply_outcome_filter)
        flayout.addWidget(self.out_apply_btn)

        self.out_pin_btn = QPushButton("Pin to Comparison")
        self.out_pin_btn.setObjectName("SecondaryBtn")
        self.out_pin_btn.clicked.connect(self.pin_current_outcome_filter)
        flayout.addWidget(self.out_pin_btn)

        self.out_reset_pins_btn = QPushButton("Reset Comparison")
        self.out_reset_pins_btn.setObjectName("SecondaryBtn")
        self.out_reset_pins_btn.clicked.connect(self.reset_outcome_comparison)
        flayout.addWidget(self.out_reset_pins_btn)
        flayout.addStretch()

        layout.addWidget(fbar)

        cards_row = QHBoxLayout()
        self.out_card_rule = KpiCard("ACTIVE FILTER RULE", "-", "Select rule & activity above")
        self.out_card_cases = KpiCard("MATCHING CASES", "-", "Cases matching rule")
        self.out_card_mean = KpiCard("MEAN CYCLE TIME", "-", "Full trace duration (days)")
        self.out_card_med_max = KpiCard("MEDIAN / MAX DURATION", "-", "Days")
        for c in (
            self.out_card_rule,
            self.out_card_cases,
            self.out_card_mean,
            self.out_card_med_max,
        ):
            cards_row.addWidget(c)
        layout.addLayout(cards_row)

        splitter = QSplitter(Qt.Vertical)
        self.out_comparison_table = SearchableTableWidget(
            "Filter Comparison Table (Click 'Pin to Comparison' to add custom rules)"
        )
        self.out_cases_table = SearchableTableWidget(
            "Matching Cases for Active Filter",
            enable_inspect_btn=True,
        )
        self.out_cases_table.case_selected.connect(self.open_case_in_explorer)

        splitter.addWidget(self.out_comparison_table)
        splitter.addWidget(self.out_cases_table)
        splitter.setSizes([240, 420])
        layout.addWidget(splitter, stretch=1)

        self.tabs.addTab(tab, "Activity && Endpoint Filter")

    # ------------------------------------------------------------------
    # Tab 3: Rework & Resource Filter
    # ------------------------------------------------------------------
    def _build_tab_rework_filter(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        fbar = QFrame()
        fbar.setObjectName("FilterBar")
        flayout = QHBoxLayout(fbar)
        flayout.setContentsMargins(10, 6, 10, 6)

        flayout.addWidget(QLabel("<b>Activity:</b>"))
        self.rw_activity_combo = QComboBox()
        self.rw_activity_combo.setMinimumWidth(220)
        flayout.addWidget(self.rw_activity_combo)

        flayout.addWidget(QLabel("<b>Lifecycle:</b>"))
        self.rw_lifecycle_combo = QComboBox()
        self.rw_lifecycle_combo.addItem("complete")
        self.rw_lifecycle_combo.addItem("All")
        flayout.addWidget(self.rw_lifecycle_combo)

        flayout.addWidget(QLabel("<b>Min Occurrences (≥):</b>"))
        self.rw_min_spin = QSpinBox()
        self.rw_min_spin.setRange(1, 100)
        self.rw_min_spin.setValue(2)
        flayout.addWidget(self.rw_min_spin)

        flayout.addWidget(QLabel("<b>Resource Scope:</b>"))
        self.rw_scope_combo = QComboBox()
        self.rw_scope_combo.addItem("Any Resource (Case-Level Rework)", False)
        self.rw_scope_combo.addItem("Same Resource (Identical Resource in Case)", True)
        flayout.addWidget(self.rw_scope_combo)

        self.rw_exclude_empty_chk = QCheckBox("Exclude Empty / UNKNOWN Resource")
        self.rw_exclude_empty_chk.setChecked(True)
        flayout.addWidget(self.rw_exclude_empty_chk)

        self.rw_apply_btn = QPushButton("Apply Filter")
        self.rw_apply_btn.clicked.connect(self.apply_rework_filter)
        flayout.addWidget(self.rw_apply_btn)
        flayout.addStretch()

        layout.addWidget(fbar)

        cards_row = QHBoxLayout()
        self.rw_card_cases = KpiCard("MATCHING CASES", "-", "Cases meeting repetition rule")
        self.rw_card_share = KpiCard("CASE SHARE (%)", "-", "Matching / Total Cases")
        self.rw_card_events = KpiCard("EVIDENCE EVENTS", "-", "Supporting event occurrences")
        self.rw_card_resources = KpiCard("DISTINCT RESOURCES", "-", "Unique resources in evidence")
        for c in (
            self.rw_card_cases,
            self.rw_card_share,
            self.rw_card_events,
            self.rw_card_resources,
        ):
            cards_row.addWidget(c)
        layout.addLayout(cards_row)

        splitter = QSplitter(Qt.Vertical)
        self.rw_cases_table = SearchableTableWidget(
            "Qualifying Cases (Double-click to Inspect in Case Explorer)",
            enable_inspect_btn=True,
        )
        self.rw_cases_table.case_selected.connect(self.open_case_in_explorer)

        self.rw_evidence_table = SearchableTableWidget(
            "Supporting Event Evidence (Exact Matching Occurrences)"
        )

        splitter.addWidget(self.rw_cases_table)
        splitter.addWidget(self.rw_evidence_table)
        splitter.setSizes([340, 280])
        layout.addWidget(splitter, stretch=1)

        self.tabs.addTab(tab, "Rework && Resource Filter")

    # ------------------------------------------------------------------
    # Tab 4: Sequence & Follower Filter
    # ------------------------------------------------------------------
    def _build_tab_sequence_filter(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        fbar = QFrame()
        fbar.setObjectName("FilterBar")
        flayout = QHBoxLayout(fbar)
        flayout.setContentsMargins(10, 6, 10, 6)

        flayout.addWidget(QLabel("<b>First Activity (A):</b>"))
        self.seq_first_combo = QComboBox()
        self.seq_first_combo.setMinimumWidth(200)
        flayout.addWidget(self.seq_first_combo)

        self.seq_swap_btn = QPushButton("⇄ Swap")
        self.seq_swap_btn.setObjectName("SecondaryBtn")
        self.seq_swap_btn.clicked.connect(self.swap_sequence_activities)
        flayout.addWidget(self.seq_swap_btn)

        flayout.addWidget(QLabel("<b>Relation:</b>"))
        self.seq_rel_combo = QComboBox()
        self.seq_rel_combo.addItem(
            "Eventually Followed By (A ... → B, i < j)", "eventually_follows"
        )
        self.seq_rel_combo.addItem(
            "Directly Followed By (A → B, j = i + 1)", "directly_follows"
        )
        flayout.addWidget(self.seq_rel_combo)

        flayout.addWidget(QLabel("<b>Second Activity (B):</b>"))
        self.seq_second_combo = QComboBox()
        self.seq_second_combo.setMinimumWidth(200)
        flayout.addWidget(self.seq_second_combo)

        flayout.addWidget(QLabel("<b>Lifecycle:</b>"))
        self.seq_lifecycle_combo = QComboBox()
        self.seq_lifecycle_combo.addItem("All")
        flayout.addWidget(self.seq_lifecycle_combo)

        self.seq_apply_btn = QPushButton("Apply Sequence Filter")
        self.seq_apply_btn.clicked.connect(self.apply_sequence_filter)
        flayout.addWidget(self.seq_apply_btn)
        flayout.addStretch()

        layout.addWidget(fbar)

        cards_row = QHBoxLayout()
        self.seq_card_ans = KpiCard("PATTERN DETECTED?", "-", "Sequence occurrence in log")
        self.seq_card_count = KpiCard("MATCHING CASES (NUMERATOR)", "-", "Cases matching A → B")
        self.seq_card_denom = KpiCard("TOTAL CASES (DENOMINATOR)", "-", "Active log cases")
        self.seq_card_pct = KpiCard("PERCENTAGE OF CASES", "-", "Matched / Total × 100%")
        for c in (
            self.seq_card_ans,
            self.seq_card_count,
            self.seq_card_denom,
            self.seq_card_pct,
        ):
            cards_row.addWidget(c)
        layout.addLayout(cards_row)

        self.seq_witness_table = SearchableTableWidget(
            "Matching Cases & Witness Event Pairs (First A Position/Timestamp → Later B Position/Timestamp)",
            enable_inspect_btn=True,
        )
        self.seq_witness_table.case_selected.connect(self.open_case_in_explorer)
        layout.addWidget(self.seq_witness_table, stretch=1)

        self.tabs.addTab(tab, "Sequence && Follower Filter")

    # ------------------------------------------------------------------
    # Tab 5: Duration & Bottlenecks
    # ------------------------------------------------------------------
    def _build_tab_fast_slow(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        fbar = QFrame()
        fbar.setObjectName("FilterBar")
        top_row = QHBoxLayout(fbar)
        top_row.setContentsMargins(10, 6, 10, 6)

        banner = QLabel(
            "<b>Cycle Time Distribution & Fast / Slow Case Comparison:</b> "
            "Split the event log by a duration threshold to compare activity frequencies and identify process bottlenecks."
        )
        banner.setWordWrap(True)
        top_row.addWidget(banner, stretch=1)

        top_row.addWidget(QLabel("<b>Slow Case Threshold (days):</b>"))
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(1.0, 365.0)
        self.threshold_spin.setValue(45.0)
        self.threshold_spin.setSingleStep(5.0)
        top_row.addWidget(self.threshold_spin)

        self.recalc_fs_btn = QPushButton("Apply Split")
        self.recalc_fs_btn.clicked.connect(self._recalculate_fast_slow)
        top_row.addWidget(self.recalc_fs_btn)
        layout.addWidget(fbar)

        cards_row = QHBoxLayout()
        self.cfs_fast = KpiCard("FAST CASES (< THRESHOLD)", "-", "Below threshold")
        self.cfs_slow = KpiCard("SLOW CASES (≥ THRESHOLD)", "-", "At or above threshold")
        self.cfs_slow_max = KpiCard("SLOW MEAN / MAX DURATION", "-", "Cycle time in days")
        self.cfs_slow_end_cancel = KpiCard(
            "SLOW CASES ENDING W/ O_Cancelled", "-", "Canceled endpoint comparison"
        )
        for c in (
            self.cfs_fast,
            self.cfs_slow,
            self.cfs_slow_max,
            self.cfs_slow_end_cancel,
        ):
            cards_row.addWidget(c)
        layout.addLayout(cards_row)

        splitter = QSplitter(Qt.Horizontal)

        chart_frame = QFrame()
        chart_frame.setObjectName("Card")
        chart_layout = QVBoxLayout(chart_frame)
        self.fs_fig = Figure(figsize=(6, 4.5), dpi=100, facecolor="#1e293b")
        self.fs_canvas = FigureCanvas(self.fs_fig)
        chart_layout.addWidget(self.fs_canvas)
        splitter.addWidget(chart_frame)

        right_splitter = QSplitter(Qt.Vertical)
        self.fs_comp_table = SearchableTableWidget(
            "Activity Frequency Comparison: Slow Cases vs Fast Cases"
        )
        self.fs_slow_cases_table = SearchableTableWidget(
            "Slow Cases List (Sorted by Longest Duration)",
            enable_inspect_btn=True,
        )
        self.fs_slow_cases_table.case_selected.connect(self.open_case_in_explorer)
        right_splitter.addWidget(self.fs_comp_table)
        right_splitter.addWidget(self.fs_slow_cases_table)
        right_splitter.setSizes([300, 300])

        splitter.addWidget(right_splitter)
        splitter.setSizes([580, 740])
        layout.addWidget(splitter, stretch=1)

        self.tabs.addTab(tab, "Duration && Bottlenecks")

    # ------------------------------------------------------------------
    # Tab 6: Case Explorer
    # ------------------------------------------------------------------
    def _build_tab_case_explorer(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        fbar = QFrame()
        fbar.setObjectName("FilterBar")
        flayout = QHBoxLayout(fbar)
        flayout.setContentsMargins(10, 6, 10, 6)

        flayout.addWidget(
            QLabel(
                "<b>Case Explorer:</b> Select any case on the left to inspect its full chronological trace."
            )
        )
        flayout.addStretch()
        flayout.addWidget(QLabel("<b>Highlight Activity:</b>"))
        self.explorer_highlight_combo = QComboBox()
        self.explorer_highlight_combo.setMinimumWidth(240)
        self.explorer_highlight_combo.addItem("Default (Outcomes & Fraud Assessment)")
        self.explorer_highlight_combo.currentIndexChanged.connect(
            self._on_explorer_highlight_changed
        )
        flayout.addWidget(self.explorer_highlight_combo)
        layout.addWidget(fbar)

        splitter = QSplitter(Qt.Horizontal)
        self.explorer_cases_table = SearchableTableWidget("Cases in Active Log")
        self.explorer_cases_table.table.selectionModel().selectionChanged.connect(
            self._on_explorer_case_selection_changed
        )

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.explorer_case_header = QLabel("<b>Selected Case:</b> None")
        right_layout.addWidget(self.explorer_case_header)

        self.explorer_trace_table = SearchableTableWidget(
            "Chronological Event Trace",
            highlight_activities=set(DEFAULT_HIGHLIGHT_ACTIVITIES),
        )
        right_layout.addWidget(self.explorer_trace_table, stretch=1)

        splitter.addWidget(self.explorer_cases_table)
        splitter.addWidget(right_widget)
        splitter.setSizes([450, 870])
        layout.addWidget(splitter, stretch=1)

        self.tabs.addTab(tab, "Case Explorer")

    # ------------------------------------------------------------------
    # Tab 7: Process Discovery & DFG
    # ------------------------------------------------------------------
    def _build_tab_discovery(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        fbar = QFrame()
        fbar.setObjectName("FilterBar")
        flayout = QHBoxLayout(fbar)
        flayout.setContentsMargins(10, 6, 10, 6)

        flayout.addWidget(QLabel("<b>Algorithm:</b>"))
        self.disc_algo_combo = QComboBox()
        self.disc_algo_combo.addItem("DFG (Frequency)", "dfg_frequency")
        self.disc_algo_combo.addItem("DFG (Performance)", "dfg_performance")
        self.disc_algo_combo.addItem("Alpha Miner", "alpha")
        self.disc_algo_combo.addItem("Heuristics Miner", "heuristics")
        self.disc_algo_combo.addItem("Inductive Miner (Petri Net)", "inductive_petri")
        self.disc_algo_combo.addItem("Inductive Miner (Process Tree)", "inductive_tree")
        self.disc_algo_combo.currentIndexChanged.connect(
            self._sync_discovery_param_visibility
        )
        flayout.addWidget(self.disc_algo_combo)

        flayout.addWidget(QLabel("<b>Lifecycle:</b>"))
        self.disc_lifecycle_combo = QComboBox()
        self.disc_lifecycle_combo.addItem("complete")
        self.disc_lifecycle_combo.addItem("All")
        flayout.addWidget(self.disc_lifecycle_combo)

        flayout.addWidget(QLabel("<b>Top Variants:</b>"))
        self.disc_variants_spin = QSpinBox()
        self.disc_variants_spin.setRange(0, 1000)
        self.disc_variants_spin.setValue(20)
        self.disc_variants_spin.setSpecialValueText("All")
        flayout.addWidget(self.disc_variants_spin)

        self.disc_min_freq_lbl = QLabel("<b>Min Edge Freq:</b>")
        self.disc_min_freq_spin = QSpinBox()
        self.disc_min_freq_spin.setRange(1, 1000000)
        self.disc_min_freq_spin.setValue(1)
        flayout.addWidget(self.disc_min_freq_lbl)
        flayout.addWidget(self.disc_min_freq_spin)

        self.disc_dep_lbl = QLabel("<b>Dep. Threshold:</b>")
        self.disc_dep_spin = QDoubleSpinBox()
        self.disc_dep_spin.setRange(0.0, 1.0)
        self.disc_dep_spin.setSingleStep(0.05)
        self.disc_dep_spin.setValue(0.50)
        flayout.addWidget(self.disc_dep_lbl)
        flayout.addWidget(self.disc_dep_spin)

        self.disc_noise_lbl = QLabel("<b>Noise Threshold:</b>")
        self.disc_noise_spin = QDoubleSpinBox()
        self.disc_noise_spin.setRange(0.0, 1.0)
        self.disc_noise_spin.setSingleStep(0.05)
        self.disc_noise_spin.setValue(0.20)
        flayout.addWidget(self.disc_noise_lbl)
        flayout.addWidget(self.disc_noise_spin)

        self.disc_run_btn = QPushButton("Discover")
        self.disc_run_btn.clicked.connect(self.run_discovery_async)
        flayout.addWidget(self.disc_run_btn)

        self.disc_fit_btn = QPushButton("Fit View")
        self.disc_fit_btn.setObjectName("SecondaryBtn")
        self.disc_fit_btn.clicked.connect(lambda: self.disc_graph_view.fit_graph())
        flayout.addWidget(self.disc_fit_btn)

        self.disc_export_btn = QPushButton("Export PNG")
        self.disc_export_btn.setObjectName("SecondaryBtn")
        self.disc_export_btn.clicked.connect(self._export_discovery_png)
        flayout.addWidget(self.disc_export_btn)
        flayout.addStretch()

        layout.addWidget(fbar)

        cards_row = QHBoxLayout()
        self.disc_kpis = [
            KpiCard("CASES COVERED", "-", ""),
            KpiCard("ELEMENTS", "-", ""),
            KpiCard("EDGES / TRANSITIONS", "-", ""),
            KpiCard("METRIC", "-", ""),
        ]
        for c in self.disc_kpis:
            cards_row.addWidget(c)
        layout.addLayout(cards_row)

        splitter = QSplitter(Qt.Horizontal)

        graph_container = QWidget()
        graph_layout = QVBoxLayout(graph_container)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.setSpacing(4)

        self.disc_graph_view = ProcessGraphView()
        self.disc_inspect_lbl = QLabel("Scroll to zoom · Drag canvas or nodes · Click node/edge to inspect")
        self.disc_inspect_lbl.setStyleSheet("color: #94a3b8; font-size: 12px; padding: 2px 4px;")
        self.disc_graph_view.item_inspected.connect(self.disc_inspect_lbl.setText)

        graph_layout.addWidget(self.disc_graph_view, stretch=1)
        graph_layout.addWidget(self.disc_inspect_lbl)

        self.disc_table = SearchableTableWidget("Model Edges / Relations")

        splitter.addWidget(graph_container)
        splitter.addWidget(self.disc_table)
        splitter.setSizes([860, 460])
        layout.addWidget(splitter, stretch=1)

        self._sync_discovery_param_visibility()
        self.tabs.addTab(tab, "Process Discovery && DFG")

    # ------------------------------------------------------------------
    # File Loading & Worker Handlers
    # ------------------------------------------------------------------
    def prompt_open_xes(self) -> None:
        default_dir = os.path.abspath("ignore_TUGAS-PM4PY")
        if not os.path.isdir(default_dir):
            default_dir = os.getcwd()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select XES Event Log",
            default_dir,
            "XES Event Log (*.xes *.xes.gz);;All Files (*.*)",
        )
        if path:
            self.start_analysis(path)

    def rerun_current_file(self) -> None:
        if self.bundle and os.path.isfile(self.bundle.file_path):
            self.start_analysis(self.bundle.file_path)

    def start_analysis(self, file_path: str) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        self.open_btn.setEnabled(False)
        self.rerun_btn.setEnabled(False)
        self.export_summary_btn.setEnabled(False)
        self.file_lbl.setText(f"<b>Dataset:</b> {os.path.basename(file_path)}")
        self.status_lbl.setText("Loading XES via PM4Py...")
        self.progress_bar.setValue(5)

        self.worker = AnalysisWorker(file_path, self)
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.finished_bundle.connect(self._on_worker_finished)
        self.worker.failed.connect(self._on_worker_failed)
        self.worker.start()

    def _on_worker_progress(self, msg: str, pct: int) -> None:
        self.status_lbl.setText(msg)
        self.progress_bar.setValue(pct)

    def _on_worker_failed(self, err_msg: str) -> None:
        self.open_btn.setEnabled(True)
        self.rerun_btn.setEnabled(self.bundle is not None)
        self.export_summary_btn.setEnabled(self.bundle is not None)
        self.status_lbl.setText("Failed to load XES file.")
        self.progress_bar.setValue(0)
        QMessageBox.critical(self, "XES Import Error", err_msg)

    def _on_worker_finished(self, bundle: AnalysisBundle) -> None:
        self.open_btn.setEnabled(True)
        self.rerun_btn.setEnabled(True)
        self.export_summary_btn.setEnabled(True)
        self.populate_from_bundle(bundle)

    # ------------------------------------------------------------------
    # Dynamic Population & Interactive Filter Execution
    # ------------------------------------------------------------------
    def populate_from_bundle(self, bundle: AnalysisBundle) -> None:
        """Populate dynamic dropdowns and initial views from an AnalysisBundle."""
        self.bundle = bundle
        self.rerun_btn.setEnabled(True)
        self.export_summary_btn.setEnabled(True)

        v = bundle.validation
        ov = bundle.overview
        activities: List[str] = v.get("activities", [])
        lifecycles: List[str] = v.get("lifecycle_values", [])

        self.file_lbl.setText(
            f"<b>Dataset:</b> {v['file_name']} "
            f"({v['total_cases']:,} cases, {v['total_events']:,} events)"
        )
        self.status_lbl.setText("Ready")
        self.progress_bar.setValue(100)

        # Populate dynamic activity & lifecycle combo boxes across all tabs
        for combo in (
            self.out_activity_combo,
            self.rw_activity_combo,
            self.seq_first_combo,
            self.seq_second_combo,
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(activities)
            combo.blockSignals(False)

        for lc_combo in (self.out_lifecycle_combo, self.seq_lifecycle_combo):
            lc_combo.blockSignals(True)
            lc_combo.clear()
            lc_combo.addItem("All")
            for lc in lifecycles:
                lc_combo.addItem(lc)
            lc_combo.blockSignals(False)

        self.rw_lifecycle_combo.blockSignals(True)
        self.rw_lifecycle_combo.clear()
        for lc in lifecycles:
            self.rw_lifecycle_combo.addItem(lc)
        self.rw_lifecycle_combo.addItem("All")
        idx_comp = self.rw_lifecycle_combo.findText("complete", Qt.MatchFixedString)
        if idx_comp >= 0:
            self.rw_lifecycle_combo.setCurrentIndex(idx_comp)
        self.rw_lifecycle_combo.blockSignals(False)

        self.disc_lifecycle_combo.blockSignals(True)
        self.disc_lifecycle_combo.clear()
        for lc in lifecycles:
            self.disc_lifecycle_combo.addItem(lc)
        self.disc_lifecycle_combo.addItem("All")
        idx_disc_comp = self.disc_lifecycle_combo.findText("complete", Qt.MatchFixedString)
        if idx_disc_comp >= 0:
            self.disc_lifecycle_combo.setCurrentIndex(idx_disc_comp)
        self.disc_lifecycle_combo.blockSignals(False)

        self.explorer_highlight_combo.blockSignals(True)
        self.explorer_highlight_combo.clear()
        self.explorer_highlight_combo.addItem("Default (Outcomes & Fraud Assessment)")
        for act in activities:
            self.explorer_highlight_combo.addItem(act)
        self.explorer_highlight_combo.blockSignals(False)

        # Set sensible initial selections based on activities in log
        self._set_combo_if_exists(self.out_activity_combo, "O_Accepted")
        self._set_combo_if_exists(
            self.rw_activity_combo,
            "W_Assess potential fraud",
            fallback="W_Assess Potential Fraud",
        )
        self._set_combo_if_exists(self.seq_first_combo, "O_Cancelled")
        self._set_combo_if_exists(self.seq_second_combo, "O_Accepted")

        # Tab 1: Overview
        lc_str = ", ".join(lifecycles) if lifecycles else "None"
        attrs_str = ", ".join(v["attributes"])
        self.validation_banner.setText(
            f"<b>Status:</b> {v['status']} | <b>File:</b> <code>{v['file_path']}</code><br>"
            f"<b>Event Attributes ({len(v['attributes'])}):</b> <code>{attrs_str}</code><br>"
            f"<b>Lifecycle Transitions:</b> <code>{lc_str}</code> | "
            f"<b>Resource Attribute (org:resource):</b> <code>{v['has_resource']}</code>"
        )
        self.ov_card_cases.set_metrics(f"{ov['total_cases']:,}", "100% of active log")
        self.ov_card_events.set_metrics(
            f"{ov['total_events']:,}",
            f"Avg {ov['total_events'] / max(ov['total_cases'], 1):.1f} events / case",
        )
        self.ov_card_mean_ct.set_metrics(
            f"{ov['mean_cycle_time_days']:.1f} days",
            f"Exact: {ov['mean_cycle_time_days']:.4f} days",
        )
        self.ov_card_median_ct.set_metrics(
            f"{ov['median_cycle_time_days']:.1f} d (med)",
            f"Min: {ov['min_cycle_time_days']:.2f} d | Max: {ov['max_cycle_time_days']:.1f} d",
        )
        self.ov_card_timerange.set_metrics(
            ov["min_timestamp"][:10], f"to {ov['max_timestamp'][:10]}"
        )
        self.ov_activity_table.set_dataframe(ov["activity_table"])
        self.ov_cases_table.set_dataframe(bundle.case_stats)

        # Tab 2: Activity & Endpoint Filter
        self.reset_outcome_comparison()
        self.apply_outcome_filter()

        # Tab 3: Rework & Resource Filter
        self.apply_rework_filter()

        # Tab 4: Sequence & Follower Filter
        self.apply_sequence_filter()

        # Tab 5: Duration & Bottlenecks
        self._populate_fast_slow(bundle.fast_slow)

        # Tab 6: Case Explorer
        self.explorer_cases_table.set_dataframe(bundle.case_stats)
        if not bundle.case_stats.empty:
            first_cid = str(bundle.case_stats.iloc[0]["case_id"])
            self._load_case_trace(first_cid)

        # Tab 7: Process Discovery & DFG (initial DFG Frequency view)
        self.run_discovery_sync()

    @staticmethod
    def _set_combo_if_exists(
        combo: QComboBox, target: str, fallback: Optional[str] = None
    ) -> None:
        idx = combo.findText(target, Qt.MatchFixedString)
        if idx < 0 and fallback:
            idx = combo.findText(fallback, Qt.MatchFixedString)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # Tab 2 Handlers (Activity & Endpoint Filter)
    # ------------------------------------------------------------------
    def apply_outcome_filter(self) -> None:
        if not self.bundle:
            return
        act = self.out_activity_combo.currentText()
        if not act:
            return
        mode = self.out_mode_combo.currentData() or "contains"
        lc = self.out_lifecycle_combo.currentText() or "All"

        res = filter_by_activity_rule(
            self.bundle.df,
            self.bundle.case_stats,
            activity=act,
            mode=mode,
            lifecycle=lc,
        )
        self.current_outcome_result = res

        self.out_card_rule.set_metrics(res["rule_label"], f"Lifecycle: {res['lifecycle']}")
        self.out_card_cases.set_metrics(
            f"{res['case_count']:,} cases",
            f"{res['case_pct']:.2f}% of {res['total_cases']:,} cases",
        )
        self.out_card_mean.set_metrics(
            f"{res['mean_cycle_time_days']:.1f} days",
            f"Exact: {res['mean_cycle_time_days']:.4f} days",
        )
        self.out_card_med_max.set_metrics(
            f"{res['median_cycle_time_days']:.1f} d (med)",
            f"Min: {res['min_cycle_time_days']:.2f} d | Max: {res['max_cycle_time_days']:.1f} d",
        )
        self.out_cases_table.set_dataframe(res["cases_table"])

    def pin_current_outcome_filter(self) -> None:
        if not self.current_outcome_result:
            return
        r = self.current_outcome_result
        row = {
            "filter_rule": r["rule_label"],
            "activity": r["activity"],
            "lifecycle": r["lifecycle"],
            "case_count": r["case_count"],
            "total_cases": r["total_cases"],
            "case_pct": round(r["case_pct"], 2),
            "mean_cycle_time_days": round(r["mean_cycle_time_days"], 2),
            "median_cycle_time_days": round(r["median_cycle_time_days"], 2),
            "max_cycle_time_days": round(r["max_cycle_time_days"], 2),
        }
        if not any(x["filter_rule"] == row["filter_rule"] for x in self.pinned_outcome_rows):
            self.pinned_outcome_rows.append(row)
        self.out_comparison_table.set_dataframe(pd.DataFrame(self.pinned_outcome_rows))

    def reset_outcome_comparison(self) -> None:
        if not self.bundle:
            return
        base_df = self.bundle.ex_11_7["summary_table"]
        self.pinned_outcome_rows = base_df.to_dict(orient="records")
        self.out_comparison_table.set_dataframe(base_df)

    # ------------------------------------------------------------------
    # Tab 3 Handlers (Rework & Resource Filter)
    # ------------------------------------------------------------------
    def apply_rework_filter(self) -> None:
        if not self.bundle:
            return
        act = self.rw_activity_combo.currentText()
        if not act:
            return
        lc = self.rw_lifecycle_combo.currentText() or "complete"
        min_cnt = int(self.rw_min_spin.value())
        same_res = bool(self.rw_scope_combo.currentData())
        excl_empty = bool(self.rw_exclude_empty_chk.isChecked())

        res = filter_rework_and_resource(
            self.bundle.df,
            self.bundle.case_stats,
            activity=act,
            lifecycle=lc,
            min_count=min_cnt,
            same_resource=same_res,
            exclude_empty_resource=excl_empty,
        )

        scope_str = "Same Resource" if same_res else "Any Resource"
        self.rw_card_cases.set_metrics(
            f"{res['case_count']:,} cases",
            f"≥ {min_cnt} occurrences ({lc}, {scope_str})",
        )
        self.rw_card_share.set_metrics(
            f"{res['case_pct']:.4f}%",
            f"{res['case_count']:,} / {res['total_cases']:,} cases",
        )
        self.rw_card_events.set_metrics(
            f"{res['evidence_event_count']:,} events",
            f"Activity: {act}",
        )
        self.rw_card_resources.set_metrics(
            f"{res['distinct_resources']:,} resources",
            "Excluding empty/UNKNOWN" if excl_empty else "Including all",
        )
        self.rw_cases_table.set_dataframe(res["cases_table"])

        ev_df = res["evidence_events"]
        if not ev_df.empty:
            cols = [
                c
                for c in (
                    "case:concept:name",
                    "time:timestamp",
                    "concept:name",
                    "lifecycle:transition",
                    "org:resource",
                )
                if c in ev_df.columns
            ]
            ev_display = ev_df[cols].rename(columns={"case:concept:name": "case_id"})
        else:
            ev_display = pd.DataFrame()
        self.rw_evidence_table.set_dataframe(ev_display)

    # ------------------------------------------------------------------
    # Tab 4 Handlers (Sequence & Follower Filter)
    # ------------------------------------------------------------------
    def swap_sequence_activities(self) -> None:
        a = self.seq_first_combo.currentIndex()
        b = self.seq_second_combo.currentIndex()
        self.seq_first_combo.setCurrentIndex(b)
        self.seq_second_combo.setCurrentIndex(a)
        self.apply_sequence_filter()

    def apply_sequence_filter(self) -> None:
        if not self.bundle:
            return
        act_a = self.seq_first_combo.currentText()
        act_b = self.seq_second_combo.currentText()
        if not act_a or not act_b:
            return
        rel = self.seq_rel_combo.currentData() or "eventually_follows"
        lc = self.seq_lifecycle_combo.currentText() or "All"

        res = filter_sequence_relation(
            self.bundle.df,
            self.bundle.case_stats,
            first_activity=act_a,
            second_activity=act_b,
            relation=rel,
            lifecycle=lc,
        )

        rel_symbol = "... →" if rel == "eventually_follows" else "→"
        self.seq_card_ans.set_metrics(
            res["answer_yes_no"], f"{act_a} {rel_symbol} {act_b}"
        )
        self.seq_card_count.set_metrics(
            f"{res['case_count']:,} cases", "Matching cases (Numerator)"
        )
        self.seq_card_denom.set_metrics(
            f"{res['denominator_total_cases']:,} cases", "Total cases (Denominator)"
        )
        self.seq_card_pct.set_metrics(
            f"{res['percentage']:.2f}%",
            f"Exact: {res['percentage']:.4f}% ({res['case_count']:,} / {res['denominator_total_cases']:,})",
        )
        self.seq_witness_table.set_dataframe(res["witness_table"])

    # ------------------------------------------------------------------
    # Tab 5 Handlers (Duration & Bottlenecks)
    # ------------------------------------------------------------------
    def _recalculate_fast_slow(self) -> None:
        if not self.bundle:
            return
        thresh = float(self.threshold_spin.value())
        fs = analyze_fast_slow(
            self.bundle.df, self.bundle.case_stats, threshold_days=thresh
        )
        self.bundle.fast_slow = fs
        self._populate_fast_slow(fs)

    def _populate_fast_slow(self, fs: dict) -> None:
        thresh = fs["threshold_days"]
        self.cfs_fast.set_metrics(
            f"{fs['fast_count']:,} ({fs['fast_pct']:.1f}%)",
            f"< {thresh:.1f} days | Mean: {fs['fast_mean_days']:.1f} d",
        )
        self.cfs_slow.set_metrics(
            f"{fs['slow_count']:,} ({fs['slow_pct']:.1f}%)",
            f"≥ {thresh:.1f} days | Mean: {fs['slow_mean_days']:.1f} d",
        )
        self.cfs_slow_max.set_metrics(
            f"Max {fs['slow_max_days']:.1f} days",
            f"Slow mean: {fs['slow_mean_days']:.1f} days",
        )
        self.cfs_slow_end_cancel.set_metrics(
            f"{fs['slow_end_o_cancelled']:,} cases ({fs['slow_end_o_cancelled_pct']:.1f}%)",
            f"vs {fs['fast_end_o_cancelled']:,} in fast cases",
        )
        self.fs_comp_table.set_dataframe(fs["comparison_table"])
        self.fs_slow_cases_table.set_dataframe(fs["slow_cases_table"])

        self.fs_fig.clear()
        if self.bundle and not self.bundle.case_stats.empty:
            ax1 = self.fs_fig.add_subplot(211)
            ax2 = self.fs_fig.add_subplot(212)

            durations = self.bundle.case_stats["duration_days"]
            ax1.set_facecolor("#0f172a")
            ax1.hist(
                durations, bins=50, color="#38bdf8", edgecolor="#0f172a", alpha=0.85
            )
            ax1.axvline(
                thresh,
                color="#ef4444",
                linestyle="--",
                linewidth=2,
                label=f"Threshold = {thresh:.0f}d",
            )
            ax1.set_yscale("log")
            ax1.set_title(
                "Case Duration Distribution (Log Scale) & Fast/Slow Split",
                color="#f8fafc",
                fontsize=10,
            )
            ax1.set_xlabel("Case Cycle Time (Days)", color="#cbd5e1", fontsize=9)
            ax1.set_ylabel("Cases (log)", color="#cbd5e1", fontsize=9)
            ax1.tick_params(colors="#cbd5e1", labelsize=8)
            ax1.legend(
                facecolor="#1e293b",
                edgecolor="#334155",
                labelcolor="#f8fafc",
                fontsize=8,
            )

            comp_df = fs["comparison_table"].head(6).iloc[::-1]
            ax2.set_facecolor("#0f172a")
            y_pos = range(len(comp_df))
            ax2.barh(
                [y + 0.18 for y in y_pos],
                comp_df["slow_case_pct"],
                height=0.35,
                color="#f97316",
                label="Slow Cases (%)",
            )
            ax2.barh(
                [y - 0.18 for y in y_pos],
                comp_df["fast_case_pct"],
                height=0.35,
                color="#38bdf8",
                label="Fast Cases (%)",
            )
            ax2.set_yticks(list(y_pos))
            ax2.set_yticklabels(
                comp_df["activity"].tolist(), color="#cbd5e1", fontsize=8
            )
            ax2.set_xlabel(
                "% of Cases Containing Activity", color="#cbd5e1", fontsize=9
            )
            ax2.set_title(
                "Top Activities More Frequent in Slow Cases",
                color="#f8fafc",
                fontsize=10,
            )
            ax2.tick_params(colors="#cbd5e1", labelsize=8)
            ax2.legend(
                facecolor="#1e293b",
                edgecolor="#334155",
                labelcolor="#f8fafc",
                fontsize=8,
            )

            self.fs_fig.tight_layout()
        self.fs_canvas.draw()

    # ------------------------------------------------------------------
    # Tab 6 Handlers (Case Explorer)
    # ------------------------------------------------------------------
    def open_case_in_explorer(self, case_id: str) -> None:
        if not self.bundle or not case_id:
            return
        self.tabs.setCurrentIndex(5)
        self.explorer_cases_table.search_input.setText(case_id)
        self._load_case_trace(case_id)

    def _on_explorer_case_selection_changed(self) -> None:
        cid = self.explorer_cases_table.get_selected_case_id()
        if cid:
            self._load_case_trace(cid)

    def _on_explorer_highlight_changed(self) -> None:
        cid = self.explorer_cases_table.get_selected_case_id()
        if cid:
            self._load_case_trace(cid)

    def _get_active_highlight_set(self) -> Set[str]:
        if self.explorer_highlight_combo.currentIndex() <= 0:
            return set(DEFAULT_HIGHLIGHT_ACTIVITIES)
        return {self.explorer_highlight_combo.currentText()}

    def _load_case_trace(self, case_id: str) -> None:
        if not self.bundle:
            return
        trace_df = get_case_trace(self.bundle.df, case_id)
        cs_row = self.bundle.case_stats[
            self.bundle.case_stats["case_id"] == str(case_id)
        ]
        if not cs_row.empty:
            r = cs_row.iloc[0]
            self.explorer_case_header.setText(
                f"<b>Selected Case:</b> <code>{case_id}</code> | "
                f"<b>Events:</b> {int(r['event_count'])} | "
                f"<b>Cycle Time:</b> {float(r['duration_days']):.2f} days "
                f"({float(r['duration_days']):.4f} d) | "
                f"<b>End Activity:</b> <code>{r['end_activity']}</code>"
            )
        else:
            self.explorer_case_header.setText(
                f"<b>Selected Case:</b> <code>{case_id}</code>"
            )

        hl = self._get_active_highlight_set()
        self.explorer_trace_table.set_dataframe(trace_df, highlight_activities=hl)
        if not trace_df.empty and "activity" in trace_df.columns:
            matches = trace_df.index[trace_df["activity"].isin(hl)].tolist()
            if matches:
                src_idx = self.explorer_trace_table.model.index(matches[0], 0)
                proxy_idx = self.explorer_trace_table.proxy.mapFromSource(src_idx)
                if proxy_idx.isValid():
                    self.explorer_trace_table.table.scrollTo(
                        proxy_idx, QAbstractItemView.PositionAtCenter
                    )
                    self.explorer_trace_table.table.selectRow(proxy_idx.row())

    # ------------------------------------------------------------------
    # Tab 7 Handlers (Process Discovery & DFG)
    # ------------------------------------------------------------------
    def _sync_discovery_param_visibility(self) -> None:
        algo = self.disc_algo_combo.currentData() or "dfg_frequency"
        show_freq = algo in ("dfg_frequency", "dfg_performance", "heuristics")
        show_dep = algo == "heuristics"
        show_noise = algo in ("inductive_petri", "inductive_tree")

        self.disc_min_freq_lbl.setVisible(show_freq)
        self.disc_min_freq_spin.setVisible(show_freq)
        self.disc_dep_lbl.setVisible(show_dep)
        self.disc_dep_spin.setVisible(show_dep)
        self.disc_noise_lbl.setVisible(show_noise)
        self.disc_noise_spin.setVisible(show_noise)

    def _get_discovery_params(self) -> tuple:
        return (
            self.disc_algo_combo.currentData() or "dfg_frequency",
            self.disc_lifecycle_combo.currentText() or "complete",
            int(self.disc_variants_spin.value()),
            int(self.disc_min_freq_spin.value()),
            float(self.disc_dep_spin.value()),
            float(self.disc_noise_spin.value()),
        )

    def run_discovery_sync(self) -> None:
        if not self.bundle:
            return
        algo, lc, top_k, min_freq, dep, noise = self._get_discovery_params()
        res = discover_process_model(
            self.bundle.df,
            algorithm=algo,
            lifecycle=lc,
            top_k_variants=top_k,
            min_edge_freq=min_freq,
            dependency_threshold=dep,
            noise_threshold=noise,
        )
        self._apply_discovery_result(res)

    def run_discovery_async(self) -> None:
        if not self.bundle:
            return
        if self.discovery_worker is not None and self.discovery_worker.isRunning():
            return
        algo, lc, top_k, min_freq, dep, noise = self._get_discovery_params()
        self.disc_run_btn.setEnabled(False)
        self.disc_inspect_lbl.setText(f"Running {self.disc_algo_combo.currentText()}...")
        self.discovery_worker = DiscoveryWorker(
            self.bundle.df, algo, lc, top_k, min_freq, dep, noise, self
        )
        self.discovery_worker.finished_result.connect(self._on_discovery_finished)
        self.discovery_worker.failed.connect(self._on_discovery_failed)
        self.discovery_worker.start()

    def _on_discovery_finished(self, res: DiscoveryResult) -> None:
        self.disc_run_btn.setEnabled(True)
        self._apply_discovery_result(res)

    def _on_discovery_failed(self, err_msg: str) -> None:
        self.disc_run_btn.setEnabled(True)
        self.disc_inspect_lbl.setText(f"Discovery failed: {err_msg}")
        QMessageBox.critical(self, "Discovery Error", err_msg)

    def _apply_discovery_result(self, res: DiscoveryResult) -> None:
        for card, kpi in zip(self.disc_kpis, res.kpis):
            title, val, sub = kpi
            card.title_lbl.setText(title.upper())
            card.set_metrics(val, sub)
        self.disc_graph_view.render_discovery(res)
        self.disc_table.set_dataframe(res.table_df)
        self.disc_inspect_lbl.setText(
            f"{len(res.nodes):,} nodes · {len(res.edges):,} edges — Scroll to zoom · Drag nodes · Click to inspect"
        )

    def _export_discovery_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Process Model PNG",
            f"{self.disc_algo_combo.currentData() or 'process_model'}.png",
            "PNG Image (*.png)",
        )
        if path:
            self.disc_graph_view.export_png(path)
            QMessageBox.information(self, "Export PNG", f"Saved graph image to:\n{path}")

    def export_all_summary(self) -> None:
        if not self.bundle:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Summary Snapshot CSV",
            "event_log_summary.csv",
            "CSV Files (*.csv)",
        )
        if path:
            export_summary_csv(self.bundle, path)
            QMessageBox.information(
                self, "Export Complete", f"Summary exported to:\n{path}"
            )

    def show_about_dialog(self) -> None:
        env = get_environment_info()
        lines = [f"<b>{k}:</b> {v}" for k, v in env.items()]
        QMessageBox.information(
            self,
            "About & Runtime Environment",
            "<h3>PM4Py Process Mining & Event Log Explorer</h3>"
            "<p>Interactive desktop analytics built with Python, PM4Py, pandas, Matplotlib, and PySide6.</p>"
            "<p>" + "<br>".join(lines) + "</p>",
        )


def launch_app(initial_xes: Optional[str] = None) -> int:
    """Launch the desktop application."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    win = MainWindow(initial_xes=initial_xes)
    win.show()
    return app.exec()
