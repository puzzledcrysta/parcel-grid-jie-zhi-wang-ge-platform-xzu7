# 界址网格台业务与测试登记

- 规模：中型
- 使用者：自然资源所界址复核员
- 核心规则：按矩形坐标切格，最高级有效权证唯一时归属，同级异主面积冻结，重复覆盖只计一次。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 权证采信 | 检查编码、字段宽度和来源行 | `POST /api/intake` | `app/modules/intake/service.py` | `tests/test_intake.py` |
| M2 测绘字段 | 归一修订、业务键和偏移时间 | `POST /api/contract` | `app/modules/contract/service.py` | `tests/test_contract.py` |
| M3 异常权证 | 定位重复、被替代与矛盾来源 | `POST /api/quality` | `app/modules/quality/versions.py` | `tests/test_quality.py` |
| M4 冲突测面 | 按规则复算并追溯证据 | `POST /api/domain` | `app/modules/domain/rule.py` | `tests/test_domain.py` |
| M5 地籍清单 | 核对独立清单和各类差异 | `POST /api/reconcile` | `app/modules/reconcile/service.py` | `tests/test_reconcile.py` |
| M6 测面批次 | 打开历史批次并对原文件复跑 | `POST /api/runs` | `app/modules/runs/service.py` | `tests/test_runs.py` |
| M7 界址复核 | 登记复核结论并下载证据 | `POST /api/review/{run_id}` | `app/modules/review/decisions.py` | `tests/test_review.py` |
| M8 批次对账 | 新旧批次并排对账、逐地块补注并拦截解释不清的确认 | `POST /api/compare` | `app/modules/compare/service.py` | `tests/test_compare.py`, `tests/test_compare_gating.py` |

## 陷阱登记

| TRAP | 现象 | 样例 | 处理位置 | 测试 |
|---|---|---|---|---|
| TRAP-01 | GB18030 来源文件 | legacy.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_gb18030` |
| TRAP-02 | BOM 前缀 | shift.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_bom` |
| TRAP-03 | 备注含引号内换行 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_multiline` |
| TRAP-04 | 分段重复表头 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_repeated` |
| TRAP-05 | 列数不足 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_width` |
| TRAP-07 | 缺测哨兵 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_missing` |
| TRAP-08 | 前导零的单号 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_leading_zero` |
| TRAP-11 | 偏移时刻 UTC 归一 | shift.csv | `app/modules/domain/values.py` | `tests/test_contract.py::test_offsets` |
| TRAP-14 | 同版业务字段冲突 | shift.csv | `app/modules/quality/versions.py` | `tests/test_quality.py::test_conflicting` |
| TRAP-16 | 末行引号截断 | truncated.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_truncated_rejected` |
| TRAP-17 | 旧版列名映射 | legacy.csv | `app/modules/contract/schema.py` | `tests/test_contract.py::test_legacy_aliased` |
| TRAP-18 | 空文件、空白文件与仅表头 | 测试构造 | `app/modules/intake/service.py` | `tests/test_intake.py::test_empty_states` |
| TRAP-26 | 陈旧复核版本拒绝 | 测试构造 | `app/modules/review/decisions.py` | `tests/test_review.py::test_stale` |
| TRAP-23 | exact touch | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_exact_touch` |
| TRAP-19 | shared and covered | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_shared_and_covered` |
| TRAP-27 | 可确认面积碰巧相同但争议冻结/外账已变，不能记为无变化 | 测试构造 | `app/modules/compare/service.py` | `tests/test_compare.py::test_equal_final_area_still_flagged_when_dispute_or_book_changes` |
| TRAP-28 | 解释不清的地块不能确认新批 | 测试构造 | `app/modules/review/decisions.py` | `tests/test_compare_gating.py::test_unexplained_parcel_blocks_confirmation_until_note` |
| TRAP-29 | 同一对批次重跑不新增核对批次 | 测试构造 | `app/modules/compare/repository.py` | `tests/test_compare.py::test_same_inputs_do_not_create_new_comparison_batch` |
| TRAP-30 | 切换失败后旧批与原确认依据仍可打开 | 测试构造 | `app/modules/runs/repository.py`, `app/modules/review/decisions.py` | `tests/test_compare_gating.py::test_switch_failure_keeps_old_batch_and_review_evidence` |

## 对账

输入 = 计入 + 隔离 + 重传及版本替换 + 空白记录 + 重复表头。按业务键全外连接，缺失一侧与数值为零分别登记。逐笔差值与总差一致。

批次对账按业务键全外连接两个批次，逐地块并排呈现采信修订、可确认面积、争议冻结、外部账记录值和外账差异的旧值→新值。任一维度变化或地块状态变化（新增、退出、隔离、重传）均不得写成无变化。隔离码与重传原因码、地块仍在测面且几何未变时的外部账单边更新可自动解释；无痕迹的纯几何变化、修订变化与地块进退场须复核员逐笔补注，否则新批的「确认」会被服务端以 `REVIEW_UNEXPLAINED` 拒绝，「退回」不受拦截。对账批次指纹由规则版本与两个批次 ID 派生，`INSERT OR IGNORE` 保证重跑同一对批次只产生一条记录；对账只读 `runs` 与 `reviews`，切换失败不会覆盖旧批结果、原输入或既有复核时间线。
