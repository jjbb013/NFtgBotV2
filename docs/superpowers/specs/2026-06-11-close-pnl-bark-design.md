# 平仓盈亏 Bark 通知设计文档

## 背景
当前 tgBotV4.py 执行平仓后，Bark 通知仅包含账户、标的、平仓方向、平仓数量等基本信息，不包含盈亏数据。用户希望在 Bark 推送中直接看到本次平仓的近似盈亏（USDT 数量及百分比）。

## 需求确认
1. 盈亏取近似值即可（使用 OKX 持仓接口返回的未实现盈亏 `upl` 和盈亏率 `uplRatio`）。
2. 若同时平掉多个持仓（如 `close_type='both'`），汇总成一个总盈亏展示。
3. 最小范围修改，仅调整 `tgBotV4.py`，不重构原有代码。
4. 在独立分支开发，完成后 commit 并 push。

## 方案（推荐：方案 A）

在 `close_okx_position()` 中，筛选出待平仓列表后、执行平仓前，读取每个持仓的：
- `upl`：未实现盈亏（USDT）
- `uplRatio`：盈亏率（OKX 通常返回小数，如 `0.05` 表示 5%）

汇总逻辑：
- `total_upl = sum(upl)`
- `pnl_pct = avg(uplRatio) * 100`（多个持仓时取平均值作为近似总盈亏率）

将 `total_upl` 和 `pnl_pct` 加入函数返回字典。

修改 `build_close_bark_content()` 签名，新增 `total_upl` 和 `pnl_pct` 参数，在 Bark 内容中追加一行：
```
盈亏: +12.3456 USDT (+2.15%)
盈亏: -3.1000 USDT (-0.85%)
```

若 OKX 返回缺少相关字段，则静默跳过盈亏行，不阻断平仓流程。

## 改动范围
仅修改 `tgBotV4.py`，不涉及 `utils.py`。

## 分支
`feature/close-pnl-notification`
