import time
import sys
import os
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError, expect, Error as PlaywrightError

# =======================================================================================
# === I. 阶段零：前置依赖与全局常量规范 (Phase Zero: Dependencies & Constants) ===
# =======================================================================================

# ----------------- 协作常量 (Collaboration Constants) -----------------
TERMINATION_PHRASE = "TASK_COMPLETED_SUCCESSFULLY"
START_CMD_MSG = "请启动双编码协作流程并开始您的协调任务。"

# ----------------- UI 定位器常量 (UI Locator Constants) -----------------
# 【2025-11-23 修复版 - 适配 Angular 标签结构】
INPUT_SEL = 'div[contenteditable="true"], div[role="textbox"]'
USER_QUERY_SEL = 'user-query' 
MODEL_RESPONSE_CONTAINER_SEL = 'model-response'
LATEST_MSG_SEL = f'{USER_QUERY_SEL}, {MODEL_RESPONSE_CONTAINER_SEL}'
MODEL_RESPONSE_SHELL_SEL = MODEL_RESPONSE_CONTAINER_SEL
LATEST_MSG_SEL_FOR_WAITING = LATEST_MSG_SEL 
RESPONSE_CONTENT_SEL = '.response-content, .model-response-text' 
DONE_STATUS_SEL = 'button[aria-label*="Stop"], button[aria-label*="停止"], button[aria-label*="Pause"]'
SEND_BUTTON_SEL = 'button[aria-label*="Send"], button[aria-label*="发送"], button mat-icon[data-mat-icon-name="send"]'

# ----------------- 隐身脚本 (Manual Stealth Injection) -----------------
# 这是一个精简版的 Stealth JS，用于移除 WebDriver 标记
STEALTH_JS = """
(() => {
    Object.defineProperty(navigator, 'webdriver', {
        get: () => false,
    });
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3],
    });
    Object.defineProperty(navigator, 'languages', {
        get: () => ['zh-CN', 'zh', 'en'],
    });
    
    // 伪造 Chrome 运行时
    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {}
    };

    // 覆盖 Permissions API
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
    );
})();
"""

# =======================================================================================
# === II. 阶段一：核心功能函数封装 (Phase One: Core Function Wrappers) ===
# =======================================================================================

def log(level: str, message: str, step: str = "ORCHESTRATOR"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}][{level:<7}][{step:<15}] {message}")

def wait_for_page_stability(page: Page, agent_name: str):
    TIMEOUT_MS = 30000
    log("INFO", f"等待 {agent_name} 页面稳定 (超时 {TIMEOUT_MS//1000}s)...", "PAGE_WAIT")
    try:
        page.wait_for_selector(INPUT_SEL, state="visible", timeout=TIMEOUT_MS)
        log("SUCCESS", f"{agent_name} 页面已稳定，输入框可见。", "PAGE_WAIT")
    except PlaywrightTimeoutError:
        log("FATAL", f"{agent_name} 页面稳定失败，未找到核心输入框。", "PAGE_WAIT")
        raise Exception("页面初始化失败，无法继续。")

def handle_termination(final_message: str):
    log("SUCCESS", "⭐⭐⭐ 发现安全词 (终止信号)！任务圆满完成。 ⭐⭐⭐", "TERMINATION")
    log("INFO", f"Agent A 的最终交付内容:\n{'='*40}\n{final_message}\n{'='*40}", "TERMINATION")
    log("INFO", "脚本将停止交互，但浏览器会保持打开，请主人喵检查结果。", "TERMINATION")
    return True

