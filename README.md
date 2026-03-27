# LARY (Life-Agent-RU-YEE)

AI 驱动的生活管理 Agent 框架，可插拔架构。通过自然语言对话完成饮食规划、食材采购等日常任务。

## 演示

https://github.com/user/LARY/raw/main/录屏2026-03-27%20195619.mp4

> 从菜谱规划到一键加购物车的完整流程演示

## 特性

- **多 Agent 协作** — 饮食规划 Agent 与采购 Agent 自动协作，从规划菜谱到一键加购物车
- **可插拔插件系统** — Agent、Memory、Extension 均为插件，支持社区开发和热加载
- **SSE 实时流式交互** — 工具调用进度、思考状态、操作日志实时推送到前端
- **安卓设备自动化** — 通过 uiautomator2 控制安卓设备，在盒马 APP 上自动搜索和加购商品
- **用户画像** — 自动收集家庭人数、口味偏好等信息，个性化推荐菜谱
- **SkillHub 技能市场** — 在线浏览、安装、卸载社区插件（尚未开放）

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11+, FastAPI, LiteLLM, Pydantic v2, SQLAlchemy (async) |
| 前端 | Vue 3 + TypeScript, Vite, Tailwind CSS |
| 基础设施 | Docker Compose, PostgreSQL 16, Redis 7, Nginx |
| 测试 | pytest + pytest-asyncio (后端), Vitest (前端) |
| Lint | Ruff (line-length=120, target py311) |

## 项目结构

```
main.py                     # FastAPI 入口
config.yaml                 # 应用配置（插件、LLM、日志）
core/
  orchestrator.py            # 编排引擎（意图路由 → Agent 执行）
  agent_comm.py              # Agent 间通信（agent_call 工具）
  intent_router.py           # LLM 意图识别
  plugin_registry.py         # 插件发现、加载、注册
  skillhub.py                # 技能市场（索引/安装/卸载）
  database.py                # SQLAlchemy 异步引擎
  interfaces/                # 抽象基类
api/
  chat.py                    # POST /api/chat (SSE 流)
  skillhub.py                # SkillHub REST API
plugins/
  agents/
    meal_agent/              # 饮食规划 Agent
    purchasing_agent/        # 采购 Agent（盒马自动化）
  memory/
    short_term_memory/       # 对话历史（Redis + PG）
    user_profile/            # 用户画像
    delivery_address/        # 配送地址
  extensions/
    device_gateway/          # 设备网关 (WebSocket)
    automation_u2/           # uiautomator2 安卓自动化
web/src/
  views/                     # ChatView, SkillHubView, DevicesView
  components/chat/           # MessageBubble, ToolCallCard, ChatInput
  composables/useSSE.ts      # SSE 流式消息处理
```

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 18+
- PostgreSQL 16 + Redis 7（可通过 Docker 启动）

### 1. 克隆仓库

```bash
git clone https://github.com/user/LARY.git
cd LARY
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 LLM API Key（至少一个）
```

支持的 LLM 提供商：
- **火山引擎**（默认）：`VOLCENGINE_API_KEY`
- **OpenAI**：`OPENAI_API_KEY`
- **Anthropic**：`ANTHROPIC_API_KEY`
- 未配置任何 Key 时自动使用 Ollama 本地模型

### 3. 启动基础设施

```bash
docker compose up -d postgres redis
```

### 4. 安装并启动后端

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python main.py
```

后端运行在 `http://localhost:8000`

### 5. 安装并启动前端

```bash
cd web
npm install
npm run dev
```

前端运行在 `http://localhost:5173`，API 请求自动代理到后端。

### Docker 一键部署

```bash
cp .env.example .env
# 编辑 .env，填入 API Key 和数据库密码
docker compose up --build -d
```

访问 `http://localhost`（可通过 `.env` 中 `NGINX_PORT` 修改端口）

#### 开发模式

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
docker compose up --build -d
```

开发模式额外提供：源码热更新（volume 挂载）、数据库/Redis 端口暴露、USB 设备透传。

#### 自定义 IP 白名单

编辑 `nginx-allow.conf` 添加或移除允许访问的 IP 段，修改后重启 nginx 即可生效，无需重新构建镜像：

```bash
docker compose restart nginx
```

#### 安卓设备连接（采购功能）

采购 Agent 通过 uiautomator2 控制安卓设备操作盒马 APP：

1. 将安卓设备通过 USB 连接到服务器，开启 USB 调试模式
2. 启用开发模式（`docker-compose.override.yml`），其中已配置 USB 设备透传
3. 如需通过网络连接设备，在 `config.yaml` 中配置：

```yaml
plugins:
  automation_u2:
    device_addr: "192.168.1.100:5555"  # 安卓设备 IP
```

## 运行测试

### 后端测试

```bash
source .venv/bin/activate
python -m pytest tests/ -v --tb=short
```

### 前端测试

```bash
cd web
npx vitest run
```

### Lint 检查

```bash
ruff check .
```

## 配置说明

| 文件 | 用途 |
|------|------|
| `.env` | 环境变量（API Key、数据库密码等），**不提交到 git** |
| `config.yaml` | 应用配置（启用的插件、LLM 模型、参数），Docker 部署时通过 volume 挂载 |
| `nginx-allow.conf` | Nginx IP 白名单，修改后 `docker compose restart nginx` 即可生效 |
| `.env.example` | 环境变量模板 |
| `docker-compose.override.yml.example` | 开发模式模板（USB 透传、端口暴露、源码挂载） |

## License

[MIT](LICENSE)
