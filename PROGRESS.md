# 進度紀錄

最新的紀錄放在最上面。每個 session 結束前新增一筆。

## 目前狀態

| 階段 | 狀態 |
|---|---|
| 規劃 | 完成（2026-11-10） |
| PREREGISTRATION | **已核准（2026-11-11，hokusai0603）**。5.1 成本模型、5.4 敏感度分析已依 P1 結果與使用者決定改寫；之後只能在第 7 節加修訂 |
| P0 UE 擴充與驗收 | **完成（2026-11-10）**：46 UE，4.5 #1–#4 全部通過（1 秒）。前提：使用修正版 UPF/SMF/NWDAF（`scripts/newstack.sh`，使用者核准的 c 方案） |
| P1 成本模型量測 | **完成（2026-11-10）**：12 格全部完整；模型 `bytes = k·(a0+b·N) + max(0,k−2)·c_conn + [P≥30s]·min(k,2)·c_ka` 對 12 格預測誤差 ≤ ±0.18%（`cost/README.md`）。P3 用的成本模型 4 項決定已完成（2026-11-11，`cost/sim_params.json`） |
| P2 trace 收集 | **完成（2026-11-11）**：4 情境 × seed 1/2/3 共 12 輪，全部第一次就通過 2.3 品質規則（0 缺漏、0 重複、UPF/iperf3 總量 1.00000–1.00036）。trace 與格式說明在 `traces/`（`traces/README.md`、`traces/summary.csv`） |
| P3 模擬器 | **完成（2026-11-11）**：`sim/`，38 個單元測試通過，seed 1 smoke run 端到端跑通、獨立驗算 60/60 一致。★ 解讀已由使用者確認全部照預設（2026-11-12，PREREGISTRATION 第 7 節） |
| P4 分析 | **完成（2026-11-12）**：12 輪 288 task 完成、獨立驗算 60/60 一致。H1 成立（每個情境 98.6%）、H2 成立（只靠 T2 的 32.6%，來自 S1）、B3 檢查不滿足（ε = 5%）、H3 成立；依規劃書第 7 節是「題目成立」。報告：`results/REPORT.md` |
| P5 整理 | **完成（2026-11-12）**：REPORT 的結果整理成 motivation 結果，回填 `~/Design-doc/Data_collection_research.md` 6.3.2 節（判斷表、Pareto 圖、regret 表與曲線、REPORT 第 6 節的 8 項不利組合、限制、探索性說明）。`~/Design-doc` 沒有 commit／push |

## 尚未解決的【待確認】項目

| # | 項目 | 在哪一階段驗證 | 結論 |
|---|---|---|---|
| 1 | v4.1.0 webconsole 能否用 REST API 批次建立訂閱者（路徑、body、是否支援自動遞增 SUPI） | P0 | **可以，有但書**。`POST /api/login` → token（header `Token`）；`POST /api/subscriber/{imsi}/{plmn}/{userNumber}` 有自動遞增 SUPI，但不會遞增 GPSI，`userNumber>1` 會在第 2 筆回 `duplicate gpsi`，所以改成每筆 POST 一次（`scripts/provision_subscribers.py`）。VM 內沒有 Go 也沒有前端 build，改用主機上的 webconsole v1.4.5（VM 是 v1.4.2）連同一個 MongoDB；產生的文件和既有 UE 逐欄比對一致 |
| 2 | `ulcl: false` 時，`uerouting.yaml` 的 `members` 是否影響選路 | P0 | **不影響**。試跑的 101、201 在 `uerouting.yaml` 尚未加入時（SMF 06:43 啟動、06:57 才修改）就由正確的 UPF 建立 PDU session 並 ping 通 MEC/MEC2。之後仍把 40 個 SUPI 加進 members 保持一致 |
| 3 | `samplingInterval = 1` 秒時，每個 UE 的通知間隔是否穩定 | P0 | **舊版 UPF 不行；修正版可以**。舊 UPF（May 13）的週期性 URR 報告用量永遠是 0，用量只來自 1 kB 門檻觸發的報告（約 3 秒一次，還會丟資料），改設定無法修正。換成修正版 UPF（682b469）＋SMF＋NWDAF 後，1 秒：600/600 筆、間隔 0.914–1.092 秒、每個視窗都有值、封包守恆 0.9997–1.0000、0 drop。見下方第二筆 P0 紀錄 |
| 4 | go-upf fork 的 `parquetDir` 能否直接輸出 trace | P2 之前 | **不能**。`parquetDir` 是 *輸入*：部署中的 UPF（May 13 build）有 EES PseudoDriver，目錄存在時會在每個新訂閱把 `training_packets_run001.parquet`（約 90 分鐘）當成正常通知重播給 IP 為 10.10.0.1–3 / 10.100.0.1–3 的 UE。已依使用者決定在 `UPF-EES*.yaml` 指向不存在的目錄停用。trace 需從 MongoDB `nwdaf.upfTrafficData` 匯出 |
| 5 | 各 VM 的時間同步誤差是否遠小於 1 秒 | P0 | **原本不符合，已修正**。開機時 5GC −398 ms、gNB −1229 ms、gNB2 −984 ms、MEC −1141 ms、MEC2 −1480 ms（NTP 沒開）；依使用者決定在 VM 內啟用 systemd-timesyncd（runtime，`scripts/testbed.sh ntp`）後 7 台都在主機 ±13 ms 內（量測誤差上限約 ±12 ms）。每次開機都要重跑 |

---

## 紀錄格式

```
### YYYY-MM-DD｜階段｜一句話總結
- 完成：
- 驗收結果：
- 修改的檔案（備份位置）：
- 【待確認】項目的結論：
- 遇到的問題與處理：
- 下一步：
```

---

### 2026-11-12｜P5｜motivation 結果回填到 Data_collection_research.md 6.3 節

- 完成：
  - 依規劃書 P5，把 `results/REPORT.md` 整理成約 2 頁的 motivation 結果，寫在 `~/Design-doc/Data_collection_research.md` 新增的 **6.3.2 節**。
  - 原本 6.3 的表格內容不變，只加上小標題「6.3.1 完整研究的評估規劃」。其他章節（包括 0 摘要、6.1 結論）都沒有改。
  - 6.3.2 的內容：
    - 實驗設定摘要；
    - 依預先登記判準的判斷表（REPORT 第 1 節，主分析與敏感度分析並列）與 go/no-go 結論；
    - H1 的量；
    - Pareto 總覽圖；
    - regret 表（ε = 1/2/5/10/20%，靜態 B2 與 B3，主分析與敏感度分析並列）與 regret 對 ε 曲線；
    - REPORT 第 6 節的 **8 項不利組合全部列出**；
    - 限制（REPORT 第 8 節）；
    - 探索性說明，只有 REPORT 本身標為探索性的「regret 上限 33.3%」一項。