def send_message_robust(page: Page, message: str, agent_name: str) -> int:
    if not message or not message.strip():
        log("WARNING", f"尝试发送给 {agent_name} 的消息为空，已跳过。", "SEND_ROBUST")
        return page.locator(LATEST_MSG_SEL_FOR_WAITING).count()

    log("INFO", f"向 {agent_name} 发送消息 (长度: {len(message)})...", "SEND_ROBUST")
    try:
        page.bring_to_front()
        count_before = page.locator(LATEST_MSG_SEL_FOR_WAITING).count()
        log("INFO", f"发送前检测到气泡数: {count_before}", "SEND_ROBUST")

        input_locator = page.locator(INPUT_SEL).first
        send_button_locator = page.locator(SEND_BUTTON_SEL).first
        
        input_locator.click()
        input_locator.fill("")
        page.evaluate("text => navigator.clipboard.writeText(text)", message)
        input_locator.press("Control+V")
        log("INFO", "内容已粘贴。", "SEND_ROBUST")
        
        page.wait_for_timeout(500)

        if send_button_locator.is_visible():
            send_button_locator.hover()
            page.wait_for_timeout(300)
            send_button_locator.click()
            log("INFO", f"消息已通过点击按钮提交给 {agent_name}。", "SEND_ROBUST")
        else:
            log("INFO", "未找到发送按钮，尝试使用 Enter 发送。", "SEND_ROBUST")
            input_locator.press("Enter")

        log("INFO", f"请求浏览器进行终极裁决 (等待新气泡出现)...", "SEND_ROBUST")
        
        js_wait_expression = """
            (args) => {
                const [selector, known_count] = args;
                const current_elements = document.querySelectorAll(selector);
                return current_elements.length > known_count;
            }
        """
        page.wait_for_function(js_wait_expression, arg=[LATEST_MSG_SEL_FOR_WAITING, count_before], timeout=60000)
        log("SUCCESS", "浏览器裁决：新气泡已生成！发送成功。", "SEND_ROBUST")

        time.sleep(1)
        new_len = page.locator(LATEST_MSG_SEL).count()
        return new_len

    except Exception as e:
        log("FATAL", f"向 {agent_name} 发送消息时发生致命错误: {e}", "SEND_ROBUST")
        raise

def get_latest_message_safe(page: Page, agent_name: str) -> tuple[str, int]:
    log("INFO", f"等待 {agent_name} 生成内容...", "GET_SAFE")
    try:
        expect(page.locator(DONE_STATUS_SEL)).to_be_hidden(timeout=180000)
        log("SUCCESS", f"{agent_name} 已完成生成 (停止按钮已消失)。", "GET_SAFE")
    except PlaywrightTimeoutError:
        log("WARNING", f"{agent_name} 生成时间超过 180s，强制提取内容。", "GET_SAFE")

    try:
        last_message_container = page.locator(LATEST_MSG_SEL).last
        text_locator = last_message_container.locator(RESPONSE_CONTENT_SEL).first
        
        if text_locator.count() == 0:
            log("WARNING", "未找到精确的内容选择器，尝试提取整个容器文本。", "GET_SAFE")
            text_locator = last_message_container

        expect(text_locator).to_be_visible(timeout=10000)
        
        raw_text = text_locator.inner_text()
        cleaned_text = raw_text.replace("显示思路", "").replace("Show thoughts", "").strip()
        cleaned_text = cleaned_text.lstrip()

        new_len = page.locator(LATEST_MSG_SEL).count()
        log("SUCCESS", f"成功提取 {agent_name} 的消息 (已过滤 Pro UI 杂质)。", "GET_SAFE")
        return cleaned_text, new_len
    except Exception as e:
        log("FATAL", f"无法从 {agent_name} 提取最新消息: {e}", "GET_SAFE")
        raise

def wait_for_response_loop(page: Page, current_len: int, agent_name: str) -> int:
    TIMEOUT_LOOP_SEC = 180
    log("INFO", f"等待 {agent_name} 回复 (当前轮数: {current_len}, 超时: {TIMEOUT_LOOP_SEC}s)...", "WAIT_LOOP")
    try:
        js_wait_expression = """
            (args) => {
                const [selector, known_count] = args;
                return document.querySelectorAll(selector).length > known_count;
            }
        """
        page.wait_for_function(js_wait_expression, arg=[LATEST_MSG_SEL_FOR_WAITING, current_len], timeout=TIMEOUT_LOOP_SEC * 1000)
        log("SUCCESS", "浏览器裁决：AI已回复！", "WAIT_LOOP")
        time.sleep(1)
        new_len = page.locator(LATEST_MSG_SEL).count()
        return new_len
    except Exception as e:
        log("FATAL", f"等待 {agent_name} 回复时发生致命错误: {e}", "WAIT_LOOP_ERROR")
        raise e

# =======================================================================================
# === III. 阶段二：主编排逻辑 (Phase Two: Main Orchestration Logic) ===
# =======================================================================================

