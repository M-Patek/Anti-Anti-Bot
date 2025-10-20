import time
import sys
import random as global_random # Keep for unseeded generation if needed elsewhere
import os
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError, expect

# =======================================================================================
# === I. 阶段零：前置依赖与全局常量规范 (Phase Zero: Dependencies & Constants) ===
# =======================================================================================

# ----------------- 协作常量 (Collaboration Constants) -----------------
TERMINATION_PHRASE = "TASK_COMPLETED_SUCCESSFULLY"
START_CMD_MSG = "请启动双编码协作流程并开始您的协调任务。"

# ----------------- UI 定位器常量 (UI Locator Constants) -----------------
# 【2025-10-20 极致拟人最终版】
INPUT_SEL = 'div[role="textbox"]'
USER_QUERY_SEL = '.user-query'
MODEL_RESPONSE_CONTAINER_SEL = '.response-container'
LATEST_MSG_SEL = f'{USER_QUERY_SEL}, {MODEL_RESPONSE_CONTAINER_SEL}'
MODEL_RESPONSE_SHELL_SEL = '.model-response'
LATEST_MSG_SEL_FOR_WAITING = f'{USER_QUERY_SEL}, {MODEL_RESPONSE_SHELL_SEL}'
RESPONSE_CONTENT_SEL = '.response-content'
# L3 Robust Selector: Targets the "stop" button via its stable SVG path, avoiding fragile, language-dependent aria-labels.
DONE_STATUS_SEL = 'button[aria-label] mat-icon[svgicon="gm_stop-fill"]'
SEND_BUTTON_SEL = 'button mat-icon[data-mat-icon-name="send"]'
# ---------------------------------------------------------------------------------------


# =======================================================================================
# === Ib. 阶段零-B：全局配置 (Phase Zero-B: Global Configuration) =====================
# =======================================================================================
class Config:
    """集中管理所有可配置的全局变量。"""
    # --- 浏览器与用户数据配置 ---
    EDGE_USER_DATA_PATH = "C:\\Users\\asus\\AppData\\Local\\Microsoft\\Edge\\User Data"
    
    # --- 目标页面URL ---
    GEMINI_URL_A = "https://gemini.google.com/u/1/app?hl=zh-cn"
    GEMINI_URL_B = "https://gemini.google.com/u/3/app?hl=zh-cn"

    class Timeouts:
        """集中管理所有超时和延迟相关的常量（单位：毫秒或秒）。"""
        PAGE_LOAD_MS = 90000
        PAGE_STABILITY_MS = 30000
        AI_GENERATION_MS = 120000
        RESPONSE_VISIBILITY_MS = 10000
        SEND_ROBUST_WAIT_MS = 60000
        RESPONSE_LOOP_SEC = 180
        MANUAL_SETUP_SEC = 30

class Session:
    """Encapsulates all L1 persona and session-specific state."""
    def __init__(self, seed: int):
        self.session_seed = seed
        self.rng = global_random.Random(seed)
        self.task_lock = False # L4 Task Lock (Mutex)

        # --- L1 Persona-Driven Forgery ---
        personas = {
            'new_user': {
                'TYPO_PROBABILITY': 0.05,      # More prone to typos
                'P_IDLE_TRIGGER': 0.30,        # More likely to be idle/exploratory
            },
            'experienced_user': {
                'TYPO_PROBABILITY': 0.015,     # More accurate typing
                'P_IDLE_TRIGGER': 0.15,        # More focused, less idle time
            }
        }
        # The seed deterministically chooses the persona for the entire session
        self.persona_name = self.rng.choice(list(personas.keys()))
        self.behavioral_params = personas[self.persona_name]
        log("INFO", f"Session initialized with seed: {self.session_seed}", "SESSION")
        log("INFO", f"L1 Persona Assigned: '{self.persona_name}'", "L1_PERSONA")

# =======================================================================================
# === II. 阶段一：核心功能函数封装 (Phase One: Core Function Wrappers) ===
# =======================================================================================