- 驗收結果：
  - 判斷只引用 REPORT 依 PREREGISTRATION 得出的結論，數字逐項對照 REPORT 與 `results/tables/regret.csv`。
  - 沒有新增 REPORT 以外的解讀或延伸結論。
- 修改的檔案（備份位置）：
  - `~/Design-doc/Data_collection_research.md`：修改前的版本備份在 `backup/2026-11-12/p5-research-doc/Design-doc/`，差異在同目錄的 `changes.diff`。
  - 新增 `~/Design-doc/figures/data_collection_mve/pareto_all.png`、`regret_vs_eps.png`，從 `results/figures/` 複製，讓圖在 Design-doc repo 內能顯示。
  - **`~/Design-doc` 沒有 commit 也沒有 push**。`git status`：本檔是 M、`figures/` 是 untracked；`upf-ees design/` 和 `Data_collection_MVE_plan.md` 的既有變更都沒有動。
  - 本檔：修改前的版本在 `backup/2026-11-12/p5-research-doc/PROGRESS.md.before`。
  - 沒有修改 `results/`、`sim/`、`traces/`、`cost/`、`PREREGISTRATION.md`；沒有開 testbed。
- 【待確認】項目的結論：無新增。
- 遇到的問題與處理：
  - 同一個 session 先收到 P4 的起始指令。當時 P4 已經完成，依使用者決定沒有重跑，`results/` 沒有改。
- 下一步：
  - MVE（P0–P5）全部完成。
  - 要不要 commit `~/Design-doc` 的變更（`Data_collection_research.md`、`figures/data_collection_mve/`），由使用者決定。
  - 依規劃書第 7 節，下一步是 C1 規劃器設計，B3 當作強 baseline；6.3.2 的不利組合（特別是 H2 只靠 T2／S1）要一併納入考量。

### 2026-11-12｜P4｜分析完成：H1、H2、H3 成立，B3 沒有消除 regret（依規劃書第 7 節為「題目成立」，附不利組合）

- 完成：
  - 執行 `sim/run_grid.py`（預設選項，B3 預設解讀），12 輪、288 個 task，13:39–13:57，1,082 秒，第一次就完成，0 錯誤；12 輪全部有效。
  - 用新增的 `scripts/p4_driver.sh` 以 `setsid nohup` 執行：獨立 session、失敗時自動續跑（最多 3 次）、完成後自動跑 `check_outputs`，狀態寫在 `results/STATUS`。session 中斷不受影響。
  - 獨立驗算 `python3 -m sim.check_outputs results`：60/60 一致。
  - 依 PREREGISTRATION 第 5 節與第 7 節寫出判斷：`results/REPORT.md`。表在 `results/tables/`，圖在 `results/figures/`（8 張 Pareto 圖＋總覽、regret 對 ε 曲線）。
- 驗收結果（判準沒有調整）：
  - **H1 成立**：ε = 5%，T1 的 B2 最低成本比 B1 低 98.68%（S1）、98.64%（S2–S4），每個情境都 ≥ 50%；合計 98.65%。敏感度 98.57–98.60%。
  - **H2 成立**：T2 的 regret 在 ε = 2/5/10%（以及 1%、20%）都是 32.6% ≥ 30%，方向一致；敏感度相同。T1 的 regret 只有 0–0.71%。
  - **B3 檢查不滿足**（ε = 5%）：T1 的 B3 regret 853%（敏感度 615%），T2 沒有可行的 θ（只因 S4 誤差 9.5–13.5%）。
  - **H3 成立**：最小 R² = 0.999998。
  - 依規劃書第 7 節：H1 成立、H2 成立、B3 沒有消除 regret →「題目成立」。
- 不利於假設的組合（完整列在 REPORT 第 6 節）：
  1. T1 不支持 H2：單一設定 p = 60, k = 1, mean+max 在所有情境滿足所有 ε。
  2. H2 只靠 T2，而且 T2 的 regret 完全來自 S1：S1 的粗週期比全量模型準（−46% 到 −48%，全量 MAE 只有 0.69 kbit/s）。只比門檻高 2.6 個百分點，接近這個結構的上限 33.3%。
  3. T2 在 S2–S4 只有 p = 1 可行（p = 5 的誤差就已經 ≥ 22%）。
  4. ε ≥ 10% 時 B3 對 T2 的 regret 是 −44% 到 −49%，滿足 B3 檢查。
  5. H3 對 B0–B2 依定義成立，只有 B3 和資料有關。
- 修改的檔案：
  - 新增 `results/`（全部輸出、`REPORT.md`）、`scripts/p4_driver.sh`。
  - 本檔。
  - 沒有修改 `sim/`、`traces/`、`cost/`、`PREREGISTRATION.md`；沒有開 testbed。
- 【待確認】項目的結論：無新增。
- 遇到的問題與處理：無。`sim/logs/p4-aborted-20261112-results/` 是先前中止的不完整輸出，沒有使用，保留。
- 下一步：P5（整理）：依規劃書寫 1–2 頁 motivation 結果，回填 `~/Design-doc/Data_collection_research.md` 6.3 節。REPORT 第 6 節的不利組合要一併呈現。

### 2026-11-12｜P4 前置｜使用者確認 P3 解讀全部照預設；P4 改在獨立 session 執行

- **使用者決定（2026-11-12）**：P3 的實作解讀全部照預設進行：
  - B3 的 CV 來源、起始週期、k；
  - T2 的評估方式；
  - 合併 seed；
  - H1 以「四個情境**每一個**都 ≥ 50%」為正式判準，四情境合計並列報告。
- 決定的時間點：
  - 在看到完整結果之前做的；使用者沒有看 `sim/smoke/` 的數字。
  - 記錄在 `PREREGISTRATION.md` 第 7 節（實作澄清，不改判準、門檻、掃描範圍）。修改前的備份與 `changes.diff` 在 `backup/2026-11-12/pre-clarification/`。
  - `sim/README.md` 和 `sim/run_grid.py` 中 `criteria.json` 的 H1 規則說明已同步。
- **本 session 曾啟動完整 run_grid，依使用者要求中止**：
  - 13:34 啟動，在 26/288 個 task 時依使用者要求中止，程序已全部結束。
  - 中止的原因：使用者希望 P4 在獨立的 session 中完成。
  - 未完成的輸出移到 `sim/logs/p4-aborted-20261112-results/`，**不是結果**，P4 不要使用；`results/` 目前不存在。
- **給 P4 session**：
  - 用 EXECUTION_GUIDE 的 P4 起始指令。
  - 執行：`mkdir -p results && setsid nohup python3 -m sim.run_grid --out results > results/run_grid.log 2>&1 < /dev/null &`
    - 用預設參數，不要加 B3 選項。
    - 約 18 分鐘，可以續跑。
  - 跑完執行 `python3 -m sim.check_outputs results` 驗算。
  - 判斷只依 PREREGISTRATION 5.3 和第 7 節的澄清。
  - 報告時要說明的性質，見下方 P3 紀錄的「由 PREREGISTRATION 定義直接推得」一段。

