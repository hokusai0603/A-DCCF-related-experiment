# 執行須知

給執行 MVE 各階段的 session 看。規劃書說明「做什麼、為什麼」，這份文件說明「怎麼安全地做、什麼時候要停」。

## 1. 每個 session 的開始與結束

**開始**：

1. 從家目錄 `~` 開 session，這樣 memory（testbed 的已知問題）會自動載入。
2. 依序讀 `PROGRESS.md` → 本文件 → 規劃書中該階段的章節 → 第 4 節列出的該階段必讀文件。
3. **一個 session 只做一個階段。** 做完該階段的驗收條件就停下來，不要接著做下一階段。

**結束**：在 `PROGRESS.md` 新增一筆紀錄（格式見該檔），內容包含：完成了什麼、驗收結果、改了哪些檔案、備份放在哪裡、遇到的問題，以及【待確認】項目的驗證結論。

## 2. 硬性規則（任何情況都不能違反）

| # | 規則 | 原因 |
|---|---|---|
| 1 | **不刪除任何 VM**，也不刪除 VM 的磁碟或 snapshot | 使用者 2026-11-09 的決定 |
| 2 | **不開機 I-UPF、I-UPF2**；本實驗只開 5GC、UPF-EES、UPF-EES2、gNB、gNB2、MEC、MEC2 | I-UPF 和 UPF-EES 共用 `192.168.103.10`、`192.168.105.10`，同時開機會 IP 衝突 |
| 3 | VM 一律在各自目錄用 `vagrant up`（或 `deploy.sh`）開機；`VBoxManage` 只用來 `controlvm <id> reset` 卡住的 VM | 用 `VBoxManage startvm` 開機，vboxsf 掛載（`/vagrant`、`/config`）會失敗 |
| 4 | **不新增 VM** | 主機磁碟只剩約 15 GB；規劃書 4.4 只保留備查 |
| 5 | infra repo（`~/free5gc-NWDAF/5G_Infrastructure`）**有大量既有的未 commit 修改**：不要 `git stash`、`git checkout -- <file>`、`git reset`、`git clean`，也**不要在這個 repo commit 或 push** | 會毀掉或混入使用者既有的修改 |
| 6 | 修改任何 testbed 設定檔之前，先把**目前的工作目錄版本**複製到 `backup/<YYYY-MM-DD>/`（保留相對路徑），修改後在同一目錄存一份 `changes.diff` | 還原時直接把備份複製回去；不依賴 git |
| 7 | 修改 MongoDB 的訂閱者資料之前，先在 5GC VM 內用 `mongodump` 匯出備份，放到 `backup/<日期>/` | 訂閱者資料目前只有手動建立的 6 筆 |
| 8 | 每次跑流量或收 trace 之前，用 `df -h ~` 檢查主機剩餘空間；**低於 8 GB 就停止**並回報 | 磁碟用光會讓 VM 異常 |
| 9 | 每個 slice 的總流量 ≤ 50 Mbps | VM 橋接在校園網路 `eno1` 上 |
| 10 | 主機的 `sudo` 需要密碼：需要 root 的主機端操作，寫成腳本交給使用者執行。VM 內的 `vagrant` 帳號可以直接 `sudo` | session 無法輸入密碼 |
| 11 | 只修改設定檔與 `scripts/` 內的腳本；**不修改 NWDAF、SMF、UPF 的程式碼** | 需要改程式碼代表規劃書的假設不成立，必須先和使用者討論 |
| 12 | **P2 開始前，`PREREGISTRATION.md` 的狀態必須是「已核准」**；P2 之後不得修改其中的判準 | 避免事後調整門檻 |

## 3. 什麼時候必須停下來問使用者

- 任何【待確認】項目的驗證結果和規劃書不同（例如 1 秒回報不穩定、webconsole 沒有批次 API）。
- 需要偏離規劃書或 `PREREGISTRATION.md`：UE 數、IMSI 號段、情境參數、ε、參數掃描範圍。
- 需要修改程式碼（規則 11）。
- 同一台 VM 在同一個 session 內需要 reset 兩次以上。
- UE 註冊或 PDU session 失敗，而且原因不在第 4 節列出的檢查清單裡。
- P4 的結果出來之後：**只依 `PREREGISTRATION.md` 的規則報告結果，不自行做 go/no-go 以外的延伸結論**。

