import os
import logging
from typing import List, Dict, Any, Tuple, Optional
from utils.command_executor import execute_command
from models.network_models import Route
import config

logger = logging.getLogger(__name__)


def discover_network_interfaces() -> List[str]:
    """
    Discover network interfaces from the system.

    Returns:
        List[str]: List of interface names
    """
    interfaces = []

    try:
        # Read network interfaces from /sys/class/net/
        for interface in os.listdir(config.NETWORK_INTERFACES_SYS_PATH):
            if interface not in config.EXCLUDED_INTERFACES:
                interfaces.append(interface)
    except Exception as e:
        logger.exception("Error discovering network interfaces")

    return interfaces


def get_interface_link_status(interface_name: str) -> str:
    """
    Get the link status of a network interface.

    Args:
        interface_name: Name of the interface

    Returns:
        str: Link status ('up', 'down', 'no-carrier', 'unknown')
    """
    try:
        # 检查接口是否启用
        operstate_path = f"/sys/class/net/{interface_name}/operstate"
        if os.path.exists(operstate_path):
            with open(operstate_path, 'r') as f:
                operstate = f.read().strip()

            # 如果接口未启用，直接返回down
            if operstate == 'down':
                return 'down'

            # 检查carrier状态（链路是否连通）
            carrier_path = f"/sys/class/net/{interface_name}/carrier"
            if os.path.exists(carrier_path):
                try:
                    with open(carrier_path, 'r') as f:
                        carrier = f.read().strip()

                    if carrier == '1':
                        return 'up'  # 链路正常
                    else:
                        return 'no-carrier'  # 链路断开（网线未插好）
                except (OSError, IOError):
                    # carrier文件可能在接口down的时候无法读取
                    return 'no-carrier'

            # 如果无法读取carrier，根据operstate判断
            if operstate == 'up':
                return 'up'
            elif operstate == 'unknown':
                return 'unknown'
            else:
                return 'no-carrier'

        # 如果无法读取operstate，使用ip命令检查
        success, output, _ = execute_command(f"ip link show {interface_name}")
        if success and output:
            if 'state UP' in output:
                return 'up'
            elif 'state DOWN' in output:
                if 'NO-CARRIER' in output:
                    return 'no-carrier'
                else:
                    return 'down'

        return 'unknown'

    except Exception as e:
        logger.exception(f"Error getting link status for {interface_name}")
        return 'unknown'


def get_interface_speed(interface_name: str) -> Optional[int]:
    """
    Get the speed of a network interface in Mbps.

    Args:
        interface_name: Name of the interface

    Returns:
        Optional[int]: Speed in Mbps, None if unavailable
    """
    try:
        speed_path = f"/sys/class/net/{interface_name}/speed"
        if os.path.exists(speed_path):
            with open(speed_path, 'r') as f:
                speed = f.read().strip()
                return int(speed)
    except (OSError, IOError, ValueError):
        pass

    return None


def should_exclude_route(destination: str, gateway: Optional[str], dev: Optional[str]) -> bool:
    """
    Determine if a route should be excluded from the results.

    Args:
        destination: Route destination
        gateway: Route gateway
        dev: Route device

    Returns:
        bool: True if route should be excluded
    """
    # 排除的目标网络模式
    excluded_destinations = [
        'multicast',
        'broadcast',
        'local',
        'unreachable',
        'prohibit',
        'blackhole',
        'throw'
    ]

    # 排除的网关值
    excluded_gateways = [
        'None',
        '',
        '0.0.0.0',
        '::',
        'null'
    ]

    # 1. 排除特定的目标网络
    if destination.lower() in excluded_destinations:
        return True

    # 2. 排除链路本地路由 (IPv6)
    if destination.startswith('fe80::/64'):
        return True

    # 3. 排除组播地址范围的路由
    if destination.startswith('224.0.0.0/') or destination.startswith('ff00::/'):
        return True

    # 4. 排除网关为None或空的路由（除了直连路由）
    if gateway and gateway.lower() in [g.lower() for g in excluded_gateways]:
        return True

    # 5. 排除主机路由中的特殊地址
    if '/32' in destination or '/128' in destination:
        ip_part = destination.split('/')[0]
        # 排除本地地址
        if ip_part in ['127.0.0.1', '::1']:
            return True
        # 排除链路本地地址
        if ip_part.startswith('169.254.') or ip_part.startswith('fe80:'):
            return True

    return False


def get_active_routes() -> Dict[str, List[Route]]:
    """
    Get active routes from the system using 'ip route show' command.

    Returns:
        Dict[str, List[Route]]: Dictionary mapping interface names to their active routes
    """
    interface_routes = {}

    # Get IPv4 routes
    success, output, _ = execute_command(config.IP_ROUTE_CMD)
    if success and output:
        for line in output.split('\n'):
            if not line.strip():
                continue

            # Parse route line
            parts = line.split()
            if not parts:
                continue

            destination = parts[0]

            # Handle default routes
            if destination == 'default':
                destination = '0.0.0.0/0'

            # Find gateway and device
            gateway = None
            dev = None

            for i, part in enumerate(parts):
                if part == 'via' and i + 1 < len(parts):
                    gateway = parts[i + 1]
                elif part == 'dev' and i + 1 < len(parts):
                    dev = parts[i + 1]

            # Skip routes that should be excluded
            if should_exclude_route(destination, gateway, dev):
                logger.debug(f"Excluding IPv4 route: {destination} via {gateway} dev {dev}")
                continue

            if dev:
                route = Route(destination=destination, gateway=gateway, dev=dev)
                if dev not in interface_routes:
                    interface_routes[dev] = []
                interface_routes[dev].append(route)

    # Get IPv6 routes
    success, output, _ = execute_command(config.IP_ROUTE6_CMD)
    if success and output:
        for line in output.split('\n'):
            if not line.strip():
                continue

            # Parse route line
            parts = line.split()
            if not parts:
                continue

            destination = parts[0]

            # Handle default routes
            if destination == 'default':
                destination = '::/0'

            # Find gateway and device
            gateway = None
            dev = None

            for i, part in enumerate(parts):
                if part == 'via' and i + 1 < len(parts):
                    gateway = parts[i + 1]
                elif part == 'dev' and i + 1 < len(parts):
                    dev = parts[i + 1]

            # Skip routes that should be excluded
            if should_exclude_route(destination, gateway, dev):
                logger.debug(f"Excluding IPv6 route: {destination} via {gateway} dev {dev}")
                continue

            if dev:
                route = Route(destination=destination, gateway=gateway, dev=dev)
                if dev not in interface_routes:
                    interface_routes[dev] = []
                interface_routes[dev].append(route)

    return interface_routes


def reload_networkd() -> Tuple[bool, Optional[str]]:
    """
    Reload systemd-networkd service.

    Returns:
        Tuple[bool, Optional[str]]: Success status and error message if any
    """
    success, _, error = execute_command(config.RELOAD_NETWORKD_CMD)
    if not success:
        # If networkctl reload fails, try restarting the service
        success, _, error = execute_command(config.RESTART_NETWORKD_CMD)

    return success, error if not success else None