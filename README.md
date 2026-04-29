# Cisco Switch Network Automation Deployment Tool

這是一個基於 Python 與 Netmiko 開發的自動化網路設備部署工具。旨在解決多台 Cisco Switch 初始設定繁瑣、容易出錯的問題。

# 🌟 核心特色 (Core Features)

- **資料與邏輯分離**：將設備清單 (`SWITCHES`) 與網路規範 (`CONFIG`) 抽離，無需修改核心代碼即可快速適應不同客戶需求。
- **多執行緒併發處理 (Concurrency)**：導入 `ThreadPoolExecutor`，支援多台設備同時派送設定，大幅縮短維運窗口時間。
- **模組化指令產生器**：針對 VLAN、STP、Port Security 等功能撰寫獨立函式，具備極佳的擴充性。
- **強健的日誌系統**：自動生成時間戳記日誌，並為每台設備保留獨立的執行紀錄，確保變更具備稽核軌跡 (Audit Trail)。
- **異常處理機制**：實作 `try-except` 捕捉連線逾時或認證失敗，確保單一設備故障不影響整體自動化流程。

## 🛠️ 實戰場景 (Use Cases)

1.  **新點開局 (Greenfield Deployment)**：當有 20 台全新的 Switch 需要在 1 小時內上架時。
2.  **安全性合規更新**：全網設備統一關閉 HTTP 服務、更新 NTP 伺服器或修改 VTY 登入限制。
3.  **VLAN 批量調整**：快速調整多個 Port 的 VLAN 歸屬與 Spanning-tree 設定。

## 🚀 如何使用 (Quick Start)

### 1. 安裝必要套件

```bash
pip install -r requirements.txt
```

或
C:\Users\USER\AppData\Local\Programs\Python\Python313\Scripts\pip.exe install netmiko

說明與教學

📘 第一部分：環境準備（如何讓程式動起來）
在跑任何自動化程式之前，環境必須先 Ready。

1. 安裝 Python 與工具包
   確保你的電腦安裝了 Python 3。接著在終端機（CMD 或 Terminal）輸入：

Bash
pip install netmiko 2. Switch 端的預先設定（開門）
這份腳本是透過 SSH 連線。如果你的 Switch 是空的，必須先手動進 Console 打這幾行，否則腳本進不去：

Bash
conf t
hostname SW-01
ip domain-name lab.local
crypto key generate rsa general-keys modulus 2048 # 產生 SSH 密鑰
username admin privilege 15 password Cisco123! # 建立帳號
enable password Enable123! # 建立特權密碼
line vty 0 4
login local
transport input ssh # 只准 SSH 進來
exit
interface vlan 1
ip address 192.168.1.1 255.255.255.0 # 設定管理 IP
no shut

📗 第二部分：腳本操作指南（如何修改與執行）
這份腳本分為三個顏色區域，你只需要動「藍色」區域：

1. 修改設備資訊 (藍色區域)
   找到 SWITCHES 列表。這裡就像是「通訊錄」。

情境：如果你今天有 3 台要設，就複製 {} 裡的內容，貼成三份，改 IP 即可。

2. 修改網路規範 (藍色區域)
   找到 CONFIG 字典。這裡就像是「施工圖」。

VLAN ID：改這裡，全台 Switch 都會同步建立。

Port 規劃：

access_ports: 填入接電腦的孔。

trunk_ports: 填入接另一台 Switch 的孔。

unused_ports: 填入沒在用的孔（腳本會自動關掉它們，這叫「安全加固」）。

3. 執行與驗證
   執行 python cisco_deploy.py。

看到 「確認開始部署？(y/n)」 時，這是最後一道防線，輸入 y。

觀察畫面上的 ✅ 符號。如果出現 ❌，去 logs/ 資料夾看對應的 .txt 檔，裡面會記錄 Switch 報錯的內容。
以及還有 PDF 說明文件
<img width="1096" height="611" alt="執行示意圖" src="https://github.com/user-attachments/assets/2fb4b17e-c414-45b5-97a2-644c089c07e0" />


