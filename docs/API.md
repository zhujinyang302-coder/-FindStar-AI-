# API 规格（寻物星图 FindStar）

基础路径：`/api/v1`（健康探测除外）。所有接口返回统一响应结构。

## 统一响应

成功：

```json
{ "code": 0, "message": "success", "data": { }, "request_id": "..." }
```

失败：

```json
{ "code": "VALIDATION_ERROR", "message": "请检查输入字段", "details": [ ], "request_id": "..." }
```

错误响应不包含 SQL、堆栈、密钥或内部网络地址。`request_id` 用于追踪。

## 鉴权

除公开接口外均需 `Authorization: Bearer <access_token>`。
私有接口的用户标识一律从登录身份推导，不信任前端传入的操作者 ID。

## 端点清单

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/auth/login` | 公开 | 登录，返回 access_token 与用户信息 |
| GET | `/items` | 公开 | 分页检索（type/category/keyword/status/page/page_size ≤ 50） |
| GET | `/items/{id}` | 公开 | 记录详情（`type=lost\|found` 可选，自动探测） |
| POST | `/lost-items` | 登录 | 发布寻物记录 |
| POST | `/found-items` | 登录 | 发布拾获记录 |
| PATCH | `/items/{type}/{id}` | 所有者/管理员 | 编辑记录 |
| POST | `/uploads` | 登录 | 上传图片，返回 object_key（服务端生成文件名） |
| GET | `/images/{object_key}` | 公开 | 受控图片代理访问 |
| GET | `/stats/overview` | 公开 | 首页基础统计 |
| POST | `/ai/extract-features` | 登录 + 限流 | 提取结构化物品特征（可编辑） |
| POST | `/matches` | 记录所有者 | 发起匹配，返回批次与候选（Top 3） |
| GET | `/matches/{id}` | 发起者/管理员 | 匹配详情（含同批次候选、分项、解释、差异点） |
| POST | `/claims` | 登录 | 提交认领申请（幂等） |
| GET | `/claims/me` | 登录 | 本人认领申请列表 |
| GET | `/admin/claims` | 管理员 | 待审核申请列表 |
| GET | `/admin/claims/{id}` | 管理员 | 审核详情（含私密核验信息） |
| PATCH | `/admin/claims/{id}` | 管理员 | 通过 / 拒绝认领（写审计日志） |
| POST | `/admin/items/{type}/{id}/remove` | 管理员 | 下架违规记录 |
| GET | `/admin/statistics` | 管理员 | 运营统计 |
| GET | `/health/live` | 公开 | 存活探测 |
| GET | `/health/ready` | 公开 | 就绪探测（检查 DB / 缓存） |

## 匹配分项口径

综合分数基线：

```
S = 0.35·S_text + 0.25·S_image + 0.20·S_location + 0.15·S_time + 0.05·S_attribute
```

- 分项归一化到 0–1，最终分数显示为 0–100；
- 视觉项不可用时替换为结构化视觉特征一致性并标记 `available=false`，权重重新归一化；
- 地点 / 时间未知返回中性分 0.5；品牌未知不扣分；类别冲突显著降分；
- 排序只用后端计算的分数，不使用模型自报分数；
- 全部候选低于阈值时返回“暂未找到可靠候选”。

## 状态机

```
active → claimed | resolved | closed | rejected
claimed → resolved | closed
resolved → closed
rejected → active | closed
closed  → (终态)
```

非法转换返回 409（`ILLEGAL_STATE_TRANSITION`）。