### 2026-11-11｜P3｜A-DCCF 模擬器完成：38 個單元測試通過，seed 1 smoke run 端到端跑通

- 完成：
  - 在 `sim/` 實作 PREREGISTRATION 3–5 節的模擬器（約 1,400 行），說明在 `sim/README.md`。
    - 模組：`prereg.py`（固定常數）、`cost_model.py`、`producers.py`、`policies/`（B0–B3）、`consumers/`（T1、T2）、`metrics.py`、`run_grid.py`、`plots.py`、`check_outputs.py`。
  - `run_grid.py` 涵蓋的內容：
    - B0、B1、B2 45 組、B3 8 組（θ_low < θ_high）。
    - T1 的 p95／中位數；T2 每輪一個 GBR。
    - c\*、c_static、B2／B3 regret（ε = 1/2/5/10/20%）、H1 表、H3（6/26/46 UE）。
    - 主分析與敏感度分析（a = 884.8）並列。
    - Pareto 圖（每個情境 × 消費者）、regret 對 ε 曲線。
  - **可續跑**：每個 task 寫自己的快取檔，中斷後用同一個指令重跑會跳過已完成的部分（已驗證）。
- 驗收結果：
  1. **單元測試**：`python3 -m pytest sim/tests`，38 個全部通過。
     - 資料：3 個真實 UE 的前 240 秒（`sim/tests/data/fixture_240s.parquet`：S2 突發、S1 固定、S3 閒置）。
     - 驗證項目：
       - 成本模型對 `cost/README.md` 第 7 節 4 個例子（62,738／5,118／21,117／853 B）。
       - mean／max／var 摘要對逐區間暴力計算。
       - T1 ground truth 與估計、10 kbps 下限、p95。
       - 新鮮度可行集合（15 組 (p, k) 中 10 組）。
       - B3 的升降級、決策時點、k 與通知數。
       - T2 的預測時刻、時間切分不重疊、目標值、特徵與資料年齡、compact 與逐秒表示資訊相同。
       - regret／c_static 的玩具例子、Pareto 前緣、R²。
  2. **smoke run**：seed 1 的 4 輪，96 個 task，356 秒，0 錯誤，輸出在 `sim/smoke/`（**不是正式結果**）。
     - `sim/check_outputs.py` 不經快取直接從 trace 重算 60 項，全部一致：B0/B1/B2 bytes、mean-only 的 T1 峰值 p95、暴力搜尋的 regret。
     - 圖表已目視檢查版面。
  3. 完整 12 輪（P4）預估約 18 分鐘。
- 修改的檔案：
  - 新增 `sim/`。
  - 本檔。
  - 沒有碰 testbed、VM、infra repo、`traces/`、`cost/`、`PREREGISTRATION.md`。
  - 沒有建立 `results/`。
- 實作上的解讀（PREREGISTRATION 沒有明訂；細節在 `sim/README.md` 第 3 節）。★ 是會影響結果的項目；**2026-11-12 使用者確認全部照預設，H1 以「每個情境都 ≥ 50%」為正式判準**，已記入 PREREGISTRATION 第 7 節：
  1. ★ **B3 的 CV 來源**：用 producer 端最近 60 個 1 秒值，閒置時 CV = 0。
     - 摘要固定 mean+max 時，A-DCCF 在 p = 60 只有一個值，算不出 CV：p 升到 60 後就永遠降不下來。
     - 替代：`--b3-cv-source received`。
  2. ★ **B3 的起始週期 p₀ = 1 秒**。替代：`--b3-p0`。
  3. ★ **B3 的 k = ⌊60/p⌋**，不限於 {1, 5, 10}，每個 UE 每分鐘一則通知。替代：`--b3-k-mode grid`。
  4. ★ **T2 的設計**：
     - 每個 UE 每秒一個預測時刻。
     - 特徵是最後一個已結束區間之前 60 秒的統計量，加上資料年齡。
     - 46 個 UE 合併成每輪一個模型；訓練目標在前 70%，測試從 70% 開始。
     - k 不影響 T2（離線）。
  5. **合併 seed**：每個情境把 3 個 seed 合併。T1 對 4,140 個誤差取 p95；T2 用合併 MAE 的比值；成本 3 輪合計。
  6. ★ **H1 的範圍**：5.3 沒寫是每個情境都要成立，還是四情境合計。`criteria.json` 兩者都列，由 P4 依原文判斷並都報告。
  7. 原始量測每筆用 b_raw = 488.93 B：表中的 r、s 是四捨五入值，r + 10s = 489.0。這樣 B1 剛好是 5.1 的 1,045.6 B／則。
- 由 PREREGISTRATION 定義直接推得、P4 報告時要說明的性質（不是實作錯誤，也不是 smoke 的結果判斷）：
  - **T1**：摘要含 max 時，峰值是精確的（max 來自 producer 的 1 秒值），平均值也精確。所以所有 mean+max(+var) 的 B2 和所有 B3 的 T1 誤差都是 0，T1 的取捨只剩新鮮度和 bytes。
  - **B2 的成本和資料無關**，B2 的 regret 只來自「各情境可行的設定不同」。H3 中 B0–B2 的 R² 必然是 1，只有 B3 和資料有關。
  - **T2 的雜訊下限**：p = 1 的 mean+max 和全量資訊相同，但多出的欄位改變 GBR 同分時的選擇，誤差不是 0。
    - S1 的全量 MAE 很小（約 0.7 kbit/s；平均吞吐量約 600），smoke 中這個雜訊達 −0.5% 到 −1.7%，粗週期甚至比全量準（約 −44%）。
    - 原因是 T2 誤差是比值，S1 的分母很小。ε = 1–2% 的 T2 結論要小心解讀。
- 【待確認】項目的結論：無新增。
- 遇到的問題與處理：
  - sklearn GBR 用隨機特徵做基準測試時一個 fit 超過 6 分鐘；真實資料的值種類少，只要 2–35 秒，所以 T2 能用每秒一個預測時刻。
  - 測試 fixture 的 SUPI 排序與一個測試的期望值寫錯，已修正測試（程式邏輯沒有改）。
  - 沒有使用 testbed。
- 下一步：
  1. 使用者確認上面標 ★ 的解讀。若要改，只需在 `run_grid.py` 加命令列選項，不必改程式。
  2. 開 P4 session，執行：
     `setsid nohup python3 -m sim.run_grid --out results > results/run_grid.log 2>&1 < /dev/null &`
     - 要先 `mkdir -p results`。
     - 中斷後用同一個指令續跑。
     - 完成後可以用 `python3 -m sim.check_outputs results` 驗算。

