import re
import os
from typing import Dict, List, Optional, Tuple
from models.network_models import NetworkInterface, Route

# Regular expressions for parsing systemd-networkd configuration files
MATCH_SECTION_REGEX = r'^\[Match\]$((?:\n[^[]+)*)'
NETWORK_SECTION_REGEX = r'^\[Network\]$((?:\n[^[]+)*)'
ROUTE_SECTION_REGEX = r'^\[Route\]$((?:\n[^[]+)*)'
DHCP_SECTION_REGEX = r'^\[DHCP\]$((?:\n[^[]+)*)'
ADDRESS_REGEX = r'Address\s*=\s*(.+)'
GATEWAY_REGEX = r'Gateway\s*=\s*(.+)'
DNS_REGEX = r'DNS\s*=\s*(.+)'
NAME_REGEX = r'Name\s*=\s*(.+)'
DESTINATION_REGEX = r'Destination\s*=\s*(.+)'


def should_exclude_systemd_route(destination: str, gateway: str) -> bool:
    """
    Determine if a systemd-networkd route should be excluded from user configuration.

    Args:
        destination: Route destination
        gateway: Route gateway

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
        'none',
        '',
        '0.0.0.0',
        '::',
        'null'
    ]

    # 1. 排除特定的目标网络（不区分大小写）
    if destination.lower() in excluded_destinations:
        return True

    # 2. 排除IPv6链路本地路由
    if destination.lower().startswith('fe80::/64'):
        return True

    # 3. 排除组播地址范围的路由
    if destination.startswith('224.0.0.0/') or destination.lower().startswith('ff00::/'):
        return True

    # 4. 排除网关为None或空的特殊路由
    if gateway and gateway.lower() in excluded_gateways:
        return True

    # 5. 排除本地环回相关路由
    if destination.startswith('127.0.0.0/') or destination.lower().startswith('::1/'):
        return True

    # 6. 排除链路本地地址路由
    if destination.startswith('169.254.0.0/') or destination.lower().startswith('fe80::/'):
        return True

    return False


def parse_network_file(file_path: str) -> Tuple[Optional[str], Optional[Dict]]:
    """
    Parse a systemd-networkd .network file and extract network configuration.

    Args:
        file_path: Path to the .network file

    Returns:
        Tuple containing:
        - Optional[str]: Interface name if found, None otherwise
        - Optional[Dict]: Dictionary with extracted configuration if successful, None otherwise
    """
    try:
        with open(file_path, 'r') as f:
            content = f.read()

        # Extract interface name from Match section
        match_section = re.search(MATCH_SECTION_REGEX, content, re.MULTILINE)
        if not match_section:
            return None, None

        match_content = match_section.group(1)
        name_match = re.search(NAME_REGEX, match_content, re.MULTILINE)
        if not name_match:
            return None, None

        interface_name = name_match.group(1).strip()

        # Initialize config dictionary
        config = {
            'ipv4_addresses': [],
            'ipv6_addresses': [],
            'ipv4_gateway': None,
            'ipv6_gateway': None,
            'dns': [],
            'systemd_networkd_routes': []
        }

        # Extract network section
        network_section = re.search(NETWORK_SECTION_REGEX, content, re.MULTILINE)
        if network_section:
            network_content = network_section.group(1)

            # Extract addresses
            for addr_match in re.finditer(ADDRESS_REGEX, network_content, re.MULTILINE):
                address = addr_match.group(1).strip()
                if ':' in address:  # IPv6
                    config['ipv6_addresses'].append(address)
                else:  # IPv4
                    config['ipv4_addresses'].append(address)

            # Extract gateways
            for gateway_match in re.finditer(GATEWAY_REGEX, network_content, re.MULTILINE):
                gateway = gateway_match.group(1).strip()
                if ':' in gateway:  # IPv6
                    config['ipv6_gateway'] = gateway
                else:  # IPv4
                    config['ipv4_gateway'] = gateway

            # Extract DNS servers
            for dns_match in re.finditer(DNS_REGEX, network_content, re.MULTILINE):
                dns_servers = dns_match.group(1).strip().split()
                config['dns'].extend(dns_servers)

        # Extract routes with filtering
        route_sections = re.finditer(r'\[Route\](?:\n[^[]+)*', content, re.MULTILINE)
        for route_section in route_sections:
            route_content = route_section.group(0)

            destination_match = re.search(DESTINATION_REGEX, route_content, re.MULTILINE)
            gateway_match = re.search(GATEWAY_REGEX, route_content, re.MULTILINE)

            if destination_match and gateway_match:
                destination = destination_match.group(1).strip()
                gateway = gateway_match.group(1).strip()

                # 过滤掉不应该显示给用户的路由
                if should_exclude_systemd_route(destination, gateway):
                    continue

                config['systemd_networkd_routes'].append({
                    'destination': destination,
                    'gateway': gateway
                })

        return interface_name, config
    except Exception as e:
        return None, None


def generate_network_config(interface: NetworkInterface) -> str:
    """
    Generate systemd-networkd configuration file content for a network interface.

    Args:
        interface: NetworkInterface object containing configuration data

    Returns:
        str: Generated configuration file content
    """
    config_content = [
        "[Match]",
        f"Name={interface.interface_name}",
        "",
        "[Network]"
    ]

    # Add addresses
    for addr in interface.ipv4_addresses:
        config_content.append(f"Address={addr}")

    for addr in interface.ipv6_addresses:
        config_content.append(f"Address={addr}")

    # Add gateways
    if interface.ipv4_gateway:
        config_content.append(f"Gateway={interface.ipv4_gateway}")

    if interface.ipv6_gateway:
        config_content.append(f"Gateway={interface.ipv6_gateway}")

    # Add DNS servers
    for dns in interface.dns:
        config_content.append(f"DNS={dns}")

    # Add routes (只添加用户配置的路由，不包括系统自动生成的路由)
    for route in interface.systemd_networkd_routes:
        # 在生成配置时也进行过滤，确保不写入不应该的路由
        if not should_exclude_systemd_route(route.destination, route.gateway):
            config_content.extend([
                "",
                "[Route]",
                f"Destination={route.destination}",
                f"Gateway={route.gateway}"
            ])

    # 确保文件以换行符结尾（Linux/Unix标准）
    return "\n".join(config_content) + "\n"