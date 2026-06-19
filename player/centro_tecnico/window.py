"""Centro Técnico ATSEP: ventana hub con pestañas de herramientas técnicas."""
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QStatusBar, QRadioButton, QButtonGroup,
    QHBoxLayout, QLabel, QVBoxLayout, QPushButton, QProgressDialog, QFileDialog,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from player.centro_tecnico.stats_widget import StatsWidget
from player.centro_tecnico.coverage_widget import CoverageWidget
from player.centro_tecnico.inspector_widget import InspectorWidget
from player.technical_monitor import TechnicalMonitorWidget
from player.calib_dialog import CalibrationWidget


class TechnicalImportWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list, dict)  # (plot_dicts, radar_health)
    error_occurred = pyqtSignal(str)

    def __init__(self, file_paths, db_path, repo_db=None, sensores=None,
                 profile_config=None, parent=None):
        super().__init__(parent)
        self.file_paths = file_paths
        self.db_path = db_path
        self.repo_db = repo_db
        self.sensores = sensores or {}
        self.profile_config = profile_config
        self.detected_rpms = {}   # (sac, sic) -> rpm, capturados del CAT34 al decodificar

    def log_import(self, msg):
        import time
        import os
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            log_path = os.path.join(base_dir, "technical_import.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] [Worker] {msg}\n")
        except Exception:
            pass

    def run(self):
        import os
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            log_path = os.path.join(base_dir, "technical_import.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass

        try:
            self.log_import("run() started")
            # 1. Crear DataEngine con nuestro repo_db (si no hay, creamos temporal, no importa)
            self.log_import("Creating DataEngine...")
            from decoder.data_engine import DataEngine
            # profile_config: misma registración/altimetría que la consola, para que
            # las posiciones/FL decodificados (y por ende el PASS) coincidan.
            engine = DataEngine(sensores=self.sensores, repo_db=self.repo_db,
                                profile_config=self.profile_config)

            def on_prog(current, total):
                self.progress.emit(current, total)
            engine.on_progress = on_prog

            # Capturar los RPM detectados (CAT34) para alimentar el PASS con los
            # mismos valores que usa la consola, en vez del fallback.
            def on_rpm(sac, sic, rpm):
                self.detected_rpms[(sac, sic)] = rpm
            engine.on_rotation_speed_detected = on_rpm

            # 2. Escanear (CPU-bound). La suite SÍ necesita raw_bytes (inspector).
            self.log_import(f"Scanning PCAP paths: {self.file_paths}")
            plots, duration, sensors = engine.scan_pcap(self.file_paths, incluir_raw_bytes=True)
            self.log_import("Scan completed.")
            
            # Convertir plots a dicts para session_records y PASS
            plot_dicts = [p.to_dict() for p in plots]

            # 3. Recopilar datos de telemetría y sensores (sin PASS para velocidad instantánea)
            radar_health = dict(engine.radar_health)
            # Agregar sensores que transmitieron pero no enviaron telemetría explícita
            for s_key in sensors:
                if s_key not in radar_health:
                    radar_health[s_key] = {"system_state": "OK", "channel_ab": "N/A"}

            self.log_import("Finished run() successfully.")
            self.finished.emit(plot_dicts, radar_health)
        except Exception as e:
            import traceback
            err_details = traceback.format_exc()
            self.log_import(f"ERROR: {e}\n{err_details}")
            self.error_occurred.emit(str(e))


class TechnicalPASSAnalysisWorker(QThread):
    finished = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, plot_dicts, sensores, sensor_rpms=None, parent=None):
        super().__init__(parent)
        self.plot_dicts = plot_dicts
        self.sensores = sensores
        self.sensor_rpms = sensor_rpms or {}

    def run(self):
        try:
            from analysis.pass_analyzer import PASSAnalyticsEngine
            pass_engine = PASSAnalyticsEngine(sensores=self.sensores)
            # Mismos RPM que la consola: sin esto analyze_data cae a un RPM fallback
            # y el Pd/jitter difiere del PASS de la consola para el mismo archivo.
            pass_results = pass_engine.analyze_data(self.plot_dicts, self.sensor_rpms)
            self.finished.emit(pass_results)
        except Exception as e:
            self.error_occurred.emit(str(e))