### 2026-11-11｜P4｜未開始：P3 模擬器尚未實作，sim/run_grid.py 不存在

- 完成：依 README 順序讀 PROGRESS.md、EXECUTION_GUIDE.md、PREREGISTRATION.md。發現 P3 狀態是「未開始」，`sim/` 不存在，家目錄內也找不到 `run_grid.py`／`cost_model.py`，P4 無法執行。
- 依使用者決定（「先停下，不做任何事」）停止：沒有建立 `sim/`、`results/`，沒有執行任何實驗，也沒有開 testbed。
- 修改的檔案：只有本檔（新增這一筆）。
- 【待確認】項目的結論：無新增。
- 下一步：先用 EXECUTION_GUIDE 第 4 節的 P3 起始指令開新 session 實作模擬器；P3 驗收後再開 P4 session。P4 的 `run_grid.py` 若執行時間長，用 `setsid nohup` 背景執行並把 log 寫到 `results/`，避免 session 中斷時被終止（P1 曾因此中斷）。

### 2026-11-11｜P2｜12 輪 ground-truth trace 全部有效，放在 traces/

- 核准：PREREGISTRATION.md 的核准者與日期已由使用者填寫（12:58），但狀態行仍是「草稿」。向使用者確認後，把狀態改成「已核准」。只改了這一行，備份在 `backup/2026-11-11/pre-approval/`（含 `changes.diff`）。
- 完成：
  - 4 情境 × seed 1/2/3，每輪 1800 秒、46 UE，順序是 seed 1 的 S1→S4，再 seed 2、seed 3。
  - 時間：06:02–12:55 UTC。
  - 每輪做法：
    - 乾淨重啟修正版 UPF/SMF/NWDAF（1 秒）。
    - P0 4.5 #1/#2 驗證 46/46。
    - 訂閱 4 個 group，60 秒後在 T0 開始排程流量。
    - 匯出 parquet，執行品質檢查。
  - 每輪開始前都檢查 `df -h ~`：全程 17 GB。
- 結果（`traces/summary.csv`）：
  - 12/12 有效，全部是 attempt 1，沒有重跑。
  - 每輪 87,147–87,216 筆紀錄，0 重複，0 缺漏（46 × 1800 格）。
  - UPF UL 總量 / iperf3 送出量：S1 1.00000、S2 1.00034–1.00036、S3 1.00008、S4 1.00010–1.00011。多出的部分是 iperf3 控制連線的 TCP 封包。
  - 逐秒相關係數 0.9988–0.9999。
  - 兩台 UPF 的 dropping-window log 全部是 0。
  - iperf3 共 11,713 次啟動，只有 1 次失敗（S4-seed3，connection reset），runner 立即重試成功。
- 新增的檔案：
  - `scripts/p2_schedule.py`：排程產生器，輸出在 `traces/schedules/`。
  - `scripts/p2_ue_runner.py`：在 gNB VM 內執行的 iperf3 runner。
  - `scripts/p2_run.sh`：單輪執行。
  - `scripts/p2_export.py`：MongoDB → parquet 匯出與品質檢查；`--reanalyze` 可以從 parquet 重算。
  - `scripts/p2_all.sh`：12 輪總控，含自動重跑規則。
  - `traces/`。
- 修改的檔案（備份位置）：
  - 只改了 `PREREGISTRATION.md` 的狀態行（見上）。
  - infra repo、NF 程式碼、MongoDB 訂閱者資料都沒有修改。
  - `newstack/` 衍生設定用 `newstack.sh gen` 重新產生為 1 秒（P1 結束時停在 30 秒），並已 deploy。
- testbed 端的變更：
  - 在 MEC、MEC2、gNB、gNB2 用 apt 安裝 iperf3 3.7。VM 原本沒有 iperf3，PREREGISTRATION 2.2 需要它；systemd daemon 未啟用。
  - 為了 apt，在這 4 台 VM 對 archive/security.ubuntu.com 加了經 VBox NAT 的 host route（runtime，重開機後消失）。
- 執行上的決定（實作細節，依 EXECUTION_GUIDE 第 3 節可以自行決定；都記在 `traces/README.md`）：
  1. **流量方向是 UL**（iperf3 預設 client→server，client 在 UE）。T1/T2 的吞吐量用 `ul_bytes`。
  2. **不開 ADRF**：每則通知約 2.8 KB 寫入，12 輪約 2.8 GB。NWDAF 寫 ADRF 失敗，但不影響 MongoDB 紀錄（0 缺漏）。
  3. **MongoDB 清理**：規劃書 P2 步驟 3 寫「清空 collection」。實際只刪每一輪自己的紀錄，而且是在 parquet 回讀筆數與 bytes 加總一致之後才刪。P0/P1 的紀錄保留。理由是 collection 只有約 18 MB，清空不會改善磁碟，反而會丟掉 P0/P1 資料。
     - 刪除範圍到每輪結束後 30 秒；之後到退訂之間的 638 筆尾端紀錄留在 MongoDB，不屬於任何 trace。
  4. 每段 on-period 用一個 iperf3 client（`-n` bytes 在實際啟動時依剩餘時間計算）。很短的段至少送 1 個 1200 B 封包；剩餘時間 < 0.02 秒的段略過（12 輪共 15 段）。
- 正式收集前 pilot 的發現（`traces/pilot-S3-seed1-d180/`，3 分鐘 S3。發現後修正匯出定義，再開始正式 12 輪；判準沒有改）：
  - **MongoDB 的 `timestamp` 是量測區間的起點**，量的是 [ts, ts+1)，不是 UPF 送出時間。
    - 依據：對齊成 [ts, ts+1) 時，和 iperf3 每秒量的相關係數是 0.9999；當成 [ts−1, ts) 只有 0.959。
    - 格點因此定為 k = round(ts − T0 − φ_u)，φ_u 是各 UE 的固定相位。
  - **UPF UL volume 對 UDP 就是 payload**：逐 UE 只比 iperf3 多出控制連線的封包。
    - 原本依 P0 ICMP 推論的「每封包 +8 B」修正是錯的，會變成 0.9935。
    - 所以 2.3 的總量比對用 raw 比值；+8 B 的版本列為輔助（`volume_ratio_hdr8`）。
  - 閒置秒的 UPF 也會送 0 值紀錄（修正版 UPF：「zero-volume measurement is valid」），所以閒置 UE 不會被算成缺漏。
- 限制（P3 要知道）：
  - 每個 UE 的 1800 格相對 T0 偏移 φ_u（< 1 秒）。[T0, T0+φ_u) 的流量落在 k = −1，不在格點內，但總量比對有計入。
  - 不同 UE 的格點彼此最多錯開 1 秒。
  - Producer 是修正版 UPF（P0 已記錄）。
