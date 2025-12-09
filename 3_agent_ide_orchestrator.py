import time
import sys
import os
import re
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError, expect, Error as PlaywrightError

# =======================================================================================
# === I. 全局配置与常量 (Configuration) ===
# =======================================================================================

# ----------------- 协作安全词 (Safety Phrases) -----------------
# 必须严格匹配，用于路由判断
PHRASE_PLAN_CREATED = "PLAN_CREATED"               # Planner -> Coder
PHRASE_PATCH_REJECT = "PATCH_REJECT"               # QA -> Coder
PHRASE_PATCH_ACCEPT = "PATCH_ACCEPT"               # QA -> Coder (中继1) / Coder -> Planner (中继2)
PHRASE_TASK_COMPLETE = "TASK_COMPLETED_SUCCESSFULLY" # Planner -> END

# ----------------- 占位符配置 (Placeholders - 请主人喵替换) -----------------
# Windows Edge 用户数据路径 (通常在 C:\Users\您的用户名\AppData\Local\Microsoft\Edge\User Data)
PLACEHOLDER_USER_DATA_DIR = r"C:\\Users\\asus\\AppData\\Local\\Microsoft\\Edge\\User Data" 

# 三个角色的 URL (可以使用同一个 URL，依靠不同的账号 Profile 或 手动切换)
# 建议：如果是同一个浏览器 Profile，可以用不同的对话窗口，脚本启动后手动点开三个不同的对话即可
# 这里假设脚本启动时会自动打开三个标签页，您需要在 30s 内让它们分别对应 Planner/Coder/QA
PLACEHOLDER_URL_PLANNER = "https://gemini.google.com/u/0/app?hl=zh-cn" 
PLACEHOLDER_URL_CODER = "https://gemini.google.com/u/3/app?hl=zh-cn"
PLACEHOLDER_URL_QA = "https://gemini.google.com/u/2/app?hl=zh-cn"

# ----------------- UI 定位器 (UI Locators) -----------------
INPUT_SEL = 'div[contenteditable="true"], div[role="textbox"]'
MODEL_RESPONSE_CONTAINER_SEL = 'model-response'
LATEST_MSG_SEL = f'user-query, {MODEL_RESPONSE_CONTAINER_SEL}'
LATEST_MSG_SEL_FOR_WAITING = LATEST_MSG_SEL 
RESPONSE_CONTENT_SEL = '.response-content, .model-response-text' 
DONE_STATUS_SEL = 'button[aria-label*="Stop"], button[aria-label*="停止"], button[aria-label*="Pause"]'
SEND_BUTTON_SEL = 'button[aria-label*="Send"], button[aria-label*="发送"], button mat-icon[data-mat-icon-name="send"]'

# ----------------- 隐身脚本 (Stealth JS) -----------------
STEALTH_JS = """
(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
    window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ? Promise.resolve({ state: Notification.permission }) : originalQuery(parameters)
    );
})();
"""

# =======================================================================================
# === II. 核心工具函数 (Core Functions) ===
# =======================================================================================

def log(level: str, message: str, step: str = "ORCHESTRATOR"):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}][{level:<7}][{step:<15}] {message}")

def wait_for_page_stability(page: Page, agent_name: str):
    try:
        page.wait_for_selector(INPUT_SEL, state="visible", timeout=30000)
    except PlaywrightTimeoutError:
        log("FATAL", f"{agent_name} 页面未就绪，请检查网络。", "INIT")
        raise

def send_message_robust(page: Page, message: str, agent_name: str) -> int:
    if not message or not message.strip():
        return page.locator(LATEST_MSG_SEL_FOR_WAITING).count()

    log("INFO", f"正在发送给 [{agent_name}]...", "SEND")
    try:
        page.bring_to_front()
        count_before = page.locator(LATEST_MSG_SEL_FOR_WAITING).count()
        
        input_locator = page.locator(INPUT_SEL).first
        input_locator.click()
        input_locator.fill("") # 清空
        page.evaluate("text => navigator.clipboard.writeText(text)", message)
        input_locator.press("Control+V")
        page.wait_for_timeout(800) 

        send_btn = page.locator(SEND_BUTTON_SEL).first
        if send_btn.is_visible():
            send_btn.click()
        else:
            input_locator.press("Enter")

        # 等待新气泡
        page.wait_for_function(
            "(args) => document.querySelectorAll(args[0]).length > args[1]",
            arg=[LATEST_MSG_SEL_FOR_WAITING, count_before],
            timeout=60000
        )
        return page.locator(LATEST_MSG_SEL).count()
    except Exception as e:
        log("FATAL", f"发送给 {agent_name} 失败: {e}", "SEND")
        raise

