"""
NTP历史客户端查询API路由
提供历史NTP客户端数据的查询接口
"""

import math
from flask import Blueprint, jsonify, request
from services.ntp_data_ingestion_service import (
    get_historical_clients, get_client_detail,
    get_interface_statistics, get_service_stats
)
import logging

logger = logging.getLogger(__name__)

# 创建NTP历史查询蓝图
ntp_history_bp = Blueprint('ntp_history', __name__, url_prefix='/api/ntp/history')


@ntp_history_bp.route('/clients', methods=['GET'])
def get_clients_list():
    """
    获取历史NTP客户端列表

    Query Parameters:
        - page (int): 当前页码，默认1
        - page_size (int): 每页记录数，默认10，最大100
        - search_ip (str): 用于精确匹配的客户端IP地址
        - interface_name (str): 筛选特定网卡下发现的客户端

    Returns:
        JSON response containing:
        - success (bool): 操作是否成功
        - data (dict): 包含客户端列表和分页信息
            - clients (list): 客户端数据列表
            - pagination (dict): 分页信息
        - message (str): 响应消息
    """
    try:
        # 解析查询参数
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 10, type=int)
        search_ip = request.args.get('search_ip', '').strip()
        interface_name = request.args.get('interface_name', '').strip()

        # 参数验证
        if page < 1:
            return jsonify({
                'success': False,
                'message': 'Invalid page number. Must be >= 1'
            }), 400

        if page_size < 1 or page_size > 100:
            return jsonify({
                'success': False,
                'message': 'Invalid page_size. Must be between 1 and 100'
            }), 400

        # 处理空字符串参数
        search_ip = search_ip if search_ip else None
        interface_name = interface_name if interface_name else None

        # 查询数据
        clients, total_count = get_historical_clients(
            page=page,
            page_size=page_size,
            search_ip=search_ip,
            interface_name=interface_name
        )

        # 计算分页信息
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
        has_next = page < total_pages
        has_prev = page > 1

        pagination_info = {
            'current_page': page,
            'page_size': page_size,
            'total_count': total_count,
            'total_pages': total_pages,
            'has_next': has_next,
            'has_prev': has_prev,
            'next_page': page + 1 if has_next else None,
            'prev_page': page - 1 if has_prev else None
        }

        # 构建响应
        response_data = {
            'clients': clients,
            'pagination': pagination_info,
            'filters': {
                'search_ip': search_ip,
                'interface_name': interface_name
            }
        }

        logger.debug(f"返回 {len(clients)} 条客户端记录，总数: {total_count}")

        return jsonify({
            'success': True,
            'data': response_data,
            'message': f'Successfully retrieved {len(clients)} clients'
        }), 200

    except Exception as e:
        logger.exception("获取历史客户端列表失败")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@ntp_history_bp.route('/clients/<client_ip>', methods=['GET'])
def get_client_details(client_ip: str):
    """
    获取特定客户端的详细信息

    Args:
        client_ip: 客户端IP地址

    Returns:
        JSON response containing:
        - success (bool): 操作是否成功
        - data (dict): 客户端详细信息
        - message (str): 响应消息
    """
    try:
        # 参数验证
        if not client_ip or not client_ip.strip():
            return jsonify({
                'success': False,
                'message': 'Client IP address is required'
            }), 400

        client_ip = client_ip.strip()

        # 查询客户端详情
        client_detail = get_client_detail(client_ip)

        if client_detail:
            logger.debug(f"返回客户端详情: {client_ip}")
            return jsonify({
                'success': True,
                'data': client_detail,
                'message': f'Successfully retrieved client details for {client_ip}'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': f'Client {client_ip} not found'
            }), 404

    except Exception as e:
        logger.exception(f"获取客户端详情失败: {client_ip}")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@ntp_history_bp.route('/interfaces/statistics', methods=['GET'])
def get_interfaces_statistics():
    """
    获取各网卡的NTP客户端统计信息

    Returns:
        JSON response containing:
        - success (bool): 操作是否成功
        - data (list): 网卡统计信息列表
        - message (str): 响应消息
    """
    try:
        # 获取统计信息
        statistics = get_interface_statistics()

        logger.debug(f"返回 {len(statistics)} 个网卡的统计信息")

        return jsonify({
            'success': True,
            'data': statistics,
            'message': f'Successfully retrieved statistics for {len(statistics)} interfaces'
        }), 200

    except Exception as e:
        logger.exception("获取网卡统计信息失败")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@ntp_history_bp.route('/service/statistics', methods=['GET'])
