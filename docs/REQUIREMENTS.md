# 需求说明与追踪（寻物星图 FindStar）

## 1. 权威来源

- 原始需求规格说明书：`寻物星图_详细开发需求文档_V1.0.docx`（已提取为 `_req.txt`）。
- 需求规格（Spec，回答“做什么”）：`.codeartsdoer/specs/findstar/spec.md`。

本仓库的代码实现严格对齐上述两份文档，未擅自删除需求或虚构云资源能力。

## 2. 需求条目与实现映射

| 编号 | 需求条目 | 优先级 | 里程碑 | 主要实现位置 |
|---|---|---|---|---|
| FR-001 | 首页与导航 | P0 | M2 | `frontend/src/pages/HomePage.vue` |
| FR-002 | 物品列表（检索与筛选） | P0 | M2 | `ItemsPage.vue`、`api/v1/items.py` |
| FR-003 | 发布寻物记录 | P0 | M2 | `PublishPage.vue`、`services/item_service.py` |
| FR-004 | 发布拾获记录 | P0 | M2 | 同上 |
| FR-005 | 图片上传与校验 | P0 | M2 | `services/image_service.py`、`api/v1/items.py` |
| FR-006 | AI 特征提取 | P0 | M3 | `ai/provider.py`、`api/v1/ai.py` |
| FR-007 | 智能匹配 | P0 | M4 | `ai/matching.py`、`services/match_service.py` |
| FR-008 | 匹配结果页 | P0 | M4 | `MatchResultPage.vue` |
| FR-009 | 记录详情与编辑 | P0 | M2 | `ItemDetailPage.vue`、`api/v1/items.py` |
| FR-010 | 认领申请 | P0 | M5 | `services/claim_service.py`、`api/v1/claims.py` |
| FR-011 | 管理员审核 | P1 | M5 | `api/v1/admin.py`、`pages/admin/AdminPage.vue` |
| FR-012 | 状态管理 | P0 | M2–M5 | `services/state_machine.py` |
| FR-013 | 数据缓存能力 | P0 | M6 | `cache/redis_cache.py` |
| FR-014 | 运营统计 | P1 | M5 | `services/stats_service.py` |
| FR-015 | 错误与提示 | P0 | M1–M5 | `core/response.py`、`core/middleware.py` |
| FR-016 | 开源与部署文档 | P0 | M7 | `README.md`、`docs/`、`LICENSE` |
| FR-017 | 开发过程记录 | P0 | M7 | 见 `.codeartsdoer/` 与提交历史 |
| — | 用户账号与访问控制 | P0 | M1–M5 | `core/security.py`、`api/deps.py` |

## 3. 关键设计决策

1. 匹配分数由后端算法计算（基线权重见 `docs/API.md`），模型只提供特征与解释草稿；
2. 候选来自数据库另一侧有效记录，禁止模型凭空生成；
3. 视觉项在无向量能力时降级为结构化视觉特征一致性，并标记不可用与重新归一化权重；
4. 状态变更统一经状态机校验并在事务中执行，同步写入审计日志；
5. 密钥只从环境变量读取；未配置真实 AI 时明确标注降级，不伪装成功；
6. 业务数据以数据库为唯一事实来源，缓存仅加速且可降级。

## 4. 里程碑

M1 可运行骨架 → M2 业务 CRUD → M3 AI 最小链路 → M4 匹配闭环 →
M5 认领与管理 → M6 云服务完善 → M7 比赛交付。当前代码覆盖 M1–M6 主体能力。