def _wait_for_new_message_bubble(page: Page, known_count: int, timeout: int, agent_name: str):
    """(Internal Helper) Waits for a new message bubble to appear using a JS function."""
    log("INFO", f"Waiting for new message from {agent_name} (known count: {known_count}, timeout: {timeout/1000}s)...", "JS_WAIT")
    js_wait_expression = """
        (args) => {
            const [selector, count] = args;
            return document.querySelectorAll(selector).length > count;
        }
    """
    page.wait_for_function(js_wait_expression, [LATEST_MSG_SEL_FOR_WAITING, known_count], timeout=timeout)

def log(level: str, message: str, step: str = "ORCHESTRATOR"):
    """记录带有时间戳、级别和步骤信息的标准化日志。"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}][{level:<7}][{step:<15}] {message}")

def wait_for_page_stability(page: Page, agent_name: str):
    """等待页面加载完成并稳定。"""
    log("INFO", f"等待 {agent_name} 页面稳定 (超时 {Config.Timeouts.PAGE_STABILITY_MS//1000}s)...", "PAGE_WAIT")
    try:
        expect(page.locator(INPUT_SEL)).to_be_visible(timeout=Config.Timeouts.PAGE_STABILITY_MS)
        log("SUCCESS", f"{agent_name} 页面已稳定，输入框可见。", "PAGE_WAIT")
    except PlaywrightTimeoutError:
        log("FATAL", f"{agent_name} 页面稳定失败，未找到核心输入框。", "PAGE_WAIT")
        raise Exception("页面初始化失败，无法继续。")

def _calculate_bezier_point(t: float, p0: dict, p1: dict, p2: dict) -> dict:
    """(Internal Helper) Calculates a point on a quadratic Bezier curve."""
    u = 1 - t
    tt = t * t
    uu = u * u
    
    x = (uu * p0['x']) + (2 * u * t * p1['x']) + (tt * p2['x']) # pyright: ignore
    y = (uu * p0['y']) + (2 * u * t * p1['y']) + (tt * p2['y']) # pyright: ignore
    return {'x': x, 'y': y} # pyright: ignore

def _move_mouse_human_like(page: Page, target_locator, session: Session):
    """(Internal Helper) Moves the mouse to a target locator using a Bezier curve."""
    log("INFO", "Simulating human-like mouse movement...", "MOUSE_MOVE")
    
    start_point = page.mouse.position
    if not start_point:
        # Fallback if the mouse position isn't available (e.g., first action)
        start_point = {'x': session.rng.randint(0, 100), 'y': session.rng.randint(0, 100)}

    target_box = target_locator.bounding_box()
    if not target_box:
        log("WARNING", "Could not get bounding box for mouse movement target.", "MOUSE_MOVE")
        return

    end_point = {'x': target_box['x'] + target_box['width'] / 2, 'y': target_box['y'] + target_box['height'] / 2}

    # Generate a random control point to make the curve more human-like
    # This point is somewhere between the start and end points, with some randomness
    control_point = {
        'x': (start_point['x'] + end_point['x']) / 2 + session.rng.uniform(-target_box['width'], target_box['width']),
        'y': (start_point['y'] + end_point['y']) / 2 + session.rng.uniform(-target_box['height'], target_box['height'])
    }

    steps = session.rng.randint(25, 40) # Human-like variation in steps
    for i in range(steps + 1):
        t = i / steps
        point = _calculate_bezier_point(t, start_point, control_point, end_point)
        page.mouse.move(point['x'], point['y'])
        # Slow down towards the end, mimicking Fitts's Law
        if t > 0.7:
             page.wait_for_timeout(session.rng.uniform(10, 25))
        else:
             page.wait_for_timeout(session.rng.uniform(5, 15))

def handle_termination(final_message: str, session: Session):
    """处理终止信号并安全退出。"""
    log("SUCCESS", "发现终止信号。任务完成，程序即将退出。", "TERMINATION")
    log("INFO", f"Agent A 的最终交付内容:\n---\n{final_message}\n---", "TERMINATION")
    log("INFO", "浏览器将保持打开状态，请检查最终结果。", "TERMINATION")
    sys.exit(0)

def send_message_robust(page: Page, message: str, agent_name: str, session: Session) -> int:
    """
    核心发送函数（v13.0 - 输入幻觉）：
    通过模拟人类打字（包含停顿、输入错误和修正）、鼠标移动、随机延迟和点击按钮，
    最大程度地模仿真实用户操作，以期绕过最深层的反自动化机制。
    """
    if not message or not message.strip():
        log("WARNING", f"尝试发送给 {agent_name} 的消息为空，已跳过。", "SEND_ROBUST")
        return page.locator(LATEST_MSG_SEL_FOR_WAITING).count()

    # --- Typing Simulation Constants ---
    TYPO_PROBABILITY = session.behavioral_params['TYPO_PROBABILITY']
    PAUSE_AFTER_SPACE_PROB = 0.4 # 40% chance of a longer pause after a space
    # A simple way to get adjacent keys for typos
    KEYBOARD_ADJACENCY = {c: c for c in "abcdefghijklmnopqrstuvwxyz1234567890"} # Default to self
    # Imperfect but good enough for simulation
    for row in ["qwertyuiop", "asdfghjkl", "zxcvbnm"]:
        for i, char in enumerate(row):
            neighbors = []
            if i > 0: neighbors.append(row[i-1])
            if i < len(row) - 1: neighbors.append(row[i+1])
            KEYBOARD_ADJACENCY[char] = session.rng.choice(neighbors)

    log("INFO", f"向 {agent_name} 发送消息 (长度: {len(message)})...", "SEND_ROBUST")
    
    try:
        session.task_lock = True # --- ACQUIRE TASK LOCK ---
        log("INFO", "Task Lock Acquired.", "L4_LOCK")
        page.bring_to_front()
        
        count_before = page.locator(LATEST_MSG_SEL_FOR_WAITING).count()
        log("INFO", f"发送前检测到气泡数: {count_before}", "SEND_ROBUST")

        input_box = page.locator(INPUT_SEL)
        send_button_locator = page.locator(SEND_BUTTON_SEL)
        
        # 步骤1: 模拟人类打字行为 (增强模式)
        input_box.click()
        log("INFO", "开始模拟打字 (增强模式)...", "SEND_ROBUST")
        for char in message:
            # Typo simulation
            if char.lower() in KEYBOARD_ADJACENCY and session.rng.random() < TYPO_PROBABILITY:
                log("INFO", "Injecting typo...", "INPUT_ILLUSION")
                typo_char = KEYBOARD_ADJACENCY[char.lower()]
                input_box.type(typo_char, delay=session.rng.uniform(60, 160))
                page.wait_for_timeout(session.rng.uniform(100, 300)) # "Realization" pause
                input_box.press("Backspace")
                page.wait_for_timeout(session.rng.uniform(80, 220))

            # Type the correct character
            input_box.type(char, delay=session.rng.uniform(50, 150))

            # Pause simulation
            if char == ' ' and session.rng.random() < PAUSE_AFTER_SPACE_PROB:
                page.wait_for_timeout(session.rng.uniform(150, 400)) # Longer pause between some words

        log("INFO", "内容已输入。", "SEND_ROBUST")
        
        # 步骤2: 模拟人类反应延迟
        page.wait_for_timeout(session.rng.uniform(300, 700))

        # 步骤3: 模拟鼠标移动到按钮上
        _move_mouse_human_like(page, send_button_locator, session)
        send_button_locator.hover()
        log("INFO", "鼠标已悬停在发送按钮上。", "SEND_ROBUST")
        page.wait_for_timeout(session.rng.uniform(100, 300))

        # 步骤4: 点击按钮
        send_button_locator.click()

        # 步骤5: 使用终极裁决进行等待
        _wait_for_new_message_bubble(page, count_before, Config.Timeouts.SEND_ROBUST_WAIT_MS, agent_name)
        log("SUCCESS", "浏览器裁决：新气泡已生成！发送成功。", "SEND_ROBUST")

        new_len = page.locator(LATEST_MSG_SEL).count()
        return new_len

    except Exception as e:
        log("FATAL", f"向 {agent_name} 发送消息时发生致命错误: {e}", "SEND_ROBUST")
        raise
    finally:
        session.task_lock = False # --- RELEASE TASK LOCK ---
        log("INFO", "Task Lock Released.", "L4_LOCK")

def get_latest_message_safe(page: Page, agent_name: str, session: Session) -> tuple[str, int]:
    """核心提取函数：等待AI生成完毕，然后提取内容。"""
    log("INFO", f"等待 {agent_name} 生成内容...", "GET_SAFE")
    try:
        expect(page.locator(DONE_STATUS_SEL)).to_be_hidden(timeout=Config.Timeouts.AI_GENERATION_MS)
        log("SUCCESS", f"{agent_name} 已完成生成。", "GET_SAFE")
    except PlaywrightTimeoutError:
        log("WARNING", f"{agent_name} 生成时间超过 {Config.Timeouts.AI_GENERATION_MS/1000}s，强制提取内容。", "GET_SAFE")

    try:
        last_message_container = page.locator(LATEST_MSG_SEL).last
        
        if last_message_container.locator(RESPONSE_CONTENT_SEL).count() > 0:
            text_locator = last_message_container.locator(RESPONSE_CONTENT_SEL)
        else:
            text_locator = last_message_container

        expect(text_locator).to_be_visible(timeout=Config.Timeouts.RESPONSE_VISIBILITY_MS)
        message_text = text_locator.inner_text().strip()
        new_len = page.locator(LATEST_MSG_SEL).count()
        
        log("SUCCESS", f"成功提取 {agent_name} 的消息。新历史记录数: {new_len}", "GET_SAFE")
        return message_text, new_len
        
    except Exception as e:
        log("FATAL", f"无法从 {agent_name} 提取最新消息: {e}", "GET_SAFE")
        raise

def _perform_idle_wander(page: Page, session: Session):
    """(Internal Helper) Simulates random 'wandering' mouse movement during idle time."""
    log("INFO", "Performing idle 'Wander' behavior...", "IDLE_BEHAVIOR")
    viewport_size = page.viewport_size
    if not viewport_size:
        log("WARNING", "Could not get viewport size for idle wander.", "IDLE_BEHAVIOR")
        return

    # Create a dummy locator for a random point on the screen
    random_x = session.rng.uniform(0, viewport_size['width'])
    random_y = session.rng.uniform(0, viewport_size['height'])
    
    # This is a bit of a hack, but it allows us to reuse the move logic
    # We create a temporary, invisible element to move to.
    page.evaluate(f"() => {{ const el = document.createElement('div'); el.id = 'idle-target'; el.style.position = 'absolute'; el.style.left = '{random_x}px'; el.style.top = '{random_y}px'; document.body.appendChild(el); }}")
    target_locator = page.locator("#idle-target")
    _move_mouse_human_like(page, target_locator, session)
    page.evaluate("() => { document.getElementById('idle-target')?.remove(); }")

def _perform_idle_nudge(page: Page, session: Session):
    """(Internal Helper) Simulates small, random scrolling behavior."""
    log("INFO", "Performing idle 'Nudge' behavior...", "IDLE_BEHAVIOR")
    scroll_amount = session.rng.randint(50, 200)
    page.mouse.wheel(0, scroll_amount)
    page.wait_for_timeout(session.rng.uniform(100, 400))
    # Simulate the small, counter-directional scroll-back
    if session.rng.random() < 0.5:
        counter_scroll = session.rng.randint(-30, -10)
        page.mouse.wheel(0, counter_scroll)

def _perform_idle_distract(page: Page, session: Session):
    """(Internal Helper) Simulates user being distracted by another tab."""
    log("INFO", "Performing idle 'Distract' behavior...", "IDLE_BEHAVIOR")
    other_tab = page.context.pages[0] if page.context.pages[1] == page else page.context.pages[1]
    other_tab.bring_to_front()
    page.wait_for_timeout(session.rng.uniform(1500, 5000)) # "Distraction" time
    page.bring_to_front() # Return focus

def wait_for_response_loop(page: Page, current_len: int, agent_name: str, session: Session) -> int:
    """核心等待函数 v2.0 (IBM): 循环检查新消息，并在间隙中执行空闲行为。"""
    log("INFO", f"等待 {agent_name} 回复 (当前轮数: {current_len}, 超时: {Config.Timeouts.RESPONSE_LOOP_SEC}s)...", "WAIT_LOOP")
    start_time = time.time()
    while time.time() - start_time < Config.Timeouts.RESPONSE_LOOP_SEC:
        if page.locator(LATEST_MSG_SEL).count() > current_len:
            log("SUCCESS", "检测到新消息！AI已回复。", "WAIT_LOOP")
            return page.locator(LATEST_MSG_SEL).count()
        
        # --- L4 Task Lock Check ---
        if not session.task_lock:
            # Use persona-driven idle trigger probability
            if session.rng.random() < session.behavioral_params['P_IDLE_TRIGGER']:
                idle_actions = [
                    (_perform_idle_wander, 0.6), # Most common
                    (_perform_idle_nudge, 0.25),
                    (_perform_idle_distract, 0.15) # Least common
                ]
                action_func, _ = session.rng.choices(idle_actions, weights=[w for _, w in idle_actions], k=1)[0]
                action_func(page, session)
        
        page.wait_for_timeout(2000) # Check every 2 seconds

    raise PlaywrightTimeoutError(f"等待 {agent_name} 回复超时 ({Config.Timeouts.RESPONSE_LOOP_SEC}s)。")

# =======================================================================================
# === III. 阶段二：主编排逻辑 (Phase Two: Main Orchestration Logic) ===
# =======================================================================================

def _humanize_prompt(message: str, session: Session) -> str:
    """(L3) Adversarial Prompt Engineering: Injects human-like noise into the prompt."""
    log("INFO", "Humanizing prompt for L3 APE...", "L3_APE")
    
    persona_name = session.persona_name
    rng = session.rng
    
    # Define persona-specific linguistic "noise"
    noise_patterns = {
        'new_user': {
            'prefixes': [("请问，", 0.2), ("那个...我想知道...", 0.15), ("不好意思，能不能告诉我...", 0.2)],
            'suffixes': [("...是这样吗？", 0.1), ("...可以吗？", 0.1)]
        },
        'experienced_user': {
            'corrections': [("哦不对，我的意思是...", 0.15), ("等等，我换个问法...", 0.1)],
            'prefixes': [],
            'suffixes': []
        }
    }
    
    patterns = noise_patterns.get(persona_name, {})
    
    # Apply a correction phrase (replaces the whole message for simulation)
    if 'corrections' in patterns and patterns['corrections'] and rng.random() < patterns['corrections'][0][1]:
        return f"{rng.choice(patterns['corrections'])[0]} {message}"
        
    # Or, apply prefixes/suffixes
    if 'prefixes' in patterns and patterns['prefixes'] and rng.random() < patterns['prefixes'][0][1]:
        message = f"{rng.choice(patterns['prefixes'])[0]}{message}"

    if 'suffixes' in patterns and patterns['suffixes'] and rng.random() < patterns['suffixes'][0][1]:
        message = f"{message}{rng.choice(patterns['suffixes'])[0]}"

    return message

def run_orchestrator(page_A: Page, page_B: Page, initial_session: Session):
    """主程序入口 v2.0 (L4 Resilience): 包含错误处理和“理论销毁/人类重试”循环。"""
    log("INFO", "=== 自动化流程正式开始 ===", "MAIN")
    
    session = initial_session
    error_count = 0
    MAX_ERRORS = 3

    while True: # The outermost loop for retries after "Theoretical Destruction"
        try:
            # --- Scene Handler & State Sync ---
            page_A.bring_to_front()
            len_A = page_A.locator(LATEST_MSG_SEL_FOR_WAITING).count()
            if len_A == 0:
                log("INFO", "场景1: A页面空白。发送启动指令...", "SCENE_HANDLER")
                len_A = send_message_robust(page_A, START_CMD_MSG, "Agent A", session)
                len_A = wait_for_response_loop(page_A, len_A, "Agent A", session)
            elif len_A > 0 and len_A % 2 != 0:
                log("INFO", "场景2: 用户已提问，等待A的回复...", "SCENE_HANDLER")
                len_A = wait_for_response_loop(page_A, len_A, "Agent A", session)

            log("INFO", "状态同步完成。进入主协作循环。", "SCENE_HANDLER")

            # --- Core Collaboration Cycle ---
            while True:
                log("INFO", "--- 开始新一轮协作 ---", "CYCLE")
                message_A, _ = get_latest_message_safe(page_A, "Agent A", session)
                if TERMINATION_PHRASE in message_A:
                    handle_termination(message_A, session)
                
                # --- L3 APE Injection ---
                humanized_message = _humanize_prompt(message_A, session)
                
                count_B_after_send = send_message_robust(page_B, humanized_message, "Agent B", session)
                wait_for_response_loop(page_B, count_B_after_send, "Agent B", session)

                message_B, _ = get_latest_message_safe(page_B, "Agent B", session)
                count_A_after_send = send_message_robust(page_A, message_B, "Agent A", session)
                wait_for_response_loop(page_A, count_A_after_send, "Agent A", session)
                
                error_count = 0 # Reset error count after a successful cycle
                log("SUCCESS", "--- 本轮协作完成 ---", "CYCLE")

        except Exception as e:
            error_count += 1
            log("ERROR", f"协作循环中发生错误 (第 {error_count}/{MAX_ERRORS} 次): {e}", "L4_RECOVERY")
            if error_count >= MAX_ERRORS:
                log("CRITICAL", "错误次数达到阈值！触发“理论销毁”...", "L4_RECOVERY")
                # --- Human Retry State ---
                frustration_wait_s = session.rng.uniform(15, 45)
                log("INFO", f"模拟人类沮丧，暂停 {frustration_wait_s:.1f} 秒...", "L4_RECOVERY")
                time.sleep(frustration_wait_s)

                # --- Complete Identity Reset ---
                log("CRITICAL", "重置身份！生成新的会话种子...", "L4_RECOVERY")
                session = Session(seed=int(time.time()))
                error_count = 0
                log("SUCCESS", "Agent 已重生。使用新身份重试任务。", "L4_RECOVERY")

# =======================================================================================
# === IV. 阶段三：程序入口与浏览器设置 (Phase Three: Entry Point & Browser Setup) ===
# =======================================================================================
if __name__ == '__main__':
    try:
        if not os.path.exists(Config.EDGE_USER_DATA_PATH):
            raise FileNotFoundError(f"Edge 用户数据目录不存在: {Config.EDGE_USER_DATA_PATH}")
        
        # Initialize the session with a seed. In a real-world scenario, this might be dynamically generated and persisted.
        session = Session(seed=int(time.time()))
        
        with sync_playwright() as p:
            log("INFO", "启动 Edge 浏览器 (使用您的个人配置)...", "SETUP")
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
            
            log("SUCCESS", "双 Agent 页面已加载。", "SETUP")
            page_A.bring_to_front()

            log("WARNING", f"您有 {Config.Timeouts.MANUAL_SETUP_SEC} 秒时间进行手动设置。", "MANUAL_SETUP")
            log("WARNING", "请在 Agent A (第一个标签页) 中输入您的初始任务。", "MANUAL_SETUP")
            
            for i in range(Config.Timeouts.MANUAL_SETUP_SEC, 0, -10):
                log("INFO", f"剩余时间: {i} 秒...", "MANUAL_SETUP")
                time.sleep(10)

            run_orchestrator(page_A=page_A, page_B=page_B, initial_session=session)

    except FileNotFoundError as e:
        log("FATAL", str(e), "SETUP_ERROR")
    except Exception as e:
        log("FATAL", f"脚本因未知错误而终止: {e}", "RUNTIME_ERROR")
    finally:
        log("INFO", "脚本执行结束。", "SHUTDOWN")
        input("按 Enter 键关闭浏览器...")
