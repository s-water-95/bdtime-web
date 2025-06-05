import os
import atexit
import logging
import threading
from flask import Flask
from routes.network_routes import network_bp
from routes.monitor_routes import monitor_bp
from routes.ntp_monitor_routes import ntp_bp
from routes.ntp_history_routes import ntp_history_bp  # 新增：导入NTP历史查询路由
import config

# 新增：导入数据库和数据接收服务相关模块
from models import ntp_models
from services.ntp_data_ingestion_service import init_db, get_ingestion_service

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# 全局变量：存储数据接收服务实例
_ingestion_service = None
_ingestion_service_lock = threading.Lock()


def initialize_database():
    """
    初始化数据库
    创建必要的表结构
    """
    try:
        logger.info("初始化NTP历史数据库...")
        init_db()
        logger.info("数据库初始化完成")
        return True
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        return False


def start_ingestion_service():
    """
    启动NTP数据接收处理服务

    Returns:
        bool: 启动是否成功
    """
    global _ingestion_service

    with _ingestion_service_lock:
        if _ingestion_service is not None:
            logger.warning("NTP数据接收服务已启动")
            return True

        try:
            logger.info("启动NTP数据接收处理服务...")
            _ingestion_service = get_ingestion_service()

            if _ingestion_service.start():
                logger.info("NTP数据接收处理服务启动成功")
                return True
            else:
                logger.error("NTP数据接收处理服务启动失败")
                _ingestion_service = None
                return False

        except Exception as e:
            logger.error(f"启动NTP数据接收处理服务时发生异常: {e}")
            _ingestion_service = None
            return False


def stop_ingestion_service():
    """
    停止NTP数据接收处理服务
    """
    global _ingestion_service

    with _ingestion_service_lock:
        if _ingestion_service is not None:
            try:
                logger.info("停止NTP数据接收处理服务...")
                _ingestion_service.stop()
                _ingestion_service = None
                logger.info("NTP数据接收处理服务已停止")
            except Exception as e:
                logger.error(f"停止NTP数据接收处理服务时发生异常: {e}")


def get_ingestion_service_instance():
    """
    获取数据接收服务实例

    Returns:
        NTPDataIngestionService: 服务实例，如果未启动则返回None
    """
    return _ingestion_service


