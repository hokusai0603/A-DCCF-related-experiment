# A-DCCF 模擬器（P3）

依 [PREREGISTRATION.md](../PREREGISTRATION.md)（2026-11-11 核准）第 3–5 節，用 P2 的 ground-truth trace 離線重播 B0–B3，計算成本與 T1／T2 準確度。
本文件說明程式結構，以及 **PREREGISTRATION 沒有明訂、由實作決定的地方**（第 3 節）。第 3 節標 ★ 的項目會影響結果，**使用者已於 2026-11-12 確認全部照預設**，也記在 PREREGISTRATION 第 7 節。

## 1. 使用方式

都在 `~/Research-data-collection` 執行。

```
python3 -m pytest sim/tests                       # 單元測試（約 2 秒）

# P4：完整掃描（12 輪），中斷後用同一個指令續跑（已完成的 task 會跳過）
setsid nohup python3 -m sim.run_grid --out results > results/run_grid.log 2>&1 < /dev/null &
tail -f results/run_grid.log                      # 最後一行是 "run_grid: DONE"
```

選項：

- `--stage compute|aggregate`：只算快取或只重做彙整。
- `--seeds 1`、`--scenarios S1,S2`：只跑部分輪次。
- `--jobs N`：平行數，預設是 CPU 數 − 1。
- `--t2-stride`：T2 的預測時刻間隔，預設 1 秒。
- `--b3-cv-source`、`--b3-p0`、`--b3-k-mode`：B3 的替代解讀，見第 3 節。

快取設定記在 `<out>/cache/config.json`。用不同設定續跑同一個 `--out` 會被拒絕，必須換一個輸出目錄。

## 2. 檔案

| 檔案 | 內容 |
|---|---|
| `prereg.py` | PREREGISTRATION 的固定常數：週期、k、摘要、θ、ε、門檻 |
| `cost_model.py` | 5.1 的兩層成本模型，參數讀自 `cost/sim_params.json`（主分析 a = 556.7，敏感度 a = 884.8） |
| `producers.py` | 讀 trace（`FINAL.json` → `a<N>/upf_1s.parquet`）；producer 端每個區間的 mean／max／var 摘要 |
| `policies/` | B0、B1、B2、B3：每個 60 秒窗用的週期 `p_win`、每個 UE 的通知數與回報數、最大延遲 k × p |
| `consumers/t1.py` | T1 的 ground truth 與估計 |
| `consumers/t2.py` | T2 的特徵、目標、時間切分與 GBR |
| `metrics.py` | 相對誤差（10 kbps 下限）、p95、T2 誤差、新鮮度、c\*、c_static、regret、Pareto 前緣、R² |
| `run_grid.py` | 掃描與彙整（可續跑的快取） |
| `plots.py` | Pareto 圖、regret 對 ε 曲線 |
| `tests/` | 單元測試。`tests/data/fixture_240s.parquet` 是 3 個真實 UE 的前 240 秒（S2 突發、S1 固定、S3 閒置） |
| `check_outputs.py` | 輸出的獨立驗算（見第 4 節） |
| `smoke/` | P3 的 smoke run（只有 seed 1）。**不是正式結果**，正式結果由 P4 產生在 `results/` |
| `logs/` | 背景執行的 log |

### `run_grid.py` 的輸出（`<out>/`）

| 檔案 | 內容 |
|---|---|
| `tables/configs.csv` | 每個（情境, 設定）一列，3 個 seed 合併：<br>• 成本：`cost_main`、`cost_sensitivity`（bytes，3 輪合計）、`notifications`、`bytes_down`、`storage_bytes`、`duplicate_ratio`<br>• 新鮮度：`max_delay_s`、`t1_fresh`<br>• T1：平均值與峰值的 p95／中位數<br>• T2：`t2_err`、`t2_mae`、`t2_mae_full` |
| `tables/runs.csv` | 同上，但是每一輪（seed）分開 |
| `tables/regret.csv` | 主分析／敏感度 × T1／T2 × ε：<br>• 各情境的 c\*<br>• c_static 與 `regret_static`<br>• B3 最佳設定與 `regret_b3` |
| `tables/h1.csv` | B1 成本對 c\*(S, T, ε) 的減少比例，分情境列出，並有四情境合計（`scenario = all`） |
| `tables/h3.csv`、`h3_fit.csv` | UE 數 6／26／46 的通知數與 bytes（12 輪合計），以及線性迴歸的斜率、截距、R² |
| `tables/b3_periods.json` | B3 在每輪、每個 UE、每個窗用的週期 |
| `criteria.json` | 5.3 各判準要用的數字，以及和預先登記門檻的算術比較。**文字判斷由 P4 撰寫** |
| `figures/pareto_<S>_<T>.png`、`pareto_all.png` | 5.4 的 Pareto 圖：<br>• x 軸：每 UE 每小時的 kB（對數）<br>• y 軸：T1 = max(平均值 p95, 峰值 p95)；T2 = 誤差（symlog）<br>• 空心點：k·p > 60 秒，對 T1 不可行 |
| `figures/regret_vs_eps.png` | regret 對 ε ∈ {1, 2, 5, 10, 20}% 的曲線，左右兩張分別是主分析與敏感度 |
| `cache/` | 每輪的 `base.npz`（各設定的成本計數與 T1 誤差）、`t2/<key>.json`（每個 T2 模型的 MAE） |

