import time
import sys
import random as global_random
import os
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError, expect

# =======================================================================================
# === I. 阶段零：前置依赖与全局常量规范 (Phase Zero: Dependencies & Constants) ===
# =======================================================================================

TERMINATION_PHRASE = "TASK_COMPLETED_SUCCESSFULLY"
START_CMD_MSG = "请启动双编码协作流程并开始您的协调任务。"

# 【ULTIMATE ANTI-BOT STRATEGY v7: HYBRID SENSING】
# 终极反-反制策略 v7：混合感知（跨界强袭）
# 核心问题：单一的DOM感知可能被“幻象结界”欺骗。
# 新策略：采用“多重感知”，同时监听 DOM脉冲(innerHTML) 和 锚点计数(.response-container数量) 的变化。
# 任何一种信号的变化都将被视为有效响应，并引入“强制快进”互动来打破页面静默。

INPUT_SEL = 'div[role="textbox"]'
CHAT_AREA_SEL = 'body'
MESSAGE_ANCHOR_SEL = '.response-container'
LATEST_MSG_SEL = MESSAGE_ANCHOR_SEL

DONE_STATUS_SEL = 'button[aria-label="停止回复"], button[aria-label="Stop responding"]'
SEND_BUTTON_SEL = 'button mat-icon[data-mat-icon-name="send"]'
# ---------------------------------------------------------------------------------------


# =======================================================================================
# === Ib. 阶段零-B：全局配置 (Phase Zero-B: Global Configuration) =====================
# =======================================================================================
class Config:
    """集中管理所有可配置的全局变量。"""
    EDGE_USER_DATA_PATH = "C:\\Users\\asus\\AppData\\Local\\Microsoft\\Edge\\User Data"
    GEMINI_URL_A = "https://gemini.google.com/u/1/app?hl=zh-cn"
    GEMINI_URL_B = "https://gemini.google.com/u/3/app?hl=zh-cn"

    class Timeouts:
        PAGE_LOAD_MS = 90000
        PAGE_STABILITY_MS = 30000
        AI_GENERATION_MS = 120000
        RESPONSE_VISIBILITY_MS = 10000
        WAIT_FOR_CHANGE_MS = 180000
        MANUAL_SETUP_SEC = 30
        CONTENT_STABILITY_MS = 1500

class Session:
    """封装会话状态和人格化参数。"""
    def __init__(self, seed: int):
        self.session_seed = seed
        self.rng = global_random.Random(seed)
        self.task_lock = False
        personas = {
            'new_user': {'P_IDLE_TRIGGER': 0.30},
            'experienced_user': {'P_IDLE_TRIGGER': 0.15}
        }
        self.persona_name = self.rng.choice(list(personas.keys()))
        self.behavioral_params = personas[self.persona_name]
        log("INFO", f"会话已初始化，种子: {self.session_seed}", "会话")
        log("INFO", f"L1人格已分配: '{self.persona_name}'", "L1人格")

# =======================================================================================
# === II. 阶段一：核心功能函数封装 (Phase One: Core Function Wrappers) ===
# =======================================================================================

def log(level: str, message: str, step: str = "协调器"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}][{level:<7}][{step:<15}] {message}")

def wait_for_full_response(page: Page, agent_name: str, previous_html: str, previous_anchor_count: int):
    log("INFO", f"等待 {agent_name} 的响应 (混合感知模式)...", "响应感知")
    js_wait_expression = """
        (args) => {
            const [selector, prevLength, prevCount, anchorSelector] = args;
            const container = document.querySelector(selector);
            if (!container) return false;
            const currentLength = container.innerHTML.length;
            const currentCount = document.querySelectorAll(anchorSelector).length;
            // 混合感知：DOM脉冲 或 锚点增加
            return currentLength !== prevLength || currentCount > prevCount;
        }
    """
    try:
        page.wait_for_function(
            js_wait_expression,
            arg=[CHAT_AREA_SEL, len(previous_html), previous_anchor_count, MESSAGE_ANCHOR_SEL],
            timeout=Config.Timeouts.WAIT_FOR_CHANGE_MS
        )
        log("SUCCESS", f"检测到来自 {agent_name} 的响应！进入稳定观察期...", "响应感知")

        # 稳定观察期，同样监听 innerHTML
        last_len = 0
        current_len = page.locator(CHAT_AREA_SEL).evaluate("el => el.innerHTML").__len__()
        while last_len != current_len:
            last_len = current_len
            page.wait_for_timeout(Config.Timeouts.CONTENT_STABILITY_MS)
            # “强制快进”互动，尝试打破页面静默
            page.mouse.wheel(0, 1)
            current_len = page.locator(CHAT_AREA_SEL).evaluate("el => el.innerHTML").__len__()
        
        log("SUCCESS", f"DOM结构已稳定，{agent_name} 已完成完整输出。", "响应感知")

    except PlaywrightTimeoutError:
        log("FATAL", f"等待 {agent_name} 响应超时。", "响应感知")
        raise

