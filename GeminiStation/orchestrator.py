"""
业务编排器 (orchestrator.py)

职责:
- 存放核心的业务逻辑 (双AI协作循环)。
- 负责调用 "核心动作库" 中的函数来完成业务。
- 负责错误处理和 "L4恢复" 逻辑。
- 只关心 "做什么" (What)，不关心 "怎么做" (How)。
"""

import time
from playwright.sync_api import Page

# 导入配置和核心动作
import config
from core_actions import (
    log, Session, wait_for_page_stability, send_message_robust,
    wait_for_ai_response, get_latest_message_safe, handle_termination
)

def run_orchestrator(page_A: Page, page_B: Page, initial_session: Session):
    """
    运行主编排逻辑 (双AI "乒乓球" 协作循环)。
    """
    log("INFO", "=== 自动化流程正式开始 ===", "主流程")
    session = initial_session
    error_count = 0
    MAX_ERRORS = 3 # L4恢复阈值

    while True:
        try:
            # --- 阶段 1: 握手与启动 ---
            page_A.bring_to_front()
            wait_for_page_stability(page_A, "Agent A")
            
            # 检查是否是空白启动
            if not page_A.locator(config.MESSAGE_ANCHOR_SEL).count():
                log("INFO", "场景1: A页面空白，发送启动指令...", "场景处理")
                # 1. 发送启动指令
                send_message_robust(page_A, config.START_CMD_MSG, "Agent A", session)
                # 2. 拍摄快照并等待A的第一次回复
                snapshot_html = page_A.locator(config.CHAT_AREA_SEL).evaluate("el => el.innerHTML")
                snapshot_count = page_A.locator(config.MESSAGE_ANCHOR_SEL).count()
                wait_for_ai_response(page_A, "Agent A", snapshot_html, snapshot_count)
            else:
                log("INFO", "场景2: 检测到已有对话，直接进入协作循环。", "场景处理")

            # --- 阶段 2: 主协作循环 ---
            log("INFO", "状态同步完成。进入主协作循环。", "场景处理")
            
            while True:
                log("INFO", "--- 开始新一轮协作 ---", "协作循环")

                # 1. 从 A 提取消息
                message_A = get_latest_message_safe(page_A, "Agent A")
                
                # 2. 检查终止信号
                if config.TERMINATION_PHRASE in message_A:
                    handle_termination(message_A)
                    break # 跳出内层循环
                
                # 3. 转发消息给 B
                page_B.bring_to_front()
                wait_for_page_stability(page_B, "Agent B")
                
                # 【LOGIC SEPARATION】步骤3.1: 发送消息 (快速返回)
                send_message_robust(page_B, message_A, "Agent B", session)
                
                # 【LOGIC SEPARATION】步骤3.2: 拍摄快照并等待 B 的完整回复
                snapshot_html_b = page_B.locator(config.CHAT_AREA_SEL).evaluate("el => el.innerHTML")
                snapshot_count_b = page_B.locator(config.MESSAGE_ANCHOR_SEL).count()
                wait_for_ai_response(page_B, "Agent B", snapshot_html_b, snapshot_count_b)

                # 4. 从 B 提取消息
                message_B = get_latest_message_safe(page_B, "Agent B")

                # 5. 转发消息给 A
                page_A.bring_to_front()
                
                # 【LOGIC SEPARATION】步骤5.1: 发送消息
                send_message_robust(page_A, message_B, "Agent A", session)
                
                # 【LOGIC SEPARATION】步骤5.2: 拍摄快照并等待 A 的完整回复
                snapshot_html_a = page_A.locator(config.CHAT_AREA_SEL).evaluate("el => el.innerHTML")
                snapshot_count_a = page_A.locator(config.MESSAGE_ANCHOR_SEL).count()
                wait_for_ai_response(page_A, "Agent A", snapshot_html_a, snapshot_count_a)
                
                # 6. 循环成功，重置错误计数器
                error_count = 0
                log("SUCCESS", "--- 本轮协作完成 ---", "协作循环")
            
            # 如果内层循环被 break (任务完成)，也 break 外层循环
            break 

        except Exception as e:
            # --- 阶段 3: L4 恢复逻辑 ---
            error_count += 1
            log("ERROR", f"协作循环出错 (尝试 {error_count}/{MAX_ERRORS}次): {e}", "L4恢复")
            
            if error_count >= MAX_ERRORS:
                log("CRITICAL", "错误次数达到阈值！触发“理论销毁”...", "L4恢复")
                frustration_wait_s = session.rng.uniform(15, 45)
                log("INFO", f"模拟人类沮丧，暂停 {frustration_wait_s:.1f} 秒...", "L4恢复")
                time.sleep(frustration_wait_s)
                
                # 【关键】通过创建新的 Session 来重置身份和随机种子
                log("CRITICAL", "重置身份！生成新的会话种子...", "L4恢复")
                session = Session(seed=int(time.time()))
                error_count = 0 # 重置错误计数
                
                log("SUCCESS", "Agent已重生。使用新身份重试任务。", "L4恢复")
                # 继续下一次 while True 循环 (将从 "阶段 1: 握手与启动" 重新开始)
