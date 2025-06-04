from flask import Blueprint, jsonify, request
from services.ntp_monitor_service import (
    start_monitoring, stop_monitoring, restart_monitoring,
    get_monitor_status, list_all_monitoring_status, cleanup_stale_pids
)
import logging

logger = logging.getLogger(__name__)

# 创建NTP监控蓝图
ntp_bp = Blueprint('ntp', __name__, url_prefix='/api/ntp')


@ntp_bp.route('/interfaces/<interface_name>/start', methods=['POST'])
def start_interface_monitoring(interface_name: str):
    """
    启动指定网卡的NTP监控

    Args:
        interface_name: 网卡名称

    Request Body (JSON, 可选):
        - port (int): NTP端口，默认123
        - timeout (float): 配对超时时间，默认2.0秒
        - output_file (str): 输出文件路径，可选

    Returns:
        JSON response containing:
        - success (bool): 操作是否成功
        - message (str): 操作结果消息
        - interface (str): 网卡名称
        - data (dict): 启动后的状态信息 (成功时)
    """
    try:
        # 解析请求参数
        data = request.get_json() if request.is_json else {}

        port = data.get('port', 123)
        timeout = data.get('timeout', 2.0)
        output_file = data.get('output_file')

        # 参数验证
        if not isinstance(port, int) or port <= 0 or port > 65535:
            return jsonify({
                'success': False,
                'message': 'Invalid port number. Must be between 1 and 65535',
                'interface': interface_name
            }), 400

        if not isinstance(timeout, (int, float)) or timeout <= 0:
            return jsonify({
                'success': False,
                'message': 'Invalid timeout value. Must be positive number',
                'interface': interface_name
            }), 400

        # 启动监控
        success, message = start_monitoring(interface_name, port, timeout, output_file)

        if success:
            # 获取启动后的状态
            status = get_monitor_status(interface_name)
            logger.info(f"Successfully started NTP monitoring for {interface_name}")

            return jsonify({
                'success': True,
                'message': message,
                'interface': interface_name,
                'data': status
            }), 201
        else:
            logger.warning(f"Failed to start NTP monitoring for {interface_name}: {message}")
            return jsonify({
                'success': False,
                'message': message,
                'interface': interface_name
            }), 400

    except Exception as e:
        logger.exception(f"Error starting NTP monitoring for {interface_name}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}',
            'interface': interface_name
        }), 500


@ntp_bp.route('/interfaces/<interface_name>/stop', methods=['POST'])
def stop_interface_monitoring(interface_name: str):
    """
    停止指定网卡的NTP监控

    Args:
        interface_name: 网卡名称

    Returns:
        JSON response containing:
        - success (bool): 操作是否成功
        - message (str): 操作结果消息
        - interface (str): 网卡名称
        - data (dict): 停止后的状态信息 (成功时)
    """
    try:
        # 停止监控
        success, message = stop_monitoring(interface_name)

        if success:
            # 获取停止后的状态
            status = get_monitor_status(interface_name)
            logger.info(f"Successfully stopped NTP monitoring for {interface_name}")

            return jsonify({
                'success': True,
                'message': message,
                'interface': interface_name,
                'data': status
            }), 200
        else:
            logger.warning(f"Failed to stop NTP monitoring for {interface_name}: {message}")
            return jsonify({
                'success': False,
                'message': message,
                'interface': interface_name
            }), 400

    except Exception as e:
        logger.exception(f"Error stopping NTP monitoring for {interface_name}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}',
            'interface': interface_name
        }), 500


@ntp_bp.route('/interfaces/<interface_name>/restart', methods=['POST'])
def restart_interface_monitoring(interface_name: str):
    """
    重启指定网卡的NTP监控

    Args:
        interface_name: 网卡名称

    Request Body (JSON, 可选):
        - port (int): NTP端口，默认123
        - timeout (float): 配对超时时间，默认2.0秒
        - output_file (str): 输出文件路径，可选

    Returns:
        JSON response containing:
        - success (bool): 操作是否成功
        - message (str): 操作结果消息
        - interface (str): 网卡名称
        - data (dict): 重启后的状态信息 (成功时)
    """
    try:
        # 解析请求参数
        data = request.get_json() if request.is_json else {}

        port = data.get('port', 123)
        timeout = data.get('timeout', 2.0)
        output_file = data.get('output_file')

        # 参数验证
        if not isinstance(port, int) or port <= 0 or port > 65535:
            return jsonify({
                'success': False,
                'message': 'Invalid port number. Must be between 1 and 65535',
                'interface': interface_name
            }), 400

        if not isinstance(timeout, (int, float)) or timeout <= 0:
            return jsonify({
                'success': False,
                'message': 'Invalid timeout value. Must be positive number',
                'interface': interface_name
            }), 400

        # 重启监控
        success, message = restart_monitoring(interface_name, port, timeout, output_file)

        if success:
            # 获取重启后的状态
            status = get_monitor_status(interface_name)
            logger.info(f"Successfully restarted NTP monitoring for {interface_name}")

            return jsonify({
                'success': True,
                'message': message,
                'interface': interface_name,
                'data': status
            }), 200
        else:
            logger.warning(f"Failed to restart NTP monitoring for {interface_name}: {message}")
            return jsonify({
                'success': False,
                'message': message,
                'interface': interface_name
            }), 400

    except Exception as e:
        logger.exception(f"Error restarting NTP monitoring for {interface_name}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}',
            'interface': interface_name
        }), 500


