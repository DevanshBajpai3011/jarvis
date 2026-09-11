import sys
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QComboBox,
    QTextEdit,
    QMessageBox,
    QFrame,
    QGraphicsDropShadowEffect,
)

from memory import get_all_memories, add_memory, edit_memory, delete_memory


class AddEditMemoryDialog(QDialog):
    """
    Dialog popup for creating or editing a memory record in ChromaDB vector storage.
    """

    def __init__(self, title: str = "Add Memory", memory_data: dict = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(420, 320)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)

        self.memory_id = memory_data.get("id") if memory_data else None
        initial_category = memory_data.get("category", "general") if memory_data else "general"
        initial_text = memory_data.get("text", "") if memory_data else ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Title Label
        title_label = QLabel(title.upper())
        title_label.setStyleSheet("color: #00FFFF; font-size: 14px; font-weight: bold; letter-spacing: 1px;")
        layout.addWidget(title_label)

        # Category
        cat_label = QLabel("Category:")
        cat_label.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(cat_label)

        self.cat_combo = QComboBox()
        self.cat_combo.setEditable(True)
        self.cat_combo.addItems(["general", "preference", "fact", "background", "work", "hobby"])
        self.cat_combo.setCurrentText(initial_category)
        self.cat_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(30, 41, 59, 0.8);
                color: #F8FAFC;
                border: 1px solid rgba(0, 255, 255, 0.3);
                border-radius: 6px;
                padding: 6px;
            }
        """)
        layout.addWidget(self.cat_combo)

        # Content Text Area
        content_label = QLabel("Memory Content:")
        content_label.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(content_label)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(initial_text)
        self.text_edit.setPlaceholderText("Enter fact or user preference to remember...")
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: rgba(30, 41, 59, 0.8);
                color: #F8FAFC;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.text_edit)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.15); }
        """)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Save Memory")
        btn_save.clicked.connect(self.accept)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 255, 255, 0.15);
                color: #00FFFF;
                border: 1px solid #00FFFF;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #00FFFF; color: #0F172A; }
        """)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)
        self.setStyleSheet("background-color: #0F172A;")

    def get_data(self) -> tuple[str, str]:
        """Returns (category, text)."""
        return self.cat_combo.currentText().strip(), self.text_edit.toPlainText().strip()


class MemoryManagerWidget(QWidget):
    """
    Interactive Memory Manager UI tab widget providing real-time search filtering
    and CRUD actions (Create, Read, Update, Delete) against persistent ChromaDB memory.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_memories = []
        self._init_ui()
        self.refresh_memories()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # ----------------------------------------------------
        # 1. TOP CONTROL BAR
        # ----------------------------------------------------
        control_layout = QHBoxLayout()
        control_layout.setSpacing(10)

        # Search Bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search memories by keyword or category...")
        self.search_input.textChanged.connect(self._filter_table)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(30, 41, 59, 0.8);
                color: #F8FAFC;
                border: 1px solid rgba(0, 255, 255, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus { border: 1px solid #00FFFF; }
        """)
        control_layout.addWidget(self.search_input, stretch=1)

        # Add Memory Button
        self.btn_add = QPushButton("➕ Add Memory")
        self.btn_add.clicked.connect(self.on_add_memory)
        self.btn_add.setStyleSheet("""
            QPushButton {
                background-color: rgba(16, 185, 129, 0.15);
                color: #10B981;
                border: 1px solid #10B981;
                border-radius: 8px;
                padding: 8px 14px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #10B981; color: #0F172A; }
        """)
        control_layout.addWidget(self.btn_add)

        # Refresh Button
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.clicked.connect(self.refresh_memories)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 240, 255, 0.12);
                color: #00F0FF;
                border: 1px solid #00F0FF;
                border-radius: 8px;
                padding: 8px 14px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #00F0FF; color: #0F172A; }
        """)
        control_layout.addWidget(self.btn_refresh)

        layout.addLayout(control_layout)

        # ----------------------------------------------------
        # 2. CENTRAL VIEW TABLE
        # ----------------------------------------------------
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Category", "Memory Content", "Timestamp", "Actions"])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)

        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.table.setStyleSheet("""
            QTableWidget {
                background-color: rgba(15, 23, 42, 0.85);
                color: #F8FAFC;
                gridline-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(0, 255, 255, 0.2);
                border-radius: 12px;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: rgba(30, 41, 59, 0.95);
                color: #00FFFF;
                padding: 8px;
                border: none;
                font-weight: bold;
                font-size: 12px;
                text-transform: uppercase;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QTableWidget::item:selected {
                background-color: rgba(0, 255, 255, 0.15);
                color: #00FFFF;
            }
        """)

        layout.addWidget(self.table)

    def refresh_memories(self):
        """Fetches all records from persistent ChromaDB memory and populates table."""
        self.all_memories = get_all_memories()
        self._populate_table(self.all_memories)

    def _populate_table(self, memories: list[dict]):
        self.table.setRowCount(0)

        for row_idx, mem in enumerate(memories):
            self.table.insertRow(row_idx)

            mem_id = mem.get("id", "")
            short_id = mem_id[:8] + "..." if len(mem_id) > 8 else mem_id

            item_id = QTableWidgetItem(short_id)
            item_id.setData(Qt.UserRole, mem_id)
            item_id.setForeground(QColor("#94A3B8"))

            item_cat = QTableWidgetItem(mem.get("category", "general"))
            item_cat.setForeground(QColor("#38BDF8"))

            item_text = QTableWidgetItem(mem.get("text", ""))
            item_text.setForeground(QColor("#F8FAFC"))

            item_time = QTableWidgetItem(mem.get("timestamp", "N/A"))
            item_time.setForeground(QColor("#64748B"))

            self.table.setItem(row_idx, 0, item_id)
            self.table.setItem(row_idx, 1, item_cat)
            self.table.setItem(row_idx, 2, item_text)
            self.table.setItem(row_idx, 3, item_time)

            # Actions Cell Widget (Edit & Delete)
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(6)

            btn_edit = QPushButton("✏️ Edit")
            btn_edit.setStyleSheet("""
                QPushButton {
                    background-color: rgba(59, 130, 246, 0.15);
                    color: #60A5FA;
                    border: 1px solid #3B82F6;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #3B82F6; color: #FFFFFF; }
            """)
            btn_edit.clicked.connect(lambda _, m=mem: self.on_edit_memory(m))
            actions_layout.addWidget(btn_edit)

            btn_delete = QPushButton("🗑️ Delete")
            btn_delete.setStyleSheet("""
                QPushButton {
                    background-color: rgba(239, 68, 68, 0.15);
                    color: #F87171;
                    border: 1px solid #EF4444;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #EF4444; color: #FFFFFF; }
            """)
            btn_delete.clicked.connect(lambda _, mid=mem_id: self.on_delete_memory(mid))
            actions_layout.addWidget(btn_delete)

            self.table.setCellWidget(row_idx, 4, actions_widget)

    def _filter_table(self, filter_text: str):
        if not filter_text or not filter_text.strip():
            self._populate_table(self.all_memories)
            return

        query = filter_text.strip().lower()
        filtered = [
            m for m in self.all_memories
            if query in m.get("text", "").lower()
            or query in m.get("category", "").lower()
            or query in m.get("id", "").lower()
        ]
        self._populate_table(filtered)

    def on_add_memory(self):
        dialog = AddEditMemoryDialog(title="Add New Memory", parent=self)
        if dialog.exec() == QDialog.Accepted:
            category, text = dialog.get_data()
            if text:
                add_memory(fact=text, category=category)
                self.refresh_memories()

    def on_edit_memory(self, memory_data: dict):
        dialog = AddEditMemoryDialog(title="Edit Memory", memory_data=memory_data, parent=self)
        if dialog.exec() == QDialog.Accepted:
            category, text = dialog.get_data()
            mem_id = memory_data.get("id")
            if mem_id and text:
                edit_memory(memory_id=mem_id, new_text=text, category=category)
                self.refresh_memories()

    def on_delete_memory(self, memory_id: str):
        reply = QMessageBox.question(
            self,
            "Delete Memory",
            "Are you sure you want to delete this memory from persistent storage?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            delete_memory(memory_id=memory_id)
            self.refresh_memories()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = MemoryManagerWidget()
    widget.setWindowTitle("J.A.R.V.I.S. Memory Vault")
    widget.resize(750, 480)
    widget.show()
    sys.exit(app.exec())