def wait_for_page_stability(page: Page, agent_name: str):
    log("INFO", f"等待 {agent_name} 页面稳定 (超时 {Config.Timeouts.PAGE_STABILITY_MS//1000}s)...", "页面等待")
    try:
        expect(page.locator(INPUT_SEL)).to_be_editable(timeout=Config.Timeouts.PAGE_STABILITY_MS)
        log("SUCCESS", f"{agent_name} 页面已稳定，输入框可交互。", "页面等待")
    except PlaywrightTimeoutError:
        log("FATAL", f"{agent_name} 页面稳定失败，未找到可交互的输入框。", "页面等待")
        raise Exception("页面初始化失败，无法继续。")

def _calculate_bezier_point(t: float, p0: dict, p1: dict, p2: dict) -> dict:
    u = 1 - t
    tt = t * t
    uu = u * u
    x = (uu * p0['x']) + (2 * u * t * p1['x']) + (tt * p2['x'])
    y = (uu * p0['y']) + (2 * u * t * p1['y']) + (tt * p2['y'])
    return {'x': x, 'y': y}

def _move_mouse_human_like(page: Page, target_locator, session: Session):
    log("INFO", "模拟类人鼠标移动...", "鼠标移动")
    viewport_size = page.viewport_size
    start_point = {'x': session.rng.randint(0, viewport_size['width'] if viewport_size else 100), 'y': session.rng.randint(0, viewport_size['height'] if viewport_size else 100)}
    target_box = target_locator.bounding_box()
    if not target_box:
        log("WARNING", "无法获取鼠标移动目标元素的边界框。", "鼠标移动")
        return
    end_point = {'x': target_box['x'] + target_box['width'] / 2, 'y': target_box['y'] + target_box['height'] / 2}
    control_point = {
        'x': (start_point['x'] + end_point['x']) / 2 + session.rng.uniform(-target_box['width'], target_box['width']),
        'y': (start_point['y'] + end_point['y']) / 2 + session.rng.uniform(-target_box['height'], target_box['height'])
    }
    steps = session.rng.randint(25, 40)
    for i in range(steps + 1):
        t = i / steps
        point = _calculate_bezier_point(t, start_point, control_point, end_point)
        page.mouse.move(point['x'], point['y'])
        page.wait_for_timeout(session.rng.uniform(5, 25))

def _perform_idle_action(page: Page, session: Session):
    pass # 省略实现

def handle_termination(final_message: str):
    log("SUCCESS", "检测到终止信号。任务完成。", "任务终止")
    log("INFO", f"Agent A 的最终交付内容:\n---\n{final_message}\n---", "任务终止")
    # sys.exit(0)

