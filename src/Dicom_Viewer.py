import sys
import pydicom
import numpy as np
import random
import string
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QPushButton,
    QFileDialog, QLabel, QWidget, QScrollArea, QGridLayout, QTableWidget,
    QTableWidgetItem, QLineEdit, QHBoxLayout, QInputDialog, QMessageBox
)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QTimer


class TagsWindow(QMainWindow):
    def __init__(self, dataset):
        super().__init__()
        self.dataset = dataset
        self.setWindowTitle("DICOM Tags")
        self.resize(600, 400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search for tags...")
        self.search_input.textChanged.connect(self.filter_tags)
        search_layout.addWidget(self.search_input)

        self.tag_table = QTableWidget()
        self.tag_table.setColumnCount(2)
        self.tag_table.setHorizontalHeaderLabels(["Tag", "Value"])
        self.tag_table.horizontalHeader().setStretchLastSection(True)
        self.populate_tag_table()

        layout.addLayout(search_layout)
        layout.addWidget(self.tag_table)
        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def populate_tag_table(self):
        self.tag_table.setRowCount(0)
        for tag in self.dataset.dir():
            value = getattr(self.dataset, tag, "")
            self.tag_table.insertRow(self.tag_table.rowCount())
            self.tag_table.setItem(self.tag_table.rowCount() - 1, 0, QTableWidgetItem(tag))
            self.tag_table.setItem(self.tag_table.rowCount() - 1, 1, QTableWidgetItem(str(value)))

    def filter_tags(self):
        filter_text = self.search_input.text().lower()
        self.tag_table.setRowCount(0)
        for tag in self.dataset.dir():  
            if filter_text in tag.lower():
                value = getattr(self.dataset, tag, "")
                self.tag_table.insertRow(self.tag_table.rowCount())
                self.tag_table.setItem(self.tag_table.rowCount() - 1, 0, QTableWidgetItem(tag))
                self.tag_table.setItem(self.tag_table.rowCount() - 1, 1, QTableWidgetItem(str(value)))


class DICOMViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DICOM Viewer")
        self.resize(800, 600)
        self.datasets = []
        self.timer = None
        self.current_frame = 0
        self.tags_window = None

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)

        self.load_button = QPushButton("Load DICOM Folder")
        self.load_button.clicked.connect(self.load_dicom_folder)

        self.tags_button = QPushButton("Tags")
        self.tags_button.clicked.connect(self.show_tags)
        self.tags_button.setEnabled(False)

        self.anonymize_button = QPushButton("Anonymize")
        self.anonymize_button.clicked.connect(self.anonymize_dicom)
        self.anonymize_button.setEnabled(False)

        self.main_elements_button = QPushButton("Main Elements")
        self.main_elements_button.clicked.connect(self.show_main_elements)
        self.main_elements_button.setEnabled(False)

        self.scroll_area = QScrollArea()
        self.tile_widget = QWidget()
        self.tile_layout = QGridLayout()
        self.tile_widget.setLayout(self.tile_layout)
        self.scroll_area.setWidget(self.tile_widget)
        self.scroll_area.setWidgetResizable(True)

        self.layout.addWidget(self.load_button)
        self.layout.addWidget(self.tags_button)
        self.layout.addWidget(self.anonymize_button)
        self.layout.addWidget(self.main_elements_button)
        self.layout.addWidget(self.scroll_area)

    def load_dicom_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select DICOM Folder")
        if not folder_path:
            return

        dicom_files = list(Path(folder_path).glob("*.dcm"))
        if not dicom_files:
            QMessageBox.warning(self, "No DICOM Files", "No DICOM files found in the selected folder.")
            return

        self.datasets = [pydicom.dcmread(str(file)) for file in dicom_files]

        if hasattr(self.datasets[0], "NumberOfFrames") and int(self.datasets[0].NumberOfFrames) > 1:
            # M2D file (multi-frame DICOM)
            self.display_cine(self.datasets[0].pixel_array)
        else:
            # Multiple DICOM files
            self.display_tiles([ds.pixel_array for ds in self.datasets])

        self.tags_button.setEnabled(True)
        self.anonymize_button.setEnabled(True)
        self.main_elements_button.setEnabled(True)

    def display_tiles(self, pixel_arrays):
        for i in reversed(range(self.tile_layout.count())):
            self.tile_layout.itemAt(i).widget().deleteLater()

        tile_size = 150
        for idx, pixel_array in enumerate(pixel_arrays):
            slice_array = (pixel_array - np.min(pixel_array)) / (np.max(pixel_array) - np.min(pixel_array)) * 255
            slice_array = slice_array.astype(np.uint8)

            height, width = slice_array.shape
            qimage = QImage(slice_array.data, width, height, width, QImage.Format_Grayscale8)
            pixmap = QPixmap.fromImage(qimage).scaled(tile_size, tile_size, Qt.KeepAspectRatio)

            tile_label = QLabel()
            tile_label.setPixmap(pixmap)
            tile_label.setAlignment(Qt.AlignCenter)
            self.tile_layout.addWidget(tile_label, idx // 8, idx % 8)

    def display_cine(self, pixel_array):
        if self.timer:
            self.timer.stop()

        for i in reversed(range(self.tile_layout.count())):
            self.tile_layout.itemAt(i).widget().deleteLater()

        self.current_frame = 0
        height, width = pixel_array.shape[1:]

        self.frames = [
            ((frame - np.min(frame)) / (np.max(frame) - np.min(frame)) * 255).astype(np.uint8)
            for frame in pixel_array
        ]

        self.cine_label = QLabel()
        self.cine_label.setAlignment(Qt.AlignCenter)
        self.tile_layout.addWidget(self.cine_label)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_cine_frame)
        self.timer.start(100)

    def update_cine_frame(self):
        frame = self.frames[self.current_frame]
        height, width = frame.shape
        qimage = QImage(frame.data, width, height, width, QImage.Format_Grayscale8)
        pixmap = QPixmap.fromImage(qimage).scaled(400, 400, Qt.KeepAspectRatio)
        self.cine_label.setPixmap(pixmap)

        self.current_frame = (self.current_frame + 1) % len(self.frames)

    def show_tags(self):
        if self.datasets:
            self.tags_window = TagsWindow(self.datasets[0])
            self.tags_window.show()

    def anonymize_dicom(self):
        if not self.datasets:
            return

        prefix, ok = QInputDialog.getText(self, "Anonymization Prefix", "Enter the prefix for anonymization:")
        if not ok or not prefix.strip():
            QMessageBox.warning(self, "Invalid Input", "Anonymization prefix cannot be empty.")
            return

        for ds in self.datasets:
            for tag in ["PatientName", "PatientID", "StudyID"]:
                if hasattr(ds, tag):
                    setattr(ds, tag, prefix + ''.join(random.choices(string.digits, k=5)))

        save_folder = QFileDialog.getExistingDirectory(self, "Save Anonymized Files To")
        if not save_folder:
            return

        try:
            for idx, ds in enumerate(self.datasets):
                save_path = Path(save_folder) / f"anonymized_{idx + 1}.dcm"
                ds.save_as(str(save_path))

            QMessageBox.information(self, "Success", "All files anonymized and saved successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save anonymized files: {e}")

    
    def show_main_elements(self):
        if not self.datasets:
            return

        ds = self.datasets[0]
        elements = {
            "Patient Name": getattr(ds, "ReferringPhysicianName", "N/A"),
            "Patient ID": getattr(ds, "PatientID", "N/A"),
            "Study Description": getattr(ds, "StudyDescription", "N/A"),
            "Modality": getattr(ds, "Modality", "N/A"),
            "Physician's Name": getattr(ds, "PatientName", "N/A"),
            "Image Dimensions": f"{ds.Rows}x{ds.Columns}" if hasattr(ds, "Rows") and hasattr(ds, "Columns") else "N/A"
        }

        main_elements_text = "\n".join(f"{key}: {value}" for key, value in elements.items())
        QMessageBox.information(self, "Main Elements", main_elements_text)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DICOMViewer()
    window.show()
    sys.exit(app.exec_())
