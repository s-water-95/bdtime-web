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