- 遇到的問題與處理：
  - `p2_export.py` 第一版的 iperf3 每秒切分在 t 剛好落在格線時無限迴圈 → 改成用整數格線切分。
  - 本 session 沒有 reset 任何 VM，也沒有 VM 卡住。
  - 結束時已退訂 consumer、停掉所有服務，7 台 VM 已 `vagrant halt`（poweroff）。I-UPF、I-UPF2 全程沒有開機。
- 【待確認】項目的結論：無新增。#4 照結論改用 MongoDB 匯出。
- 下一步：P3（模擬器）。讀 `traces/README.md`；每輪用 `FINAL.json` 的 `final_attempt` 對應的 `upf_1s.parquet`。

### 2026-11-11｜P1（收尾）｜成本模型 4 項決定定案，寫進 PREREGISTRATION 5.1／5.4（仍是草稿）

- 完成：使用者決定「全部照建議」，P1 紀錄最後列出的 4 項依建議定案：
  1. **樣本單位**：用兩層模型，每則通知 bytes = a + Σ（每次回報）(r + n_stat × s)。
     - 參數：a = 556.7 B、r = 248.1 B、s = 24.09 B；原始量測 n_stat = 10，r + 10s = 488.93 B。
     - 拆解方式：實測 546 筆 item 的 JSON 拆成 10 個數值欄位（平均 23.2 B）與其餘部分（237.9 B，範圍 233–239），再乘以線上／JSON 比 1.0384。
     - 原本 5.1 寫「每個統計量算一筆 b」。照這個算法，B2 p = 1 s、k = 10、mean+max 只比 B1 便宜 3%；p = 1 s、k = 1、mean+max 每則 1,495 B，比原始量測的 1,045.6 B 還貴，不合理，所以不採用。
  2. **c_conn**：主分析不納入（a = 556.7 B）。5.4 新增必報的敏感度分析：a = 884.8 B（= a0 + c_conn × 21/23），重算 H1、H2、B3 檢查。
  3. **b 的單位**：用線上 IP bytes，雙向合計。
  4. **c_ka**：忽略（p = 30 s、46 UE 時占 EES bytes 的 0.65%）。
- 例子（一個 UE、1 分鐘，主分析）：
  - B1：62,738 B。
  - B2 p = 10 s、k = 1、mean+max：5,118 B（−91.8%）。
  - B2 p = 1 s、k = 10、mean+max：21,117 B（−66.3%）。
  - B2 p = 60 s、k = 1、mean+max：853 B（−98.6%）。
- 修改的檔案（備份位置：`backup/2026-11-11/pre-costmodel/`，含 `changes.diff`）：
  - `PREREGISTRATION.md`：5.1 改寫，5.4 新增一點；狀態仍是草稿。
  - `cost/README.md`：第 7 節改成定案內容，第 8 節新增檔案。
  - `PROGRESS.md`。
  - 新增 `scripts/p1_params.py`，產生 `cost/sim_params.json`。
  - 沒有碰任何 VM、infra repo 或 MongoDB。
- 【待確認】項目的結論：無新增。
- 遇到的問題與處理：上一則說明用「23 個 UE 併成一則通知」舉例，不符合 PREREGISTRATION B2 的定義（同一個 UE 的 k 次回報依時間打包），已更正。在正確定義下，c_conn 不會因 B2 打包而消失。每台 UPF 每個回報時刻仍同時送 23 則，所以 c_conn 只影響 a 的大小，不影響 B2 和 B1 的差異方向。
- 限制（已寫進 5.1）：b 會隨數值位數變化（P1 實測 464–480 B）。P2 流量較大，預估每筆原始量測最多多出約 4%。參數固定，不修正。
- 下一步：使用者核准 PREREGISTRATION（填核准者與日期），之後才能開始 P2。

### 2026-11-10｜P1｜成本模型量測完成：a0 = 557 B、b = 470–479 B（線上 489 B），另有連線與 keep-alive 兩項開銷

- 完成：
  - repPeriod 1/5/10/30 秒 × 訂閱 UE 6/26/46，12 格各 600 秒，全部完整（每 UE 紀錄數＝期望值，tcpdump 0 drop），原始資料與結果在 `cost/`（說明：`cost/README.md`；數據：`cost/cells.csv`、`cost/fit.json`）。
  - 合成驗證（N = 1…46 筆 item，每個 N 30 次）：JSON body `a = 47.9, b = 470.84`（R² 0.9999993）；線上 IP bytes `a = 550.2, b = 488.93`（R² 0.999975）。線性成立，截距和實測 a0（556.7）差 1.2%。
  - 新增腳本：`p1_cell.sh`、`p1_matrix.sh`、`p1_analyze.py`、`p1_fit.py`、`p1_synth.py`、`p1_synth_prep.py`、`p1_synth_run.sh`、`p1_synth_analyze.py`、`consumer-p1-{6,26,46}.json`；修改 `newstack.sh`（`PERIOD=` 只改衍生設定、`start-adrf`/`stop-adrf`）、`testbed.sh`（`CONSUMER=` 選消費者設定）。
- 驗收結果（規劃書 P1 的 4 個做法）：
  1. 擷取：EES（UPF→NWDAF，主）、PFCP、ADRF、消費者（輔）全部擷取。
  2. 每則通知 body 與線上 bytes：body = 外框 49 B＋item 464–480 B；請求 header 265 B；回應 64 B（204）；線上 1,147–1,372 B／則。
  3. 通知率、CPU、MongoDB 成長：見 `cost/README.md` 第 6 節（最高 NWDAF 9.4% core，1 s／46 UE）。
  4. 擬合：`bytes = k·(a0 + b·N) + max(0,k−2)·c_conn + [P≥30 s]·min(k,2)·c_ka`，a0 = 556.7 B、b = 469–479 B（JSON）／488.9 B（線上）、c_conn = 359.3 B／新連線、c_ka = 102.5 B／閒置連線／30 s；對 12 格 EES bytes/秒的預測誤差 −0.18%～+0.16%。H3：通知數對 UE 數完全線性；bytes 在本矩陣內 R² ≥ 0.9999995，但因 c_conn 而截距為負（分段線性，取決於每個 producer 的訂閱數）。
