# 寻物星图 FindStar — AI 智能失物招领系统

# 求各位大佬对本项目拷打，目前只是一个demo

寻物星图（FindStar）是一个响应式 Web 应用（用户端 + 管理端），用于校园失物招领：
用户发布寻物 / 拾获记录，系统通过多模态 AI 提取物品特征，并结合文本语义、图片、地点、
时间与结构化属性进行跨描述候选匹配，配套认领申请与审核闭环。

> 重要说明：匹配分数由后端算法计算，仅用于推荐候选，**不代表物品归属或找回概率**；
> AI 输出只用于推荐与解释，绝不作为归属判定依据。

## 功能一览（对应需求 FR-001 ~ FR-017）

- 首页与导航：产品入口、最新公开记录、基础统计，含加载 / 空 / 错误状态（FR-001）
- 记录检索与筛选：分页、类别、关键词、类型与状态过滤，筛选条件同步 URL（FR-002）
- 发布寻物 / 拾获记录：字段校验、允许无图、AI 识别可编辑、防重复提交（FR-003 / FR-004）
- 图片上传：JPG/PNG/WebP，单张 ≤ 5 MB，最多 5 张，MIME + 文件签名校验，拒绝可执行文件（FR-005）
- AI 特征提取：AIProvider 抽象（OpenAI 兼容 + 本地降级），输出经 Schema 校验（FR-006）
- 智能匹配：候选来自数据库另一侧有效记录，后端评分、Top 3、阈值、解释与持久化（FR-007）
- 匹配结果页：分项依据、差异点、认领入口，区分算法分数与真实结果（FR-008）
- 记录详情与编辑：公开字段白名单，仅所有者可编辑（FR-009）
- 认领申请：幂等、私密核验信息保护、本人申请可查（FR-010）
- 管理员审核：通过 / 拒绝、二次确认、审计留痕、状态联动（FR-011）
- 状态管理：active/claimed/resolved/closed/rejected 状态机（FR-012）
- Redis 缓存：热点列表与匹配结果缓存、失效、降级（FR-013）
- 运营统计：记录总量 / 有效量 / 匹配请求量 / 认领量 / 完成量（FR-014）
- 统一错误与提示：统一响应结构、请求追踪标识、不泄露堆栈与密钥（FR-015）
- 部署与文档：README、环境变量示例、迁移脚本、许可证、Demo 说明（FR-016 / FR-017）

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Vite + TypeScript + Element Plus + Vue Router + Pinia + axios |
| 后端 | Python 3.11+、FastAPI、Pydantic v2、SQLAlchemy 2.x、Alembic |
| 数据库 | 开发 SQLite；生产 华为云 RDS for MySQL（通过 DATABASE_URL 切换） |
| 缓存 | Redis 兼容服务（未配置时自动降级为进程内内存缓存） |
| AI | 后端 AIProvider 适配层，OpenAI 兼容协议；未配置密钥时本地降级并明确标注 |

## 目录结构

```
寻物星图/
├─ backend/                 # FastAPI 后端
│  ├─ app/
│  │  ├─ api/v1/            # 路由（auth/items/ai/matches/claims/admin/health）
│  │  ├─ core/              # 配置、日志、统一响应与异常、安全、中间件
│  │  ├─ db/                # 连接、模型、枚举
│  │  ├─ schemas/           # Pydantic 请求/响应
│  │  ├─ services/          # 业务服务（记录/匹配/认领/统计/审计/状态机/图片）
│  │  ├─ ai/                # AIProvider、匹配评分算法、文本相似度
│  │  ├─ cache/             # Redis 封装与降级
│  │  └─ main.py
│  ├─ alembic/              # 数据库迁移
│  ├─ tests/                # 单元测试
│  ├─ requirements.txt
│  └─ Dockerfile
├─ frontend/                # Vue 3 前端
│  ├─ src/
│  │  ├─ api/  components/  layouts/  pages/  router/  stores/  types/  utils/
│  │  └─ main.ts
│  ├─ package.json
│  ├─ nginx.conf
│  └─ Dockerfile
├─ infra/docker-compose.yml # 本地开发编排（可选）
├─ scripts/                 # init_db.py / seed_demo_data.py
├─ docs/                    # API、部署、测试、演示文档
├─ .env.example
├─ LICENSE
└─ README.md
```

## 快速开始（本地开发）

### 1. 后端

```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows
pip install -r requirements.txt

cp ../.env.example ../.env      # 按需填写；开发环境可直接使用默认值

python ../scripts/init_db.py            # 显式执行数据库迁移
python ../scripts/seed_demo_data.py     # 写入演示数据（可重复执行）

uvicorn app.main:app --reload --port 8000
```

- 健康检查：`GET http://localhost:8000/health/live`
- 接口文档：`http://localhost:8000/docs`

### 2. 前端

```bash
cd frontend
npm install
npm run dev      # 默认 http://localhost:5173，已配置代理到后端 8000
```

演示账号（仅开发环境，正式环境请通过环境变量配置）：
- 管理员：`admin@findstar.demo` / `DemoAdmin@2026`
- 普通用户：`alice@findstar.demo` / `User@2026`、`bob@findstar.demo` / `User@2026`

## 环境变量

见根目录 `.env.example`。要点：
- `DATABASE_URL` 切换数据库（SQLite / MySQL）；
- `REDIS_URL` 为空时自动降级为内存缓存；
- `AI_PROVIDER=openai_compatible` 且配置 `AI_API_BASE/AI_API_KEY/AI_MODEL_NAME` 时调用真实模型，
  否则使用本地降级适配器，并在页面明确标注降级状态；
- 所有密钥/密码只能通过环境变量注入，禁止提交仓库。

## 测试

```bash
cd backend
pytest            # 核心逻辑单元测试：字段校验、状态转换、评分算法
```

## Docker（可选）

```bash
docker compose -f infra/docker-compose.yml up --build
# 前端 http://localhost:8080 ，后端 http://localhost:8000
```

## 安全与隐私

- 后端鉴权（JWT）+ 管理员 RBAC；私有接口的用户标识从登录身份推导；
- 密码仅存 bcrypt 哈希；公开接口使用字段白名单；
- 私密核验信息仅授权审核者可见，不进入公开响应与普通日志；
- 上传校验 MIME、文件签名、大小与数量，文件名由服务端生成；
- 统一错误响应不包含堆栈、SQL、密钥或内部地址，并携带 `request_id`。

## 已知限制与降级说明

- 未配置真实模型时，AI 能力处于降级状态，页面会明确提示，绝不伪装成功；
- 未配置图像向量能力时，视觉项降级为结构化视觉特征一致性，并在分项中标记为“不可用”；
- 未配置 Redis 时使用进程内缓存，仅用于加速；业务数据始终以数据库为唯一事实来源；
- 首版不做原生 App、统一身份认证、支付、物流、实时地图导航与归属自动判定。

## 许可证

本项目采用 MIT 许可证，详见 [LICENSE](./LICENSE)。
