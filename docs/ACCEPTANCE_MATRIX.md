# 交付验收覆盖矩阵（V3 双向匹配）

对应需求基线：`.codeartsdoer/specs/bidirectional_match/spec.md` 的 FR-301 ~ FR-312。

| 需求 | 落地能力 | 测试证据 |
|---|---|---|
| FR-301 信息隔离与可见性总则 | 8×6 可见性矩阵、禁用对侧全量读取与全局检索、旧入口 410 | `tests/test_visibility_policy.py`、`tests/test_legacy_routes.py` |
| FR-302 上传与发布 | 照片/文字二选一、信息量校验、上传告知、发布即待审、幂等 | `tests/test_integration_flow.py`、`tests/test_migration_script.py` |
| FR-303 双向匹配与候选生成 | 硬约束 → 语义召回 → 后端评分 → 阈值/配额、批次幂等 | `tests/test_recall_service.py`、`tests/test_scoring.py`、`tests/test_concurrency.py` |
| FR-304 候选披露与隐私分级 | 三套白名单 DTO、脱敏与模糊化、缩略图访问策略 | `tests/test_dto_isolation.py`、`tests/test_disclosure_policy.py`、`tests/test_security.py` |
| FR-305 候选内筛选与解释 | 批次内筛选、固定排序口径、解释独立失败域 | `tests/test_integration_flow.py`、`tests/test_scoring.py` |
| FR-306 双向联系、认领与归还闭环 | 申请提交/幂等/冷却、发布者确认 CAS、状态联动 | `tests/test_integration_flow.py`、`tests/test_concurrency.py` |
| FR-307 匹配结果生命周期 | 过期、失效、归档、清理、读取二次校验 | `tests/test_lifecycle.py` |
| FR-308 访问控制与反滥用 | 频控权威计数、异常检测、防遍历、管理员隔离 | `tests/test_rate_limit.py`、`tests/test_security.py`、`tests/test_concurrency.py` |
| FR-309 管理员审核衔接 | 仅上下架审核、自审禁止、重复决定冲突、审核历史 | `tests/test_review_service.py`、`tests/test_review_history.py` |
| FR-310 通知 | 10 类事件 outbox、脱敏正文、已读幂等、投递重试 | `tests/test_notification_service.py`、`tests/test_notification_events.py` |
| FR-311 存量迁移与旧入口下线 | 幂等迁移、六条一致性断言、7 天回滚手册 | `tests/test_migration_script.py`、`docs/MIGRATION.md` |
| FR-312 匹配质量评估与运营反馈 | 六项指标、配置版本留痕、离线评估与抽检脚本 | `tests/test_quality.py`、`tests/test_evaluate_script.py` |

## 验证命令

```bash
cd backend && python -m pytest
cd frontend && npm run typecheck
cd frontend && npx vite build
cd backend && python -m alembic upgrade head
cd .. && python scripts/migrate_bidirectional_match.py --dry-run
```

## 已知边界

- 预匹配（tasks 4.8，P1）默认关闭，当前仅保留配置开关，未启用待审预匹配。
- 沙箱环境下 FastAPI `TestClient` 的 socketpair 受限，自动化集成测试使用服务层路径；HTTP 冒烟验证在非 pytest 进程执行通过。