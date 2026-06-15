"""Centro Técnico ATSEP: ventana hub con pestañas de herramientas técnicas."""
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QStatusBar, QRadioButton, QButtonGroup,
    QHBoxLayout, QLabel,
)

from player.centro_tecnico.stats_widget import StatsWidget
from player.centro_tecnico.coverage_widget import CoverageWidget
from player.technical_monitor import TechnicalMonitorWidget


class CentroTecnicoWindow(QMainWindow):
    def __init__(self, repo_db=None, worker=None, session_records=None,
                 db_path="pass_analytics.duckdb", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Centro Técnico ATSEP")
        self.resize(1280, 800)
        self._repo_db = repo_db
        self._worker = worker
        self._session_records = session_records or []
        self._db_path = db_path

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.stats_tab = StatsWidget(self.source_provider)
        self.coverage_tab = CoverageWidget(self.source_provider, db_path=db_path)
        self.tabs.addTab(self.stats_tab, "📊 Estadísticas")
        self.tabs.addTab(QWidget(), "✅ PASS / SASS-C")     # poblada en Task 11
        self.monitor_tab = TechnicalMonitorWidget(self)
        self.tabs.addTab(self.monitor_tab, "📡 Monitor ATSEP")
        self.tabs.addTab(self._inspector_placeholder(), "🔬 Inspector")  # Task 12
        self.tabs.addTab(self.coverage_tab, "🛰 Cobertura")

        self._build_statusbar()

    def _inspector_placeholder(self):
        return QWidget()

    def _build_statusbar(self):
        bar = QStatusBar()
        self.setStatusBar(bar)
        cont = QWidget()
        lay = QHBoxLayout(cont)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.addWidget(QLabel("Fuente:"))
        self.rb_duckdb = QRadioButton("DuckDB")
        self.rb_session = QRadioButton("Sesión actual")
        self.rb_duckdb.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.rb_duckdb)
        grp.addButton(self.rb_session)
        lay.addWidget(self.rb_duckdb)
        lay.addWidget(self.rb_session)
        lay.addStretch(1)
        bar.addPermanentWidget(cont, 1)
        self.rb_duckdb.toggled.connect(self._on_source_changed)

    def current_source_kind(self):
        return "duckdb" if self.rb_duckdb.isChecked() else "session"

    def source_provider(self):
        """Devuelve la DataSource activa según el conmutador."""
        from player.stats.data_source import DuckDBSource, SessionSource
        if self.current_source_kind() == "duckdb":
            return DuckDBSource(self._db_path)
        return SessionSource(self._session_records)

    def _on_source_changed(self, _checked):
        if hasattr(self.stats_tab, "on_source_changed"):
            self.stats_tab.on_source_changed()
        if hasattr(self.coverage_tab, "on_source_changed"):
            self.coverage_tab.on_source_changed()