以下事項可以自行決定，不需要問：腳本的實作細節、`scripts/`、`sim/` 內的檔案安排、暫時性失敗的重試、log 的格式。

## 4. 各階段的必讀文件與起始指令

infra repo 以下簡稱 `INFRA` = `~/free5gc-NWDAF/5G_Infrastructure`。

### P0：UE 擴充到 46 個並驗收（規劃書 4.1–4.3、4.5，5 的 P0）

必讀：

- `INFRA/README.md`：拓樸、啟動順序（Quick Start）
- `INFRA/DOCUMENTATION.md`：webconsole 的使用方式、UE 和路由設定
- `INFRA/config/5GC/nwdafcfg.yaml`（`groupMembership`、`samplingInterval`）、`smfcfg.yaml`、`uerouting.yaml`
- `INFRA/config/UERAN/ue*.yaml`、`gNB/run.sh`、`gNB2/run.sh`
- `INFRA/NWDAF/docs/impl/nwdaf-uecomm-consumer-tutorial.md`、`INFRA/NWDAF/nwdaf_uecomm_consumer/`：如何建立 group 訂閱
- `~/Design-doc/upf-ees design/2026-10-21-upf-ees-fixes-and-testbed-validation.md`：UPF-EES 的行為與限制

起始指令：

```
讀 ~/Research-data-collection/README.md，依其中的順序讀文件，然後只執行 P0：
UE 擴充到 46 個，並依規劃書 4.5 驗收。嚴格遵守 EXECUTION_GUIDE.md 的硬性規則與停止條件。
結束前更新 PROGRESS.md。
```

### P1：成本模型量測（規劃書 5 的 P1）

必讀：P0 的 `PROGRESS.md` 紀錄；UPF-EES 測試報告中通知格式、h2c 與重試行為的段落。

起始指令：

```
讀 ~/Research-data-collection/README.md，依其中的順序讀文件，然後只執行 P1：成本模型量測。
量測原始資料與擬合結果放在 cost/。嚴格遵守 EXECUTION_GUIDE.md。結束前更新 PROGRESS.md。
```

### P2：Ground-truth trace 收集（規劃書 5 的 P2）

前提：`PREREGISTRATION.md` 已核准。必讀：`PREREGISTRATION.md` 第 2、3 節（情境參數、品質規則）。

起始指令：

```
讀 ~/Research-data-collection/README.md，依其中的順序讀文件。確認 PREREGISTRATION.md 已核准後，只執行 P2：
依 PREREGISTRATION.md 收集 ground-truth trace，放在 traces/。每輪開始前檢查磁碟。
嚴格遵守 EXECUTION_GUIDE.md。結束前更新 PROGRESS.md。
```

### P3：A-DCCF 模擬器（規劃書 5 的 P3）

不需要開 testbed。必讀：`PREREGISTRATION.md` 全文、`cost/` 的成本模型、`traces/` 的格式說明。

起始指令：

```
讀 ~/Research-data-collection/README.md，依其中的順序讀文件，然後只執行 P3：
在 sim/ 實作 A-DCCF 模擬器，策略、消費者、指標與參數掃描完全依照 PREREGISTRATION.md。
先用小段 trace 寫單元測試驗證指標計算。結束前更新 PROGRESS.md。
```

### P4：分析（規劃書 5 的 P4）

起始指令：

```
讀 ~/Research-data-collection/README.md，依其中的順序讀文件，然後只執行 P4：
執行 sim/run_grid.py，依 PREREGISTRATION.md 第 5 節產生結果表、Pareto 圖與 regret 曲線，放在 results/，
並依預先登記的規則寫出 H1、H2、H3 的判斷。不要自行調整判準。結束前更新 PROGRESS.md。
```
