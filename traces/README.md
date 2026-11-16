# P2 ground-truth traces

PREREGISTRATION 2.1–2.3（已核准 2026-11-11）。46 UE × 4 情境 × seed 1/2/3，每輪 1800 秒，1 秒粒度。
Producer 是修正版 UPF（go-upf 682b469）＋SMF＋NWDAF（`scripts/newstack.sh`），資料來自 MongoDB
`free5gc.nwdaf.upfTrafficData`。

## 目錄

```
traces/
  README.md                  本文件
  summary.csv                12 輪的摘要（採用的 attempt、品質指標、總量）
  schedules/<S>-seed<n>.json  流量排程（scripts/p2_schedule.py 產生，執行前固定）
  <S>-seed<n>/FINAL.json      這一輪採用哪一次 attempt、是否有效（valid）
  <S>-seed<n>/a<k>/           第 k 次 attempt（無效的 attempt 也保留）
  pilot-*/                    正式收集前的 3 分鐘 pilot（不屬於 trace 集合）
  p2_all.log, boot-*.log      執行紀錄
```

**P3 使用方式**：每輪讀 `FINAL.json` 的 `final_attempt`，用 `a<final_attempt>/upf_1s.parquet`；
`valid: false` 的輪次要在結果中標註（PREREGISTRATION 2.3）。

## 每個 attempt 目錄

| 檔案 | 內容 |
|---|---|
| `upf_1s.parquet` | **ground truth**：SUPI × 秒（見下） |
| `upf_records.parquet` | 這一輪 MongoDB 的全部原始紀錄（含重複，已標記） |
| `iperf3_1s.parquet` | iperf3 client 每秒送出量，用和 `upf_1s` 相同的格點 |
| `iperf3_tests.parquet` | 每次 iperf3 啟動一列：排定／實際時間、送出 bytes、封包、遺失 |
| `quality.json` | 2.3 品質規則的結果與輔助指標；`valid` |
| `meta.json` | `t0`（排程起點，epoch 秒）、`since`（訂閱時間）、`duration_s` |
| `ue_check.csv` | 本輪每個 SUPI 的 UE IP、uesimtun、gNB（P0 4.5 #1/#2 驗證結果） |
| `plan-gNB*.json` | 實際交給 runner 的排程（含 UE IP、server、port） |
| `iperf3-gNB*.tgz`、`iperf3srv-MEC*.tgz` | iperf3 client JSON 原始輸出與 runner log；server log |
| `nwdaf_subs.log`、`upf_drops.txt`、`run.log` | correlationId→SUPI 對應、UPF dropping-window log 次數、執行 log |
| `mongo_deleted.json` | 匯出並回讀驗證後，從 MongoDB 刪除的本輪紀錄數 |

### `upf_1s.parquet`（46 × 1800 列）

| 欄位 | 型別 | 意義 |
|---|---|---|
| `supi` | str | `imsi-208930000000001` … |
| `k` | int | 秒序號 0…1799 |
| `ul_bytes`, `dl_bytes` | int64 | 該秒 UPF 量到的 UL/DL bytes |
| `ul_pkts`, `dl_pkts` | int64 | 該秒封包數 |
| `n_rec` | int | 落在這一格的紀錄數（正常 1；0 = 缺漏；2 = 碰撞，已加總） |
| `missing` | bool | 這一格沒有紀錄（bytes 填 0） |
| `phi_s` | float | 該 UE 的相位 φ（0–1 秒） |

**時間定義**（pilot 驗證）：

- MongoDB 的 `timestamp` 是約 1 秒量測區間的**起點** ts。紀錄量的是 [ts, ts+1)。
  - pilot 驗證：照這個定義對齊時，和 iperf3 每秒量的相關係數是 0.9999；若當成 [ts−1, ts) 只有 0.959。
  - 由 bytes×8/throughput 推得的平均區間長度是 1.0001 秒。
- 每個 UE 的紀錄時間相對 T0 有固定的小數相位 φ_u（各 UE 的 φ_u 是其 frac(ts − T0) 的圓形平均）。
  - 格點 k 對應 [T0 + φ_u + k, T0 + φ_u + k + 1)，k = round(ts − T0 − φ_u)。
  - 抖動約 ±0.1 秒，不會跨格。
  - 不同 UE 的格點最多錯開 1 秒以內；以 60 秒為窗分析時可以忽略。
  - 排程從 T0 開始，所以 [T0, T0 + φ_u) 的流量落在 k = −1，不在 1800 格內。總量比對使用全部紀錄。
- 重複紀錄以（SUPI, timestamp）去重，保留第一筆。
- `ul_bytes` 是 UDP payload：pilot 中逐 UE 的 UPF UL bytes = iperf3 payload，每個 UE 只多出約 8 個 iperf3 控制連線的 TCP 封包、約 450 B。
- 流量方向：iperf3 client 在 UE（gNB VM），server 在 MEC/MEC2，所以是 **UL**。
  - DL 只有 iperf3 控制連線的 TCP 回應。
  - PREREGISTRATION 的 T1/T2「吞吐量」以 `ul_bytes × 8` bps 計。

## 品質規則（PREREGISTRATION 2.3）的實作

- **總流量差距** = |Σ UPF UL bytes（全部去重紀錄） / Σ iperf3 client 送出 bytes − 1| ≤ 5%。
  - 不做 header 修正：pilot 顯示 UPF UL volume 就是 UDP payload。
  - 加上每封包 8 B 的版本列為輔助（`volume_ratio_hdr8`）。
- **缺漏秒數** = `missing` 格數 / (46 × 1800) ≤ 2%。
- 無效時自動重跑最多 2 次（`scripts/p2_all.sh`）。三次都無效時，保留最後一次並標記 `valid: false`。

## 流量排程（`schedules/`）

- `scripts/p2_schedule.py` 產生。
- 每個 UE 有一串 on-segment `[start_s, end_s, rate_bps]`（相對 T0），其餘時間不送。
- 亂數：`default_rng(SeedSequence([seed, ue_index, stream]))`。
- 各情境：
  - **S1**：每個 UE 整段固定速率，速率 ~ U[0.2, 1.0] Mbps。
  - **S2**：on ~ Exp(10 s)、off ~ Exp(30 s)，on 時 1 Mbps；起始狀態以 0.25 機率為 on。
  - **S3**：依 SUPI 順序固定分配 23 個 S1、14 個 S2、9 個閒置，各 seed 相同。
    - slice 1：S1 11、S2 7、閒置 5；slice 2：S1 12、S2 7、閒置 4。
  - **S4**：[0, 900) 用 S1，[900, 1800) 用新的 S2 過程。
- 每個 slice 的瞬間峰值負載最高 14.9 Mbps（規則 9 上限 50 Mbps）。
- runner（`scripts/p2_ue_runner.py`，在 gNB VM 內執行）：
  - 每段用一個 iperf3 3.7 UDP client：`-B <UE IP> -u -b <rate> -l 1200 -n <bytes>`，每個 UE 一個 server port。
  - bytes 在實際啟動時依剩餘時間計算，所以晚啟動時仍維持原定的結束時間。
  - 很短的 on 段（< 1 個封包）至少送 1 個 1200 B 封包。
  - 實際啟動延遲在 `iperf3_tests.parquet` 和 `quality.json` 的 `iperf3.launch_late_s`。