- 修改的檔案（備份位置）：infra repo **沒有任何修改**（週期只寫進 `newstack/` 衍生設定）；`scripts/newstack.sh`、`testbed.sh` 修改前版本在 `backup/2026-11-10/pre-p1/scripts/`。MongoDB 只多了量測資料：`nwdaf.upfTrafficData` 與 ADRF `adrf.data_store_records`（P1 開始前已有 22,122 筆，未刪）。合成測試期間 5GC `enp0s9` 暫時 `gro off`，測完已恢復 `on`（runtime 設定）。
- 【待確認】項目的結論：規劃書 P1 第 1 點「h2c 明文」不適用：UPF notifier 明文時是 HTTP/1.1 keep-alive（`go-upf/internal/ees/notifier.go`，Go `http.Transport` 預設值）。
- 遇到的問題與處理：
  - 13:19 UTC 矩陣腳本隨上一個 Claude session 結束被終止（p10-u26 進行中）→ 停掉殘留的 tcpdump，改用 `setsid nohup` 從 p10-u26 重跑；已完成的 7 格不受影響（`cost/raw/matrix-part1.log`）。
  - 開機時 `testbed.sh` 尾端出現 syntax error：我在開機腳本執行中修改了 `testbed.sh`（bash 逐行讀檔），NTP 等步驟已完成，不影響。之後腳本執行中不再修改。
  - 合成測試第一次：`pkill -f` 比對到自己的 shell，pcap 沒有壓縮與傳回 → 改成 `pkill -x tcpdump`，手動取回（sha256 一致）。分析上，大請求的 HTTP 標記落在最後一段，前面的段被算到上一則 → 改用 TCP seq/ack 歸屬；GRO 合併段造成段數低估 → 關 GRO 重跑（GRO 開著的結果保留為 `cost/synth/gro_on_*`）。
  - 本 session 沒有 reset 任何 VM。
- 新發現（影響 P3 的成本模型）：
  - **連線重用上限**：UPF notifier 每個目的地最多保留 2 條閒置連線，同一 UPF 上 k 個訂閱同時觸發時有 k−2 則要新開 TCP 連線（實測新連線/則與 Σmax(0,k−2)/總數 完全一致）。每則固定成本因此從 557 B（k ≤ 2）升到約 885 B（k = 23）。
  - **30 秒週期的 keep-alive**：Go TCP keep-alive 30 秒，週期 30 s 時每條閒置連線每週期多約 103 B；1／5／10 s 時沒有。
  - **PFCP** 和訂閱數無關（46 個 session 全部回報，`urrPeriod` 決定頻率）；**NWDAF→ADRF** 每則通知約 2.83 KB，是 EES 本身的 2.1 倍。
- 下一步（**需要使用者決定，P3 之前**；也牽涉 PREREGISTRATION 5.1，最好在核准前決定）：
  1. 模擬器的 `a` 是否包含連線開銷 c_conn（clubbing 會同時省掉 a0 和新連線；不含則低估 B2 的效益）。
  2. b 用 JSON（≈ 470–479 B）還是線上（488.9 B）；主成本若是線上 bytes，建議 488.9。
  3. 摘要的「樣本」單位：一筆 item（10 個數值欄位＋時間＋IP，約 470 B）還是每個統計量；PREREGISTRATION 5.1 目前寫「每增加一個統計量就算一個樣本」。
  4. 是否要把 c_ka（≥ 30 s 週期）納入模擬器。
  - 下一個階段是 P2（需先核准 PREREGISTRATION）。P2 的開機順序同 P0 紀錄，另加 `newstack.sh start-adrf`（若 P2 也要 ADRF）。

P1 開始前的使用者決定（2026-11-10，本 session）：

1. **擷取點**：規劃書寫「UPF→SMF（`smf.notifUris.upf`）、SMF→NWDAF」，但修正版 UPF 的 EES 通知是**直送 NWDAF**（`192.168.107.5:8080`；SMF 只負責建立 UPF 訂閱，P0 SMF log 只有 46 個訂閱 POST、沒有任何通知進來），UPF→SMF 只剩 N4 PFCP 用量報告。決定：**UPF→NWDAF 的 EES HTTP 為主成本（擬合 a、b）**；N4 PFCP、NWDAF→ADRF、NWDAF→消費者一併擷取作為輔助紀錄，不進成本模型。另：notifier 用 Go `http.Transport` 的預設值，明文時是 **HTTP/1.1 keep-alive，不是 h2c**（規劃書 P1 第 1 點的「h2c」不適用這一段）。
2. **b 的取得方式**：逐 SUPI 訂閱下每則通知固定 1 筆 item（`notifier.go`：一個訂閱一則通知、每個 UE 一筆），真實流量只能量到 a + b。決定：**結構分解＋合成驗證**——b = 真實 body 中一筆 `notificationItem` 的 JSON bytes，a = 實測每則通知線上 bytes − b；再用 `scripts/` 的臨時接收端（5GC，非 NWDAF port）＋UPF-EES 上的發送腳本送 N = 1…46 筆的合成通知，驗證線性與斜率。不改任何 NF 程式碼，合成資料不進 NWDAF/MongoDB。
3. **ADRF**：P0 時 NWDAF 每則通知都寫 ADRF 失敗（`:9888` 沒有在跑）。決定：**把 ADRF 跑起來**（5GC `~/adrf`，既有 `config/5GC/adrfcfg.yaml`，不改設定），並把 ADRF 寫入量與 `adrf` 資料庫成長列為輔助指標。
4. **矩陣**：repPeriod 1/5/10/30 秒 × UE 數 6/26/46，**每格 10 分鐘**。46 個 UE 都上線、每 UE 5 pps ping（同 P0），UE 數用消費者訂閱的 group 控制（6 = `group-test-001/002`，26 = 再加 `group-mve-s1`，46 = 四個全部）。

### 2026-11-10｜P0（續）｜b 方案失敗，依授權換成修正版 UPF/SMF/NWDAF，4.5 #4 在 1 秒通過

使用者指示：先做 (b) 測 2–3 秒，若還有問題，授權進行 (c) 替換。

- 完成：
  - **(b) 2 秒，舊版**（`p0/collection_check_2s*`）：節奏 300/300、0 drop、封包守恆 1.000，但每 UE 序列是 `0,16,15` 循環，即用量約 3 秒才來一次。查出原因是 `smfcfg.yaml` 的 `urrThreshold: 1000`（bytes）：5 pps×84 B 約 2.4–3 秒就觸發一次門檻報告並把計數器歸零。把門檻調到 1 TB 後（`p0/run-2s-thr*`），**13,800 筆全部是 0**：這個 UPF build 的週期性 URR 報告本來就不帶用量，舊版只能靠門檻報告（間隔隨流量變化，不是固定週期）。設定無法修正 → (b) 失敗，3 秒也不必測。
  - **(c) 替換**（`scripts/newstack.sh`，舊執行檔完全沒動）：UPF = `~/go-upf` @ `682b469`（PR #79 最新，在主機用 Go 1.26.2 靜態編譯，`newstack/bin/`，含 PROVENANCE 與 sha256）；SMF = 5GC `~/ees-audit-20261021/smf`；NWDAF = 5GC `~/ees-audit-20261027/nwdaf`。放在各 VM 的 `~/mve-bin/`，其他 core NF 仍是 v4.1.0（與 10-21 驗證相同）。執行用設定由 `newstack.sh gen` 從 `config/5GC` **衍生**到 `newstack/`：SMF `urrThreshold 0`、拿掉 `nupfEe*`；NWDAF 加 46 個 `pduSessionIds`（全部 PSI 1，已用 `nr-cli ps-list` 確認 46/46）；UPF `ees.ip/port`。共用的 `smfcfg.yaml` `urrThreshold` 已改回原本的 1000。
  - `gNB*/run.sh` 在 `nr-ue` 之間加 `sleep 1`：第一次 1 秒測試時 006 遇到 `TUN allocation failure [ioctl(TUNSETIFF) Device or resource busy]`（多個 nr-ue 同時配置 TUN 的競爭）。`p0_period_run.sh` 改成 #1/#2 不是 46/46 就先重啟 RAN 一次，再不行就停止。
  - 新增腳本：`set_period.sh`、`p0_period_run.sh`、`newstack.sh`；`testbed.sh` 加 `boot`/`halt`/`start-ping`；`p0_check_collection.py` 加 `--period/--nwdaf-log/--upf-log/--tol`。
