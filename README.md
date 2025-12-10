# Anti-Anti-Bot

### 🛡️ 项目概述 (Project Overview)

**Anti-Anti-Bot** 是一个先进、高鲁棒性的 AI 代理（Agent）协作与编排框架，旨在通过模拟人类行为和复杂的流程控制，实现多个大型语言语言模型（LLM）的自动化协作。

该项目包含一个基于 PySide6 的图形用户界面（GUI）应用 **Gemini Station**，以及一套旨在规避自动化检测机制（Anti-Anti-Bot）的核心动作库，确保在浏览器环境中的自动化任务能够稳定、高效地运行。

### ✨ 核心特性 (Key Features)

* **多Agent协作模式**：支持 Planner/Coder/QA 任务执行循环，以及 Auditor/Vigilance 代码审查流程。

* **图形化控制面板 (v9.3)**：基于 PySide6 实现，提供实时日志、状态更新、错误计数和会话管理，支持“新任务”和“从 Agent A/B 恢复”等多种启动模式。

* **高级反检测机制 (v9.2/v9.3)**：

  * **行为模拟 (L1 人格)**：模拟人类的贝塞尔曲线鼠标移动、随机微操作（如滚动）和专家“思考延迟”。

  * **鲁棒 I/O (L2/L4 恢复)**：包含消息发送 L2 恢复机制和 L4 致命错误（如达到错误阈值）的身份（Session）重置恢复机制。

  * **Playwright 隐身补丁**：通过注入 JavaScript 移除 `WebDriver` 标志和自动化控制横幅。

* **模块化架构**：使用 `app_context.py` 作为全局信号中心，实现前端 GUI 和后端自动化逻辑的完全解耦。

### 🤖 协作 Agent 角色定义

| 角色 (Agent) | 职责 (Role) | 关键输出信号 |
| :--- | :--- | :--- |
| **Planner** | 任务分发器，管理任务列表，按顺序分发子任务。 | `PLAN_CREATED`, `TASK_COMPLETED_SUCCESSFULLY` |
| **Coder** | 代码实现者，执行任务，编写或修改代码，并响应 QA 的反馈。 | 局部代码块/Diff, `PATCH_ACCEPT` |
| **QA** | 质量保证工程师，对照任务蓝图审查 Coder 的代码。 | `PATCH_ACCEPT`, `PATCH_REJECT` |
| **Auditor** | 全域领航员，负责代码审查流程的宏观导航和文件覆盖率（DFS 策略）。 | `NAVIGATOR_KICKOFF`, `TASK_FOR_VIGILANCE` |
| **Vigilance** | 性能与安全验证专家，根据 Auditor 的任务进行深度代码缺陷分析。 | `VIGILANCE_REPORT` |

### 🛠️ 技术栈与依赖 (Tech Stack & Dependencies)

该项目主要使用 Python 编写，依赖于以下库：

| 库 | 用途 |
| :--- | :--- |
| `playwright` | 核心浏览器自动化引擎，负责所有 I/O 操作。 |
| `PySide6` | 用于构建跨平台 GUI 的 Qt 绑定。 |

您可以使用以下命令安装所需的依赖：

```bash
pip install -r requirements.txt
```

### ⚙️ 架构概览 (Architecture Overview)

项目采用清晰的分层架构，以保证鲁棒性和可维护性：

- **前端 GUI (`main.py`)**：负责显示，运行在主线程，避免阻塞。
- 
- **后端工作器 (`backend_worker.py`)**：继承自 `QObject`，在单独的 `QThread` 中运行，负责启动 Playwright 实例和浏览器会话。
- 
- **核心编排 (`orchestrator.py`)**：包含 Agent 协作的业务逻辑、状态机和 L4 恢复机制。
- 
- **核心动作库 (`core_actions.py`)**：包含所有低级、高鲁棒性的浏览器交互函数（如发送消息、等待响应）和反检测逻辑（如 L1 人格、L2 恢复）。
- 
- **配置与通信 (`config.py`, `app_context.py`)**：存放全局配置、CSS 选择器和信号中心。
