import os
import logging
from flask import Flask
from routes.network_routes import network_bp
from routes.monitor_routes import monitor_bp
from routes.ntp_monitor_routes import ntp_bp  # 新增：导入NTP监控路由
import config

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__)

    # Register blueprints
    app.register_blueprint(network_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(ntp_bp)  # 新增：注册NTP监控蓝图

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Not found'}, 404

    @app.errorhandler(500)
    def server_error(error):
        logger.exception("An error occurred during a request.")
        return {'error': 'Internal server error'}, 500

    # 修改：更新健康检查路由，增加NTP监控服务
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
                    'ntp_monitor': 'healthy'  # 新增：NTP监控服务状态
                },
                'message': 'All services are running'
            }

            # 可选：检查NTP监控服务的具体状态
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

            return health_status, 200

        except Exception as e:
            logger.exception("Health check failed")
            return {
                'status': 'unhealthy',
                'services': ['network', 'monitor', 'ntp_monitor'],
                'message': f'Health check error: {str(e)}'
            }, 503

    # 新增：NTP监控相关的启动日志
    logger.info("Flask application created successfully")
    logger.info(f"NTP PID directory: {config.NTP_PID_DIR}")
    logger.info(f"NTP worker script: {config.NTP_WORKER_SCRIPT_PATH}")

    # 检查tcpdump是否可用（可选警告）
    import subprocess
    try:
        result = subprocess.run(['which', 'tcpdump'], capture_output=True, timeout=5)
        if result.returncode != 0:
            logger.warning("tcpdump not found in PATH. NTP monitoring may not work.")
        else:
            logger.info("tcpdump found and available for NTP monitoring")
    except Exception as e:
        logger.warning(f"Could not check tcpdump availability: {e}")

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)