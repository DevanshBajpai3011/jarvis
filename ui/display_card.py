import sys
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QPushButton,
    QFrame,
    QGraphicsDropShadowEffect,
    QSizePolicy,
)


class DisplayCardModal(QDialog):
    """
    Modern translucent dark glass modal dialog for rendering rich formatted Markdown/HTML content
    (recipes, code snippets, lists, tabular data) sent by J.A.R.V.I.S.
    """

    def __init__(self, title: str = "J.A.R.V.I.S. Visual Display", markdown_content: str = "", parent=None):
        super().__init__(parent)
        self.title_text = title
        self.markdown_content = markdown_content
        self._drag_pos = QPoint()

        self._init_ui(parent)

    def _init_ui(self, parent):
        self.setWindowTitle(self.title_text)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(680, 520)
        self.setMaximumSize(800, 600)
        self.setMinimumSize(460, 340)

        # Center over parent overlay window if available
        if parent:
            try:
                p_geo = parent.geometry()
                self.move(
                    p_geo.x() + max(0, (p_geo.width() - self.width()) // 2),
                    p_geo.y() + max(0, (p_geo.height() - self.height()) // 2),
                )
            except Exception:
                pass

        # Outer dark translucent container frame with cyan border accent
        self.container = QFrame(self)
        self.container.setObjectName("DisplayContainer")

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(35)
        shadow.setColor(QColor(0, 255, 255, 90))
        shadow.setOffset(0, 6)
        self.container.setGraphicsEffect(shadow)

        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(10, 10, 10, 10)
        dialog_layout.addWidget(self.container)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(18, 16, 18, 16)
        container_layout.setSpacing(12)

        # ----------------------------------------------------
        # 1. HEADER LAYOUT
        # ----------------------------------------------------
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        self.icon_label = QLabel("🖥️")
        self.icon_label.setStyleSheet("font-size: 20px;")
        header_layout.addWidget(self.icon_label)

        self.header_title = QLabel(self.title_text.upper())
        self.header_title.setObjectName("DisplayHeaderTitle")
        header_layout.addWidget(self.header_title, stretch=1)

        self.btn_dismiss = QPushButton("Dismiss")
        self.btn_dismiss.setObjectName("DisplayDismissBtn")
        self.btn_dismiss.setFixedSize(80, 30)
        self.btn_dismiss.clicked.connect(self.accept)
        header_layout.addWidget(self.btn_dismiss)

        container_layout.addLayout(header_layout)

        # ----------------------------------------------------
        # 2. SCROLLABLE MARKDOWN/HTML CONTENT AREA
        # ----------------------------------------------------
        self.content_browser = QTextBrowser()
        self.content_browser.setObjectName("DisplayContentBrowser")
        self.content_browser.setOpenExternalLinks(True)
        self.content_browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        if self.markdown_content:
            self.content_browser.setMarkdown(self.markdown_content)
        else:
            self.content_browser.setMarkdown("*No content provided.*")

        container_layout.addWidget(self.content_browser, stretch=1)

        # Apply QSS
        self.setStyleSheet(self._get_stylesheet())

    def _get_stylesheet(self) -> str:
        return """
            QFrame#DisplayContainer {
                background-color: rgba(15, 23, 42, 0.95);
                border: 1px solid #00FFFF;
                border-radius: 16px;
            }
            QLabel#DisplayHeaderTitle {
                color: #00FFFF;
                font-family: 'Segoe UI', sans-serif;
                font-size: 15px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QPushButton#DisplayDismissBtn {
                background-color: rgba(0, 255, 255, 0.12);
                color: #00FFFF;
                border: 1px solid #00FFFF;
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#DisplayDismissBtn:hover {
                background-color: #EF4444;
                color: #FFFFFF;
                border: 1px solid #EF4444;
            }
            QTextBrowser#DisplayContentBrowser {
                background-color: rgba(30, 41, 59, 0.65);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                padding: 14px;
                color: #F8FAFC;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
                line-height: 1.5;
            }
        """

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton and not self._drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = QPoint()
        event.accept()


def show_display_card(title: str, markdown_content: str, parent=None):
    """
    Helper function to instantiate and pop up the DisplayCardModal dialog.
    """
    modal = DisplayCardModal(title=title, markdown_content=markdown_content, parent=parent)
    modal.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    demo_md = """# Classic Roasted Tomato Soup
## Ingredients:
- 1 kg Ripe Tomatoes
- 4 cloves Garlic
- 1 tbsp Olive Oil
- 1/2 cup Fresh Basil
- 1 cup Vegetable Broth

## Instructions:
1. Roast tomatoes and garlic at 200°C for 25 mins.
2. Blend roasted ingredients with fresh basil and warm broth.
3. Season with salt and pepper to taste.
"""
    modal = DisplayCardModal(title="Tomato Soup Recipe", markdown_content=demo_md)
    modal.show()
    sys.exit(app.exec())
