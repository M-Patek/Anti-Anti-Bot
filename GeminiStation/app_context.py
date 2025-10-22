"""
应用上下文与信号中心 (app_context.py) (v9.3)

职责:
- 定义全局共享的 PySide6 信号。
- 充当后端 (core_actions, orchestrator) 和 前端 (gui_main) 之间的解耦通信桥梁。
- 允许非 Qt 对象 (如 Session, log) 发出 Qt 信号。
"""

from PySide6.QtCore import QObject, Signal

class LogEmitter(QObject):
    """负责日志信号"""
    # 信号: (消息, 日志级别/步骤)
    log = Signal(str, str)

class StatusEmitter(QObject):
    """负责状态栏信号"""
    status_changed = Signal(str)
    session_id_updated = Signal(str)
    error_count_updated = Signal(int)

class AppContext(QObject):
    """
    统一的全局上下文，持有所有信号发射器实例。
    """
    def __init__(self):
        super().__init__()
        self.log_emitter = LogEmitter()
        self.status_emitter = StatusEmitter()
        
    def emit_log(self, message: str, level: str = "INFO"):
        """便捷方法，用于从任何地方发射日志信号"""
        self.log_emitter.log.emit(message, level)
        
    def emit_status(self, message: str):
        """便捷方法，用于发射状态变更信号"""
        self.status_emitter.status_changed.emit(message)
        
    def emit_session(self, session_id: str):
        """便捷方法，用于发射会话ID变更信号"""
        self.status_emitter.session_id_updated.emit(session_id)
        
    def emit_error_count(self, count: int):
        """便捷方法，用于发射错误计数变更信号"""
        self.status_emitter.error_count_updated.emit(count)


# --- 全局单例 ---
# 创建一个全局唯一的上下文实例，供整个应用程序导入和使用。
context = AppContext()

