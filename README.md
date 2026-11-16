# Research-data-collection

SEAL 層（ADAE / AIMLE）資料收集效率的最小驗證實驗（MVE）工作目錄。

- 研究背景：[~/Design-doc/Data_collection_research.md](../Design-doc/Data_collection_research.md)
- 實驗規劃書：[~/Design-doc/Data_collection_MVE_plan.md](../Design-doc/Data_collection_MVE_plan.md)

## 開始任何工作之前，依序讀

1. [PROGRESS.md](PROGRESS.md)：目前做到哪裡、還有哪些未解決的問題
2. [EXECUTION_GUIDE.md](EXECUTION_GUIDE.md)：執行規則、停止條件、各階段的必讀文件與起始指令
3. 規劃書中目前階段的章節
4. [PREREGISTRATION.md](PREREGISTRATION.md)：P2 之後的實驗設計與判準（P2 開始前必須經使用者核准）

## 目錄結構

| 路徑 | 內容 | 建立於 |
|---|---|---|
| `README.md`、`EXECUTION_GUIDE.md`、`PREREGISTRATION.md`、`PROGRESS.md` | 說明、規則、預先登記、進度紀錄 | 已建立 |
| `backup/<日期>/` | 修改 testbed 前的設定檔與資料庫備份 | P0 |
| `scripts/` | testbed 端腳本：訂閱者批次建立、流量排程產生、trace 匯出、量測 | P0–P2 |
| `cost/` | P1 的量測原始資料與成本模型參數 | P1 |
| `traces/` | P2 的 ground-truth trace（parquet，體積大） | P2 |
| `sim/` | A-DCCF 模擬器：`cost_model.py`、`producers.py`、`policies/`、`consumers/`、`metrics.py`、`run_grid.py` | P3 |
| `results/` | 結果表、Pareto 圖、regret 曲線 | P4 |

## GitHub repo 不包含的內容

這個目錄同步到 private repo [hokusai0603/A-DCCF-related-experiment](https://github.com/hokusai0603/A-DCCF-related-experiment)。下列內容只保存在 testbed 主機上（見 `.gitignore`）：

| 路徑 | 原因 |
|---|---|
| `backup/` | 其他 repo 設定檔的複本與 MongoDB dump |
| `newstack/bin/` 的執行檔 | 實驗室 go-upf fork 編出的 UPF；來源 commit 與 sha256 記在 `newstack/bin/PROVENANCE.txt` |
| `results/cache/`、`__pycache__/` | 可以用 `python3 -m sim.run_grid --out results` 重新產生 |
