"""PySide6 GUI: drag an ebook in, get it converted and placed on the Pico."""
import re
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from converter import CONVERTERS, convert, peek_meta, strip_meta_header, suggest_author, suggest_title

PICO_BOOKS_DIR = Path(__file__).resolve().parent.parent / "pico" / "books"
STYLE_PATH = Path(__file__).resolve().parent / "style.qss"


def slugify(title):
    slug = re.sub(r"[^\w\s-]", "", title).strip().lower()
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug or "book"


def format_library_path(folder):
    try:
        relative = folder.relative_to(PICO_BOOKS_DIR)
        return "Books" if str(relative) == "." else f"Books/{relative}"
    except ValueError:
        return str(folder)


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


class BookTree(QTreeWidget):
    """The library tree, with drag-and-drop to reorganize books/folders that
    are already on the Pico — separate from the DropZone above, which is
    only for importing new ebooks.
    """

    library_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

    def dragEnterEvent(self, event):
        if event.source() is self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() is self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        # Only handle drags that originated inside this tree — dropping a
        # file from Finder here isn't supported (use the drop zone above).
        if event.source() is not self:
            event.ignore()
            return

        source_item = self.currentItem()
        source_path = source_item.data(0, Qt.ItemDataRole.UserRole) if source_item else None
        if not isinstance(source_path, Path) or source_path == PICO_BOOKS_DIR:
            event.ignore()
            return

        target_item = self.itemAt(event.position().toPoint())
        target_folder = PICO_BOOKS_DIR
        if target_item is not None:
            target_path = target_item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(target_path, Path):
                target_folder = target_path if target_path.is_dir() else target_path.parent

        if source_path.is_dir() and (target_folder == source_path or target_folder.is_relative_to(source_path)):
            event.ignore()
            return
        if target_folder == source_path.parent:
            event.ignore()
            return

        destination = target_folder / source_path.name
        if destination.exists():
            answer = QMessageBox.question(
                self, "Overwrite?", f'"{source_path.name}" already exists there. Overwrite it?'
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        target_folder.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(destination))
        event.acceptProposedAction()
        self.library_changed.emit(f'Moved "{source_path.name}" to {format_library_path(target_folder)}')


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.source_path = None
        self.destination_folder = PICO_BOOKS_DIR

        self.setObjectName("root")
        self.setWindowTitle("Tempo Companion")
        self.resize(520, 690)
        self.setMinimumSize(460, 600)

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

        root_layout.addWidget(self._section_label("AUTHOR"))

        self.author_input = QLineEdit()
        self.author_input.setPlaceholderText("Author (kept separate from title for future sorting)")
        root_layout.addWidget(self.author_input)

        self.skip_front_matter_checkbox = QCheckBox("Skip to Chapter 1 (leave out title page, TOC, foreword, etc.)")
        self.skip_front_matter_checkbox.setChecked(True)
        root_layout.addWidget(self.skip_front_matter_checkbox)

        self.name_pacing_checkbox = QCheckBox("Pause longer the first time a name appears")
        self.name_pacing_checkbox.setChecked(True)
        root_layout.addWidget(self.name_pacing_checkbox)

        self.destination_label = QLabel("")
        self.destination_label.setObjectName("destinationLabel")
        root_layout.addWidget(self.destination_label)

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
        self.new_folder_button = QPushButton("+ New Folder")
        self.new_folder_button.setObjectName("secondaryButton")
        self.new_folder_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_folder_button.clicked.connect(self.create_folder)
        library_header.addWidget(self.new_folder_button)
        root_layout.addLayout(library_header)

        self.book_tree = BookTree()
        self.book_tree.setObjectName("bookTree")
        self.book_tree.setHeaderHidden(True)
        self.book_tree.itemClicked.connect(self.on_tree_item_clicked)
        self.book_tree.library_changed.connect(self.on_library_changed)
        root_layout.addWidget(self.book_tree, stretch=1)

        library_hint = QLabel(
            "Click a folder (or a book inside one) to choose where new conversions are saved. "
            "Drag books or folders onto each other to reorganize."
        )
        library_hint.setObjectName("destinationLabel")
        library_hint.setWordWrap(True)
        root_layout.addWidget(library_hint)

        self.refresh_library_tree()
        self._update_destination_label()

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
        self.author_input.setText(suggest_author(self.source_path))
        self.convert_button.setEnabled(True)
        self._set_status("", "idle")

    def run_convert(self):
        if not self.source_path:
            return
        title = self.title_input.text().strip() or self.source_path.stem
        author = self.author_input.text().strip()
        destination = self.destination_folder / f"{slugify(title)}.txt"

        if destination.exists():
            answer = QMessageBox.question(
                self,
                "Overwrite?",
                f'"{destination.name}" already exists there. Overwrite it?',
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        try:
            self.destination_folder.mkdir(parents=True, exist_ok=True)
            text = convert(
                self.source_path,
                destination,
                skip_front_matter=self.skip_front_matter_checkbox.isChecked(),
                mark_name_introductions=self.name_pacing_checkbox.isChecked(),
                title=title,
                author=author,
            )
        except Exception as error:
            self._set_status(f"Failed: {error}", "error")
            return

        word_count = len(strip_meta_header(text).split())
        byline = f" by {author}" if author else ""
        self._set_status(
            f'Added "{title}"{byline} ({word_count:,} words) as {destination.name}',
            "success",
        )
        self.refresh_library_tree()

    def create_folder(self):
        parent = self._selected_folder() or PICO_BOOKS_DIR
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        name = name.strip()
        if not ok or not name:
            return
        new_folder = parent / name
        if new_folder.exists():
            QMessageBox.warning(self, "Already exists", f'"{name}" already exists there.')
            return
        try:
            new_folder.mkdir(parents=True)
        except OSError as error:
            QMessageBox.warning(self, "Couldn't create folder", str(error))
            return
        self.refresh_library_tree()
        self._set_status(f'Created folder "{name}"', "success")

    def on_tree_item_clicked(self, item, _column):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path is None:
            return
        self.destination_folder = path if path.is_dir() else path.parent
        self._update_destination_label()

    def on_library_changed(self, message):
        # A drag-drop move may have relocated the folder we were about to
        # save into — reset to root rather than risk pointing at a path
        # that no longer exists.
        self.destination_folder = PICO_BOOKS_DIR
        self._update_destination_label()
        self._set_status(message, "success")
        self.refresh_library_tree()

    def _selected_folder(self):
        item = self.book_tree.currentItem()
        if item is None:
            return None
        path = item.data(0, Qt.ItemDataRole.UserRole)
        return path if path and path.is_dir() else None

    def _update_destination_label(self):
        self.destination_label.setText(f"Save to: {format_library_path(self.destination_folder)}")
        self.destination_label.setProperty("hasCustomPath", self.destination_folder != PICO_BOOKS_DIR)
        self.destination_label.style().unpolish(self.destination_label)
        self.destination_label.style().polish(self.destination_label)

    def refresh_library_tree(self):
        self.book_tree.clear()
        PICO_BOOKS_DIR.mkdir(parents=True, exist_ok=True)
        root_item = QTreeWidgetItem(["📚 Books"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, PICO_BOOKS_DIR)
        self.book_tree.addTopLevelItem(root_item)
        self._populate_tree(PICO_BOOKS_DIR, root_item)
        self.book_tree.expandAll()

    def _populate_tree(self, folder, parent_item):
        entries = sorted(folder.iterdir(), key=lambda entry: (entry.is_file(), entry.name.lower()))
        for entry in entries:
            if entry.is_dir():
                item = QTreeWidgetItem([f"📁 {entry.name}"])
                item.setData(0, Qt.ItemDataRole.UserRole, entry)
                parent_item.addChild(item)
                self._populate_tree(entry, item)
            elif entry.suffix == ".txt":
                title, author = peek_meta(entry)
                text = strip_meta_header(entry.read_text(encoding="utf-8"))
                word_count = len(text.split())
                byline = f"  ·  {author}" if author else ""
                item = QTreeWidgetItem([f"{title}{byline}  ·  {word_count:,} words"])
                item.setData(0, Qt.ItemDataRole.UserRole, entry)
                parent_item.addChild(item)

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
