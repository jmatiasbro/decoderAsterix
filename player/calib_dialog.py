"""
player/calib_dialog.py — Fase 6: panel técnico de calibración de registración.

Corre el ajuste de red (fusion.calib_network) sobre un PCAP, muestra las
propuestas por sensor (editable) y escribe el bloque `registration` en los
archivos default-site-params/{sac}_{sic}.json (con backup .bak).

USO EXCLUSIVO DEL ROL TÉCNICO: el llamador (main_window) gatea la apertura.
"""
import os
import json
import shutil

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QCheckBox,
    QDoubleSpinBox, QApplication, QWidget, QProgressBar,
)

SITE_DIR = "default-site-params"


class _SolverThread(QThread):
    """Corre el LSQ de red fuera del hilo de UI."""
    done = pyqtSignal(object)
    fail = pyqtSignal(str)
    progress = pyqtSignal(int, int)   # (actual, total) del escaneo PCAP

    def __init__(self, pcap, sensores, iteraciones=8):
        super().__init__()
        self.pcap, self.sensores, self.iter = pcap, sensores, iteraciones

    def run(self):
        try:
            from fusion.calib_network import resolver_red
            from fusion.calib_solver import evaluar
            report = resolver_red(self.pcap, self.sensores, iteraciones=self.iter,
                                  progress_cb=lambda a, t: self.progress.emit(a, t))
            self.done.emit(evaluar(report))
        except Exception as e:
            self.fail.emit(str(e))


VERDICT_ES = {
    'applicable': 'Aplicable',
    'aligned': 'Ya alineado',
    'insufficient_samples': 'Pocas muestras',
    'low_coverage': 'Cobertura insuficiente',
    'high_residual': 'Medición ruidosa',
}


