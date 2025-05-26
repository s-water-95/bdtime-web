from flask import Blueprint, jsonify
from services.monitor_service import get_system_stats, get_detailed_cpu_info, get_detailed_memory_info
import logging

logger = logging.getLogger(__name__)

monitor_bp = Blueprint('monitor', __name__, url_prefix='/api/monitor')


@monitor_bp.route('/system_stats', methods=['GET'])
def get_system_statistics():
    """
    获取当前系统的CPU和内存使用情况的最新快照数据

    Returns:
        JSON response containing:
        - cpu_percent: CPU使用率百分比
        - memory: 内存使用情况 (total_gb, used_gb, free_gb, percent)
        - timestamp: 数据采集时间戳
    """
    success, result = get_system_stats()

    if not success:
        logger.error(f"Failed to get system statistics: {result}")
        return jsonify({'error': result}), 500

    logger.debug("System statistics retrieved successfully")
    return jsonify(result), 200


@monitor_bp.route('/cpu_details', methods=['GET'])
def get_cpu_details():
    """
    获取详细的CPU信息（可选接口，用于未来功能扩展）

    Returns:
        JSON response containing detailed CPU information
    """
    success, result = get_detailed_cpu_info()

    if not success:
        logger.error(f"Failed to get CPU details: {result}")
        return jsonify({'error': result}), 500

    return jsonify(result), 200


@monitor_bp.route('/memory_details', methods=['GET'])
def get_memory_details():
    """
    获取详细的内存信息（可选接口，用于未来功能扩展）

    Returns:
        JSON response containing detailed memory information
    """
    success, result = get_detailed_memory_info()

    if not success:
        logger.error(f"Failed to get memory details: {result}")
        return jsonify({'error': result}), 500

    return jsonify(result), 200


@monitor_bp.route('/health', methods=['GET'])
def health_check():
    """
    监控服务健康检查接口

    Returns:
        JSON response indicating service health status
    """
    try:
        # 简单的健康检查：尝试获取系统统计信息
        success, _ = get_system_stats()

        if success:
            return jsonify({
                'status': 'healthy',
                'service': 'monitor',
                'message': 'Monitor service is operational'
            }), 200
        else:
            return jsonify({
                'status': 'unhealthy',
                'service': 'monitor',
                'message': 'Failed to collect system statistics'
            }), 503

    except Exception as e:
        logger.exception("Health check failed")
        return jsonify({
            'status': 'error',
            'service': 'monitor',
            'message': f'Health check error: {str(e)}'
        }), 500