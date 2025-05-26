import os
import logging
from flask import Flask
from routes.network_routes import network_bp
from routes.monitor_routes import monitor_bp
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
    app.register_blueprint(monitor_bp)  # 新增：注册监控路由

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Not found'}, 404

    @app.errorhandler(500)
    def server_error(error):
        logger.exception("An error occurred during a request.")
        return {'error': 'Internal server error'}, 500

    # 新增：健康检查路由
    @app.route('/api/health', methods=['GET'])
    def health_check():
        """全局健康检查接口"""
        return {
            'status': 'healthy',
            'services': ['network', 'monitor'],
            'message': 'Server is running'
        }, 200

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)