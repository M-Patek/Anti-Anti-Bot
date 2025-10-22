"""
核心动作库 (core_actions.py)

职责:
- 封装所有与浏览器交互的 "原子" 操作 (如点击、输入、等待)。
- 封装会话状态 (Session) 管理。
- 提供统一的日志记录 (log) 功能。
- 不关心业务逻辑，只负责 "如何执行"。
"""

import time
import sys
import random as global_random
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, expect, Locator

# 从其他模块导入依赖
import config # 导入配置

# =======================================================================================
# I. 日志与会话管理 (Log & Session)
# =======================================================================================

def log(level: str, message: str, step: str = "协调器"):
    """统一的日志输出函数"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}][{level:<7}][{step:<15}] {message}")

class Session:
    """封装会话状态和人格化参数。"""
    def __init__(self, seed: int):
        self.session_seed = seed
        self.rng = global_random.Random(seed)
        self.task_lock = False
        # 定义不同的人格化行为参数
        personas = {
            'new_user': {'P_IDLE_TRIGGER': 0.30},
            'experienced_user': {'P_IDLE_TRIGGER': 0.15}
        }
        self.persona_name = self.rng.choice(list(personas.keys()))
        self.behavioral_params = personas[self.persona_name]
        log("INFO", f"会话已初始化，种子: {self.session_seed}", "会话")
        log("INFO", f"L1人格已分配: '{self.persona_name}'", "L1人格")

# =======================================================================================
# II. 页面等待函数 (Wait Functions)
# =======================================================================================

def wait_for_page_stability(page: Page, agent_name: str):
    """等待页面加载稳定，确保输入框可交互。"""
    log("INFO", f"等待 {agent_name} 页面稳定 (超时 {config.Config.Timeouts.PAGE_STABILITY_MS//1000}s)...", "页面等待")
    try:
        # 核心检查: 等待输入框变为可编辑状态
        expect(page.locator(config.INPUT_SEL)).to_be_editable(timeout=config.Config.Timeouts.PAGE_STABILITY_MS)
        log("SUCCESS", f"{agent_name} 页面已稳定，输入框可交互。", "页面等待")
    except PlaywrightTimeoutError:
        log("FATAL", f"{agent_name} 页面稳定失败，未找到可交互的输入框。", "页面等待")
        raise Exception("页面初始化失败，无法继续。")

def wait_for_initial_change(page: Page, previous_html: str, previous_anchor_count: int) -> bool:
    """
    等待初步的页面变化 (DOM脉冲 或 锚点增加)。
    这是一个非阻塞性的快速检查。
    """
    log("INFO", f"等待初步响应...", "初步响应确认")
    js_wait_expression = """
        (args) => {
            const [selector, prevLength, prevCount, anchorSelector] = args;
            const container = document.querySelector(selector);
            if (!container) return false;
            const currentLength = container.innerHTML.length;
            const currentCount = document.querySelectorAll(anchorSelector).length;
            // 混合感知：DOM脉冲 或 锚点增加 (只要有一个变化就立刻返回)
            return currentLength !== prevLength || currentCount > prevCount;
        }
    """
    try:
        page.wait_for_function(
            js_wait_expression,
            arg=[config.CHAT_AREA_SEL, len(previous_html), previous_anchor_count, config.MESSAGE_ANCHOR_SEL],
            timeout=30000 # 等待初步响应的时间可以短一些
        )
        log("SUCCESS", f"检测到初步响应！", "初步响应确认")
        return True # 表示检测到变化
    except PlaywrightTimeoutError:
        log("WARNING", f"等待初步响应超时。", "初步响应确认")
        return False # 表示未检测到变化

def wait_for_ai_response(page: Page, agent_name: str, previous_html: str, previous_anchor_count: int):
    """
    (v9.2) 升级后的AI响应等待函数，兼容Pro模式。
    执行四重确认：初步响应 -> 检测思考动画 -> 等待动画消失 -> 等待内容稳定。
    """
    log("INFO", f"开始等待 {agent_name} 的AI响应 (Pro模式兼容)...", "AI响应感知")
    
    # 第一重确认：等待任何形式的响应（思考动画或直接答案）
    if not wait_for_initial_change(page, previous_html, previous_anchor_count):
        # 如果连初步响应都没有，可能出错了
        log("ERROR", "未检测到初步响应，AI可能未回复。")
        raise Exception(f"{agent_name} 未在指定时间内响应。")

    log("INFO", f"检测到初步响应，开始第二重确认...", "AI响应感知")

    # 第二重确认：检查是否存在“思考中”动画 (更鲁棒的方式)
    thinking_indicators = page.locator(config.THINKING_INDICATOR_SEL)
    fallback_indicators = page.locator(config.FALLBACK_THINKING_SEL)

    # 优先使用精确的定位器
    indicators_to_wait_for = thinking_indicators if thinking_indicators.count() > 0 else fallback_indicators

    # 第三重确认：等待所有“思考中”动画消失
    if indicators_to_wait_for.count() > 0:
        log("INFO", f"检测到 {indicators_to_wait_for.count()} 个“思考/加载中”指示器，等待其完成...", "AI响应感知")
        try:
            # 遍历所有找到的指示器，等待它们全部消失
            for i in range(indicators_to_wait_for.count()):
                 expect(indicators_to_wait_for.nth(i)).to_be_hidden(timeout=config.Config.Timeouts.AI_GENERATION_MS)
            log("SUCCESS", f"所有“思考/加载中”指示器已结束。", "AI响应感知")
        except PlaywrightTimeoutError:
            log("WARNING", f"等待部分“思考/加载中”指示器消失超时，可能已出结果。", "AI响应感知")
        except Exception as e:
            # 捕获可能的 StaleElementReferenceError 等错误
             log("WARNING", f"等待指示器消失时遇到错误: {e}，继续执行。", "AI响应感知")
    
    # 第四重确认：进入稳定观察期，确保所有文本都已输出
    log("INFO", f"进入最终内容稳定观察期...", "AI响应感知")
    last_len = 0
    try:
        current_len = page.locator(config.CHAT_AREA_SEL).evaluate("el => el.innerHTML.length")
        page.wait_for_timeout(500) # 初始延迟
        current_len = page.locator(config.CHAT_AREA_SEL).evaluate("el => el.innerHTML.length")
    except Exception as e:
        log("WARNING", f"在稳定期检查时页面元素失效: {e}，假定已稳定。", "AI响应感知")
        return # 页面可能已跳转或重载，直接返回

    stability_start_time = time.time()
    while last_len != current_len:
        last_len = current_len
        page.wait_for_timeout(config.Config.Timeouts.CONTENT_STABILITY_MS)
        try:
            current_len = page.locator(config.CHAT_AREA_SEL).evaluate("el => el.innerHTML.length")
        except Exception as e:
            log("WARNING", f"在稳定期检查时页面元素失效: {e}，强制认为已稳定。", "AI响应感知")
            break # 页面可能已跳转或重载，跳出循环
        
        # 增加一个总的稳定观察期超时，防止无限等待
        if time.time() - stability_start_time > config.Config.Timeouts.WAIT_FOR_CHANGE_MS:
             log("WARNING", "稳定观察期超时，强制认为内容已稳定。")
             break
    
    log("SUCCESS", f"内容已稳定，{agent_name} 已完成完整输出。", "AI响应感知")

# =======================================================================================
# III. 模拟人类行为函数 (Human-like Actions)
# =======================================================================================

def _calculate_bezier_point(t: float, p0: dict, p1: dict, p2: dict) -> dict:
    """计算贝塞尔曲线上的点"""
    u = 1 - t
    tt = t * t
    uu = u * u
    x = (uu * p0['x']) + (2 * u * t * p1['x']) + (tt * p2['x'])
    y = (uu * p0['y']) + (2 * u * t * p1['y']) + (tt * p2['y'])
    return {'x': x, 'y': y}

def _move_mouse_human_like(page: Page, target_locator: Locator, session: Session):
    """模拟类人的贝塞尔曲线鼠标移动"""
    log("INFO", "模拟类人鼠标移动...", "鼠标移动")
    try:
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
    except Exception as e:
        log("WARNING", f"类人鼠标移动失败: {e}", "鼠标移动")
        # 即使失败，也继续尝试点击，不阻塞主流程

# =======================================================================================
# IV. 核心交互函数 (Core IO)
# =======================================================================================

def handle_termination(final_message: str):
    """处理终止信号"""
    log("SUCCESS", "检测到终止信号。任务完成。", "任务终止")
    log("INFO", f"Agent A 的最终交付内容:\n---\n{final_message}\n---", "任务终止")
    # 在工程化结构中，我们不在此处退出，而是让主循环自然结束
    # sys.exit(0) 

def send_message_robust(page: Page, message: str, agent_name: str, session: Session):
    """
    (v9.2) 鲁棒的消息发送函数。
    负责填充、模拟鼠标移动、点击，并等待用户消息上屏。
    """
    if not message or not message.strip():
        log("WARNING", f"尝试向 {agent_name} 发送空消息，已跳过。", "发送消息")
        return
        
    log("INFO", f"向 {agent_name} 发送消息 (长度: {len(message)})...", "发送消息")
    try:
        session.task_lock = True
        log("INFO", "已获取任务锁。", "L4锁")
        page.bring_to_front()
        
        # 拍摄快照，用于后续对比
        snapshot_html = page.locator(config.CHAT_AREA_SEL).evaluate("el => el.innerHTML")
        snapshot_count = page.locator(config.MESSAGE_ANCHOR_SEL).count()
        log("INFO", f"发送前快照(DOM长度: {len(snapshot_html)}, 锚点数: {snapshot_count})", "发送消息")

        input_box = page.locator(config.INPUT_SEL)
        send_button_locator = page.locator(config.SEND_BUTTON_SEL)
        
        # 动作分离
        input_box.fill(message)
        log("INFO", "消息内容已填充。", "发送消息")
        page.wait_for_timeout(session.rng.uniform(300, 700))
        
        _move_mouse_human_like(page, send_button_locator, session)
        send_button_locator.hover()
        page.wait_for_timeout(session.rng.uniform(100, 300))
        send_button_locator.click()

        # 【LOGIC SEPARATION】只等待用户自己的消息上屏，然后立刻返回
        wait_for_initial_change(page, snapshot_html, snapshot_count)
        log("SUCCESS", "用户发送的消息已确认上屏！", "发送消息")

    except Exception as e:
        log("FATAL", f"向 {agent_name} 发送消息时发生严重错误: {e}", "发送消息")
        raise # 抛出异常，由编排器 (orchestrator) 捕获
    finally:
        session.task_lock = False
        log("INFO", "任务锁已释放。", "L4锁")


def get_latest_message_safe(page: Page, agent_name: str) -> str:
    """
    (v9.2) “次元切割”高权限提取脚本。
    使用 JS 优先提取最后一条消息的 Markdown 内容，并清除噪音。
    """
    log("INFO", f"为 {agent_name} 执行“次元切割”高权限提取脚本...", "提取消息")
    try:
        js_get_last_message_script = f"""
            () => {{
                const allMessages = document.querySelectorAll('{config.MESSAGE_ANCHOR_SEL}');
                if (allMessages.length === 0) return '';
                for (let i = allMessages.length - 1; i >= 0; i--) {{
                    const messageContainer = allMessages[i];
                    // 创建克隆以避免修改实时DOM
                    const clone = messageContainer.cloneNode(true);
                    // 移除页脚、菜单按钮和思考指示器等噪音
                    clone.querySelectorAll('.response-container-footer, [class*="menu-button"], [class*="thoughts"], [class*="generating"], .bard-avatar.thinking').forEach(el => el.remove());
                    
                    // 优先提取 markdown 内容
                    const markdownEl = clone.querySelector('[class*="markdown"]');
                    if (markdownEl && markdownEl.innerText.trim()) {{
                        return markdownEl.innerText.trim();
                    }}
                    // 备用方案：提取清理后的整个容器文本
                    const fullText = clone.innerText;
                    if (fullText && fullText.trim()) {{
                        return fullText.trim();
                    }}
                }}
                return '';
            }}
        """
        message_text = page.evaluate(js_get_last_message_script)

        # JS 提取失败的备用方案 (Fallback)
        if not message_text:
            log("WARNING", "高权限提取脚本未能找到任何有效消息内容。使用备用方案...", "提取消息")
            last_container = page.locator(config.MESSAGE_ANCHOR_SEL).last
            if last_container.count() > 0:
                full_text = last_container.inner_text().strip()
                # 再次尝试清除噪音
                buttons_text = ["复制", "修改回复", "分享和导出", "赞", "踩", "更多选项"]
                for btn_txt in buttons_text:
                    full_text = full_text.replace(btn_txt, "")
                message_text = full_text.strip()

        log("SUCCESS", f"成功从 {agent_name} 提取到消息 (长度: {len(message_text)})", "提取消息")
        return message_text

    except Exception as e:
        log("FATAL", f"无法从 {agent_name} 提取最新消息: {e}", "提取消息")
        raise # 抛出异常，由编排器 (orchestrator) 捕获