class CentroTecnicoWindow(QMainWindow):
    def __init__(self, repo_db=None, worker=None, session_records=None,
                 db_path="pass_analytics.duckdb", profile_config=None,
                 sensor_rpms=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Centro Técnico ATSEP")
        self.resize(1280, 800)
        self._db_path = db_path
        self._worker = worker
        self._session_records = session_records or []
        # Config de la consola para que el PASS/decode de la suite coincida.
        self._profile_config = profile_config
        self._sensor_rpms = dict(sensor_rpms or {})

        # Asegurar que repo_db esté instanciado en el hilo principal
        self._repo_db = repo_db
        if not self._repo_db:
            from storage.duckdb_repo import DuckDBRepository
            try:
                self._repo_db = DuckDBRepository(self._db_path)
            except Exception as e:
                print(f"[CentroTecnicoWindow] Error instanciando DuckDBRepository en el hilo principal: {e}")

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.stats_tab = StatsWidget(self.source_provider)
        self.coverage_tab = CoverageWidget(self.source_provider, db_path=db_path)
        self.tabs.addTab(self.stats_tab, "📊 Estadísticas")
        self.tabs.addTab(self._build_pass_page(), "✅ PASS / SASS-C")
        self.monitor_tab = TechnicalMonitorWidget(self)
        self.tabs.addTab(self.monitor_tab, "📡 Monitor ATSEP")
        self.inspector_tab = InspectorWidget(self._repo_db, self._worker, self)
        self.tabs.addTab(self.inspector_tab, "🔬 Inspector")
        self.tabs.addTab(self.coverage_tab, "🛰 Cobertura")

        # Análisis y Calibración de registración (antes diálogo del menú Config).
        sensores = getattr(self.parent(), "sensores", {})
        pcap_path = getattr(self.parent(), "pcap_path", "")
        self.calib_tab = CalibrationWidget(sensores, pcap_path=pcap_path, parent=self)
        self.calib_tab.cambios_guardados.connect(self._on_calib_guardado)
        self.tabs.addTab(self.calib_tab, "🛠 Calibración")

        # Barra de herramientas superior prominente
        self._build_toolbar()
        
        # Barra de estado inferior
        self._build_statusbar()

    def _build_toolbar(self):
        toolbar = self.addToolBar("Archivo")
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #1A1C23;
                border-bottom: 2px solid #5E81AC;
                padding: 6px;
            }
        """)
        
        btn_import = QPushButton("📁 Cargar Archivo de Datos Técnicos (PCAP / Crudo)")
        btn_import.setStyleSheet("""
            QPushButton {
                background-color: #5E81AC;
                color: #ECEFF4;
                border: 1px solid #81A1C1;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #81A1C1;
                border: 1px solid #88C0D0;
            }
            QPushButton:pressed {
                background-color: #4C566A;
            }
        """)
        btn_import.clicked.connect(self._import_file)
        self.btn_import_tech = btn_import
        toolbar.addWidget(btn_import)

    def _build_pass_page(self, resultados=None) -> QWidget:
        if resultados:
            from player.pass_dashboard import PassDashboardDialog
            container = QWidget(self)
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            dialog = PassDashboardDialog(resultados, self)
            # Reparentar TODO el cuerpo del diálogo (encabezado + selector de
            # radares + tabs), no solo las tabs: así el PASS de la suite conserva
            # el selector de radares igual que el informe de la pantalla principal.
            cuerpo = dialog.layout()
            while cuerpo.count():
                item = cuerpo.takeAt(0)
                w = item.widget()
                if w is not None:
                    layout.addWidget(w)
                elif item.layout() is not None:
                    layout.addLayout(item.layout())
            self._pass_dialog = dialog
            return container
        else:
            container = QWidget(self)
            layout = QVBoxLayout(container)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            lbl = QLabel("Evaluación de Prestaciones Radar (PASS / SASS-C)\n"
                        "El análisis requiere procesar y cruzar todos los ploteos (Pd, Jitter, Bias) y puede tomar unos segundos.")
            lbl.setStyleSheet("color: #D8DEE9; font-size: 11pt; font-weight: bold; text-align: center; margin-bottom: 12px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            btn_calc = QPushButton("📊 Calcular Análisis PASS (SASS-C)")
            btn_calc.setStyleSheet("""
                QPushButton {
                    background-color: #A3BE8C;
                    color: #2E3440;
                    border: 1px solid #A3BE8C;
                    border-radius: 6px;
                    padding: 12px 28px;
                    font-size: 11pt;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #B48EAD;
                    color: #ECEFF4;
                    border: 1px solid #B48EAD;
                }
                QPushButton:pressed {
                    background-color: #4C566A;
                    color: #ECEFF4;
                }
            """)
            btn_calc.clicked.connect(self._run_lazy_pass_analysis)
            self.btn_calc_pass = btn_calc
            
            layout.addStretch(1)
            layout.addWidget(lbl)
            layout.addWidget(btn_calc, 0, Qt.AlignmentFlag.AlignCenter)
            layout.addStretch(1)
            return container

    def _console_plots(self):
        """Plots EXACTOS que usa el PASS de la consola (worker._plots -> to_dict).

        Correr el PASS sobre estos garantiza paridad con la consola; las filas de
        DuckDB normalizan campos (mode3a octal, FL string) y cambian el agrupamiento
        de targets -> estimated_period distinto -> Pd distinto.
        """
        w = self._worker
        if w is None or not hasattr(w, "_plots"):
            return None
        try:
            w._mutex.lock()
            raw = list(w._plots)
            w._mutex.unlock()
            return [p.to_dict() for p in raw]
        except Exception:
            try:
                w._mutex.unlock()
            except Exception:
                pass
            return None

    def _run_lazy_pass_analysis(self):
        # 1) Archivo importado para análisis -> esos plots. 2) Sesión actual -> los
        # mismos plots en memoria que la consola. 3) Fallback -> la fuente activa.
        plot_dicts = getattr(self, "_imported_records", None)
        if not plot_dicts:
            plot_dicts = self._console_plots()
        if not plot_dicts:
            plot_dicts = self.source_provider().load()
        if not plot_dicts:
            QMessageBox.warning(self, "Análisis PASS", "No hay datos cargados para analizar.")
            return

        self.btn_calc_pass.setEnabled(False)
        self.btn_calc_pass.setText("Procesando...")

        self._pass_calc_progress = QProgressDialog("Calculando métricas PASS (Pd, Jitter, Bias)...", None, 0, 0, self)
        self._pass_calc_progress.setWindowTitle("Procesando SASS-C")
        self._pass_calc_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._pass_calc_progress.show()

        sensores = getattr(self.parent(), "sensores", {})
        # IMPORTANTE: `_sensor_rpms` del app trae un default 12.0 por sensor (no
        # detectado), que fuerza un período erróneo de 5.0 s y un Pd inflado a 100%.
        # Sólo se usan RPM genuinamente detectados (!= 12.0); si no hay, se pasa {}
        # y analyze_data estima el período real de los datos (~detección de antena).
        raw_rpms = dict(getattr(self.parent(), "_sensor_rpms", {}) or {})
        rpms = {k: v for k, v in raw_rpms.items() if v and abs(v - 12.0) > 1e-6}
        self.pass_calc_worker = TechnicalPASSAnalysisWorker(
            plot_dicts, sensores, rpms, self)
        self.pass_calc_worker.finished.connect(self._on_lazy_pass_finished)
        self.pass_calc_worker.error_occurred.connect(self._on_lazy_pass_error)
        self.pass_calc_worker.start()

    def _on_lazy_pass_finished(self, resultados):
        self._pass_calc_progress.close()
        self.refresh_pass_page(resultados)

    def _on_lazy_pass_error(self, err_msg):
        self._pass_calc_progress.close()
        self.btn_calc_pass.setEnabled(True)
        self.btn_calc_pass.setText("📊 Calcular Análisis PASS (SASS-C)")
        QMessageBox.critical(self, "Error en Análisis", f"Ocurrió un error al calcular PASS:\n{err_msg}")

    def refresh_pass_page(self, resultados):
        # Reemplazar pestaña PASS con el nuevo dashboard calculado
        idx = -1
        for i in range(self.tabs.count()):
            if "PASS" in self.tabs.tabText(i):
                idx = i
                break
        if idx >= 0:
            old_widget = self.tabs.widget(idx)
            new_widget = self._build_pass_page(resultados)
            self.tabs.insertTab(idx, new_widget, "✅ PASS / SASS-C")
            self.tabs.removeTab(idx + 1)
            if old_widget:
                old_widget.deleteLater()

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

    def _import_file(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar Archivo(s) de Datos Técnicos", ".",
            "Todos los Soportados (*.pcap *.pcapng *.raw *.ast *.bin *.Z);;Archivos PCAP (*.pcap *.pcapng);;Archivos Crudos (*.raw *.ast *.bin *.Z);;Todos (*)"
        )
        if not file_paths:
            return

        self.btn_import_tech.setEnabled(False)

        self.progress_dialog = QProgressDialog("Inicializando importación...", "Cancelar", 0, 100, self)
        self.progress_dialog.setWindowTitle("Importación de Datos Técnicos")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoReset(False)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()

        sensores = getattr(self.parent(), "sensores", {})

        self.import_worker = TechnicalImportWorker(
            file_paths=file_paths,
            db_path=self._db_path,
            repo_db=self._repo_db,
            sensores=sensores,
            profile_config=self._profile_config,
            parent=self
        )
        self.import_worker.progress.connect(self._on_import_progress)
        self.import_worker.finished.connect(self._on_import_finished)
        self.import_worker.error_occurred.connect(self._on_import_error)
        self.progress_dialog.canceled.connect(self._cancel_import)

        self.import_worker.start()

    def _cancel_import(self):
        if hasattr(self, "import_worker"):
            try:
                self.import_worker.progress.disconnect()
                self.import_worker.finished.disconnect()
                self.import_worker.error_occurred.disconnect()
            except Exception:
                pass
            if self.import_worker.isRunning():
                self.import_worker.terminate()
                self.import_worker.wait()
        self.btn_import_tech.setEnabled(True)
        QMessageBox.warning(self, "Importación", "Importación cancelada por el usuario.")

    def _on_import_progress(self, val, total):
        if total > 0:
            pct = int(100 * val / total)
            self.progress_dialog.setValue(pct)
            self.progress_dialog.setLabelText(f"Decodificando: {val} / {total} plots...")

    def _on_import_finished(self, plot_dicts, radar_health):
        self.progress_dialog.blockSignals(True)
        self.progress_dialog.close()
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        self.btn_import_tech.setEnabled(True)

        # Guardar en memoria de sesión. _imported_records marca que el PASS debe
        # correr sobre el archivo importado (no sobre los plots de la consola).
        self._session_records = plot_dicts
        self._imported_records = plot_dicts

        # Si no teníamos repo_db y el worker lo creó
        if not self._repo_db:
            self._repo_db = self.import_worker.repo_db

        # RPM detectados en este decode -> el auto-PASS los usa (coincide con consola).
        try:
            if self.import_worker.detected_rpms:
                self._sensor_rpms = dict(self.import_worker.detected_rpms)
        except Exception:
            pass

        # Guardar ploteos importados en DuckDB en el hilo principal
        if self._repo_db:
            try:
                self._repo_db.recrear_tabla()
                self._repo_db.guardar_plots_bulk(plot_dicts)
            except Exception as e:
                QMessageBox.critical(
                    self, "Error de Guardado en Base de Datos",
                    f"No se pudieron guardar los ploteos en DuckDB:\n{e}"
                )

        # Actualizar fuentes y vistas en las pestañas (Estadísticas y Cobertura)
        self._on_source_changed(True)

        # Graficar automáticamente en la pestaña Stats
        self.stats_tab.generate()

        # Actualizar pestaña del Inspector con el nuevo repo
        self.inspector_tab.refresh(self._repo_db)

        # Resetear la pestaña PASS para que muestre el botón de calcular para el nuevo archivo
        self.refresh_pass_page(None)

        # Actualizar el Monitor ATSEP con el estado de los sensores
        for key, data in radar_health.items():
            self.monitor_tab.update_sensor_status(key, data)

        QMessageBox.information(
            self, "Importación Exitosa",
            f"Se importaron {len(plot_dicts)} plots técnicos exitosamente en pocos segundos.\n"
            "A continuación se calcularán automáticamente las prestaciones PASS / SASS-C."
        )

        if plot_dicts:
            self._run_lazy_pass_analysis()

    def _on_import_error(self, err_msg):
        self.progress_dialog.blockSignals(True)
        self.progress_dialog.close()
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        self.btn_import_tech.setEnabled(True)
        QMessageBox.critical(
            self, "Error de Importación",
            f"Ocurrió un error al decodificar/importar los datos:\n{err_msg}"
        )

    def current_source_kind(self):
        return "duckdb" if self.rb_duckdb.isChecked() else "session"

    def source_provider(self):
        """Devuelve la DataSource activa según el conmutador.

        Para DuckDB reutiliza la conexión viva del app (repo_db.conn) —los mismos
        datos que el PASS— y así evita una segunda conexión que DuckDB rechazaría.
        """
        from player.stats.data_source import DuckDBSource, SessionSource
        if self.current_source_kind() == "duckdb":
            conn = getattr(self._repo_db, "conn", None) if self._repo_db else None
            return DuckDBSource(self._db_path, conn=conn)
        return SessionSource(self._session_records)

    def _on_source_changed(self, _checked):
        if hasattr(self.stats_tab, "on_source_changed"):
            self.stats_tab.on_source_changed()
        if hasattr(self.coverage_tab, "on_source_changed"):
            self.coverage_tab.on_source_changed()

    def _on_calib_guardado(self):
        """Tras guardar/desactivar correcciones: el app recarga sus sensores."""
        app = self.parent()
        if app is not None and hasattr(app, "_recargar_sensores_calib"):
            app._recargar_sensores_calib()
