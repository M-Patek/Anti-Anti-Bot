"""
主程序入口 (main.py)

职责:
- 程序的唯一入口 (if __name__ == '__main__':)。
- 负责初始化 Playwright 浏览器上下文 (Context)。
- 负责加载两个 Agent 页面 (A 和 B)。
- 负责执行 "手动设置" 倒计时。
- 负责调用 "业务编排器" (orchestrator) 来启动主逻辑。
- 负责捕获顶层异常 (Fatal Errors) 并安全退出。
"""

import os
import time
import sys
from playwright.sync_api import sync_playwright

# 导入本地模块
from config import Config
from core_actions import log, Session, wait_for_page_stability
from orchestrator import run_orchestrator

def main():
    """主函数"""
    try:
        # 1. 检查环境配置
        if not os.path.exists(Config.EDGE_USER_DATA_PATH):
            raise FileNotFoundError(f"Edge 用户数据目录未找到: {Config.EDGE_USER_DATA_PATH}")
        
        # 2. 初始化会话
        session = Session(seed=int(time.time()))

        # 3. 启动 Playwright
        with sync_playwright() as p:
            log("INFO", "正在启动 Edge 浏览器并加载个人配置...", "启动设置")
            context = p.chromium.launch_persistent_context(
                user_data_dir=Config.EDGE_USER_DATA_PATH,
                headless=False,
                channel="msedge",
                slow_mo=50,
                args=['--start-maximized', '--disable-blink-features=AutomationControlled']
            )
            
            # 4. 加载页面
            page_A = context.pages[0] if context.pages else context.new_page()
            page_A.goto(Config.GEMINI_URL_A, wait_until="domcontentloaded", timeout=Config.Timeouts.PAGE_LOAD_MS)
            
            page_B = context.new_page()
            page_B.goto(Config.GEMINI_URL_B, wait_until="domcontentloaded", timeout=Config.Timeouts.PAGE_LOAD_MS)
            
            log("SUCCESS", "双Agent页面已加载。", "启动设置")

            # 5. 等待页面稳定
            wait_for_page_stability(page_A, "Agent A")
            wait_for_page_stability(page_B, "Agent B")
            
            page_A.bring_to_front()

            # 6. 手动设置阶段
            log("WARNING", f"您有 {Config.Timeouts.MANUAL_SETUP_SEC} 秒进行手动设置。", "手动设置")
            log("WARNING", "请在 Agent A (第一个标签页) 中输入您的初始任务。", "手动设置")
            for i in range(Config.Timeouts.MANUAL_SETUP_SEC, 0, -10):
                log("INFO", f"剩余时间: {i} 秒...", "手动设置")
                if i <= 10:
                    time.sleep(min(i, 10))
                    break
                time.sleep(10)
            
            # 7. 移交控制权给编排器
            run_orchestrator(page_A=page_A, page_B=page_B, initial_session=session)

    except FileNotFoundError as e:
        log("FATAL", str(e), "启动错误")
    except Exception as e:
        log("FATAL", f"脚本因未捕获的顶层错误而终止: {e}", "运行时错误")
        # 可以在这里添加更详细的堆栈跟踪
        import traceback
        traceback.print_exc()
    finally:
        log("INFO", "脚本执行结束。", "关闭")
        input("按回车键关闭浏览器...")

if __name__ == '__main__':
    main()