def get_latest_message_safe(page: Page, agent_name: str) -> str:
    log("INFO", f"等待 [{agent_name}] 回复...", "RECEIVE")
    try:
        expect(page.locator(DONE_STATUS_SEL)).to_be_hidden(timeout=180000) # 3分钟超时
    except:
        log("WARNING", f"[{agent_name}] 生成耗时过长，尝试强制提取。", "RECEIVE")

    try:
        last_msg = page.locator(LATEST_MSG_SEL).last
        content_loc = last_msg.locator(RESPONSE_CONTENT_SEL).first
        if content_loc.count() == 0: content_loc = last_msg 
        
        raw_text = content_loc.inner_text()
        cleaned = raw_text.replace("Show thoughts", "").replace("显示思路", "").strip()
        
        # 简单预览
        preview = cleaned[:50].replace('\n', ' ')
        log("SUCCESS", f"收到 [{agent_name}]: {preview}...", "RECEIVE")
        return cleaned
    except Exception as e:
        log("FATAL", f"从 {agent_name} 提取消息失败: {e}", "RECEIVE")
        raise

# =======================================================================================
# === III. 核心编排逻辑 (Orchestration Logic) ===
# =======================================================================================

def run_agent_pool_orchestrator(pages: dict):
    agent_planner = pages['Planner']
    agent_coder = pages['Coder']
    agent_qa = pages['QA']

    log("INFO", "=== 30秒预备时间结束，开始接管流程 ===", "MAIN")
    
    # 1. 初始读取：直接去读 Planner 页面上主人喵已经生成好的任务
    # 假设主人喵已经完成了 Prompt 交互，Planner 输出了第一条 PLAN_CREATED
    current_msg = get_latest_message_safe(agent_planner, "Planner")
    current_sender = "Planner" 

    # 2. 状态机死循环
    while True:
        log("INFO", f"当前持有令牌: [{current_sender}] -> 正在解析路由...", "ROUTER")
        
        # --- A. 终止检查 ---
        if PHRASE_TASK_COMPLETE in current_msg:
            log("SUCCESS", "⭐⭐⭐ 任务圆满完成 (TASK_COMPLETED_SUCCESSFULLY) ⭐⭐⭐", "DONE")
            log("INFO", "脚本停止运行。浏览器将保持打开供主人喵检阅。", "DONE")
            break

        # --- B. 路由逻辑 ---
        next_agent_name = ""
        next_agent_page = None
        
        # 1. 发送者是 Planner
        if current_sender == "Planner":
            # Planner 发话，无论是 PLAN_CREATED 还是闲聊，都扔给 Coder 去执行
            log("ROUTER", "规则匹配: [Planner] -> [Coder]", "ROUTING")
            next_agent_name = "Coder"
            next_agent_page = agent_coder

        # 2. 发送者是 Coder
        elif current_sender == "Coder":
            if current_msg.startswith(PHRASE_PATCH_ACCEPT):
                # Coder 只有在收到 QA 的通过信号后，才会发出这个，这是给 Planner 的完成信号
                log("ROUTER", "规则匹配: [Coder] (PATCH_ACCEPT) -> [Planner] (子任务完成)", "ROUTING")
                next_agent_name = "Planner"
                next_agent_page = agent_planner
            else:
                # Coder 发出的是代码或者修正补丁，给 QA 审
                log("ROUTER", "规则匹配: [Coder] (Code/Patch) -> [QA] (审查)", "ROUTING")
                next_agent_name = "QA"
                next_agent_page = agent_qa

        # 3. 发送者是 QA
        elif current_sender == "QA":
            if current_msg.startswith(PHRASE_PATCH_ACCEPT):
                # QA 通过了，先告诉 Coder
                log("ROUTER", "规则匹配: [QA] (PATCH_ACCEPT) -> [Coder] (确认通过)", "ROUTING")
                next_agent_name = "Coder"
                next_agent_page = agent_coder
            elif current_msg.startswith(PHRASE_PATCH_REJECT):
                # QA 拒绝了，回给 Coder 修
                log("ROUTER", "规则匹配: [QA] (PATCH_REJECT) -> [Coder] (修Bug)", "ROUTING")
                next_agent_name = "Coder"
                next_agent_page = agent_coder
            else:
                # QA 如果废话，默认还是回给 Coder
                log("WARNING", "QA 未发出明确信号，默认回退给 Coder。", "ROUTING")
                next_agent_name = "Coder"
                next_agent_page = agent_coder

        # --- C. 执行中继 ---
        if next_agent_page:
            # 1. 发送
            send_message_robust(next_agent_page, current_msg, next_agent_name)
            
            # 2. 接收回复 (阻塞等待)
            response_text = get_latest_message_safe(next_agent_page, next_agent_name)
            
            # 3. 更新状态
            current_msg = response_text
            current_sender = next_agent_name
        else:
            log("FATAL", "路由逻辑异常：未找到下一跳 Agent。", "ERROR")
            break