def run_orchestrator(page_A: Page, page_B: Page):
    log("INFO", "=== 自动化流程正式开始 ===", "MAIN")

    wait_for_page_stability(page_A, "Agent A")
    wait_for_page_stability(page_B, "Agent B")

    len_A = page_A.locator(LATEST_MSG_SEL_FOR_WAITING).count()
    log("INFO", f"Agent A 当前气泡数: {len_A}", "SCENE_HANDLER")

    if len_A == 0:
        log("INFO", "场景1: A页面空白。发送启动指令...", "SCENE_HANDLER")
        len_A = send_message_robust(page_A, START_CMD_MSG, "Agent A")
        len_A = wait_for_response_loop(page_A, 1, "Agent A")
    
    elif len_A > 0 and len_A % 2 != 0:
        log("INFO", "场景2: 用户已提问，等待A的回复...", "SCENE_HANDLER")
        len_A = wait_for_response_loop(page_A, len_A, "Agent A")

    log("INFO", "状态同步完成。进入主协作循环。", "SCENE_HANDLER")

    while True:
        log("INFO", "--- 开始新一轮协作 ---", "CYCLE")
        
        message_A, len_A = get_latest_message_safe(page_A, "Agent A")
        
        if TERMINATION_PHRASE in message_A:
            should_stop = handle_termination(message_A)
            if should_stop:
                break
        
        len_B_before = page_B.locator(LATEST_MSG_SEL_FOR_WAITING).count()
        len_B = send_message_robust(page_B, message_A, "Agent B")
        len_B = wait_for_response_loop(page_B, len_B_before + 1, "Agent B")

        message_B, len_B = get_latest_message_safe(page_B, "Agent B")
        
        len_A = send_message_robust(page_A, message_B, "Agent A")
        len_A = wait_for_response_loop(page_A, len_A, "Agent A")
        
        log("SUCCESS", "--- 本轮协作完成 ---", "CYCLE")

# =======================================================================================
# === IV. 阶段三：程序入口与浏览器设置 (Phase Three: Entry Point & Browser Setup) ===
# =======================================================================================
if __name__ == '__main__':
    try:
        EDGE_USER_DATA_PATH = "C:\\Users\\asus\\AppData\\Local\\Microsoft\\Edge\\User Data"
        if not os.path.exists(EDGE_USER_DATA_PATH):
            log("WARNING", f"未找到默认路径: {EDGE_USER_DATA_PATH}", "SETUP")
            EDGE_USER_DATA_PATH = os.path.join(os.getcwd(), "edge_user_data")

        GEMINI_URL_A = "https://gemini.google.com/u/0/app?hl=zh-cn"
        GEMINI_URL_B = "https://gemini.google.com/u/3/app?hl=zh-cn"
        
        with sync_playwright() as p:
            log("INFO", "启动 Edge 浏览器 (Manual Stealth 模式)...", "SETUP")
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=EDGE_USER_DATA_PATH,
                    headless=False,
                    channel="msedge",
                    slow_mo=50,
                    # 1. 禁用自动化控制特性
                    args=[
                        '--start-maximized',
                        '--disable-blink-features=AutomationControlled'
                    ],
                    # 2. 移除顶部的“正由自动测试软件控制”横幅
                    ignore_default_args=["--enable-automation"]
                )
            except PlaywrightError as e:
                if "Target page, context or browser has been closed" in str(e) or "exitCode=21" in str(e):
                    log("FATAL", "========================================", "ERROR")
                    log("FATAL", "启动失败！检测到 Edge 浏览器可能已在运行。", "ERROR")
                    log("FATAL", "请关闭所有 Edge 窗口后重试。", "ERROR")
                    sys.exit(1)
                else:
                    raise e
            
            # 【反检测核心】手动注入 Stealth JS
            # 为每一个新创建的页面自动注入隐身代码
            context.add_init_script(STEALTH_JS)

            page_A = context.pages[0] if context.pages else context.new_page()
            page_A.goto(GEMINI_URL_A, wait_until="domcontentloaded", timeout=90000)
            
            if len(context.pages) > 1:
                page_B = context.pages[1]
            else:
                page_B = context.new_page()
            page_B.goto(GEMINI_URL_B, wait_until="domcontentloaded", timeout=90000)
            
            log("SUCCESS", "双 Agent 页面已加载 (手动隐身补丁已应用)。", "SETUP")
            page_A.bring_to_front()

            MANUAL_SETUP_TIME = 30
            log("WARNING", f"您有 {MANUAL_SETUP_TIME} 秒时间进行手动设置（登录账号/确认环境）。", "MANUAL_SETUP")
            
            for i in range(MANUAL_SETUP_TIME, 0, -10):
                log("INFO", f"剩余时间: {i} 秒...", "MANUAL_SETUP")
                time.sleep(10)

            run_orchestrator(page_A=page_A, page_B=page_B)
            
            log("SUCCESS", "========================================", "DONE")
            log("SUCCESS", "任务协作流已结束。", "DONE")
            input(">>> 检查完毕后，请按 Enter 键关闭浏览器并结束脚本 <<<")

    except Exception as e:
        log("FATAL", f"脚本因错误而终止: {e}", "RUNTIME_ERROR")
        import traceback
        traceback.print_exc()
    finally:
        log("INFO", "脚本执行结束。", "SHUTDOWN")