## 3. 實作上的解讀

### 3.1 資料

- 吞吐量 = `ul_bytes × 8`（bit/s），用每個 UE 自己的格點 k = 0…1799（`traces/README.md`）。
  - 60 秒窗是 k 的 [60w, 60w + 60)，每輪 30 個窗。
  - `missing` 的格子以 0 計；P2 的 12 輪都是 0 缺漏。
- Producer 在每個 1 秒格點都有量測值，所以 producer 端能算出區間內的 mean、max 和 var（1 秒值的母體變異數）。
- `valid: false` 的輪次在 `configs.csv` 以 `all_runs_valid` 標註。目前 12 輪全部有效。

### 3.2 每個情境合併 3 個 seed

- T1 的 p95／中位數：把 3 輪 × 46 UE × 30 窗 = 4,140 個相對誤差合在一起計算。
- T2 誤差：合併 MAE 的比值，即 Σ|誤差| / 筆數。3 輪的測試筆數相同，所以等於 3 輪 MAE 平均值的比值。
- 成本：3 輪合計。
- `runs.csv` 另外列出每一輪的值。

### 3.3 T1

- 平均值估計 = 區間平均的平均。所有 p 都整除 60，所以一定精確（PREREGISTRATION 第 4 節的說明）。
- 峰值估計：
  - 摘要含 max 時，取區間 max 的最大值。因為 max 是 producer 從 1 秒值算出來的，所以這個估計也**精確**。
  - 只有 mean 時，取區間平均的最大值。
- 推論：
  - 任何「mean+max」或「mean+max+var」的 B2，以及所有 B3（固定 mean+max），T1 誤差都是 0。
  - T1 的成本差異只剩新鮮度（k·p ≤ 60）和 bytes。
  - 這是第 4 節定義的直接結果，不是實作錯誤；P4 報告時應說明。

### 3.4 T2

- **預測時刻**：每個 UE 每 1 秒一個，t = 60…1790；目標是 [t, t + 10) 的平均吞吐量。
- **可用的資料**：在 t 時，A-DCCF 只有已經結束的區間。令 b = 最後一個結束時間 ≤ t 的區間終點。
  - 特徵是 [b − 60, b) 內收到的統計量，再加上資料年齡 age = t − b。
  - age 讓粗週期的設定能反映「資料舊了多少」。p = 1 時 age 永遠是 0。
- **特徵表示**：
  - 固定週期（B2）：每個區間一欄（60/p × 統計量個數），稱為 compact。
  - 週期會變（B3）：每秒一欄，用分段常數表示（60 × 統計量個數）。
  - 兩種表示的資訊相同，測試 `test_t2_per_second_equals_compact_information` 驗證過。
- **訓練與測試**：
  - 每輪一個模型，46 個 UE 合併。
  - 訓練：目標區間在前 70% 內（t + 10 ≤ 1260）。
  - 測試：t ≥ 1260。
  - 中間 t = 1251–1259 的預測時刻不使用，避免訓練目標和測試期間重疊。
  - 單位 kbit/s。模型是 `GradientBoostingRegressor(random_state=0)`，其他參數用預設值。
- **全量模型**：B1 的 1 秒原始資料，等於 B2 的 p = 1、mean，共用同一個模型。
- **k 不影響 T2**：T2 是離線訓練，沒有新鮮度限制。不同 k 的 B2 共用同一個 T2 模型。
- **雜訊下限**：p = 1 時，max 等於 mean、var 等於 0，資訊和全量相同。
  - 但多出的欄位會改變決策樹拜訪特徵的順序，不同特徵同分時會選到不同的分割，所以誤差不是剛好 0。
  - 在測試 fixture 上差約 0.6%；真實 S1、S2 的差異小於 0.01 kbit/s。
  - 這代表 T2 誤差在 ε = 1% 附近有雜訊。
- **S1 的分母很小**：S1 是固定速率，全量模型的 MAE 很小（S1-seed1 約 0.7 kbit/s，平均吞吐量約 600 kbit/s）。
  - 粗週期反而比較準：p = 30 的 MAE 是 0.40，T2 誤差約 −44%，因為逐秒的封包抖動對預測只是雜訊。
  - 這是 3 節 T2 誤差定義（比值）本身的性質，列為限制。