def send_message_robust(page: Page, message: str, agent_name: str, session: Session):
    if not message or not message.strip():
        log("WARNING", f"尝试向 {agent_name} 发送空消息，已跳过。", "发送消息")
        return
    log("INFO", f"向 {agent_name} 发送消息 (长度: {len(message)})...", "发送消息")
    try:
        session.task_lock = True
        log("INFO", "已获取任务锁。", "L4锁")
        page.bring_to_front()
        
        snapshot_html = page.locator(CHAT_AREA_SEL).evaluate("el => el.innerHTML")
        snapshot_count = page.locator(MESSAGE_ANCHOR_SEL).count()
        log("INFO", f"发送前快照(DOM长度: {len(snapshot_html)}, 锚点数: {snapshot_count})", "发送消息")

        input_box = page.locator(INPUT_SEL)
        send_button_locator = page.locator(SEND_BUTTON_SEL)
        input_box.fill(message)
        log("INFO", "消息内容已填充。", "发送消息")
        page.wait_for_timeout(session.rng.uniform(300, 700))
        _move_mouse_human_like(page, send_button_locator, session)
        send_button_locator.hover()
        page.wait_for_timeout(session.rng.uniform(100, 300))
        send_button_locator.click()

        wait_for_full_response(page, f"{agent_name}(用户侧)", snapshot_html, snapshot_count)
        log("SUCCESS", "混合感知：用户发送的消息已显示！", "发送消息")

    except Exception as e:
        log("FATAL", f"向 {agent_name} 发送消息时发生严重错误: {e}", "发送消息")
        raise
    finally:
        session.task_lock = False
        log("INFO", "任务锁已释放。", "L4锁")


def get_latest_message_safe(page: Page, agent_name: str) -> str:
    log("INFO", f"为 {agent_name} 执行“次元切割”高权限提取脚本...", "提取消息")
    try:
        js_get_last_message_script = f"""
            () => {{
                const allMessages = document.querySelectorAll('{MESSAGE_ANCHOR_SEL}');
                if (allMessages.length === 0) return '';
                for (let i = allMessages.length - 1; i >= 0; i--) {{
                    const messageContainer = allMessages[i];
                    const clone = messageContainer.cloneNode(true);
                    clone.querySelectorAll('.response-container-footer, [class*="menu-button"], [class*="thoughts"]').forEach(el => el.remove());
                    const markdownEl = clone.querySelector('[class*="markdown"]');
                    if (markdownEl && markdownEl.innerText.trim()) {{
                        return markdownEl.innerText.trim();
                    }}
                    const fullText = clone.innerText;
                    if (fullText && fullText.trim()) {{
                        return fullText.trim();
                    }}
                }}
                return '';
            }}
        """
        message_text = page.evaluate(js_get_last_message_script)

        if not message_text:
            log("WARNING", "高权限提取脚本未能找到任何有效消息内容。", "提取消息")
            last_container = page.locator(LATEST_MSG_SEL).last
            if last_container.count() > 0:
                message_text = last_container.inner_text().strip()

        log("SUCCESS", f"成功从 {agent_name} 提取到消息 (长度: {len(message_text)})", "提取消息")
        return message_text

    except Exception as e:
        log("FATAL", f"无法从 {agent_name} 提取最新消息: {e}", "提取消息")
        raise

# =======================================================================================
# === III. 阶段二：主编排逻辑 (Phase Two: Main Orchestration Logic) ===
# =======================================================================================

