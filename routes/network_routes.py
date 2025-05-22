from flask import Blueprint, jsonify, request
from services.network_service import get_all_interfaces, get_interface, configure_interface
from services.system_service import reload_networkd
import logging

logger = logging.getLogger(__name__)

network_bp = Blueprint('network', __name__, url_prefix='/api/network')

@network_bp.route('/interfaces', methods=['GET'])
def get_interfaces():
    """Get all network interfaces"""
    interfaces = get_all_interfaces()
    return jsonify([interface.to_dict() for interface in interfaces])


@network_bp.route('/interfaces/<interface_name>', methods=['GET'])
def get_interface_details(interface_name):
    """Get details for a specific network interface"""
    interface = get_interface(interface_name)

    if not interface:
        return jsonify({'error': f'Interface {interface_name} not found'}), 404

    return jsonify(interface.to_dict())


@network_bp.route('/interfaces/<interface_name>', methods=['POST'])
def configure_network_interface(interface_name):
    """Configure a network interface"""
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400

    config_data = request.get_json()

    # Ensure interface_name is consistent
    config_data['interface_name'] = interface_name

    success, result = configure_interface(interface_name, config_data)

    if not success:
        return jsonify({'error': result}), 400

    return jsonify(result.to_dict()), 201


@network_bp.route('/reload', methods=['POST'])
def reload_network():
    """Reload networkd configuration"""
    success, error = reload_networkd()

    if not success:
        return jsonify({'error': f'Failed to reload network configuration: {error}'}), 500

    return jsonify({'message': 'Network configuration reloaded successfully'}), 200