import ipaddress
import re
from typing import List, Dict, Any, Union, Optional


def validate_ip_address(ip: str) -> bool:
    """
    Validate if the given string is a valid IPv4 or IPv6 address with optional CIDR notation.

    Args:
        ip: IP address string potentially with CIDR notation (e.g., "192.168.1.1/24" or "2001:db8::1/64")

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        # If CIDR notation is not included, add a default one for validation
        if '/' not in ip:
            test_ip = ip + '/32' if ':' not in ip else ip + '/128'
        else:
            test_ip = ip

        ipaddress.ip_network(test_ip, strict=False)
        return True
    except (ValueError, TypeError):
        return False


def validate_route(route: Dict[str, str]) -> bool:
    """
    Validate if the given route dictionary has valid destination and gateway.

    Args:
        route: Dictionary containing route information

    Returns:
        bool: True if valid, False otherwise
    """
    if not isinstance(route, dict):
        return False

    if 'destination' not in route or 'gateway' not in route:
        return False

    # Destination should be a valid network (with CIDR)
    try:
        ipaddress.ip_network(route['destination'])
    except (ValueError, TypeError):
        return False

    # Gateway should be a valid IP address (without CIDR)
    try:
        gateway = route['gateway']
        if '/' in gateway:
            return False
        ipaddress.ip_address(gateway)
        return True
    except (ValueError, TypeError):
        return False


def validate_network_config(config: Dict[str, Any]) -> Union[List[str], bool]:
    """
    Validate the network configuration data.

    Args:
        config: Network configuration dictionary

    Returns:
        Union[List[str], bool]: List of error messages if invalid, True if valid
    """
    errors = []

    # Validate interface name
    if 'interface_name' not in config or not config['interface_name']:
        errors.append("Interface name is required")

    # Validate IPv4 addresses
    if 'ipv4_addresses' in config and config['ipv4_addresses']:
        for addr in config['ipv4_addresses']:
            if not validate_ip_address(addr) or ':' in addr:  # Ensure it's IPv4
                errors.append(f"Invalid IPv4 address format: {addr}")

    # Validate IPv6 addresses
    if 'ipv6_addresses' in config and config['ipv6_addresses']:
        for addr in config['ipv6_addresses']:
            if not validate_ip_address(addr) or ':' not in addr:  # Ensure it's IPv6
                errors.append(f"Invalid IPv6 address format: {addr}")

    # Validate IPv4 gateway
    if 'ipv4_gateway' in config and config['ipv4_gateway']:
        if not validate_ip_address(config['ipv4_gateway']) or ':' in config['ipv4_gateway']:
            errors.append(f"Invalid IPv4 gateway format: {config['ipv4_gateway']}")

    # Validate IPv6 gateway
    if 'ipv6_gateway' in config and config['ipv6_gateway']:
        if not validate_ip_address(config['ipv6_gateway']) or ':' not in config['ipv6_gateway']:
            errors.append(f"Invalid IPv6 gateway format: {config['ipv6_gateway']}")

    # Validate DNS servers
    if 'dns' in config and config['dns']:
        for dns in config['dns']:
            if not validate_ip_address(dns):
                errors.append(f"Invalid DNS server address: {dns}")

    # Validate routes
    if 'routes' in config and config['routes']:
        for route in config['routes']:
            if not validate_route(route):
                errors.append(f"Invalid route configuration: {route}")

    return errors if errors else True