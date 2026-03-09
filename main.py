import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
import database

# Import UI components (will be created in next steps)
from ui.dashboard import DashboardWidget
from ui.task_form import TaskFormWidget
from ui.reports import ReportsWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Personal Timesheet Tracker")
        self.setMinimumSize(900, 600)
        self.setup_ui()
        self.apply_theme()

    def setup_ui(self):
        # Main Tab Widget
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True) # Cleaner look
        self.setCentralWidget(self.tabs)

        # Tabs
        self.dashboard_tab = DashboardWidget(self)
        self.task_tab = TaskFormWidget(self)
        self.reports_tab = ReportsWidget(self)

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.task_tab, "Add Task")
        self.tabs.addTab(self.reports_tab, "Weekly Stats & Reports")
        
        # Connect signals for refreshing when tab changes
        self.tabs.currentChanged.connect(self.on_tab_changed)

    def on_tab_changed(self, index):
        if index == 0:
            self.dashboard_tab.refresh_data()
        elif index == 2:
            self.reports_tab.refresh_data()

    def apply_theme(self):
        # Simple Notion/Linear inspired dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1A1A1A;
            }
            QTabWidget::pane {
                border: 0px;
                background: #1A1A1A;
            }
            QTabBar::tab {
                background: #252525;
                color: #A0A0A0;
                padding: 10px 20px;
                border: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                font-size: 14px;
                font-family: 'Segoe UI', Inter, sans-serif;
            }
            QTabBar::tab:selected {
                background: #1A1A1A;
                color: #FFFFFF;
                border-bottom: 2px solid #5C5CFF;
            }
            QTabBar::tab:hover {
                background: #2A2A2A;
            }
            QWidget {
                color: #E0E0E0;
                font-family: 'Segoe UI', Inter, sans-serif;
            }
        """)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Cleaner cross-platform basis
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