### 3.5 策略與成本

- **B0**：2 個訂閱，每秒一筆原始量測，不打包。
  - 成本是 B1 的 2 倍，重複比例 0.5。
  - A-DCCF → 消費者的 bytes 是每個消費者收到自己的訂閱。
- **B1**：1 個訂閱，A-DCCF 分送給兩個消費者。B_down = 2 × B_up。
- **原始量測的成本**：每次回報用 b_raw = 488.93 B，所以每則 = 1,045.63 B，和 5.1 一致。
  - 摘要回報用 r + n_stat × s。
  - 表中的 r、s 是四捨五入值，r + 10s = 489.0 B，所以原始量測不用 r + 10s。
- **B2 的通知數**：每 UE ⌈(1800/p)/k⌉，45 組全部整除。B2 的成本和資料無關，所以四個情境相同。
- **c\* 與 c_static**：只從 B2 的 45 組中選（5.2）。B0、B1 只出現在 Pareto 圖和 H1 的比較基準。
  - 對 T1 的可行條件：k·p ≤ 60，而且平均值 p95 和峰值 p95 都 ≤ ε。
  - 對 T2 的可行條件：T2 誤差 ≤ ε。
  - 同成本時取設定列表中較前面的一組。
- **儲存量**：唯一回報數 × 回報 bytes（不含通知外框）。
- **敏感度分析**：所有策略（含 B0）一律把 a 換成 884.8 B，準確度不變（5.4）。

### 3.6 B3 ★（第 4 節沒有寫明的部分）

| 項目 | 採用的解讀 | 替代選項（命令列） | 理由 |
|---|---|---|---|
| CV 的來源 | **producer 端**最近 60 個 1 秒值的 std/mean（母體 std） | `--b3-cv-source received`：A-DCCF 收到的區間平均的 CV | B3 是在 B2（producer 端處理）上加規則。摘要固定 mean+max，A-DCCF 在 p = 60 時只有一個值，無法算 CV：p 一旦升到 60 就永遠不會降 |
| 平均為 0（閒置） | CV = 0，會升一級 | — | 沒有流量就不需要高解析度 |
| 決策時點 | 每個 60 秒窗結束時決定，套用在下一個窗；一次最多升或降一級 | — | 照第 4 節文字 |
| 起始週期 | **p₀ = 1 秒** | `--b3-p0 <s>` | 一開始沒有資料可算 CV，先用全解析度（和 B1 相同）。升到 60 秒需要 5 個窗 |
| k | **k = ⌊60/p⌋**，不限於 {1, 5, 10}：p = 1/2/5/10/30/60 → k = 60/30/12/6/2/1，每個 UE 每個窗剛好一則通知 | `--b3-k-mode grid`：{1, 5, 10} 中滿足 k·p ≤ 60 的最大值 | 第 4 節寫「k 取滿足新鮮度限制的最大值」，沒有說限於 B2 的 k 網格 |
| 打包 | 一則通知不混合不同週期的回報；週期改變時先送出 | — | 讓最大延遲 k·p 有明確定義 |

θ 組合：θ_low < θ_high 共 8 組。B3 的 regret 依 5.2，分母是 B2 的 Σ_S c\*(S)。

### 3.7 判準的數字（`criteria.json`）

- **H1**：同時列出「每個情境都 ≥ 50%」和「四情境合計 ≥ 50%」。正式判準是**每個情境都 ≥ 50%**（使用者 2026-11-12 確認，PREREGISTRATION 第 7 節），合計並列報告。
- **H2**：列出 ε = 2%、5%、10% 時 T1、T2 的 regret，以及是否有可行的靜態設定。
- **B3 檢查**：列出每個 ε 下 T1、T2 的 B3 regret。
- **H3**：
  - UE 子集：6 = `…001–006`，26 = 再加 `…101–120`，46 = 全部，和 P1 的 group 一致。
  - 數字是 12 輪合計的通知數與 bytes。
  - 策略：B0、B1、ε = 5% 的 c_static（T1、T2），以及 8 組 B3。
  - B0–B2 每個 UE 的成本固定，R² 必然是 1；只有 B3 和資料有關。

## 4. 執行時間

- smoke run（seed 1，4 輪，96 個 task，`--jobs 7`）：356 秒（`sim/logs/smoke_seed1.log`）。
  - 每個 T2 模型平行時約 1.5–60 秒，B3 和 p = 1 多統計量最慢。
- 完整 12 輪（288 個 task）：預估約 18 分鐘。
- 彙整（`--stage aggregate`）約 5 秒。
- `sim/check_outputs.py <out>`：不經快取、直接從 trace 重算部分數字並和輸出表核對。
  - 核對項目：B0／B1／B2 bytes、mean-only 的 T1 峰值 p95、暴力搜尋的 regret。
  - smoke 結果 60/60 一致。
