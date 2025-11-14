import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QFileDialog, QTextEdit, QLineEdit, QGroupBox
)

from safe_ro_core import NDVIProcessor, Sentinel1FloodDetector, FireDetector


class SafeROGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SAFE-RO – Satellite Hazard Analyzer")
        self.resize(800, 600)

        # Paths
        self.red_path = ""
        self.nir_path = ""
        self.s1_path = ""
        self.firms_path = ""

        # Widgets
        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)

        self._init_ui()

    # ---------------- UI ---------------- #

    def _init_ui(self):
        main_layout = QVBoxLayout()

        main_layout.addWidget(self._create_ndvi_group())
        main_layout.addWidget(self._create_flood_group())
        main_layout.addWidget(self._create_fire_group())

        # Output box
        main_layout.addWidget(QLabel("Console output:"))
        main_layout.addWidget(self.output_box)

        self.setLayout(main_layout)

    def _create_ndvi_group(self):
        group = QGroupBox("NDVI (vegetation index)")
        layout = QVBoxLayout()

        # Red band
        red_layout = QHBoxLayout()
        self.red_line = QLineEdit()
        btn_red = QPushButton("Select RED band (.tif)")
        btn_red.clicked.connect(self.select_red)
        red_layout.addWidget(self.red_line)
        red_layout.addWidget(btn_red)

        # NIR band
        nir_layout = QHBoxLayout()
        self.nir_line = QLineEdit()
        btn_nir = QPushButton("Select NIR band (.tif)")
        btn_nir.clicked.connect(self.select_nir)
        nir_layout.addWidget(self.nir_line)
        nir_layout.addWidget(btn_nir)

        # Compute button
        btn_ndvi = QPushButton("Compute NDVI stats")
        btn_ndvi.clicked.connect(self.compute_ndvi)

        layout.addLayout(red_layout)
        layout.addLayout(nir_layout)
        layout.addWidget(btn_ndvi)
        group.setLayout(layout)
        return group

    def _create_flood_group(self):
        group = QGroupBox("Flood detection (Sentinel-1)")
        layout = QVBoxLayout()

        s1_layout = QHBoxLayout()
        self.s1_line = QLineEdit()
        btn_s1 = QPushButton("Select Sentinel-1 band (.tif)")
        btn_s1.clicked.connect(self.select_s1)
        s1_layout.addWidget(self.s1_line)
        s1_layout.addWidget(btn_s1)

        # Threshold line edit (optional)
        thr_layout = QHBoxLayout()
        self.thr_line = QLineEdit()
        self.thr_line.setPlaceholderText("Optional threshold (e.g. -16.5)")
        thr_layout.addWidget(QLabel("Threshold:"))
        thr_layout.addWidget(self.thr_line)

        btn_flood = QPushButton("Detect flooded area")
        btn_flood.clicked.connect(self.detect_floods)

        layout.addLayout(s1_layout)
        layout.addLayout(thr_layout)
        layout.addWidget(btn_flood)
        group.setLayout(layout)
        return group

    def _create_fire_group(self):
        group = QGroupBox("Fire detections (FIRMS CSV)")
        layout = QVBoxLayout()

        firms_layout = QHBoxLayout()
        self.firms_line = QLineEdit()
        btn_firms = QPushButton("Select FIRMS CSV")
        btn_firms.clicked.connect(self.select_firms)
        firms_layout.addWidget(self.firms_line)
        firms_layout.addWidget(btn_firms)

        btn_fires = QPushButton("Count high-confidence fires")
        btn_fires.clicked.connect(self.detect_fires)

        layout.addLayout(firms_layout)
        layout.addWidget(btn_fires)
        group.setLayout(layout)
        return group

    # ---------------- File selection slots ---------------- #

    def select_red(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select RED band", "", "TIF files (*.tif *.tiff)")
        if path:
            self.red_path = path
            self.red_line.setText(path)

    def select_nir(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select NIR band", "", "TIF files (*.tif *.tiff)")
        if path:
            self.nir_path = path
            self.nir_line.setText(path)

    def select_s1(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Sentinel-1 band", "", "TIF files (*.tif *.tiff)")
        if path:
            self.s1_path = path
            self.s1_line.setText(path)

    def select_firms(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select FIRMS CSV", "", "CSV files (*.csv)")
        if path:
            self.firms_path = path
            self.firms_line.setText(path)

    # ---------------- Actions ---------------- #

    def log(self, text: str):
        self.output_box.append(text)

    def compute_ndvi(self):
        if not Path(self.red_path).is_file() or not Path(self.nir_path).is_file():
            self.log("[NDVI] Please select both RED and NIR bands.")
            return

        proc = NDVIProcessor(self.red_path, self.nir_path)
        ndvi = proc.compute_ndvi()
        stats = {
            "min": float(ndvi.min()),
            "max": float(ndvi.max()),
            "mean": float(ndvi.mean()),
        }
        self.log(f"[NDVI] Stats: {stats}")

    def detect_floods(self):
        if not Path(self.s1_path).is_file():
            self.log("[FLOOD] Please select a Sentinel-1 band.")
            return

        threshold = None
        txt = self.thr_line.text().strip()
        if txt:
            try:
                threshold = float(txt)
            except ValueError:
                self.log("[FLOOD] Invalid threshold, using automatic percentile.")

        det = Sentinel1FloodDetector(self.s1_path)
        mask = det.detect(threshold=threshold)
        flooded_percent = float(mask.mean() * 100.0)
        self.log(f"[FLOOD] Estimated flooded area: {flooded_percent:.2f}%")

    def detect_fires(self):
        if not Path(self.firms_path).is_file():
            self.log("[FIRE] Please select a FIRMS CSV file.")
            return

        det = FireDetector(self.firms_path)
        fires = det.filter_by_confidence(80)
        self.log(f"[FIRE] High-confidence fires (>=80): {len(fires)}")



def main():
    app = QApplication(sys.argv)
    gui = SafeROGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