# =======================================================================================
# === IV. 主程序 (Main) ===
# =======================================================================================
if __name__ == '__main__':
    try:
        user_data_path = PLACEHOLDER_USER_DATA_DIR
        # 如果路径包含 Placeholder，提示用户修改
        if "YourName" in user_data_path:
            log("WARNING", "请修改脚本中的 PLACEHOLDER_USER_DATA_DIR 为您的真实路径！", "SETUP")
            # 这里的 fallback 仅用于防止报错，实际无法持久化登录
            user_data_path = os.path.join(os.getcwd(), "edge_user_data_agents")

        with sync_playwright() as p:
            log("INFO", "正在启动浏览器池 (3 Agents)...", "SETUP")
            
            # 启动
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_path,
                headless=False, 
                channel="msedge", 
                args=['--start-maximized', '--disable-blink-features=AutomationControlled'],
                ignore_default_args=["--enable-automation"]
            )
            context.add_init_script(STEALTH_JS)

            # 确保 3 个标签页
            while len(context.pages) < 3:
                context.new_page()
            
            # 映射页面对象
            page_planner = context.pages[0]
            page_coder = context.pages[1]
            page_qa = context.pages[2]

            # 导航
            log("INFO", "加载 Planner 页面...", "SETUP")
            page_planner.goto(PLACEHOLDER_URL_PLANNER, wait_until="domcontentloaded")
            log("INFO", "加载 Coder 页面...", "SETUP")
            page_coder.goto(PLACEHOLDER_URL_CODER, wait_until="domcontentloaded")
            log("INFO", "加载 QA 页面...", "SETUP")
            page_qa.goto(PLACEHOLDER_URL_QA, wait_until="domcontentloaded")

            page_planner.bring_to_front()

            # --- 关键：30秒人工预设时间 ---
            MANUAL_TIME = 30
            log("WARNING", f"【重要】您有 {MANUAL_TIME} 秒时间进行人工操作：", "MANUAL")
            log("INFO", "1. 确认三个页面分别对应 Planner, Coder, QA (顺序是 Tab1, Tab2, Tab3)", "MANUAL")
            log("INFO", "2. 在 Planner 页面输入您的 Prompt，并生成第一条任务 (必须含 PLAN_CREATED)", "MANUAL")
            log("INFO", "3. 确保 Coder 和 QA 页面处于空闲待命状态", "MANUAL")
            
            for i in range(MANUAL_TIME, 0, -5):
                log("INFO", f"剩余时间: {i} 秒...", "MANUAL")
                time.sleep(5)

            # 启动编排
            agents = {
                'Planner': page_planner,
                'Coder': page_coder,
                'QA': page_qa
            }
            
            run_agent_pool_orchestrator(agents)
            
            input("按 Enter 键退出...")

    except Exception as e:
        log("FATAL", f"发生错误: {e}", "ERROR")
        import traceback
        traceback.print_exc()
