import os

# Network configuration paths
NETWORK_CONFIG_DIR = "/etc/systemd/network/"
# NETWORK_CONFIG_BACKUP_DIR = "/etc/systemd/network/backups/"
NETWORK_CONFIG_BACKUP_DIR = "/opt/network-backups/"
NETWORK_INTERFACES_SYS_PATH = "/sys/class/net/"

# Excluded network interfaces
EXCLUDED_INTERFACES = ["bonding_masters", "sit0", "lo"]

# Application configuration
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

# Commands
RESTART_NETWORKD_CMD = "systemctl restart systemd-networkd"
RELOAD_NETWORKD_CMD = "networkctl reload"
IP_ROUTE_CMD = "ip route show"
IP_ROUTE6_CMD = "ip -6 route show"

# NTP Monitor configuration
# NTP监控相关配置
NTP_PID_DIR = os.environ.get("NTP_PID_DIR", "/tmp/ntp_monitor/")
"""
NTP监控进程PID文件和日志文件的存储目录
默认使用 /tmp/ntp_monitor/，生产环境建议使用 /var/run/ntp_monitor/
目录需要确保运行Flask应用的用户有读写权限
"""

# 获取ntp_worker.py脚本的绝对路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
NTP_WORKER_SCRIPT_PATH = os.environ.get("NTP_WORKER_SCRIPT_PATH",
                                       os.path.join(_current_dir, "ntp_worker.py"))
"""
ntp_worker.py脚本的绝对路径
默认假设ntp_worker.py与config.py在同一目录下
可通过环境变量NTP_WORKER_SCRIPT_PATH指定自定义路径
"""

# NTP监控默认配置
NTP_DEFAULT_PORT = 123
"""默认NTP端口"""

NTP_DEFAULT_TIMEOUT = 2.0
"""默认数据包配对超时时间（秒）"""

# 确保NTP_PID_DIR目录存在
try:
    os.makedirs(NTP_PID_DIR, exist_ok=True)
except Exception:
    # 如果无法创建目录，回退到当前目录下的临时目录
    NTP_PID_DIR = os.path.join(_current_dir, "tmp_ntp_monitor")
    os.makedirs(NTP_PID_DIR, exist_ok=True)

# 验证ntp_worker.py脚本是否存在
if not os.path.exists(NTP_WORKER_SCRIPT_PATH):
    # 如果脚本不存在，记录警告但不阻止应用启动
    import logging
    logging.getLogger(__name__).warning(
        f"NTP worker script not found at {NTP_WORKER_SCRIPT_PATH}. "
        "NTP monitoring features will not work properly."
    )