def run_orchestrator(page_A: Page, page_B: Page, initial_session: Session):
    log("INFO", "=== 自动化流程正式开始 ===", "主流程")
    session = initial_session
    error_count = 0
    MAX_ERRORS = 3
    while True:
        try:
            page_A.bring_to_front()
            wait_for_page_stability(page_A, "Agent A")
            
            start_new_task = False
            if not page_A.locator(MESSAGE_ANCHOR_SEL).count():
                start_new_task = True
                log("INFO", "场景1: A页面空白，判定为新任务。", "场景处理")
            else:
                last_message_on_A = get_latest_message_safe(page_A, "Agent A (状态检查)")
                if TERMINATION_PHRASE in last_message_on_A:
                    start_new_task = True
                    log("INFO", "场景2: 检测到上次任务已完成，判定为新任务。", "场景处理")
                else:
                    log("INFO", "场景3: 检测到未完成的对话，继续执行...", "场景处理")

            if start_new_task:
                log("INFO", "发送新任务启动指令...", "场景处理")
                send_message_robust(page_A, START_CMD_MSG, "Agent A", session)
                snapshot_html = page_A.locator(CHAT_AREA_SEL).evaluate("el => el.innerHTML")
                snapshot_count = page_A.locator(MESSAGE_ANCHOR_SEL).count()
                wait_for_full_response(page_A, "Agent A", snapshot_html, snapshot_count)

            log("INFO", "状态同步完成。进入主协作循环。", "场景处理")
            while True:
                log("INFO", "--- 开始新一轮协作 ---", "协作循环")

                message_A = get_latest_message_safe(page_A, "Agent A")
                if TERMINATION_PHRASE in message_A:
                    handle_termination(message_A)
                    break
                
                page_B.bring_to_front()
                wait_for_page_stability(page_B, "Agent B")
                send_message_robust(page_B, message_A, "Agent B", session)
                snapshot_html_b = page_B.locator(CHAT_AREA_SEL).evaluate("el => el.innerHTML")
                snapshot_count_b = page_B.locator(MESSAGE_ANCHOR_SEL).count()
                wait_for_full_response(page_B, "Agent B", snapshot_html_b, snapshot_count_b)

                message_B = get_latest_message_safe(page_B, "Agent B")

                page_A.bring_to_front()
                send_message_robust(page_A, message_B, "Agent A", session)
                snapshot_html_a = page_A.locator(CHAT_AREA_SEL).evaluate("el => el.innerHTML")
                snapshot_count_a = page_A.locator(MESSAGE_ANCHOR_SEL).count()
                wait_for_full_response(page_A, "Agent A", snapshot_html_a, snapshot_count_a)
                
                error_count = 0
                log("SUCCESS", "--- 本轮协作完成 ---", "协作循环")

        except Exception as e:
            error_count += 1
            log("ERROR", f"协作循环出错 (尝试 {error_count}/{MAX_ERRORS}次): {e}", "L4恢复")
            if error_count >= MAX_ERRORS:
                log("CRITICAL", "错误次数达到阈值！触发“理论销毁”...", "L4恢复")
                frustration_wait_s = session.rng.uniform(15, 45)
                log("INFO", f"模拟人类沮丧，暂停 {frustration_wait_s:.1f} 秒...", "L4恢复")
                time.sleep(frustration_wait_s)
                log("CRITICAL", "重置身份！生成新的会话种子...", "L4恢复")
                session = Session(seed=int(time.time()))
                error_count = 0
                log("SUCCESS", "Agent已重生。使用新身份重试任务。", "L4恢复")

# =======================================================================================
# === IV. 阶段三：程序入口与浏览器设置 (Phase Three: Entry Point & Browser Setup) ===
# =======================================================================================
if __name__ == '__main__':
    try:
        if not os.path.exists(Config.EDGE_USER_DATA_PATH):
            raise FileNotFoundError(f"Edge 用户数据目录未找到: {Config.EDGE_USER_DATA_PATH}")
        session = Session(seed=int(time.time()))
        with sync_playwright() as p:
            log("INFO", "正在启动 Edge 浏览器并加载个人配置...", "启动设置")
            context = p.chromium.launch_persistent_context(
                user_data_dir=Config.EDGE_USER_DATA_PATH,
                headless=False,
                channel="msedge",
                slow_mo=50,
                args=['--start-maximized', '--disable-blink-features=AutomationControlled']
            )
            page_A = context.pages[0] if context.pages else context.new_page()
            page_A.goto(Config.GEMINI_URL_A, wait_until="domcontentloaded", timeout=Config.Timeouts.PAGE_LOAD_MS)
            page_B = context.new_page()
            page_B.goto(Config.GEMINI_URL_B, wait_until="domcontentloaded", timeout=Config.Timeouts.PAGE_LOAD_MS)
            log("SUCCESS", "双Agent页面已加载。", "启动设置")
            wait_for_page_stability(page_A, "Agent A")
            wait_for_page_stability(page_B, "Agent B")
            page_A.bring_to_front()
            log("WARNING", f"您有 {Config.Timeouts.MANUAL_SETUP_SEC} 秒进行手动设置。", "手动设置")
            log("WARNING", "请在 Agent A (第一个标签页) 中输入您的初始任务。", "手动设置")
            for i in range(Config.Timeouts.MANUAL_SETUP_SEC, 0, -10):
                log("INFO", f"剩余时间: {i} 秒...", "手动设置")
                time.sleep(10)
            run_orchestrator(page_A=page_A, page_B=page_B, initial_session=session)
    except FileNotFoundError as e:
        log("FATAL", str(e), "启动错误")
    except Exception as e:
        log("FATAL", f"脚本因未知错误而终止: {e}", "运行时错误")
    finally:
        log("INFO", "脚本执行结束。", "关闭")
        input("按回车键关闭浏览器...")
