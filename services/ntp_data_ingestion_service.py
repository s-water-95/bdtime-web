"""
NTP数据接收处理服务
负责接收来自ntp_worker.py进程的TCP数据，进行数据处理和数据库存储
"""

import json
import logging
import queue
import socketserver
import threading
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

from sqlalchemy import create_engine, and_, or_, func
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

import config
from models.ntp_models import Base, NTPClient

logger = logging.getLogger(__name__)


def init_db() -> None:
    """
    初始化数据库，创建表（如果不存在）
    """
    try:
        engine = create_engine(f'sqlite:///{config.NTP_DB_PATH}', echo=config.DEBUG)
        Base.metadata.create_all(engine)
        logger.info(f"数据库初始化完成: {config.NTP_DB_PATH}")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise


class NTPDataRequestHandler(socketserver.StreamRequestHandler):
    """
    处理来自ntp_worker.py的TCP连接和数据接收
    """

    def handle(self):
        """处理客户端连接"""
        client_address = self.client_address[0]
        logger.info(f"NTP数据客户端连接: {client_address}")

        try:
            while True:
                # 读取一行数据（以换行符分隔）
                line = self.rfile.readline()
                if not line:
                    break

                try:
                    # 解码并解析JSON数据
                    data_str = line.decode('utf-8').strip()
                    if not data_str:
                        continue

                    session_data = json.loads(data_str)

                    # 将数据推入处理队列
                    self.server.data_queue.put(session_data, block=False)

                    logger.debug(f"接收到NTP会话数据: {session_data.get('client_ip', 'unknown')}")

                except json.JSONDecodeError as e:
                    logger.warning(f"JSON解析失败: {e}, 数据: {data_str[:100]}")
                except queue.Full:
                    logger.warning("数据队列已满，丢弃数据")
                except Exception as e:
                    logger.error(f"处理数据失败: {e}")

        except Exception as e:
            logger.error(f"连接处理异常: {e}")
        finally:
            logger.info(f"NTP数据客户端断开连接: {client_address}")


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """
    多线程TCP服务器，支持并发连接
    """
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass, data_queue):
        super().__init__(server_address, RequestHandlerClass)
        self.data_queue = data_queue