def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__)

    # 新增：初始化数据库
    logger.info("开始初始化应用组件...")

    if not initialize_database():
        logger.warning("数据库初始化失败，NTP历史功能可能无法正常工作")

    # 新增：启动数据接收处理服务
    ingestion_started = start_ingestion_service()
    if not ingestion_started:
        logger.warning("NTP数据接收服务启动失败，历史数据收集功能将无法工作")

    # Register blueprints
    app.register_blueprint(network_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(ntp_bp)
    app.register_blueprint(ntp_history_bp)  # 新增：注册NTP历史查询蓝图

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Not found'}, 404

    @app.errorhandler(500)
    def server_error(error):
        logger.exception("An error occurred during a request.")
        return {'error': 'Internal server error'}, 500

    # 修改：更新健康检查路由，增加更多服务状态检查
    @app.route('/api/health', methods=['GET'])
    def health_check():
        """全局健康检查接口"""
        try:
            # 检查各个服务的健康状态
            health_status = {
                'status': 'healthy',
                'services': {
                    'network': 'healthy',
                    'monitor': 'healthy',
                    'ntp_monitor': 'healthy',
                    'ntp_history': 'healthy',  # 新增：NTP历史服务状态
                    'ntp_ingestion': 'healthy'  # 新增：数据接收服务状态
                },
                'message': 'All services are running'
            }

            # 检查NTP监控服务的具体状态
            try:
                from services.ntp_monitor_service import list_all_monitoring_status
                ntp_status = list_all_monitoring_status()
                running_monitors = sum(1 for status in ntp_status if status.get('is_monitoring', False))

                health_status['ntp_monitor_details'] = {
                    'total_interfaces': len(ntp_status),
                    'running_monitors': running_monitors,
                    'pid_dir': config.NTP_PID_DIR,
                    'worker_script': config.NTP_WORKER_SCRIPT_PATH
                }
            except Exception as e:
                logger.warning(f"Failed to get NTP monitor details: {e}")
                health_status['services']['ntp_monitor'] = 'degraded'
                health_status['ntp_monitor_error'] = str(e)

            # 新增：检查NTP数据接收服务状态
            ingestion_service = get_ingestion_service_instance()
            if ingestion_service:
                try:
                    ingestion_stats = ingestion_service.get_stats()
                    health_status['ntp_ingestion_details'] = {
                        'running': ingestion_stats.get('running', False),
                        'total_received': ingestion_stats.get('total_received', 0),
                        'total_processed': ingestion_stats.get('total_processed', 0),
                        'queue_size': ingestion_stats.get('queue_size', 0),
                        'host_port': f"{config.NTP_INGESTION_HOST}:{config.NTP_INGESTION_PORT}",
                        'database_path': config.NTP_DB_PATH
                    }

                    if not ingestion_stats.get('running', False):
                        health_status['services']['ntp_ingestion'] = 'stopped'

                except Exception as e:
                    logger.warning(f"Failed to get NTP ingestion details: {e}")
                    health_status['services']['ntp_ingestion'] = 'degraded'
                    health_status['ntp_ingestion_error'] = str(e)
            else:
                health_status['services']['ntp_ingestion'] = 'not_started'
                health_status['ntp_ingestion_details'] = {
                    'running': False,
                    'error': 'Service not started'
                }

            # 新增：检查数据库健康状态
            try:
                from services.ntp_data_ingestion_service import get_historical_clients
                # 简单查询测试数据库连接
                _, total_count = get_historical_clients(page=1, page_size=1)
                health_status['database_details'] = {
                    'accessible': True,
                    'total_clients': total_count,
                    'database_path': config.NTP_DB_PATH
                }
            except Exception as e:
                logger.warning(f"Database health check failed: {e}")
                health_status['services']['ntp_history'] = 'degraded'
                health_status['database_details'] = {
                    'accessible': False,
                    'error': str(e)
                }

            # 确定整体健康状态
            degraded_services = [k for k, v in health_status['services'].items()
                                 if v in ['degraded', 'stopped', 'not_started']]

            if degraded_services:
                health_status['status'] = 'degraded'
                health_status['message'] = f'Some services have issues: {", ".join(degraded_services)}'

            return health_status, 200

        except Exception as e:
            logger.exception("Health check failed")
            return {
                'status': 'unhealthy',
                'services': ['network', 'monitor', 'ntp_monitor', 'ntp_history', 'ntp_ingestion'],
                'message': f'Health check error: {str(e)}'
            }, 503

    # 新增：应用上下文相关的路由，用于获取服务状态
    @app.route('/api/services/status', methods=['GET'])
    def get_services_status():
        """获取所有服务的详细状态"""
        try:
            status = {}

            # NTP监控服务状态
            try:
                from services.ntp_monitor_service import list_all_monitoring_status
                status['ntp_monitoring'] = list_all_monitoring_status()
            except Exception as e:
                status['ntp_monitoring'] = {'error': str(e)}

            # NTP数据接收服务状态
            ingestion_service = get_ingestion_service_instance()
            if ingestion_service:
                status['ntp_ingestion'] = ingestion_service.get_stats()
            else:
                status['ntp_ingestion'] = {'running': False, 'error': 'Service not started'}

            # 数据库统计
            try:
                from services.ntp_data_ingestion_service import get_interface_statistics
                status['interface_statistics'] = get_interface_statistics()
            except Exception as e:
                status['interface_statistics'] = {'error': str(e)}

            return {
                'success': True,
                'data': status,
                'timestamp': app.logger.getEffectiveLevel()  # 使用logger级别作为时间戳的替代
            }, 200

        except Exception as e:
            logger.exception("获取服务状态失败")
            return {
                'success': False,
                'message': f'Failed to get services status: {str(e)}'
            }, 500

    # 新增：应用启动完成的日志
    logger.info("Flask应用创建完成")
    logger.info(f"NTP PID目录: {config.NTP_PID_DIR}")
    logger.info(f"NTP工作脚本: {config.NTP_WORKER_SCRIPT_PATH}")
    logger.info(f"NTP数据库: {config.NTP_DB_PATH}")
    logger.info(f"NTP数据接收服务: {config.NTP_INGESTION_HOST}:{config.NTP_INGESTION_PORT}")

    # 检查tcpdump是否可用（可选警告）
    import subprocess
    try:
        result = subprocess.run(['which', 'tcpdump'], capture_output=True, timeout=5)
        if result.returncode != 0:
            logger.warning("tcpdump未在PATH中找到，NTP监控可能无法工作")
        else:
            logger.info("tcpdump可用，NTP监控功能正常")
    except Exception as e:
        logger.warning(f"无法检查tcpdump可用性: {e}")

    # 新增：检查关键目录和文件的权限
    def check_permissions():
        """检查关键目录和文件的权限"""
        warnings = []

        # 检查PID目录权限
        try:
            test_file = os.path.join(config.NTP_PID_DIR, '.permission_test')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except Exception:
            warnings.append(f"NTP PID目录 {config.NTP_PID_DIR} 无写权限")

        # 检查数据库目录权限
        try:
            db_dir = os.path.dirname(config.NTP_DB_PATH)
            test_file = os.path.join(db_dir, '.permission_test')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except Exception:
            warnings.append(f"数据库目录 {os.path.dirname(config.NTP_DB_PATH)} 无写权限")

        # 检查worker脚本是否存在
        if not os.path.exists(config.NTP_WORKER_SCRIPT_PATH):
            warnings.append(f"NTP工作脚本 {config.NTP_WORKER_SCRIPT_PATH} 不存在")

        for warning in warnings:
            logger.warning(f"权限检查: {warning}")

    check_permissions()

    return app


def setup_graceful_shutdown():
    """
    设置优雅关闭处理程序
    确保在应用关闭时正确停止所有服务
    """

    def cleanup():
        """清理函数"""
        logger.info("应用关闭，开始清理资源...")

        # 停止数据接收服务
        stop_ingestion_service()

        # 可以在这里添加其他清理逻辑
        logger.info("资源清理完成")

    # 注册退出时的清理函数
    atexit.register(cleanup)

    # 注册信号处理器（如果需要的话）
    import signal

    def signal_handler(signum, frame):
        """信号处理器"""
        logger.info(f"接收到信号 {signum}，开始优雅关闭...")
        cleanup()
        exit(0)

    try:
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        logger.info("信号处理器注册完成")
    except Exception as e:
        logger.warning(f"信号处理器注册失败: {e}")


if __name__ == '__main__':
    # 设置优雅关闭
    setup_graceful_shutdown()

    # 创建并运行应用
    app = create_app()

    try:
        logger.info(f"启动Flask应用: {config.HOST}:{config.PORT}")
        logger.info(f"调试模式: {config.DEBUG}")

        app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, threaded=True)

    except KeyboardInterrupt:
        logger.info("接收到中断信号，正在关闭应用...")
    except Exception as e:
        logger.error(f"应用运行时发生错误: {e}")
    finally:
        # 确保清理资源
        stop_ingestion_service()
        logger.info("应用已关闭")