class CalibrationDialog(QDialog):
    COLS = ["Radar (SAC/SIC)", "Muestras", "Cobertura 360°",
            "Corrección azimut (°)", "Corrección rango (NM)",
            "Tipo", "Estado", "Aplicar"]

    def __init__(self, sensores, pcap_path="", parent=None):
        super().__init__(parent)
        self.sensores = sensores
        self.pcap_path = pcap_path
        self._thread = None
        self.setWindowTitle("Análisis y Calibración")
        self.resize(820, 560)
        self._build()

    QSS = """
        QDialog { background-color: #0E131F; }
        QLabel { color: #E0E6ED; font-family: 'Segoe UI', sans-serif; font-size: 9pt; }
        QPushButton {
            background-color: #121824; border: 1px solid #00E5FF; border-radius: 4px;
            color: #00E5FF; font-family: 'Segoe UI', sans-serif; font-size: 9pt;
            font-weight: bold; padding: 6px 14px;
        }
        QPushButton:hover { border: 1px solid #39FF14; color: #39FF14;
                            background-color: rgba(57,255,20,20); }
        QPushButton:pressed { background-color: rgba(57,255,20,50); }
        QPushButton:disabled { color: #5A6273; border: 1px solid #2A3142; }
        QTableWidget {
            background-color: #0B0E14; alternate-background-color: #121824;
            gridline-color: #2A3142; color: #E0E6ED; border: 1px solid #4B5263;
            border-radius: 4px; font-size: 9pt;
        }
        QTableWidget::item:selected { background-color: rgba(0,229,255,45); }
        QHeaderView::section {
            background-color: #121824; color: #00E5FF; border: 1px solid #2A3142;
            padding: 5px; font-weight: bold;
        }
        QTableCornerButton::section { background-color: #121824; border: 1px solid #2A3142; }
        QDoubleSpinBox {
            background-color: #1A2130; color: #FFFFFF; border: 1px solid #4B5263;
            border-radius: 3px; padding: 2px;
        }
        QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #00E5FF;
                               background-color: #1A2130; border-radius: 3px; }
        QCheckBox::indicator:checked { background-color: #00E5FF; }
        QProgressBar {
            border: 1px solid #4B5263; border-radius: 4px; text-align: center;
            color: #FFFFFF; background-color: #121824;
        }
        QProgressBar::chunk { background-color: #00E5FF; border-radius: 3px; }
    """

    def _build(self):
        self.setStyleSheet(self.QSS)
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.lbl_pcap = QLabel(self._pcap_label())
        self.lbl_pcap.setWordWrap(True)
        btn_pick = QPushButton("Elegir PCAP…")
        btn_pick.clicked.connect(self._pick_pcap)
        self.btn_calc = QPushButton("Calcular correcciones")
        self.btn_calc.clicked.connect(self._calcular)
        top.addWidget(self.lbl_pcap, 1)
        top.addWidget(btn_pick)
        top.addWidget(self.btn_calc)
        lay.addLayout(top)

        self.tabla = QTableWidget(0, len(self.COLS))
        self.tabla.setHorizontalHeaderLabels(self.COLS)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tabla, 1)

        self.barra = QProgressBar()
        self.barra.setVisible(False)
        lay.addWidget(self.barra)

        self.lbl_estado = QLabel("Elegí un PCAP y apretá «Calcular». (Es offline: no inicia playback ni UDP.)")
        lay.addWidget(self.lbl_estado)

        bot = QHBoxLayout()
        self.btn_save = QPushButton("Guardar y aplicar a tildados")
        self.btn_save.clicked.connect(self._guardar)
        self.btn_save.setEnabled(False)
        self.btn_off = QPushButton("Desactivar tildados")
        self.btn_off.clicked.connect(self._desactivar)
        self.btn_off.setEnabled(False)
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.reject)
        bot.addStretch(1)
        bot.addWidget(self.btn_save)
        bot.addWidget(self.btn_off)
        bot.addWidget(btn_close)
        lay.addLayout(bot)

    def _pcap_label(self):
        return f"PCAP: {os.path.basename(self.pcap_path)}" if self.pcap_path else "PCAP: (ninguno)"

    def _pick_pcap(self):
        path, _ = QFileDialog.getOpenFileName(self, "Elegir PCAP", "", "PCAP (*.pcap);;Todos (*)")
        if path:
            self.pcap_path = path
            self.lbl_pcap.setText(self._pcap_label())

    def _calcular(self):
        if not self.pcap_path or not os.path.exists(self.pcap_path):
            QMessageBox.warning(self, "PCAP", "Elegí un archivo PCAP válido.")
            return
        self.btn_calc.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.barra.setVisible(True)
        self.barra.setRange(0, 0)  # indeterminado hasta el primer progreso
        self.lbl_estado.setText("Escaneando PCAP… (luego corre el LSQ de red)")
        self._thread = _SolverThread(self.pcap_path, self.sensores)
        self._thread.progress.connect(self._on_progress)
        self._thread.done.connect(self._on_done)
        self._thread.fail.connect(self._on_fail)
        self._thread.start()

    def _on_progress(self, actual, total):
        if total > 0:
            self.barra.setRange(0, total)
            self.barra.setValue(actual)
            if actual >= total:
                self.lbl_estado.setText("Calculando correcciones…")
                self.barra.setRange(0, 0)  # indeterminado durante el solve

    def _on_fail(self, msg):
        self.barra.setVisible(False)
        self.btn_calc.setEnabled(True)
        self.lbl_estado.setText("Error en el cálculo.")
        QMessageBox.critical(self, "Error", msg)

    def _on_done(self, prop):
        self.barra.setVisible(False)
        self.btn_calc.setEnabled(True)
        self._poblar(prop['proposals'])
        n_app = sum(1 for p in prop['proposals'] if p['registration']['verdict'] == 'applicable')
        self.lbl_estado.setText(f"{len(prop['proposals'])} sensores · {n_app} aplicables (tildados por defecto).")
        self.btn_save.setEnabled(True)
        self.btn_off.setEnabled(True)

    def _poblar(self, proposals):
        self.tabla.setRowCount(0)
        for p in proposals:
            r = p['registration']; st = r['stats']
            row = self.tabla.rowCount()
            self.tabla.insertRow(row)

            def _item(txt, editable=False):
                it = QTableWidgetItem(str(txt))
                if not editable:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                return it

            self.tabla.setItem(row, 0, _item(p['sac_sic']))
            self.tabla.setItem(row, 1, _item(st['n']))
            self.tabla.setItem(row, 2, _item(f"{st['coverage_az_pct']:.0f}"))

            sp_az = QDoubleSpinBox(); sp_az.setRange(-20, 20); sp_az.setDecimals(3)
            sp_az.setSingleStep(0.01); sp_az.setValue(r['azimuth_offset_deg'])
            self.tabla.setCellWidget(row, 3, sp_az)
            sp_rng = QDoubleSpinBox(); sp_rng.setRange(-20, 20); sp_rng.setDecimals(3)
            sp_rng.setSingleStep(0.01); sp_rng.setValue(r['range_offset_nm'])
            self.tabla.setCellWidget(row, 4, sp_rng)

            self.tabla.setItem(row, 5, _item("Absoluta" if r['absolute'] else "Relativa"))
            it_estado = _item(VERDICT_ES.get(r['verdict'], r['verdict']))
            _colores = {'applicable': '#39FF14', 'aligned': '#00E5FF'}
            it_estado.setForeground(QColor(_colores.get(r['verdict'], '#8A93A6')))
            self.tabla.setItem(row, 6, it_estado)

            chk = QCheckBox()
            chk.setChecked(r['verdict'] == 'applicable')
            cont = QWidget(); cl = QHBoxLayout(cont); cl.setContentsMargins(0, 0, 0, 0)
            cl.setAlignment(Qt.AlignmentFlag.AlignCenter); cl.addWidget(chk)
            self.tabla.setCellWidget(row, 7, cont)
            # guardar refs para leer al guardar
            sp_az.setProperty("sac_sic", p['sac_sic'])
            self.tabla.item(row, 0).setData(Qt.ItemDataRole.UserRole,
                                            {'chk': chk, 'az': sp_az, 'rng': sp_rng,
                                             'src': r['source'], 'abs': r['absolute'],
                                             'stats': st, 'verdict': r['verdict']})

    def _guardar(self):
        cambios = []
        for row in range(self.tabla.rowCount()):
            ref = self.tabla.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if not ref or not ref['chk'].isChecked():
                continue
            sac_sic = self.tabla.item(row, 0).text()
            cambios.append((sac_sic, ref['az'].value(), ref['rng'].value(), ref))
        if not cambios:
            QMessageBox.information(self, "Guardar", "No hay sensores tildados.")
            return
        if QMessageBox.question(
            self, "Confirmar",
            f"Se escribirá registration.enabled=true en {len(cambios)} sensor(es) "
            f"y se moverá su posición. ¿Continuar?") != QMessageBox.StandardButton.Yes:
            return

        errores = []
        for sac_sic, az, rng, ref in cambios:
            try:
                self._escribir_registration(sac_sic, az, rng, ref)
            except Exception as e:
                errores.append(f"{sac_sic}: {e}")
        if errores:
            QMessageBox.warning(self, "Guardado parcial", "Errores:\n" + "\n".join(errores))
        else:
            QMessageBox.information(
                self, "Guardado",
                f"{len(cambios)} sensor(es) actualizados.\n"
                "Recargá/reproducí la captura para que la corrección tome efecto.")
        self.accept()

    def _desactivar(self):
        sensores = [self.tabla.item(r, 0).text() for r in range(self.tabla.rowCount())
                    if (ref := self.tabla.item(r, 0).data(Qt.ItemDataRole.UserRole))
                    and ref['chk'].isChecked()]
        if not sensores:
            QMessageBox.information(self, "Desactivar", "No hay sensores tildados.")
            return
        if QMessageBox.question(
            self, "Confirmar",
            f"Se desactivará la corrección (enabled=false) en {len(sensores)} sensor(es). "
            "El offset calculado se conserva. ¿Continuar?") != QMessageBox.StandardButton.Yes:
            return
        hechos, omitidos, errores = 0, 0, []
        for sac_sic in sensores:
            try:
                if self._desactivar_registration(sac_sic):
                    hechos += 1
                else:
                    omitidos += 1
            except Exception as e:
                errores.append(f"{sac_sic}: {e}")
        msg = f"Desactivados: {hechos}. Sin corrección previa: {omitidos}."
        if errores:
            QMessageBox.warning(self, "Desactivación parcial", msg + "\nErrores:\n" + "\n".join(errores))
        else:
            QMessageBox.information(self, "Desactivado",
                                    msg + "\nRecargá/reproducí la captura para ver el efecto.")
        self.accept()

    def _desactivar_registration(self, sac_sic) -> bool:
        """Pone registration.enabled=false (conserva el offset). Devuelve False si
        el sensor no tenía bloque registration."""
        sac, sic = sac_sic.split('/')
        path = os.path.join(SITE_DIR, f"{sac}_{sic}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"no existe {path}")
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not data.get('registration'):
            return False
        shutil.copyfile(path, path + ".bak")
        data['registration']['enabled'] = False
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True

    def _escribir_registration(self, sac_sic, az, rng, ref):
        sac, sic = sac_sic.split('/')
        path = os.path.join(SITE_DIR, f"{sac}_{sic}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"no existe {path}")
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        shutil.copyfile(path, path + ".bak")
        data['registration'] = {
            'azimuth_offset_deg': round(az, 4),
            'range_offset_nm': round(rng, 4),
            'range_scale': 1.0,
            'enabled': True,
            'source': ref['src'],
            'absolute': ref['abs'],
            'stats': ref['stats'],
            'verdict': ref['verdict'],
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
