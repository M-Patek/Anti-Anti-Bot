"""
GUI 主程序入口 (gui_main.py) (v9.3 - 最终集成版)

职责:
- 启动 PySide6 应用程序 (QApplication)。
- 创建和显示主窗口 (MainWindow)。
- 作为唯一的程序入口点，管理后端工作线程 (BackendWorker)。
- 通过信号与槽 (Signal & Slot) 连接前端与后端。
- 显示来自 app_context 的实时日志和状态更新。
"""

import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QRadioButton, QGroupBox, QSplitter,
    QLabel, QStatusBar, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor, QTextCursor

# 导入我们的信号中心和后端工作器
from app_context import context  # 全局信号实例
from backend_worker import BackendWorker

class MainWindow(QMainWindow):
    """
    主窗口类，作为所有UI元素的容器。
    """
    def __init__(self):
        super().__init__()
        
        # 后端线程和工作器实例
        self.thread = None
        self.worker = None

        self.init_ui()
        self.init_signals()
        
        self.log_count = 0
        self.max_log_lines = 2000 # 限制日志行数防止内存溢出

    def init_ui(self):
        """
        初始化主窗口 UI (三区域布局)。
        """
        # --- 窗口基础设置 ---
        self.setWindowTitle("Gemini Station 控制面板 v9.3")
        self.resize(1200, 800)

        # --- Zone 1: 控制面板 (左侧) ---
        control_group_box = QGroupBox("控制与配置")
        control_layout = QVBoxLayout()

        # 启动模式
        mode_box = QGroupBox("启动模式")
        mode_layout = QVBoxLayout()
        self.radio_new = QRadioButton("新任务 (New Start)")
        self.radio_resume_a = QRadioButton("从 Agent A 恢复 (Resume from A)")
        self.radio_resume_b = QRadioButton("从 Agent B 恢复 (Resume from B)")
        self.radio_new.setChecked(True) # 默认选中
        mode_layout.addWidget(self.radio_new)
        mode_layout.addWidget(self.radio_resume_a)
        mode_layout.addWidget(self.radio_resume_b)
        mode_box.setLayout(mode_layout)

        # 启动/停止按钮
        self.btn_start = QPushButton("启动 (Start)")
        self.btn_start.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_stop = QPushButton("停止 (Stop)")
        self.btn_stop.setStyleSheet("background-color: #F44336; color: white; font-weight: bold;")
        self.btn_stop.setEnabled(False) # 默认禁用

        # 清除日志按钮
        self.btn_clear_logs = QPushButton("清除日志")
        
        # 将控件添加到 Zone 1 布局
        control_layout.addWidget(mode_box)
        control_layout.addWidget(self.btn_start)
        control_layout.addWidget(self.btn_stop)
        control_layout.addWidget(self.btn_clear_logs)
        control_layout.addStretch(1) # 弹簧，将控件推到顶部
        
        self.control_widget = QWidget()
        self.control_widget.setLayout(control_layout)

        # --- Zone 2: 实时日志 (右侧) ---
        log_group_box = QGroupBox("实时日志")
        log_layout = QVBoxLayout()
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Courier New", 10))
        self.log_display.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")
        log_layout.addWidget(self.log_display)
        log_group_box.setLayout(log_layout)

        # --- QSplitter (连接 Zone 1 和 Zone 2) ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.control_widget)
        splitter.addWidget(log_group_box)
        splitter.setSizes([300, 900]) # 初始比例

        # 设置中心部件
        self.setCentralWidget(splitter)

        # --- Zone 3: 状态栏 (底部) ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # 状态标签
        self.status_label = QLabel("状态: 准备就绪")
        self.status_bar.addPermanentWidget(self.status_label, 2)

        # 会话ID标签
        self.session_label = QLabel("Session: N/A")
        self.status_bar.addPermanentWidget(self.session_label, 1)

        # 错误计数标签
        self.error_label = QLabel("Errors: 0")
        self.status_bar.addPermanentWidget(self.error_label, 0)

    def init_signals(self):
        """
        连接所有信号与槽。
        """
        # 按钮点击
        self.btn_start.clicked.connect(self.start_work)
        self.btn_stop.clicked.connect(self.stop_work)
        self.btn_clear_logs.clicked.connect(lambda: (self.log_display.clear(), setattr(self, 'log_count', 0)))

        # 核心上下文信号
        context.log_emitter.log.connect(self._append_log)
        context.status_emitter.status_changed.connect(self._update_status)
        context.status_emitter.session_id_updated.connect(self._update_session)
        context.status_emitter.error_count_updated.connect(self._update_errors)

    # --- 槽函数 (Slots) ---

    @Slot(str, str)
    def _append_log(self, message: str, level: str):
        """
        向日志显示区域追加格式化的日志。
        """
        # 颜色映射
        color_map = {
            "INFO": "#D4D4D4",     # 默认 (白色)
            "SUCCESS": "#6A9955",  # 绿色
            "WARNING": "#F0E68C",  # 卡其色
            "ERROR": "#F44336",    # 红色
            "FATAL": "#FF00FF",    # 品红 (用于严重错误)
            "CRITICAL": "#FF6347", # 番茄色
            "L1人格": "#9CDCFE",   # 浅蓝
            "L2恢复": "#CE9178",   # 橙色
            "L4恢复": "#C586C0",   # 紫色
            "思考延迟": "#4D4D4D",  # 深灰
            "默认": "#808080"      # 灰色 (用于未分类的 step)
        }
        
        # 根据 level (在日志函数中是 step) 选择颜色
        # 我们在 core_actions.py 中将 step 作为 level 传递
        color = color_map.get(level, color_map["默认"]) 

        # 限制日志行数
        self.log_count += 1
        if self.log_count > self.max_log_lines:
            self.log_display.document().clear() # 清空
            self.log_count = 1
            self.log_display.append('<span style="color: #F44336; font-weight: bold;">--- 日志行数达到上限，已自动清空 ---</span>')

        # 添加带颜色的 HTML
        self.log_display.append(f'<span style="color: {color};">{message}</span>')
        
        # 自动滚动到底部
        self.log_display.moveCursor(QTextCursor.MoveOperation.End)

    @Slot(str)
    def _update_status(self, message: str):
        self.status_label.setText(f"状态: {message}")

    @Slot(str)
    def _update_session(self, session_id: str):
        self.session_label.setText(f"Session: {session_id}")

    @Slot(int)
    def _update_errors(self, count: int):
        self.error_label.setText(f"Errors: {count}")
        if count > 0:
            self.error_label.setStyleSheet("color: red; font-weight: bold;")
        else:
            self.error_label.setStyleSheet("") # 恢复默认

    @Slot()
    def start_work(self):
        """
        启动后端工作线程。
        """
        # 1. 获取启动模式
        start_mode = "new"
        if self.radio_resume_a.isChecked():
            start_mode = "resume_from_a"
        elif self.radio_resume_b.isChecked():
            start_mode = "resume_from_b"
        
        # 2. 禁用UI
        self.control_widget.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._update_status("正在启动...")
        self._update_errors(0) # 重置错误计数

        # 3. 创建工作器和线程
        self.worker = BackendWorker(start_mode)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        # 4. 连接工作器特定的信号
        self.worker.finished.connect(self._on_work_finished)
        self.worker.fatal_error.connect(self._on_fatal_error)
        
        # 5. 连接线程的 started 信号到 worker 的 run 方法
        self.thread.started.connect(self.worker.run)
        
        # 6. 启动线程
        self.thread.start()
        self._append_log(f"--- 启动工作线程 (模式: {start_mode}) ---", "INFO")

    @Slot()
    def stop_work(self):
        """
        请求停止后端工作线程。
        """
        if self.worker:
            self._update_status("正在请求停止...")
            self.btn_stop.setEnabled(False) # 防止重复点击
            self.worker.stop()
            self._append_log("--- 发送停止请求... ---", "WARNING")

    @Slot()
    def _on_work_finished(self):
        """
        工作线程正常结束时调用的槽。
        """
        self._append_log("--- 工作线程已停止 ---", "INFO")
        self._update_status("准备就绪")
        
        # 启用UI
        self.control_widget.setEnabled(True)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

        # 清理
        if self.thread:
            self.thread.quit()
            self.thread.wait()
        self.thread = None
        self.worker = None

    @Slot(str)
    def _on_fatal_error(self, error_message: str):
        """
        工作线程发生致命错误时调用的槽。
        """
        self._append_log(f"致命错误: {error_message}", "FATAL")
        QMessageBox.critical(self, "致命错误", f"后端线程因严重错误而终止:\n\n{error_message}")
        self._on_work_finished() # 同样执行清理

    def closeEvent(self, event):
        """
        重写窗口关闭事件，确保线程被清理。
        """
        self._append_log("--- 应用程序正在关闭... ---", "INFO")
        if self.thread and self.thread.isRunning():
            self.stop_work() # 请求停止
            self.thread.quit() # 退出线程循环
            if not self.thread.wait(5000): # 等待最多5秒
                 self._append_log("线程未能及时停止，强制终止。", "FATAL")
                 self.thread.terminate() # 强制终止 (最后的手段)
        event.accept()


# 应用程序的主入口点
if __name__ == "__main__":
    # 创建应用程序实例
    app = QApplication(sys.argv)
    
    # 创建主窗口实例
    main_window = MainWindow()
    
    # 显示主窗口
    main_window.show()
    
    # 启动事件循环
    sys.exit(app.exec())

