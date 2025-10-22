"""
配置中心 (config.py)

职责:
- 存放所有全局常量 (如终止短语)。
- 存放所有 Playwright CSS 选择器 (Selectors)。
- 存放所有硬编码的配置 (如URL、路径、超时时间)。
"""

import os

# =======================================================================================
# I. 全局常量
# =======================================================================================
TERMINATION_PHRASE = "TASK_COMPLETED_SUCCESSFULLY"
START_CMD_MSG = "请启动双编码协作流程并开始您的协调任务。"

# =======================================================================================
# II. CSS 选择器 (Selectors)
# =======================================================================================
# 【ULTIMATE ANTI-BOT STRATEGY v9.2: PRECISE LOCKING】
INPUT_SEL = 'div[role="textbox"]'
CHAT_AREA_SEL = 'body'
MESSAGE_ANCHOR_SEL = '.response-container'

# v9.2 策略: 优先锁定代表AI头像思考状态的元素
THINKING_INDICATOR_SEL = '.bard-avatar.thinking'
# 备用定位器
FALLBACK_THINKING_SEL = '[class*="loading"], [class*="generating"]'

SEND_BUTTON_SEL = 'button mat-icon[data-mat-icon-name="send"]'

# =======================================================================================
# III. 全局配置类
# =======================================================================================
class Config:
    """集中管理所有可配置的全局变量。"""
    
    # 路径配置
    # 注意: 原始路径是硬编码的。一个更健壮的方案是使用:
    # USER_HOME = os.path.expanduser('~')
    # EDGE_USER_DATA_PATH = os.path.join(USER_HOME, "AppData", "Local", "Microsoft", "Edge", "User Data")
    EDGE_USER_DATA_PATH = "C:\\Users\\asus\\AppData\\Local\\Microsoft\\Edge\\User Data"

    # URL 配置
    GEMINI_URL_A = "https://gemini.google.com/u/1/app?hl=zh-cn"
    GEMINI_URL_B = "https://gemini.google.com/u/3/app?hl=zh-cn"

    class Timeouts:
        """超时时间配置 (毫秒/秒)"""
        PAGE_LOAD_MS = 90000       # 页面加载
        PAGE_STABILITY_MS = 30000  # 页面稳定 (等待输入框可编辑)
        AI_GENERATION_MS = 120000  # AI生成 (等待“思考中”动画消失)
        WAIT_FOR_CHANGE_MS = 180000 # 内容稳定观察期的总超时
        CONTENT_STABILITY_MS = 1500 # 内容稳定观察期的检查间隔
        MANUAL_SETUP_SEC = 30      # 手动设置时间 (秒)