def get_service_statistics():
    """
    获取NTP数据接收服务的统计信息

    Returns:
        JSON response containing:
        - success (bool): 操作是否成功
        - data (dict): 服务统计信息
        - message (str): 响应消息
    """
    try:
        # 获取服务统计信息
        stats = get_service_stats()

        logger.debug("返回服务统计信息")

        return jsonify({
            'success': True,
            'data': stats,
            'message': 'Successfully retrieved service statistics'
        }), 200

    except Exception as e:
        logger.exception("获取服务统计信息失败")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@ntp_history_bp.route('/search', methods=['POST'])
def advanced_search():
    """
    高级搜索历史NTP客户端

    Request Body (JSON):
        - filters (dict): 搜索过滤条件
            - client_ips (list): 客户端IP列表（OR条件）
            - interface_names (list): 网卡名称列表（OR条件）
            - date_range (dict): 时间范围
                - start_date (str): 开始日期 (ISO格式)
                - end_date (str): 结束日期 (ISO格式)
            - latency_range (dict): 延迟范围
                - min_latency (float): 最小延迟（秒）
                - max_latency (float): 最大延迟（秒）
        - sort (dict): 排序选项
            - field (str): 排序字段
            - order (str): 排序顺序 ('asc' 或 'desc')
        - pagination (dict): 分页选项
            - page (int): 页码
            - page_size (int): 每页大小

    Returns:
        JSON response containing search results
    """
    try:
        # 解析请求体
        if not request.is_json:
            return jsonify({
                'success': False,
                'message': 'Request must be JSON'
            }), 400

        search_data = request.get_json()

        # 提取搜索参数
        filters = search_data.get('filters', {})
        sort_options = search_data.get('sort', {})
        pagination = search_data.get('pagination', {})

        # 获取分页参数
        page = pagination.get('page', 1)
        page_size = pagination.get('page_size', 10)

        # 参数验证
        if page < 1 or page_size < 1 or page_size > 100:
            return jsonify({
                'success': False,
                'message': 'Invalid pagination parameters'
            }), 400

        # 注意：这是一个简化的实现
        # 实际的高级搜索需要在ntp_data_ingestion_service.py中实现更复杂的查询逻辑
        # 这里作为示例，只实现基本的IP和接口过滤

        search_ip = None
        interface_name = None

        # 处理客户端IP过滤（取第一个作为示例）
        client_ips = filters.get('client_ips', [])
        if client_ips and isinstance(client_ips, list) and len(client_ips) > 0:
            search_ip = client_ips[0]

        # 处理接口名称过滤（取第一个作为示例）
        interface_names = filters.get('interface_names', [])
        if interface_names and isinstance(interface_names, list) and len(interface_names) > 0:
            interface_name = interface_names[0]

        # 执行搜索
        clients, total_count = get_historical_clients(
            page=page,
            page_size=page_size,
            search_ip=search_ip,
            interface_name=interface_name
        )

        # 计算分页信息
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

        response_data = {
            'clients': clients,
            'pagination': {
                'current_page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            },
            'applied_filters': filters,
            'sort_options': sort_options
        }

        logger.info(f"高级搜索返回 {len(clients)} 条记录")

        return jsonify({
            'success': True,
            'data': response_data,
            'message': f'Advanced search completed, found {total_count} matching records'
        }), 200

    except Exception as e:
        logger.exception("高级搜索失败")
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@ntp_history_bp.route('/export', methods=['POST'])
def export_clients():
    """
    导出历史NTP客户端数据

    Request Body (JSON):
        - format (str): 导出格式 ('json' 或 'csv')
        - filters (dict): 过滤条件（同advanced_search）
        - limit (int): 最大导出记录数，默认1000

    Returns:
        导出的数据文件或错误信息
    """
    try:
        # 解析请求体
        if not request.is_json:
            return jsonify({
                'success': False,
                'message': 'Request must be JSON'
            }), 400

        export_data = request.get_json()

        # 获取导出参数
        export_format = export_data.get('format', 'json').lower()
        filters = export_data.get('filters', {})
        limit = export_data.get('limit', 1000)

        # 参数验证
        if export_format not in ['json', 'csv']:
            return jsonify({
                'success': False,
                'message': 'Invalid export format. Must be "json" or "csv"'
            }), 400

        if limit < 1 or limit > 10000:
            return jsonify({
                'success': False,
                'message': 'Invalid limit. Must be between 1 and 10000'
            }), 400

        # 简化实现：导出所有数据
        clients, total_count = get_historical_clients(
            page=1,
            page_size=min(limit, total_count) if 'total_count' in locals() else limit,
            search_ip=filters.get('search_ip'),
            interface_name=filters.get('interface_name')
        )

        if export_format == 'json':
            # JSON格式导出
            export_result = {
                'export_info': {
                    'total_records': len(clients),
                    'export_format': 'json',
                    'exported_at': datetime.utcnow().isoformat(),
                    'filters_applied': filters
                },
                'clients': clients
            }

            return jsonify({
                'success': True,
                'data': export_result,
                'message': f'Successfully exported {len(clients)} records in JSON format'
            }), 200

        elif export_format == 'csv':
            # CSV格式导出（简化实现，返回CSV数据的字符串表示）
            import io
            import csv

            output = io.StringIO()

            if clients:
                # 获取CSV列标题
                fieldnames = clients[0].keys()
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()

                for client in clients:
                    writer.writerow(client)

            csv_data = output.getvalue()
            output.close()

            return jsonify({
                'success': True,
                'data': {
                    'csv_content': csv_data,
                    'export_info': {
                        'total_records': len(clients),
                        'export_format': 'csv',
                        'exported_at': datetime.utcnow().isoformat()
                    }
                },
                'message': f'Successfully exported {len(clients)} records in CSV format'
            }), 200

    except Exception as e:
        logger.exception("导出数据失败")
        return jsonify({
            'success': False,
            'message': f'Export failed: {str(e)}'
        }), 500


@ntp_history_bp.route('/cleanup', methods=['POST'])
def cleanup_old_records():
    """
    清理旧的历史记录

    Request Body (JSON):
        - days (int): 保留天数，默认30天

    Returns:
        JSON response containing cleanup results
    """
    try:
        # 解析请求体
        cleanup_data = request.get_json() if request.is_json else {}
        days = cleanup_data.get('days', 30)

        # 参数验证
        if not isinstance(days, int) or days < 1 or days > 365:
            return jsonify({
                'success': False,
                'message': 'Invalid days parameter. Must be between 1 and 365'
            }), 400

        # 执行清理（需要在ingestion service中实现）
        from services.ntp_data_ingestion_service import get_ingestion_service

        deleted_count = get_ingestion_service().cleanup_old_records(days)

        logger.info(f"清理了 {deleted_count} 条超过 {days} 天的记录")

        return jsonify({
            'success': True,
            'data': {
                'deleted_count': deleted_count,
                'retention_days': days,
                'cleaned_at': datetime.utcnow().isoformat()
            },
            'message': f'Successfully cleaned up {deleted_count} old records'
        }), 200

    except Exception as e:
        logger.exception("清理旧记录失败")
        return jsonify({
            'success': False,
            'message': f'Cleanup failed: {str(e)}'
        }), 500


@ntp_history_bp.route('/health', methods=['GET'])
def history_health_check():
    """
    历史数据服务健康检查

    Returns:
        JSON response indicating history service health status
    """
    try:
        # 获取服务统计信息作为健康检查
        stats = get_service_stats()

        # 简单的健康检查：检查数据接收服务是否运行
        is_healthy = stats.get('running', False)

        return jsonify({
            'status': 'healthy' if is_healthy else 'degraded',
            'service': 'ntp_history',
            'message': 'NTP history service is operational' if is_healthy else 'NTP history service may have issues',
            'stats': {
                'ingestion_service_running': stats.get('running', False),
                'total_received': stats.get('total_received', 0),
                'total_processed': stats.get('total_processed', 0),
                'queue_size': stats.get('queue_size', 0)
            }
        }), 200 if is_healthy else 503

    except Exception as e:
        logger.exception("历史数据服务健康检查失败")
        return jsonify({
            'status': 'unhealthy',
            'service': 'ntp_history',
            'message': f'Health check error: {str(e)}'
        }), 503


# 错误处理器
@ntp_history_bp.errorhandler(404)
def history_not_found(error):
    """处理404错误"""
    return jsonify({
        'success': False,
        'message': 'NTP history endpoint not found'
    }), 404


@ntp_history_bp.errorhandler(405)
def history_method_not_allowed(error):
    """处理405错误"""
    return jsonify({
        'success': False,
        'message': 'Method not allowed for this NTP history endpoint'
    }), 405


@ntp_history_bp.errorhandler(500)
def history_server_error(error):
    """处理500错误"""
    logger.exception("Internal server error in NTP history service")
    return jsonify({
        'success': False,
        'message': 'Internal server error in NTP history service'
    }), 500