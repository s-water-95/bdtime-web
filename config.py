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

# 新增：NTP历史客户端数据库和数据接收配置
NTP_DB_PATH = os.environ.get("NTP_DB_PATH",
                             os.path.join(_current_dir, "data", "ntp_clients.db"))
"""
SQLite数据库文件的绝对路径
用于存储历史NTP客户端数据
默认存储在应用目录下的data/ntp_clients.db
"""

NTP_INGESTION_HOST = os.environ.get("NTP_INGESTION_HOST", "127.0.0.1")
"""
NTP数据接收服务监听的IP地址
默认监听本地回环地址，确保安全性
生产环境可根据需要调整
"""

NTP_INGESTION_PORT = int(os.environ.get("NTP_INGESTION_PORT", "10000"))
"""
NTP数据接收服务监听的端口
默认使用10000端口，请确保该端口未被占用
如果运行多个Flask实例，需要使用不同的端口
"""

NTP_BATCH_SIZE = int(os.environ.get("NTP_BATCH_SIZE", "100"))
"""
数据处理服务批量写入数据库的记录数
默认100条记录批量写入，平衡性能和实时性
较大的批量大小可以提高写入性能但增加延迟
"""

NTP_BATCH_INTERVAL_SECONDS = float(os.environ.get("NTP_BATCH_INTERVAL_SECONDS", "5.0"))
"""
数据处理服务批量写入数据库的最大等待时间（秒）
默认5秒，即使未达到批量大小也会强制写入
确保数据不会无限期等待
"""

# 确保必要的目录存在
try:
    # 确保NTP_PID_DIR目录存在
    os.makedirs(NTP_PID_DIR, exist_ok=True)

    # 确保NTP数据库目录存在
    ntp_db_dir = os.path.dirname(NTP_DB_PATH)
    os.makedirs(ntp_db_dir, exist_ok=True)

except Exception:
    # 如果无法创建目录，回退到当前目录下的临时目录
    import logging

    logger = logging.getLogger(__name__)

    try:
        NTP_PID_DIR = os.path.join(_current_dir, "tmp_ntp_monitor")
        os.makedirs(NTP_PID_DIR, exist_ok=True)

        NTP_DB_PATH = os.path.join(_current_dir, "tmp_data", "ntp_clients.db")
        os.makedirs(os.path.dirname(NTP_DB_PATH), exist_ok=True)

        logger.warning(f"使用回退目录: PID目录={NTP_PID_DIR}, 数据库={NTP_DB_PATH}")
    except Exception as fallback_error:
        logger.error(f"无法创建回退目录: {fallback_error}")

# 验证ntp_worker.py脚本是否存在
if not os.path.exists(NTP_WORKER_SCRIPT_PATH):
    # 如果脚本不存在，记录警告但不阻止应用启动
    import logging

    logging.getLogger(__name__).warning(
        f"NTP worker script not found at {NTP_WORKER_SCRIPT_PATH}. "
        "NTP monitoring features will not work properly."
    )


# 配置验证和警告
def validate_config():
    """验证配置参数的有效性"""
    warnings = []

    # 验证端口范围
    if not (1024 <= NTP_INGESTION_PORT <= 65535):
        warnings.append(f"NTP_INGESTION_PORT ({NTP_INGESTION_PORT}) 建议使用1024-65535范围内的端口")

    # 验证批量配置
    if NTP_BATCH_SIZE <= 0:
        warnings.append(f"NTP_BATCH_SIZE ({NTP_BATCH_SIZE}) 必须大于0")

    if NTP_BATCH_INTERVAL_SECONDS <= 0:
        warnings.append(f"NTP_BATCH_INTERVAL_SECONDS ({NTP_BATCH_INTERVAL_SECONDS}) 必须大于0")

    # 验证目录权限
    try:
        # 测试PID目录写权限
        test_file = os.path.join(NTP_PID_DIR, ".test_write")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
    except Exception:
        warnings.append(f"NTP_PID_DIR ({NTP_PID_DIR}) 目录无写权限")

    try:
        # 测试数据库目录写权限
        db_dir = os.path.dirname(NTP_DB_PATH)
        test_file = os.path.join(db_dir, ".test_write")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
    except Exception:
        warnings.append(f"NTP数据库目录 ({os.path.dirname(NTP_DB_PATH)}) 无写权限")

    if warnings:
        import logging
        logger = logging.getLogger(__name__)
        for warning in warnings:
            logger.warning(f"配置警告: {warning}")


# 在模块加载时验证配置
validate_config()

# 导出主要配置供外部使用
__all__ = [
    'NETWORK_CONFIG_DIR', 'NETWORK_CONFIG_BACKUP_DIR', 'NETWORK_INTERFACES_SYS_PATH',
    'EXCLUDED_INTERFACES', 'DEBUG', 'HOST', 'PORT',
    'RESTART_NETWORKD_CMD', 'RELOAD_NETWORKD_CMD', 'IP_ROUTE_CMD', 'IP_ROUTE6_CMD',
    'NTP_PID_DIR', 'NTP_WORKER_SCRIPT_PATH', 'NTP_DEFAULT_PORT', 'NTP_DEFAULT_TIMEOUT',
    'NTP_DB_PATH', 'NTP_INGESTION_HOST', 'NTP_INGESTION_PORT',
    'NTP_BATCH_SIZE', 'NTP_BATCH_INTERVAL_SECONDS'
]