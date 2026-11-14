# 部署文档（寻物星图 FindStar）

## 1. 环境要求

- Python 3.11+（开发环境实测 3.13）
- Node.js 18+（推荐 20）
- 可选：MySQL 8 / Redis 7 / Docker

## 2. 本地开发部署

### 2.1 后端

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate ；Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp ../.env.example ../.env
python ../scripts/init_db.py
python ../scripts/seed_demo_data.py
uvicorn app.main:app --reload --port 8000
```

### 2.2 前端

```bash
cd frontend
npm install
npm run dev
```

## 3. 容器化部署（本地）

```bash
docker compose -f infra/docker-compose.yml up --build
```

- 前端：http://localhost:8080
- 后端：http://localhost:8000
- 默认 `AI_PROVIDER=mock`（未接入真实模型，页面会显示降级状态）

## 4. 生产部署要点（华为云）

> 以下为部署指引；实际资源名称、地域与配额以参赛账号及组委会通知为准，
> 不得虚构云资源可用性。

1. **数据库**：开通 RDS for MySQL，设置
   `DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:3306/<db>?charset=utf8mb4`。
2. **缓存**：开通 Redis 兼容服务，设置 `REDIS_URL=redis://...`。未开通时缓存自动降级。
3. **对象存储（可选）**：如开通 OBS，可扩展 `image_service` 为 OBS 适配器；未开通时使用受控本地存储，
   生产环境请勿依赖临时容器文件系统。
4. **模型 API**：设置 `AI_PROVIDER=openai_compatible` 与
   `AI_API_BASE`、`AI_API_KEY`、`AI_MODEL_NAME`；密钥只注入后端环境，不进入前端构建。
5. **应用配置**：
   - `APP_ENV=production`
   - `APP_SECRET_KEY` 使用随机值（生产环境会校验，示例值将被拒绝）
   - `CORS_ORIGINS` 设置为前端明确域名
6. **迁移**：部署后执行 `python scripts/init_db.py`（Alembic 迁移），
   不要依赖应用启动时自动重建数据库。
7. **HTTPS**：在生产环境前置反向代理 / 负载均衡终止 TLS。
8. **可观测**：`/health/live` 用作存活探针，`/health/ready` 用作就绪探针；
   日志为结构化 JSON，含 `request_id`、接口、耗时与错误类别。

## 5. 数据迁移与初始化

- 迁移由 Alembic 管理：`alembic revision --autogenerate -m "..."` 生成，`python scripts/init_db.py` 执行升级；
- 演示数据脚本具备重复执行保护（按 email / title 去重），可安全重复运行；
- 结构变更必须提供可重复执行的迁移脚本，保证存量数据不丢失。

## 6. 仓库合规

- 不得提交 `.env`、云密钥、真实个人信息或未经授权图片（已在 `.gitignore` 中排除）；
- 提供 `.env.example`（占位符）；启动时校验必需配置，错误日志只显示变量名不显示值。