@ntp_bp.route('/interfaces/<interface_name>/status', methods=['GET'])
def get_interface_monitoring_status(interface_name: str):
    """
    获取指定网卡的NTP监控状态

    Args:
        interface_name: 网卡名称

    Returns:
        JSON response containing:
        - success (bool): 操作是否成功
        - interface (str): 网卡名称
        - data (dict): 监控状态信息
    """
    try:
        # 获取监控状态
        status = get_monitor_status(interface_name)

        logger.debug(f"Retrieved NTP monitoring status for {interface_name}")

        return jsonify({
            'success': True,
            'interface': interface_name,
            'data': status
        }), 200

    except Exception as e:
        logger.exception(f"Error getting NTP monitoring status for {interface_name}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}',
            'interface': interface_name
        }), 500


@ntp_bp.route('/interfaces/status', methods=['GET'])
def get_all_interfaces_monitoring_status():
    """
    获取所有网卡的NTP监控状态

    Returns:
        JSON response containing:
        - success (bool): 操作是否成功
        - count (int): 网卡数量
        - data (list): 所有网卡的监控状态列表
    """
    try:
        # 获取所有监控状态
        status_list = list_all_monitoring_status()

        logger.debug(f"Retrieved NTP monitoring status for {len(status_list)} interfaces")

        return jsonify({
            'success': True,
            'count': len(status_list),
            'data': status_list
        }), 200

    except Exception as e:
        logger.exception("Error getting all NTP monitoring status")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@ntp_bp.route('/cleanup', methods=['POST'])
def cleanup_stale_processes():
    """
    清理无效的PID文件

    Returns:
        JSON response containing:
        - success (bool): 操作是否成功
        - message (str): 操作结果消息
        - cleaned_count (int): 清理的PID文件数量
    """
    try:
        # 清理无效PID文件
        cleaned_count = cleanup_stale_pids()

        logger.info(f"Cleaned up {cleaned_count} stale PID files")

        return jsonify({
            'success': True,
            'message': f'Successfully cleaned up {cleaned_count} stale PID files',
            'cleaned_count': cleaned_count
        }), 200

    except Exception as e:
        logger.exception("Error cleaning up stale PID files")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@ntp_bp.route('/health', methods=['GET'])
def ntp_health_check():
    """
    NTP监控服务健康检查接口

    Returns:
        JSON response indicating NTP monitoring service health status
    """
    try:
        # 获取所有监控状态作为健康检查
        status_list = list_all_monitoring_status()

        # 统计监控状态
        total_interfaces = len(status_list)
        running_count = sum(1 for status in status_list if status.get('is_monitoring', False))

        return jsonify({
            'status': 'healthy',
            'service': 'ntp_monitor',
            'message': 'NTP monitoring service is operational',
            'stats': {
                'total_interfaces': total_interfaces,
                'running_monitors': running_count,
                'stopped_monitors': total_interfaces - running_count
            }
        }), 200

    except Exception as e:
        logger.exception("NTP monitoring health check failed")
        return jsonify({
            'status': 'unhealthy',
            'service': 'ntp_monitor',
            'message': f'Health check error: {str(e)}'
        }), 503


# 错误处理器
@ntp_bp.errorhandler(404)
def ntp_not_found(error):
    """处理404错误"""
    return jsonify({
        'success': False,
        'message': 'NTP monitoring endpoint not found'
    }), 404


@ntp_bp.errorhandler(405)
def ntp_method_not_allowed(error):
    """处理405错误"""
    return jsonify({
        'success': False,
        'message': 'Method not allowed for this NTP monitoring endpoint'
    }), 405


@ntp_bp.errorhandler(500)
def ntp_server_error(error):
    """处理500错误"""
    logger.exception("Internal server error in NTP monitoring")
    return jsonify({
        'success': False,
        'message': 'Internal server error in NTP monitoring service'
    }), 500