"""PySide6 GUI: drag an ebook in, get it converted and placed on the Pico."""
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from converter import CONVERTERS, convert, suggest_title

PICO_BOOKS_DIR = Path(__file__).resolve().parent.parent / "pico" / "books"
STYLE_PATH = Path(__file__).resolve().parent / "style.qss"


def slugify(title):
    slug = re.sub(r"[^\w\s-]", "", title).strip().lower()
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug or "book"


class DropZone(QFrame):
    file_selected = Signal(str)
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setFixedHeight(150)
        self.setProperty("dragging", False)
        self.setProperty("hasFile", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)

        self.icon_label = QLabel("📖")
        self.icon_label.setObjectName("dropIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel("Drop an ebook here")
        self.title_label.setObjectName("dropTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.subtitle_label = QLabel("or click to browse  ·  .epub supported")
        self.subtitle_label.setObjectName("dropSubtitle")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)

    @staticmethod
    def _supported(path):
        return Path(path).suffix.lower() in CONVERTERS

    def dragEnterEvent(self, event: QDragEnterEvent):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(self._supported(url.toLocalFile()) for url in urls):
            self._set_property("dragging", True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_property("dragging", False)

    def dropEvent(self, event: QDropEvent):
        self._set_property("dragging", False)
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if self._supported(path):
                self.file_selected.emit(path)
                event.acceptProposedAction()
                return
        event.ignore()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def _set_property(self, name, value):
        self.setProperty(name, value)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_file(self, name):
        self._set_property("hasFile", True)
        self.icon_label.setText("✅")
        self.title_label.setText(name)
        self.subtitle_label.setText("Click or drop another file to replace it")

    def reset(self):
        self._set_property("hasFile", False)
        self.icon_label.setText("📖")
        self.title_label.setText("Drop an ebook here")
        self.subtitle_label.setText("or click to browse  ·  .epub supported")


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.source_path = None

        self.setObjectName("root")
        self.setWindowTitle("Tempo Companion")
        self.resize(520, 640)
        self.setMinimumSize(460, 560)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(28, 26, 28, 24)
        root_layout.setSpacing(14)

        title = QLabel("Tempo Companion")
        title.setObjectName("appTitle")
        subtitle = QLabel("Convert ebooks and send them to your Pico reader")
        subtitle.setObjectName("appSubtitle")
        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)
        root_layout.addSpacing(6)

        root_layout.addWidget(self._section_label("EBOOK"))

        self.drop_zone = DropZone()
        self.drop_zone.file_selected.connect(self.set_source_path)
        self.drop_zone.clicked.connect(self.choose_file)
        root_layout.addWidget(self.drop_zone)

        root_layout.addWidget(self._section_label("TITLE ON THE PICO"))

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Book title")
        root_layout.addWidget(self.title_input)

        self.convert_button = QPushButton("Convert && Add to Pico")
        self.convert_button.setObjectName("primaryButton")
        self.convert_button.setEnabled(False)
        self.convert_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.convert_button.clicked.connect(self.run_convert)
        root_layout.addWidget(self.convert_button)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setProperty("state", "idle")
        self.status_label.setWordWrap(True)
        root_layout.addWidget(self.status_label)

        root_layout.addSpacing(6)
        library_header = QHBoxLayout()
        library_header.addWidget(self._section_label("BOOKS ON THE PICO"))
        library_header.addStretch()
        root_layout.addLayout(library_header)

        self.book_list = QListWidget()
        self.book_list.setObjectName("bookList")
        root_layout.addWidget(self.book_list, stretch=1)

        self.refresh_book_list()

    @staticmethod
    def _section_label(text):
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def choose_file(self):
        extensions = " ".join(f"*{ext}" for ext in CONVERTERS)
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose an ebook", "", f"Supported ebooks ({extensions});;All files (*)"
        )
        if path:
            self.set_source_path(path)

    def set_source_path(self, path):
        self.source_path = Path(path)
        self.drop_zone.set_file(self.source_path.name)
        self.title_input.setText(suggest_title(self.source_path))
        self.convert_button.setEnabled(True)
        self._set_status("", "idle")

    def run_convert(self):
        if not self.source_path:
            return
        title = self.title_input.text().strip() or self.source_path.stem
        destination = PICO_BOOKS_DIR / f"{slugify(title)}.txt"

        if destination.exists():
            answer = QMessageBox.question(
                self,
                "Overwrite?",
                f'"{destination.name}" already exists on the Pico. Overwrite it?',
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        try:
            PICO_BOOKS_DIR.mkdir(parents=True, exist_ok=True)
            text = convert(self.source_path, destination)
        except Exception as error:
            self._set_status(f"Failed: {error}", "error")
            return

        word_count = len(text.split())
        self._set_status(
            f'Added "{title}" to the Pico ({word_count:,} words) as {destination.name}',
            "success",
        )
        self.refresh_book_list()

    def refresh_book_list(self):
        self.book_list.clear()
        books = sorted(PICO_BOOKS_DIR.glob("*.txt")) if PICO_BOOKS_DIR.exists() else []
        if not books:
            item = QListWidgetItem("No books yet — convert one above")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setForeground(QColor("#55576a"))
            self.book_list.addItem(item)
            return
        for book_path in books:
            word_count = len(book_path.read_text(encoding="utf-8").split())
            name = book_path.stem.replace("_", " ").title()
            self.book_list.addItem(f"{name}  ·  {word_count:,} words")

    def _set_status(self, text, state):
        self.status_label.setText(text)
        self.status_label.setProperty("state", state)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE_PATH.read_text(encoding="utf-8"))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
