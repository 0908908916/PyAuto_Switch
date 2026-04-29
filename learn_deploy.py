#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║       Cisco Switch 自動化部署腳本（學習教學版）           ║
║                                                          ║
║  目的：透過 SSH 自動連線到 Switch 並推送設定指令          ║
║  作者：自動化部署學習腳本                                 ║
║  需求：pip install netmiko                               ║
╚══════════════════════════════════════════════════════════╝

【什麼是 Netmiko？】
  Netmiko 是一個 Python 套件，專門用來透過 SSH 連線到網路設備
  （Cisco、Juniper、HP 等），並自動發送指令、接收回應。
  就像你自己開 PuTTY 連進去打指令，但改成程式幫你做。

【整體流程】
  1. 程式讀取 Switch 的 IP / 帳號 / 密碼
  2. 自動建立 SSH 連線
  3. 進入 enable 模式（等同於你手動打 enable）
  4. 進入 configure terminal 模式
  5. 一條一條發送設定指令
  6. 執行 write memory 儲存設定
  7. 斷線，繼續下一台
"""

# ──────────────────────────────────────────────────────────
# 【匯入套件】
# 這裡載入程式需要用到的工具
# ──────────────────────────────────────────────────────────

import logging                          # 用來記錄執行過程（像日記一樣）
import os                               # 用來操作檔案和資料夾
from datetime import datetime           # 用來取得現在的時間（存 log 用）
from concurrent.futures import (        # 用來同時執行多個任務（多執行緒）
    ThreadPoolExecutor,
    as_completed
)

# Netmiko 的主要連線類別和例外錯誤處理
from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoTimeoutException,            # 連線逾時的錯誤
    NetmikoAuthenticationException      # 帳號密碼錯誤的錯誤
)


# ──────────────────────────────────────────────────────────
# 【日誌設定】
# logging 讓程式執行時把訊息同時印在畫面上，也存到檔案裡
# 這樣事後可以查看每台 Switch 到底做了什麼
# ──────────────────────────────────────────────────────────

LOG_DIR = "logs"                        # 日誌資料夾名稱
os.makedirs(LOG_DIR, exist_ok=True)     # 如果資料夾不存在就建立（exist_ok 代表已存在也不報錯）

logging.basicConfig(
    level=logging.INFO,                 # INFO 等級：顯示一般訊息（不顯示 debug 細節）
    format="%(asctime)s [%(levelname)s] %(message)s",  # 格式：時間 [等級] 訊息
    handlers=[
        # Handler 1：存到檔案（檔名包含執行時間，方便區分）
        logging.FileHandler(
            f"{LOG_DIR}/deploy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            encoding="utf-8"
        ),
        # Handler 2：同時印在 CMD 畫面上
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)    # 建立這支程式專屬的 logger


# ──────────────────────────────────────────────────────────
# 【Switch 設備清單】
#
# 這裡定義要連線的 Switch 資訊
# 每一個 {} 代表一台 Switch，填入對應的資料
#
# 欄位說明：
#   ip       → Switch 的管理 IP（就是你 SSH 連進去的那個 IP）
#   hostname → Switch 的名稱（只是方便識別，不影響連線）
#   username → SSH 登入帳號（你在 Console 設定的那個）
#   password → SSH 登入密碼
#   secret   → Enable 密碼（進入特權模式用的）
# ──────────────────────────────────────────────────────────

SWITCHES = [
    {
        "ip":       "192.168.1.1",      # ← 改成你 SW-01 的實際 IP
        "hostname": "SW-01",
        "username": "admin",            # ← 改成你設定的帳號
        "password": "Cisco123!",        # ← 改成你設定的密碼
        "secret":   "Enable123!",       # ← 改成你設定的 enable 密碼
    }
]


# ──────────────────────────────────────────────────────────
# 【全域設定】
#
# 這裡定義要推送到所有 Switch 的設定內容
# 修改這裡就能控制所有 Switch 要套用什麼設定
# ──────────────────────────────────────────────────────────

CONFIG = {
    # VLAN 清單：每個 VLAN 有 id（編號）和 name（名稱）
    "vlans": [
        {"id": 10,  "name": "Management"},  # 管理用 VLAN
        {"id": 20,  "name": "Users"},        # 使用者 VLAN
        {"id": 30,  "name": "Servers"},      # 伺服器 VLAN
        {"id": 999, "name": "BlackHole"},    # 未使用 port 丟這裡（安全用途）
    ],

    # NTP 伺服器：讓 Switch 校時，確保時間正確（log 的時間戳記很重要）
    "ntp_servers": ["192.168.1.254"],        # ← 改成你的 NTP 伺服器 IP

    # DNS 伺服器：讓 Switch 可以解析網域名稱
    "dns_servers":  ["8.8.8.8", "8.8.4.4"],
    "domain_name":  "company.local",         # ← 改成你的網域名稱

    # Syslog：讓 Switch 把日誌送到中央伺服器
    "syslog_server": "192.168.1.200",        # ← 改成你的 Syslog 伺服器 IP

    # STP（Spanning Tree Protocol）模式
    # rapid-pvst = 802.1w，現代 Cisco 推薦使用
    "stp_mode": "rapid-pvst",

    # Access Port：接一般使用者電腦的 port（只走一個 VLAN）
    "access_ports": [
        "GigabitEthernet0/1",
        "GigabitEthernet0/2",
        "GigabitEthernet0/3",
    ],

    # Trunk Port：接其他 Switch 或 Router 的 port（走多個 VLAN）
    "trunk_ports": [
        "GigabitEthernet0/24",
    ],

    # 未使用的 Port：關閉並丟進 BlackHole VLAN（安全最佳實踐）
    "unused_ports": [
        "GigabitEthernet0/20",
        "GigabitEthernet0/21",
    ],

    # Access Port 要走的 VLAN
    "access_vlan": 20,

    # 同時連線的 Switch 數量（2 台就設 2，10 台可以設 10）
    "max_workers": 1,

    # SSH 連線逾時秒數
    "ssh_timeout": 30,
}


# ──────────────────────────────────────────────────────────
# 【指令產生函式】
#
# 每個函式負責產生一類設定的指令清單
# 回傳的是一個 list，裡面每個字串就是一條 CLI 指令
# 這樣等等可以一次全部送給 Switch 執行
# ──────────────────────────────────────────────────────────

def build_vlan_commands(vlans: list) -> list:
    """
    產生 VLAN 設定指令

    【實際效果等同於在 Switch 手動打：】
        SW(config)# vlan 10
        SW(config-vlan)# name Management
        SW(config)# vlan 20
        SW(config-vlan)# name Users
        ...
    """
    cmds = []
    for v in vlans:
        cmds.append(f"vlan {v['id']}")          # 建立 VLAN
        cmds.append(f" name {v['name']}")        # 設定 VLAN 名稱
    return cmds


def build_ntp_commands(servers: list) -> list:
    """
    產生 NTP 校時指令

    【實際效果等同於：】
        SW(config)# ntp server 192.168.1.254
    """
    return [f"ntp server {s}" for s in servers]


def build_dns_commands(servers: list, domain: str) -> list:
    """
    產生 DNS 設定指令

    【實際效果等同於：】
        SW(config)# ip domain-name company.local
        SW(config)# ip name-server 8.8.8.8
    """
    cmds = [f"ip domain-name {domain}"]
    for s in servers:
        cmds.append(f"ip name-server {s}")
    return cmds


def build_syslog_commands(server: str) -> list:
    """
    產生 Syslog 設定指令
    讓 Switch 的 log 自動送到中央 Syslog 伺服器

    【實際效果等同於：】
        SW(config)# logging host 192.168.1.200
        SW(config)# logging trap informational
        SW(config)# logging on
    """
    return [
        f"logging host {server}",
        "logging trap informational",
        "logging on",
    ]


def build_stp_commands(mode: str) -> list:
    """
    產生 STP 設定指令
    STP 防止網路迴圈，rapid-pvst 是較快的收斂版本

    【實際效果等同於：】
        SW(config)# spanning-tree mode rapid-pvst
    """
    return [f"spanning-tree mode {mode}"]


def build_port_commands(access_ports, trunk_ports, unused_ports, access_vlan) -> list:
    """
    產生 Port 設定指令

    【Access Port 等同於：】
        SW(config)# interface GigabitEthernet0/1
        SW(config-if)# switchport mode access
        SW(config-if)# switchport access vlan 20
        SW(config-if)# spanning-tree portfast        ← 讓 port 快速 up
        SW(config-if)# spanning-tree bpduguard enable ← 防止接上別的 Switch
        SW(config-if)# no shutdown

    【Trunk Port 等同於：】
        SW(config)# interface GigabitEthernet0/24
        SW(config-if)# switchport mode trunk
        SW(config-if)# switchport trunk allowed vlan all

    【未使用 Port 等同於：】
        SW(config)# interface GigabitEthernet0/20
        SW(config-if)# switchport access vlan 999
        SW(config-if)# shutdown                      ← 關閉，防止未授權連線
    """
    cmds = []

    # Access Port 設定
    for port in access_ports:
        cmds += [
            f"interface {port}",
            " switchport mode access",
            f" switchport access vlan {access_vlan}",
            " switchport nonegotiate",          # 關閉 DTP 自動協商
            " spanning-tree portfast",
            " spanning-tree bpduguard enable",
            " no shutdown",
        ]

    # Trunk Port 設定
    for port in trunk_ports:
        cmds += [
            f"interface {port}",
            " switchport mode trunk",
            " switchport trunk allowed vlan all",
            " switchport nonegotiate",
            " no shutdown",
        ]

    # 未使用 Port → 關閉 + 隔離
    for port in unused_ports:
        cmds += [
            f"interface {port}",
            " switchport mode access",
            " switchport access vlan 999",      # 丟進 BlackHole VLAN
            " shutdown",                         # 關閉 port
        ]

    return cmds


def build_security_commands() -> list:
    """
    產生安全強化指令

    【包含：】
    - 登入失敗 5 次鎖定 120 秒（防暴力破解）
    - VTY 只允許 SSH（不允許 Telnet）
    - 關閉 HTTP 管理介面
    - 關閉 CDP（減少資訊洩露）
    - 開啟密碼加密
    - 時間戳記（方便查 log）
    """
    return [
        "login block-for 120 attempts 5 within 60",  # 暴力破解防護
        "line vty 0 15",
        " transport input ssh",                       # 只允許 SSH
        " exec-timeout 10 0",                         # 閒置 10 分鐘自動斷線
        " login local",
        "exit",
        "line con 0",
        " exec-timeout 10 0",
        "exit",
        "no ip http server",                          # 關閉 HTTP
        "no ip http secure-server",                   # 關閉 HTTPS
        "no cdp run",                                 # 關閉 CDP
        "no ip source-route",
        "service password-encryption",               # 加密設定檔裡的密碼
        "service timestamps log datetime msec",       # log 加時間戳記
        "service timestamps debug datetime msec",
    ]


def build_all_commands(sw_info: dict, cfg: dict) -> list:
    """
    整合所有指令，回傳完整的指令清單

    這個函式把上面所有 build_xxx 函式的結果合併在一起
    最後送給 Switch 執行的就是這份清單
    """
    cmds = []
    cmds += build_vlan_commands(cfg["vlans"])
    cmds += build_ntp_commands(cfg["ntp_servers"])
    cmds += build_dns_commands(cfg["dns_servers"], cfg["domain_name"])
    cmds += build_syslog_commands(cfg["syslog_server"])
    cmds += build_stp_commands(cfg["stp_mode"])
    cmds += build_port_commands(
        cfg["access_ports"],
        cfg["trunk_ports"],
        cfg["unused_ports"],
        cfg["access_vlan"]
    )
    cmds += build_security_commands()
    return cmds


# ──────────────────────────────────────────────────────────
# 【部署單台 Switch 的函式】
#
# 這個函式負責：
#   1. 建立 SSH 連線
#   2. 進入 enable 模式
#   3. 推送所有設定指令
#   4. 儲存設定（write memory）
#   5. 回傳結果（成功或失敗）
# ──────────────────────────────────────────────────────────

def deploy_switch(sw_info: dict, cfg: dict) -> dict:
    """
    部署單台 Switch

    參數：
        sw_info → 這台 Switch 的資訊（IP、帳號、密碼等）
        cfg     → 全域設定（要推送的設定內容）

    回傳：
        dict → 包含 ip、hostname、status（OK/FAIL）、message
    """

    ip = sw_info["ip"]
    hostname = sw_info.get("hostname", ip)  # 如果沒有 hostname 就用 IP 代替

    # 預設結果為失敗，成功後再更新
    result = {
        "ip":       ip,
        "hostname": hostname,
        "status":   "FAIL",
        "message":  ""
    }

    # ── 連線參數（傳給 Netmiko 的格式）──
    device = {
        "device_type": "cisco_ios",     # 告訴 Netmiko 這是 Cisco IOS 設備
        "host":        ip,              # Switch 的 IP
        "username":    sw_info.get("username", "admin"),
        "password":    sw_info.get("password", ""),
        "secret":      sw_info.get("secret", ""),   # Enable 密碼
        "timeout":     cfg.get("ssh_timeout", 30),  # 連線逾時秒數
        "banner_timeout": 20,           # 等待 banner 訊息的秒數
    }

    try:
        logger.info(f"[{hostname}] 開始 SSH 連線到 {ip} ...")

        # ── with 語法：連線成功後自動在結束時斷線 ──
        with ConnectHandler(**device) as conn:

            # 進入 enable 模式（等同於手動打 enable + 輸入密碼）
            conn.enable()
            logger.info(f"[{hostname}] 已進入 enable 模式")

            # 產生要推送的指令清單
            commands = build_all_commands(sw_info, cfg)
            logger.info(f"[{hostname}] 準備推送 {len(commands)} 條指令")

            # ── 發送指令 ──
            # send_config_set 會自動：
            #   1. 輸入 configure terminal
            #   2. 逐條發送指令
            #   3. 輸入 end 離開設定模式
            output = conn.send_config_set(
                commands,
                delay_factor=1.5        # 每條指令之間的延遲倍數（網路慢時調大）
            )

            # 儲存設定（等同於手動打 write memory）
            save_output = conn.save_config()
            logger.info(f"[{hostname}] 設定已儲存（write memory）")

            # 把這台 Switch 的完整輸出存到獨立 log 檔
            log_path = f"{LOG_DIR}/{hostname}_{ip}.txt"
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"=== {hostname} ({ip}) ===\n")
                f.write(f"時間：{datetime.now()}\n\n")
                f.write("--- 指令輸出 ---\n")
                f.write(output + "\n")
                f.write("--- 儲存設定輸出 ---\n")
                f.write(save_output + "\n")

            # 更新結果為成功
            result["status"] = "OK"
            result["message"] = f"成功推送 {len(commands)} 條指令"
            logger.info(f"[{hostname}] ✅ 部署完成！")

    # ── 例外處理：各種可能的錯誤 ──

    except NetmikoAuthenticationException:
        # 帳號密碼錯誤
        result["message"] = "認證失敗，請確認帳號密碼是否正確"
        logger.error(f"[{hostname}] ❌ {result['message']}")

    except NetmikoTimeoutException:
        # 連線逾時（IP 不通或 Switch 沒回應）
        result["message"] = "連線逾時，請確認 IP 是否正確且網路可達"
        logger.error(f"[{hostname}] ❌ {result['message']}")

    except Exception as e:
        # 其他未預期的錯誤
        result["message"] = str(e)
        logger.error(f"[{hostname}] ❌ 未預期錯誤：{e}")

    return result


# ──────────────────────────────────────────────────────────
# 【批次部署函式】
#
# 使用 ThreadPoolExecutor 同時連線多台 Switch
# 就像同時開多個 PuTTY 視窗，但由程式自動管理
# ──────────────────────────────────────────────────────────

def deploy_all(switches: list, cfg: dict) -> None:
    """
    批次部署所有 Switch

    【多執行緒概念】
    max_workers = 2 代表同時連 2 台
    如果有 10 台，程式會先連前 2 台
    其中一台完成後，立刻接著連第 3 台，以此類推
    """

    total = len(switches)
    success = 0
    failed = 0
    results = []

    logger.info(f"{'='*55}")
    logger.info(f"開始部署 {total} 台 Switch（同時連線數：{cfg['max_workers']}）")
    logger.info(f"{'='*55}")

    # ThreadPoolExecutor：建立執行緒池
    with ThreadPoolExecutor(max_workers=cfg["max_workers"]) as executor:

        # 把每台 Switch 的部署任務丟進執行緒池
        # futures 是一個 dict：{任務物件: switch 資訊}
        futures = {
            executor.submit(deploy_switch, sw, cfg): sw
            for sw in switches
        }

        # as_completed：哪台先完成就先處理哪台的結果
        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            if result["status"] == "OK":
                success += 1
            else:
                failed += 1

    # ── 印出部署報表 ──
    print(f"\n{'='*60}")
    print(f"  📋 部署完成報表  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    print(f"  總計：{total} 台  ✅ 成功：{success}  ❌ 失敗：{failed}")
    print(f"{'='*60}")

    # 依 hostname 排序顯示
    for r in sorted(results, key=lambda x: x["hostname"]):
        icon = "✅" if r["status"] == "OK" else "❌"
        print(f"  {icon}  {r['hostname']:<12} {r['ip']:<18} {r['message']}")

    print(f"{'='*60}")
    print(f"  📁 詳細 log 請查看 {LOG_DIR}/ 資料夾")
    print(f"{'='*60}\n")


# ──────────────────────────────────────────────────────────
# 【主程式入口】
#
# Python 慣例：if __name__ == "__main__" 代表
# 「直接執行這支程式時才執行以下程式碼」
# 如果這支程式被別的程式 import，就不會自動執行
# ──────────────────────────────────────────────────────────

if __name__ == "__main__":

    # ── 執行前確認提示 ──
    print("\n" + "="*60)
    print("  Cisco Switch 自動化部署腳本")
    print("="*60)
    print(f"  準備部署 {len(SWITCHES)} 台 Switch：")
    for sw in SWITCHES:
        print(f"    → {sw['hostname']}  {sw['ip']}")
    print("="*60)

    # 讓使用者確認後再執行（避免誤觸）
    confirm = input("\n  確認開始部署？(y/n)：").strip().lower()

    if confirm == "y":
        deploy_all(SWITCHES, CONFIG)
    else:
        print("  已取消部署。")
