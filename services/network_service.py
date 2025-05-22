import os
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
import config
from models.network_models import NetworkInterface, NetworkConfig, Route
from services.file_service import find_network_files, write_config_file, get_interface_config_file
from services.system_service import discover_network_interfaces, get_active_routes, reload_networkd, \
    get_interface_link_status
from utils.config_parser import parse_network_file, generate_network_config, should_exclude_systemd_route
from utils.validators import validate_network_config

logger = logging.getLogger(__name__)


def filter_user_configurable_routes(routes: List[Dict]) -> List[Route]:
    """
    Filter routes to only include user-configurable ones.

    Args:
        routes: List of route dictionaries

    Returns:
        List[Route]: Filtered list of Route objects
    """
    filtered_routes = []

    for route_data in routes:
        destination = route_data.get('destination', '')
        gateway = route_data.get('gateway', '')

        # 跳过应该被排除的路由
        if should_exclude_systemd_route(destination, gateway):
            logger.debug(f"Filtering out route: {destination} via {gateway}")
            continue

        filtered_routes.append(Route(
            destination=destination,
            gateway=gateway
        ))

    return filtered_routes


def get_all_interfaces() -> List[NetworkInterface]:
    """
    Get information about all network interfaces.

    Returns:
        List[NetworkInterface]: List of network interface objects
    """
    interfaces = []

    # Get all system interfaces
    system_interfaces = discover_network_interfaces()

    # Get all network files
    network_files = find_network_files()

    # Get active routes for all interfaces
    active_routes = get_active_routes()

    # Create a mapping of interface names to their configuration files
    interface_configs = {}
    for file_path in network_files:
        interface_name, config_data = parse_network_file(file_path)
        if interface_name and config_data:
            interface_configs[interface_name] = {
                'file_path': file_path,
                'config': config_data
            }

    # Create NetworkInterface objects for each system interface
    for interface_name in system_interfaces:
        interface = NetworkInterface(interface_name=interface_name)

        # Get link status for this interface
        link_status = get_interface_link_status(interface_name)

        # If we have configuration for this interface, add it
        if interface_name in interface_configs:
            config_data = interface_configs[interface_name]
            interface.config_file = config_data['file_path']
            interface.ipv4_addresses = config_data['config']['ipv4_addresses']
            interface.ipv6_addresses = config_data['config']['ipv6_addresses']
            interface.ipv4_gateway = config_data['config']['ipv4_gateway']
            interface.ipv6_gateway = config_data['config']['ipv6_gateway']
            interface.dns = config_data['config']['dns']

            # 过滤systemd-networkd路由
            interface.systemd_networkd_routes = filter_user_configurable_routes(
                config_data['config']['systemd_networkd_routes']
            )

        # Set status based on link status
        if link_status == 'up':
            interface.status = "up"
        elif link_status == 'down':
            interface.status = "down"
        elif link_status == 'no-carrier':
            interface.status = "no-carrier"
        else:
            interface.status = "unknown"

        # Add active system routes (这些已经在system_service.py中过滤过了)
        if interface_name in active_routes:
            interface.active_system_routes = active_routes[interface_name]

        interfaces.append(interface)

    # Sort interfaces by name
    interfaces.sort(key=lambda x: x.interface_name)

    return interfaces


def get_interface(interface_name: str) -> Optional[NetworkInterface]:
    """
    Get information about a specific network interface.

    Args:
        interface_name: Name of the interface

    Returns:
        Optional[NetworkInterface]: Network interface object if found, None otherwise
    """
    # Verify that the interface exists
    system_interfaces = discover_network_interfaces()
    if interface_name not in system_interfaces:
        return None

    # Create a new NetworkInterface object
    interface = NetworkInterface(interface_name=interface_name)

    # Get link status for this interface
    link_status = get_interface_link_status(interface_name)

    # Get configuration file for this interface
    config_file = get_interface_config_file(interface_name)
    if config_file:
        interface.config_file = config_file
        _, config_data = parse_network_file(config_file)

        if config_data:
            interface.ipv4_addresses = config_data['ipv4_addresses']
            interface.ipv6_addresses = config_data['ipv6_addresses']
            interface.ipv4_gateway = config_data['ipv4_gateway']
            interface.ipv6_gateway = config_data['ipv6_gateway']
            interface.dns = config_data['dns']

            # 过滤systemd-networkd路由
            interface.systemd_networkd_routes = filter_user_configurable_routes(
                config_data['systemd_networkd_routes']
            )

    # Set status based on link status
    if link_status == 'up':
        interface.status = "up"
    elif link_status == 'down':
        interface.status = "down"
    elif link_status == 'no-carrier':
        interface.status = "no-carrier"
    else:
        interface.status = "unknown"

    # Get active routes for this interface (这些已经在system_service.py中过滤过了)
    active_routes = get_active_routes()
    if interface_name in active_routes:
        interface.active_system_routes = active_routes[interface_name]

    return interface


def configure_interface(interface_name: str, config_data: Dict[str, Any]) -> Tuple[bool, Union[NetworkInterface, str]]:
    """
    Configure a network interface.

    Args:
        interface_name: Name of the interface
        config_data: Configuration data

    Returns:
        Tuple containing:
        - bool: Success status
        - Union[NetworkInterface, str]: NetworkInterface object if successful, error message otherwise
    """
    # Validate interface existence
    system_interfaces = discover_network_interfaces()
    if interface_name not in system_interfaces:
        return False, f"Interface {interface_name} does not exist"

    # Validate configuration data
    validation_result = validate_network_config(config_data)
    if validation_result is not True:
        return False, f"Invalid configuration: {', '.join(validation_result)}"

    # Get current interface configuration
    current_interface = get_interface(interface_name)

    # Create a new NetworkInterface object with the updated configuration
    new_interface = NetworkInterface(
        interface_name=interface_name,
        config_file=f"{config.NETWORK_CONFIG_DIR}{interface_name}.network",
        ipv4_addresses=config_data.get('ipv4_addresses', []),
        ipv6_addresses=config_data.get('ipv6_addresses', []),
        ipv4_gateway=config_data.get('ipv4_gateway'),
        ipv6_gateway=config_data.get('ipv6_gateway'),
        dns=config_data.get('dns', []),
        status="configured"
    )

    # Add routes from the configuration (with filtering)
    if 'routes' in config_data and config_data['routes']:
        for route_data in config_data['routes']:
            destination = route_data['destination']
            gateway = route_data['gateway']

            # 只添加用户应该能配置的路由
            if not should_exclude_systemd_route(destination, gateway):
                new_interface.systemd_networkd_routes.append(
                    Route(destination=destination, gateway=gateway)
                )
            else:
                logger.warning(f"Skipping excluded route: {destination} via {gateway}")

    # Add active system routes that are not managed by systemd-networkd
    if current_interface and current_interface.active_system_routes:
        managed_routes = set()
        if current_interface.systemd_networkd_routes:
            managed_routes = {(route.destination, route.gateway) for route in current_interface.systemd_networkd_routes}

        # Add non-managed active routes to the new configuration
        for route in current_interface.active_system_routes:
            route_key = (route.destination, route.gateway)
            if (route_key not in managed_routes and
                    route.destination not in ['0.0.0.0/0', '::/0'] and
                    not should_exclude_systemd_route(route.destination, route.gateway or '')):
                new_interface.systemd_networkd_routes.append(route)

    # Generate configuration file content
    config_content = generate_network_config(new_interface)

    # Write configuration to file
    success, error = write_config_file(f"{interface_name}.network", config_content)
    if not success:
        return False, f"Failed to write configuration file: {error}"

    return True, new_interface