- 驗收結果（新版，1 秒，`p0/run-1s-newstack-r2/`，08:59–09:11 UTC，46 UE × 5 pps）：
  1. 40/40 新 UE＋6/6 既有 UE 通過。
  2. 46/46 ping MEC/MEC2 通過。
  3. NWDAF 46 個逐 SUPI SMF 訂閱、UPF-EES/UPF-EES2 各 23 個 EES 訂閱、MongoDB 46/46 有紀錄且 IP 正確。
  4. **通過**：每 UE 600/600 筆、無重複、間隔 0.914–1.092 秒（時間戳不再對齊整秒，有毫秒）；600/600 個視窗都有值；每視窗 UL 封包 5（26,442）／4（1,104）／6（54）（4/6 是邊界抖動，總數守恆）；UL 封包／實際封包 0.9997–1.0000；兩台 UPF 0 drop。
  - 新版 MongoDB 紀錄格式與舊版相同（`metadata.{correlationId,groupId,ipAddr}`＋volume/packets/throughput），volume 不含 IP header（10 個 ICMP 封包 = 640 B）。
- 修改的檔案（備份位置）：本次修改前的各版本在 `backup/2026-11-10/pre-stage-b/`（四個週期設定）、`pre-threshold/`、`pre-newstack/`（smfcfg）、`pre-stagger/`（gNB*/run.sh）；最初版本仍在 `backup/2026-11-10/infra/`，`changes.diff` 已重新產生（相對最初版本，9 個檔案）。目前 `config/5GC` 的週期是 1 秒（`samplingInterval`/`urrPeriod`/`periodSec`）。
- 遇到的問題：
  - 第一次 1 秒測試中 UPF-EES 卡住（VBox heartbeat flatline，08:48:48 UTC，slice 1 資料面與報告同時停止）→ `VBoxManage controlvm reset` 一次（本 session 唯一一次），重跑 `setup.sh`＋`dn-routes` 後正常，第二次測試 12 分鐘沒有再發生。這和主機上已知的 2 vCPU guest hang 一致；若 P2 長時間收集再發生，考慮把 UPF-EES* 改成 1 vCPU（要改 Vagrantfile，需先討論）。
  - 舊版設定（`UPF-EES*.yaml` 的 `periodSec`/`parquetDir`）對新版沒有作用，保留 P0 前半的修改。
- 下一步：
  1. P1/P2 一律用新版：開機 `scripts/testbed.sh boot` → `scripts/newstack.sh gen && newstack.sh deploy` → `newstack.sh start-upf && start-core && start-nwdaf` → `testbed.sh start-ran` → `testbed.sh start-consumer`。舊版的 `testbed.sh start-upf/start-core/start-nwdaf` 只留作對照。
  2. 1 秒 ground truth 成立，PREREGISTRATION 不需要因週期而修改；但「producer 是修正版 UPF」要寫進限制。
  3. 若之後要回到使用者原本的 closed-loop demo（舊版），`smfcfg.yaml` 的 `urrPeriod` 與 `nwdafcfg.yaml` 的 `samplingInterval` 要改回 5。

### 2026-11-10｜P0｜46 UE 上線、4.5 #1–#3 通過；#4 因 UPF-EES2 在 1 秒設定下丟掉約 40% 用量而停下

- 完成：
  - 訂閱者：用 webconsole REST API 建立 40 筆（`…101`–`120` slice 010203、`…201`–`220` slice 112233），先試跑 2 筆並逐欄比對既有 UE，再批次建立 38 筆，0 失敗。MongoDB 共 46 筆。
  - 設定（4.3 檢查清單全部）：`ue-s1-scale.yaml`、`ue-s2-scale.yaml`（新檔）；`uerouting.yaml` members；`nwdafcfg.yaml` 新增實驗 group `group-mve-s1`（101–120）、`group-mve-s2`（201–220），原本的 `group-test-001/002` 不動；`gNB/run.sh`、`gNB2/run.sh` 加 `nr-ue -n 20`；pool 容量 23/253。
  - 為了 4.5 #4 另外改：`nwdafcfg.yaml` `samplingInterval 5→1`、`smfcfg.yaml` `urrPeriod 5→1`、`UPF-EES*.yaml` `ees.periodSec 5→1`（這個 UPF build 的 EES aggregator tick 取 `max(periodSec, urrPeriod)`，見 `UPF-EES/go-upf/internal/ees/aggregator.go` `AdjustReportPeriod`；只改 `samplingInterval` 不可能有 1 秒資料），以及 `ees.parquetDir` 指向不存在目錄（停用 PseudoDriver，使用者核准）。
  - 使用者核准後把既有 `imsi-208930000000004` 的 slice-level charging 從 Online（quota 100000）改成 Offline。
  - 腳本（`scripts/`）：`testbed.sh`（開機後的 mount／Mongo 路由／DN 路由／NTP 修正與各服務啟停）、`provision_subscribers.py`、`p0_verify_ues.py`（#1 #2）、`p0_check_collection.py`（#3 #4）、`clock_offsets.sh`、`make_changes_diff.sh`、`webui-host.yaml`、`consumer-mve.json`。證據在 `p0/`。
  - session 結束時 consumer 已退訂、所有服務已停、7 台 VM 已 `vagrant halt`（poweroff），主機 webconsole 已停。I-UPF、I-UPF2 全程沒有開機。磁碟維持 15 GB 可用。
