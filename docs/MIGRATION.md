# 存量迁移与回滚操作手册（V1 → V3 双向匹配）

本手册对应 `.codeartsdoer/specs/bidirectional_match/tasks.md` 任务 13，用于把 V1 存量数据迁移到 V3 双向匹配结构。

## 1. 前置条件

1. 已完成数据库备份（生产使用云数据库快照或 `mysqldump`）。
2. 已停止旧版写入流量，旧认领接口已由 `app/api/v1/legacy.py` 返回 410。
3. 已确认 `0002_admin_review_schema` 与 `0003_bidirectional_match_schema` 迁移脚本随发布包一同部署。
4. 迁移脚本不随应用启动自动执行，必须由发布流程显式调用。

## 2. 迁移步骤

```bash
# 1) 升级结构
cd backend
alembic upgrade head

# 2) 迁移演练（零写入）
cd ..
python scripts/migrate_bidirectional_match.py --dry-run

# 3) 正式迁移（按批次提交，可续跑）
python scripts/migrate_bidirectional_match.py --batch-size 200

# 4) 仅迁移记录状态、不生成批次（特殊情况）
python scripts/migrate_bidirectional_match.py --skip-batches
```

迁移脚本特性：

- 幂等：重复执行不会新增或覆盖已迁移数据。
- 每批独立事务，可中断后重跑。
- 支持 `--from-id` 从指定记录开始续跑。
- 输出迁移前后计数、批次号、差异清单与抽样核对结果。
- 差异非零时以非零退出码终止，禁止继续上线。

## 3. 六条一致性断言

1. 每条候选都必须关联存在的批次（`batch_fk` 非空且批次存在）。
2. 记录的 `info_sufficient` 与实际图片/描述信息量一致。
3. `pending` 申请必须持有 `active_lock_key`，且不得为自申请。
4. 不存在 `visibility_scope='public'` 的记录。
5. 迁移前后可匹配记录数一致。
6. 不存在遗留的旧 `review_status` / 非法八态取值。

## 4. 回滚方案（7 天窗口）

迁移脚本记录 `migrated_at`。超过 7 天后拒绝自动回滚，需走备份恢复流程。

```bash
# 路径 A：结构回退（空库或已确认业务数据可丢弃时）
cd backend
alembic downgrade 0001_initial

# 路径 B：备份恢复（推荐）
# 使用迁移前快照恢复数据库，再按旧版本应用启动
```

回滚演练要求：在测试库恢复到迁移前状态，并核对业务数据未丢失。

## 5. 存量用户规则变更告知

迁移批次号记录在发布报告中。存量用户首次登录后展示一次“可见性规则变更 + 新使用路径”说明：

- 不再提供全部失物/拾获记录浏览与全局检索。
- 发布记录先进入待上架审核，审核通过后自动匹配。
- 认领与归还由对侧记录发布者确认，管理员仅审核上下架。

后端通过 `users.migration_notice_seen` 标记已告知，同一用户只展示一次。