"""
后端工作线程 (backend_worker.py) (v9.3)

职责:
- 继承自 QObject，以便移至 QThread。
- 包含所有耗时的 Playwright 启动和浏览器自动化逻辑 (原 main.py 的内容)。
- 在一个单独的线程中运行，以防阻塞 GUI。
- 定义 `run` 方法作为线程入口点。
- 定义 `stop` 方法以允许主线程请求停止。
- 通过发出 `finished` 和 `fatal_error` 信号来报告其最终状态。
"""

import os
import time
import sys
import traceback
from PySide6.QtCore import QObject, Signal
from playwright.sync_api import sync_playwright

# 导入本地模块
import config
from core_actions import Session, wait_for_page_stability, log
from orchestrator import run_orchestrator
from app_context import context # 导入全局信号中心

class BackendWorker(QObject):
    """
    封装所有后端逻辑的工作器。
    """
    finished = Signal()      # 任务完成信号 (无论成功与否)
    fatal_error = Signal(str) # 发生致命错误信号

    def __init__(self, start_mode: str):
        super().__init__()
        self.start_mode = start_mode
        self._stop_requested = False

    def run(self):
        """
        线程的主执行函数 (原 main.py 的逻辑)。
        """
        try:
            # 1. 检查环境配置
            if not os.path.exists(config.Config.EDGE_USER_DATA_PATH):
                raise FileNotFoundError(f"Edge 用户数据目录未找到: {config.Config.EDGE_USER_DATA_PATH}")
            
            # 2. 初始化会话
            # Session 的 __init__ 现已修改，会自动发出信号
            session = Session(seed=int(time.time()))

            # 3. 启动 Playwright
            with sync_playwright() as p:
                context.emit_log("正在启动 Edge 浏览器并加载个人配置...", "启动设置")
                
                # 检查停止请求
                if self._stop_requested:
                    raise Exception("启动被用户取消")

                browser_context = p.chromium.launch_persistent_context(
                    user_data_dir=config.Config.EDGE_USER_DATA_PATH,
                    headless=False,
                    channel="msedge",
                    slow_mo=50,
                    args=['--start-maximized', '--disable-blink-features=AutomationControlled']
                )
                
                # 4. 加载页面
                page_A = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
                page_A.goto(config.Config.GEMINI_URL_A, wait_until="domcontentloaded", timeout=config.Config.Timeouts.PAGE_LOAD_MS)
                
                page_B = browser_context.new_page()
                page_B.goto(config.Config.GEMINI_URL_B, wait_until="domcontentloaded", timeout=config.Config.Timeouts.PAGE_LOAD_MS)
                
                context.emit_log("双Agent页面已加载。", "启动设置")

                # 5. 等待页面稳定
                wait_for_page_stability(page_A, "Agent A")
                wait_for_page_stability(page_B, "Agent B")
                
                page_A.bring_to_front()

                # 6. 手动设置阶段 (现在由 GUI 控制启动，但我们保留倒计时日志)
                context.emit_log(f"您有 {config.Config.Timeouts.MANUAL_SETUP_SEC} 秒进行手动设置。", "手动设置")
                context.emit_log("请在 Agent A (第一个标签页) 中输入您的初始任务。", "手动设置")
                
                for i in range(config.Config.Timeouts.MANUAL_SETUP_SEC, 0, -5):
                    if self._stop_requested:
                        raise Exception("启动倒计时被用户取消")
                    
                    context.emit_log(f"剩余时间: {i} 秒...", "手动设置")
                    if i <= 5:
                        time.sleep(min(i, 5))
                        break
                    time.sleep(5)
                
                # 7. 移交控制权给编排器
                # 我们将 self (worker 实例) 传递下去，以便编排器可以检查 _stop_requested
                run_orchestrator(
                    page_A=page_A, 
                    page_B=page_B, 
                    initial_session=session, 
                    start_mode=self.start_mode,
                    worker=self
                )

        except FileNotFoundError as e:
            context.emit_log(str(e), "FATAL")
            self.fatal_error.emit(str(e))
        except Exception as e:
            if "Target page, context or browser has been closed" in str(e):
                 context.emit_log("浏览器实例似乎已被用户手动关闭。", "WARNING")
            else:
                context.emit_log(f"脚本因未捕获的顶层错误而终止: {e}", "FATAL")
                # 捕获详细的堆栈跟踪
                tb = traceback.format_exc()
                context.emit_log(tb, "FATAL")
                self.fatal_error.emit(f"{e}\n\n{tb}")
        finally:
            context.emit_log("后端工作器执行结束。", "关闭")
            self.finished.emit() # 确保在最后发出 finished 信号

    def stop(self):
        """
        从主线程调用的方法，用于请求停止。
        """
        self._stop_requested = True
        context.emit_log("收到停止请求，将在下一检查点停止。", "INFO")

    def is_stop_requested(self) -> bool:
        """
        编排器调用的方法，用于检查是否应停止。
        """
        return self._stop_requested