- 驗收結果（規劃書 4.5）：
  1. **通過**：40/40 新 IMSI 在 core log 有 `Handle Registration Complete` 與 `Allocated PDUAdress`，`nr-cli ps-list` PS-ACTIVE，IP 與 SMF 分配一致、在正確 pool、有對應 `uesimtunX`（`p0/ue_check.csv`）。既有 6 個也通過。
  2. **通過**：40/40 新 UE `ping -c 3` MEC/MEC2 全收到；修正 004 後 46/46。注意：`nr-binder` 對 ping 無效（LD_PRELOAD 不作用在有 capability 的 ping；而且要在 `build/` 內執行），改用等效的 `ping -I uesimtunX`。
  3. **通過**：一次 group 訂閱（4 個 group）→ NWDAF 建立 46 個逐 SUPI 的 SMF 訂閱（corr-1…46，`p0/nwdaf_subscriptions.txt`），兩台 UPF 各 23 個 EES 訂閱在送通知，MongoDB 46/46 個 corrId 都有紀錄且紀錄的 ipAddr 與該 SUPI 的 UE IP 一致。紀錄裡沒有 SUPI，只有 `correlationId`/`groupId`/`ipAddr`，SUPI 要用 NWDAF log 對應。
  4. **不通過**（10 分鐘，07:25–07:35 UTC，46 UE 各以 5 pps ping MEC，資料面 68,356／68,515 個 request 100% 有回應）：
     - 通知節奏穩定：每 UE 577–600 筆／600 秒，間隔 1–2 秒、最差 UE 96% 剛好 1 秒，無重複時間戳。
     - 但量測粒度約 3 秒：非零紀錄的間隔中位數 3 秒（最長 16 秒），其餘秒是 0，資料以約 3 秒一包集中在某一秒。
     - **slice 2 用量遺失**：回報的 UL 封包數／實際封包數，slice 1（UPF-EES）= 1.001，slice 2（UPF-EES2）= 0.58–0.61。UPF-EES2 同期 log 有 2,403 次 `ees aggregator dropping duplicate window (already sent)`，UPF-EES 為 0（兩台 USAR 數相同，約 18.2k）。原因是 aggregator 把晚到的量測 snap 到已送出的 1 秒視窗後直接丟棄，與時序有關。
     - 規劃書的備案「改用 2 秒」無法解決「約 3 秒粒度＋丟資料」，而且修正需要改 UPF 程式碼（規則 11），所以依停止條件停下，沒有自行改週期。`p0/collection_check.csv`、`p0/collection_check_summary.txt`。
- 修改的檔案（備份位置）：`backup/2026-11-10/infra/`（修改前的 `config/5GC/{nwdafcfg,smfcfg,uerouting,amfcfg,webuicfg,UPF-EES,UPF-EES2}.yaml`、`config/UERAN/*.yaml`、`gNB*/run.sh`、`gNB*/setup.sh`），差異在 `backup/2026-11-10/changes.diff`（9 個檔案，含 2 個新檔）；MongoDB `free5gc` 修改前的 `mongodump` 在 `backup/2026-11-10/mongodump/`（MongoDB 其實在主機上，所以 dump 在主機執行），004 修改前的 chargingData 在 `backup/2026-11-10/imsi-004-chargingData-before.json`；5GC VM 的 `~/free5gc/config` 在 `backup/2026-11-10/vm-5GC/`。infra repo 沒有 commit、stash、checkout，也沒有開分支（規劃書 P0 步驟 1 的「開實驗分支」與規則 5 衝突，依規則 5 只用備份）。
- 【待確認】項目的結論：見上表 #1–#5。
- 遇到的問題與處理（都是 runtime 或 VM 內處理，沒有改 NWDAF/SMF/UPF 程式碼；VM 重開後要重跑 `testbed.sh mount`、`dn-routes`、`ntp`，以及各 VM 的 `/vagrant/setup.sh`）：
  - 部署中的是舊版本：SMF（Mar 26）、NWDAF（Apr 14）、UPF（May 13）；2026-10-21 修好的版本只在 `~/ees-audit-*` 隔離目錄，沒有部署。舊 NWDAF 不需要 `pduSessionIds`。
  - 5GC 的 vboxsf 全部沒掛上：guest 的 `mount.vboxsf` 會把 share 名稱當成 cwd 下的路徑（`~/adrf` 存在）→ 在空目錄內手動 mount（`testbed.sh mount`）。
  - 5GC 連不到 MongoDB（主機 140.113.110.82）：`setup.sh` 把預設路由改到不存在的 192.168.105.1 → 加 host route 經 VBox NAT。
  - UPF-EES2 的 gtp5g 沒有對應新 kernel（5.15.0-181）→ 在 VM 內用原本的 v0.9.14 原始碼重新 `make install`（已持久）。
  - UE 到 DN 不通：MEC/MEC2 回程路由指向 I-UPF/I-UPF2 的 N6 IP，UPF-EES* 的出口 gateway 不存在 → 在 UPF-EES*／MEC* 加 on-link host route（全部 NIC 都橋接在同一個 eno1 L2），UPF 本來就有 MASQUERADE（`testbed.sh dn-routes`）。
  - 004 沒有資料面：slice-level Online charging 且 core 沒跑 CHF → FAR 為 DROP。slice 2 的範本因此改用 006；004 經核准改為 Offline 後恢復。
  - 發現 PseudoDriver 會造假用量（無 GTP 封包時仍回報數 MB）→ 經核准停用（見【待確認】#4）。
  - webconsole 有 chargingData 重複插入的問題（slice-level upsert filter 有 `qosRef:0` 永遠不 match）→ 腳本先去重，新 UE 的 chargingData 與範本完全一致（每 UE 2 筆）。
- 下一步（**需要使用者決定，P1 之前**）：
  1. 4.5 #4 怎麼處理：(a) 回到 5 秒（`samplingInterval`/`urrPeriod`/`periodSec` 改回 5）並量測 5 秒時是否守恆；(b) 測 2–3 秒是否守恆、無 drop；(c) 部署 2026-10-21 修好的 UPF/SMF/NWDAF（需要另外驗證，也涉及程式碼／版本，規則 11）；(d) ground truth 改用 iperf3／UE 端量測。目前設定仍是 1 秒，VM 已關機。
  2. PREREGISTRATION 若以 1 秒 ground truth 為前提，要依上面的決定修改後再核准。
  3. P1 開始時：開機 → 各 VM `/vagrant/setup.sh` → `scripts/testbed.sh mount && dn-routes && ntp` → `start-upf`/`start-core`/`start-nwdaf`/`start-ran`/`start-consumer`。

### 2026-11-10｜規劃｜建立工作目錄與執行文件

- 完成：建立 `README.md`、`EXECUTION_GUIDE.md`、`PREREGISTRATION.md`（草稿）、`PROGRESS.md`。
- 修改的檔案：`~/Design-doc/Data_collection_MVE_plan.md`（定案事項；T2 改成預測未來 10 秒；加入新鮮度限制）。testbed 完全沒有修改，VM 都是關機狀態。
- 下一步：使用者審閱 `PREREGISTRATION.md`；之後開新 session 執行 P0。
