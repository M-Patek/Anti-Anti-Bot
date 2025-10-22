"""
业务编排器 (orchestrator.py) (v9.3 - 最终集成版)

职责:
- 存放核心的业务逻辑 (双AI协作循环)。
- 负责调用 "核心动作库" 中的函数来完成业务。
- (v9.3) 接受 `start_mode` 以支持多点启动。
- (v9.3) 接受 `worker` 实例，在循环中检查停止信号。
- (v9.3) 通过 `app_context` 发出详细的状态信号。
- 负责错误处理和 "L4恢复" 逻辑。
"""

import time
from playwright.sync_api import Page

# 导入配置、核心动作、信号中心
import config
from core_actions import (
    log, Session, wait_for_page_stability, send_message_robust,
    wait_for_ai_response, get_latest_message_safe, handle_termination
)
from app_context import context

# v9.3: 用于类型提示，避免循环导入
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend_worker import BackendWorker

def run_orchestrator(
    page_A: Page, 
    page_B: Page, 
    initial_session: Session, 
    start_mode: str,
    worker: 'BackendWorker' # v9.3: 传入 worker 实例
):
    """
    运行主编排逻辑 (双AI "乒乓球" 协作循环)。
    """
    log("INFO", "=== 自动化流程正式开始 ===", "主流程")
    session = initial_session
    error_count = 0
    MAX_ERRORS = 3 # L4恢复阈值

    while True:
        try:
            # --- 阶段 0: 检查停止信号 ---
            if worker.is_stop_requested():
                log("INFO", "在主循环开始前检测到停止请求。", "主流程")
                break

            # --- 阶段 1: 握手与启动 (根据 start_mode) ---
            log_step = "场景处理"
            if start_mode == 'new':
                log("INFO", "场景1: 'New Start' 模式启动...", log_step)
                context.emit_status("场景1: 新任务启动...")
                page_A.bring_to_front()
                wait_for_page_stability(page_A, "Agent A")
                
                # 检查是否是空白启动
                if not page_A.locator(config.MESSAGE_ANCHOR_SEL).count():
                    log("INFO", "A页面空白，发送启动指令...", log_step)
                    # 1. 发送启动指令
                    send_message_robust(page_A, config.START_CMD_MSG, "Agent A", session)
                    # 2. 拍摄快照并等待A的第一次回复
                    snapshot_html = page_A.locator(config.CHAT_AREA_SEL).evaluate("el => el.innerHTML")
                    snapshot_count = page_A.locator(config.MESSAGE_ANCHOR_SEL).count()
                    wait_for_ai_response(page_A, "Agent A", snapshot_html, snapshot_count, session)
                else:
                    log("INFO", "检测到已有对话，直接进入协作循环。", log_step)

            elif start_mode == 'resume_from_a':
                log("INFO", "场景2: 'Resume from A' 模式启动。直接进入主循环。", log_step)
                context.emit_status("场景2: 从 A 恢复...")
                page_A.bring_to_front()
                wait_for_page_stability(page_A, "Agent A")

            elif start_mode == 'resume_from_b':
                log("INFO", "场景3: 'Resume from B' 模式启动。执行一次性 B->A 同步...", log_step)
                context.emit_status("场景3: 从 B 恢复...")
                # 1. 从 B 提取消息
                page_B.bring_to_front()
                wait_for_page_stability(page_B, "Agent B")
                message_B = get_latest_message_safe(page_B, "Agent B")

                # 2. 转发消息给 A
                page_A.bring_to_front()
                wait_for_page_stability(page_A, "Agent A")
                send_message_robust(page_A, message_B, "Agent A", session)
                
                # 3. 拍摄快照并等待 A 的完整回复
                snapshot_html_a = page_A.locator(config.CHAT_AREA_SEL).evaluate("el => el.innerHTML")
                snapshot_count_a = page_A.locator(config.MESSAGE_ANCHOR_SEL).count()
                wait_for_ai_response(page_A, "Agent A", snapshot_html_a, snapshot_count_a, session)

            # --- 阶段 2: 主协作循环 ---
            log_step = "协作循环"
            log("INFO", "状态同步完成。进入统一的主协作循环。", log_step)
            
            while True:
                # --- 停止检查点 1 ---
                if worker.is_stop_requested():
                    log("INFO", "在 A->B 步骤前检测到停止请求。", log_step)
                    break 

                log("INFO", "--- 开始新一轮协作 (A -> B) ---", log_step)
                context.emit_status("等待 Agent A...")

                # 1. 从 A 提取消息
                message_A = get_latest_message_safe(page_A, "Agent A")
                
                # 2. 检查终止信号
                if config.TERMINATION_PHRASE in message_A:
                    handle_termination(message_A)
                    break # 跳出内层循环
                
                # 3. 转发消息给 B
                page_B.bring_to_front()
                wait_for_page_stability(page_B, "Agent B")
                
                # v9.3: 注入思考延迟
                if session.rng.random() < session.behavioral_params['P_THINKING_DELAY']:
                    delay = session.rng.uniform(
                        session.behavioral_params['MIN_THINK_DELAY_S'],
                        session.behavioral_params['MAX_THINK_DELAY_S']
                    )
                    log("INFO", f"模拟专家思考，暂停 {delay:.1f} 秒... (转发至 B)", "思考延迟")
                    context.emit_status(f"模拟思考... ({delay:.1f}s)")
                    time.sleep(delay)

                # --- 停止检查点 2 ---
                if worker.is_stop_requested():
                    log("INFO", "在 B 响应前检测到停止请求。", log_step)
                    break
                
                context.emit_status("A -> B (发送中...)")
                # 【LOGIC SEPARATION】步骤3.1: 发送消息 (快速返回)
                send_message_robust(page_B, message_A, "Agent B", session)
                
                context.emit_status("等待 Agent B...")
                # 【LOGIC SEPARATION】步骤3.2: 拍摄快照并等待 B 的完整回复
                snapshot_html_b = page_B.locator(config.CHAT_AREA_SEL).evaluate("el => el.innerHTML")
                snapshot_count_b = page_B.locator(config.MESSAGE_ANCHOR_SEL).count()
                wait_for_ai_response(page_B, "Agent B", snapshot_html_b, snapshot_count_b, session)

                # 4. 从 B 提取消息
                message_B = get_latest_message_safe(page_B, "Agent B")

                # 5. 转发消息给 A
                page_A.bring_to_front()

                # v9.3: 注入思考延迟
                if session.rng.random() < session.behavioral_params['P_THINKING_DELAY']:
                    delay = session.rng.uniform(
                        session.behavioral_params['MIN_THINK_DELAY_S'],
                        session.behavioral_params['MAX_THINK_DELAY_S']
                    )
                    log("INFO", f"模拟专家思考，暂停 {delay:.1f} 秒... (转发至 A)", "思考延迟")
                    context.emit_status(f"模拟思考... ({delay:.1f}s)")
                    time.sleep(delay)

                # --- 停止检查点 3 ---
                if worker.is_stop_requested():
                    log("INFO", "在 A 响应前检测到停止请求。", log_step)
                    break

                context.emit_status("B -> A (发送中...)")
                # 【LOGIC SEPARATION】步骤5.1: 发送消息
                send_message_robust(page_A, message_B, "Agent A", session)
                
                context.emit_status("等待 Agent A...")
                # 【LOGIC SEPARATION】步骤5.2: 拍摄快照并等待 A 的完整回复
                snapshot_html_a = page_A.locator(config.CHAT_AREA_SEL).evaluate("el => el.innerHTML")
                snapshot_count_a = page_A.locator(config.MESSAGE_ANCHOR_SEL).count()
                wait_for_ai_response(page_A, "Agent A", snapshot_html_a, snapshot_count_a, session)
                
                # 6. 循环成功，重置错误计数器
                if error_count > 0:
                    error_count = 0
                    context.emit_error_count(error_count) # 向 GUI 更新错误计数
                    
                log("SUCCESS", "--- 本轮协作完成 ---", log_step)
            
            # 如果内层循环被 break (任务完成或停止请求)，也 break 外层循环
            break 

        except Exception as e:
            # --- 阶段 3: L4 恢复逻辑 ---
            log_step_l4 = "L4恢复"
            error_count += 1
            context.emit_error_count(error_count) # 向 GUI 更新错误计数
            log("ERROR", f"协作循环出错 (尝试 {error_count}/{MAX_ERRORS}次): {e}", log_step_l4)
            context.emit_status(f"错误 (尝试 {error_count}/{MAX_ERRORS})")
            
            if error_count >= MAX_ERRORS:
                log("CRITICAL", "错误次数达到阈值！触发“理论销毁”...", log_step_l4)
                context.emit_status("L4恢复: 重置身份")
                frustration_wait_s = session.rng.uniform(15, 45)
                log("INFO", f"模拟人类沮丧，暂停 {frustration_wait_s:.1f} 秒...", log_step_l4)
                time.sleep(frustration_wait_s)
                
                # 【关键】通过创建新的 Session 来重置身份和随机种子
                log("CRITICAL", "重置身份！生成新的会话种子...", log_step_l4)
                # Session __init__ 会自动发送新 Session ID 到 GUI
                session = Session(seed=int(time.time()))
                error_count = 0 # 重置错误计数
                context.emit_error_count(error_count) # 向 GUI 更新
                
                log("SUCCESS", "Agent已重生。使用新身份重试任务。", log_step_l4)
                # 继续下一次 while True 循环 (将从 "阶段 1: 握手与启动" 重新开始)
                # 重置 start_mode 为 'new'，因为我们正在重新启动
                start_mode = 'new'