class NTPDataIngestionService:
    """
    NTP数据接收处理服务
    负责TCP服务器、数据处理和数据库操作
    """

    def __init__(self):
        """初始化服务"""
        self.host = config.NTP_INGESTION_HOST
        self.port = config.NTP_INGESTION_PORT
        self.batch_size = config.NTP_BATCH_SIZE
        self.batch_interval = config.NTP_BATCH_INTERVAL_SECONDS

        # 线程安全的数据队列
        self.data_queue = queue.Queue(maxsize=1000)  # 限制队列大小防止内存溢出

        # 服务状态
        self.running = False
        self.tcp_server = None
        self.processing_thread = None
        self.server_thread = None

        # 数据库相关
        self.engine = None
        self.SessionLocal = None

        # 统计信息
        self.stats = {
            'total_received': 0,
            'total_processed': 0,
            'total_inserted': 0,
            'total_updated': 0,
            'last_batch_time': None,
            'last_batch_size': 0,
            'processing_errors': 0
        }

        self._init_database()

    def _init_database(self) -> None:
        """初始化数据库连接"""
        try:
            self.engine = create_engine(
                f'sqlite:///{config.NTP_DB_PATH}',
                echo=config.DEBUG,
                pool_pre_ping=True,
                connect_args={'check_same_thread': False}  # SQLite多线程支持
            )
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            logger.info("数据库连接初始化完成")
        except Exception as e:
            logger.error(f"数据库连接初始化失败: {e}")
            raise

    def start(self) -> bool:
        """
        启动TCP服务器和数据处理线程

        Returns:
            bool: 启动是否成功
        """
        if self.running:
            logger.warning("NTP数据接收服务已在运行中")
            return False

        try:
            logger.info(f"启动NTP数据接收服务: {self.host}:{self.port}")

            # 创建TCP服务器
            self.tcp_server = ThreadedTCPServer(
                (self.host, self.port),
                NTPDataRequestHandler,
                self.data_queue
            )

            # 启动服务器线程
            self.server_thread = threading.Thread(
                target=self.tcp_server.serve_forever,
                name="NTPTCPServer"
            )
            self.server_thread.daemon = True
            self.server_thread.start()

            # 启动数据处理线程
            self.processing_thread = threading.Thread(
                target=self._data_processing_loop,
                name="NTPDataProcessor"
            )
            self.processing_thread.daemon = True
            self.processing_thread.start()

            self.running = True
            logger.info("NTP数据接收服务启动成功")
            return True

        except Exception as e:
            logger.error(f"NTP数据接收服务启动失败: {e}")
            self.stop()
            return False

    def stop(self) -> None:
        """停止服务"""
        if not self.running:
            return

        logger.info("停止NTP数据接收服务...")
        self.running = False

        # 停止TCP服务器
        if self.tcp_server:
            try:
                self.tcp_server.shutdown()
                self.tcp_server.server_close()
            except Exception as e:
                logger.warning(f"停止TCP服务器时出错: {e}")

        # 等待处理线程完成
        if self.processing_thread and self.processing_thread.is_alive():
            logger.info("等待数据处理线程完成...")
            self.processing_thread.join(timeout=10)

        # 处理剩余的数据
        self._process_remaining_data()

        logger.info("NTP数据接收服务已停止")

    def _data_processing_loop(self) -> None:
        """数据处理循环"""
        logger.info("数据处理线程启动")

        batch_data = []
        last_batch_time = time.time()

        while self.running:
            try:
                # 尝试从队列获取数据
                try:
                    data = self.data_queue.get(timeout=1.0)
                    batch_data.append(data)
                    self.stats['total_received'] += 1

                    # 标记任务完成
                    self.data_queue.task_done()

                except queue.Empty:
                    # 队列为空，检查是否需要强制处理批次
                    pass

                current_time = time.time()

                # 检查是否达到批处理条件
                should_process = (
                        len(batch_data) >= self.batch_size or
                        (batch_data and (current_time - last_batch_time) >= self.batch_interval)
                )

                if should_process:
                    if batch_data:
                        self._process_batch(batch_data.copy())
                        batch_data.clear()
                        last_batch_time = current_time

            except Exception as e:
                logger.error(f"数据处理循环异常: {e}")
                self.stats['processing_errors'] += 1
                time.sleep(1)  # 避免错误循环

        # 处理剩余数据
        if batch_data:
            self._process_batch(batch_data)

        logger.info("数据处理线程结束")

    def _process_batch(self, batch_data: List[Dict[str, Any]]) -> None:
        """
        批量处理数据

        Args:
            batch_data: 待处理的数据列表
        """
        if not batch_data:
            return

        logger.debug(f"开始处理批次，数据量: {len(batch_data)}")

        session = self.SessionLocal()
        try:
            inserted_count = 0
            updated_count = 0

            for session_data in batch_data:
                try:
                    client_ip = session_data.get('client_ip')
                    interface_name = session_data.get('interface_name')

                    if not client_ip or not interface_name:
                        logger.warning(f"数据缺少必要字段: {session_data}")
                        continue

                    # 查找现有记录（基于client_ip作为唯一标识）
                    existing_client = session.query(NTPClient).filter(
                        NTPClient.client_ip == client_ip
                    ).first()

                    if existing_client:
                        # 更新现有记录
                        existing_client.update_from_session_data(session_data)
                        updated_count += 1
                        logger.debug(f"更新客户端记录: {client_ip}")
                    else:
                        # 插入新记录
                        new_client = NTPClient.from_session_data(session_data)
                        session.add(new_client)
                        inserted_count += 1
                        logger.debug(f"插入新客户端记录: {client_ip}")

                    self.stats['total_processed'] += 1

                except Exception as e:
                    logger.error(f"处理单条数据失败: {e}, 数据: {session_data}")
                    self.stats['processing_errors'] += 1
                    continue

            # 提交事务
            session.commit()

            # 更新统计信息
            self.stats['total_inserted'] += inserted_count
            self.stats['total_updated'] += updated_count
            self.stats['last_batch_time'] = datetime.now()
            self.stats['last_batch_size'] = len(batch_data)

            logger.info(f"批次处理完成: 插入 {inserted_count}, 更新 {updated_count}")

        except SQLAlchemyError as e:
            logger.error(f"数据库操作失败: {e}")
            session.rollback()
            self.stats['processing_errors'] += 1
        except Exception as e:
            logger.error(f"批次处理异常: {e}")
            session.rollback()
            self.stats['processing_errors'] += 1
        finally:
            session.close()

    def _process_remaining_data(self) -> None:
        """处理队列中剩余的数据"""
        remaining_data = []

        try:
            while True:
                data = self.data_queue.get_nowait()
                remaining_data.append(data)
                self.data_queue.task_done()
        except queue.Empty:
            pass

        if remaining_data:
            logger.info(f"处理剩余数据: {len(remaining_data)} 条")
            self._process_batch(remaining_data)

    def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        stats = self.stats.copy()
        stats.update({
            'running': self.running,
            'queue_size': self.data_queue.qsize(),
            'last_batch_time': self.stats['last_batch_time'].isoformat() if self.stats['last_batch_time'] else None
        })
        return stats

    # 查询接口

    def get_historical_clients(self, page: int = 1, page_size: int = 10,
                               search_ip: Optional[str] = None,
                               interface_name: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
        """
        获取历史NTP客户端列表

        Args:
            page: 页码（从1开始）
            page_size: 每页大小
            search_ip: 搜索的客户端IP（精确匹配）
            interface_name: 筛选的网卡名称

        Returns:
            Tuple[List[Dict[str, Any]], int]: (客户端列表, 总数)
        """
        session = self.SessionLocal()
        try:
            # 构建查询
            query = session.query(NTPClient)

            # 添加过滤条件
            if search_ip:
                query = query.filter(NTPClient.client_ip == search_ip)

            if interface_name:
                query = query.filter(NTPClient.interface_name == interface_name)

            # 获取总数
            total_count = query.count()

            # 添加排序和分页
            query = query.order_by(NTPClient.last_seen_timestamp.desc())

            if page_size > 0:
                offset = (page - 1) * page_size
                query = query.offset(offset).limit(page_size)

            # 执行查询
            clients = query.all()

            # 转换为字典格式
            client_list = [client.to_summary_dict() for client in clients]

            return client_list, total_count

        except Exception as e:
            logger.error(f"查询历史客户端失败: {e}")
            return [], 0
        finally:
            session.close()

    def get_client_detail(self, client_ip: str) -> Optional[Dict[str, Any]]:
        """
        获取特定客户端的详细信息

        Args:
            client_ip: 客户端IP地址

        Returns:
            Optional[Dict[str, Any]]: 客户端详细信息，如果不存在返回None
        """
        session = self.SessionLocal()
        try:
            client = session.query(NTPClient).filter(
                NTPClient.client_ip == client_ip
            ).first()

            if client:
                return client.to_dict()
            return None

        except Exception as e:
            logger.error(f"查询客户端详情失败: {e}")
            return None
        finally:
            session.close()

    def get_interface_statistics(self) -> List[Dict[str, Any]]:
        """
        获取各网卡的统计信息

        Returns:
            List[Dict[str, Any]]: 网卡统计信息列表
        """
        session = self.SessionLocal()
        try:
            # 按网卡分组统计
            stats_query = session.query(
                NTPClient.interface_name,
                func.count(NTPClient.id).label('client_count'),
                func.sum(NTPClient.session_count).label('total_sessions'),
                func.max(NTPClient.last_seen_timestamp).label('last_activity'),
                func.avg(NTPClient.client_to_server_latency_seconds).label('avg_latency')
            ).group_by(NTPClient.interface_name)

            results = stats_query.all()

            statistics = []
            for result in results:
                statistics.append({
                    'interface_name': result.interface_name,
                    'client_count': result.client_count,
                    'total_sessions': result.total_sessions or 0,
                    'last_activity': result.last_activity.isoformat() if result.last_activity else None,
                    'average_latency_seconds': float(result.avg_latency) if result.avg_latency else None
                })

            return statistics

        except Exception as e:
            logger.error(f"查询网卡统计信息失败: {e}")
            return []
        finally:
            session.close()

    def cleanup_old_records(self, days: int = 30) -> int:
        """
        清理超过指定天数的旧记录

        Args:
            days: 保留天数

        Returns:
            int: 删除的记录数
        """
        session = self.SessionLocal()
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            deleted_count = session.query(NTPClient).filter(
                NTPClient.last_seen_timestamp < cutoff_date
            ).delete()

            session.commit()
            logger.info(f"清理了 {deleted_count} 条超过 {days} 天的旧记录")
            return deleted_count

        except Exception as e:
            logger.error(f"清理旧记录失败: {e}")
            session.rollback()
            return 0
        finally:
            session.close()


# 全局服务实例
_ingestion_service = None


def get_ingestion_service() -> NTPDataIngestionService:
    """获取数据接收服务实例"""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = NTPDataIngestionService()
    return _ingestion_service


# 便捷函数
def get_historical_clients(page: int = 1, page_size: int = 10,
                           search_ip: Optional[str] = None,
                           interface_name: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
    """获取历史NTP客户端列表"""
    return get_ingestion_service().get_historical_clients(page, page_size, search_ip, interface_name)


def get_client_detail(client_ip: str) -> Optional[Dict[str, Any]]:
    """获取客户端详细信息"""
    return get_ingestion_service().get_client_detail(client_ip)


def get_interface_statistics() -> List[Dict[str, Any]]:
    """获取网卡统计信息"""
    return get_ingestion_service().get_interface_statistics()


def get_service_stats() -> Dict[str, Any]:
    """获取服务统计信息"""
    return get_ingestion_service().get_stats()