#!/usr/bin/env python3
"""
NTP客户端监控程序
运行在NTP服务器上，监控所有NTP客户端请求
特点：低开销、持久化存储、实时统计
"""

import sqlite3
import struct
import socket
import time
import threading
import signal
import sys
import logging
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List, Optional
import json
import netifaces

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ntp_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class NTPPacket:
    """NTP数据包结构"""
    li_vn_mode: int = 0  # Leap Indicator, Version Number, Mode
    stratum: int = 0  # 时间层级
    poll: int = 0  # 轮询间隔
    precision: int = 0  # 精度
    root_delay: int = 0  # 根延迟
    root_dispersion: int = 0  # 根离散度
    reference_id: int = 0  # 参考ID
    reference_timestamp: float = 0.0  # 参考时间戳
    origin_timestamp: float = 0.0  # 原始时间戳 (T1)
    receive_timestamp: float = 0.0  # 接收时间戳 (T2)
    transmit_timestamp: float = 0.0  # 传输时间戳 (T3)


@dataclass
class ClientStats:
    """客户端统计信息"""
    client_ip: str
    interface: str
    first_seen: datetime
    last_seen: datetime
    request_count: int = 0
    total_delay: float = 0.0
    total_offset: float = 0.0
    min_delay: float = float('inf')
    max_delay: float = 0.0
    stratum_requests: Dict[int, int] = None

    def __post_init__(self):
        if self.stratum_requests is None:
            self.stratum_requests = defaultdict(int)


class NTPMonitor:
    """NTP监控主程序"""

    def __init__(self, db_path: str = "ntp_monitor.db",
                 batch_size: int = 100,
                 flush_interval: int = 30):
        self.db_path = db_path
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.running = False

        # 内存缓存
        self.client_cache: Dict[str, ClientStats] = {}
        self.pending_records = deque()
        self.cache_lock = threading.Lock()

        # 网络接口映射
        self.interface_map = self._get_interface_mapping()

        # 初始化数据库
        self._init_database()

        # 启动后台线程
        self.db_thread = None

    def _get_interface_mapping(self) -> Dict[str, str]:
        """获取网络接口映射"""

        interface_map = {}
        try:
            for interface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        ip = addr_info.get('addr')
                        if ip:
                            interface_map[ip] = interface
        except ImportError:
            logger.warning("netifaces not available, interface detection disabled")
        return interface_map

    def _init_database(self):
        """初始化SQLite数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 创建客户端统计表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS client_stats (
                client_ip TEXT PRIMARY KEY,
                interface TEXT,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                request_count INTEGER,
                avg_delay REAL,
                avg_offset REAL,
                min_delay REAL,
                max_delay REAL,
                stratum_distribution TEXT
            )
        ''')

        # 创建详细记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ntp_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP,
                client_ip TEXT,
                interface TEXT,
                stratum INTEGER,
                poll_interval INTEGER,
                precision INTEGER,
                root_delay REAL,
                root_dispersion REAL,
                network_delay REAL,
                time_offset REAL,
                t1 REAL,
                t2 REAL,
                t3 REAL,
                t4 REAL
            )
        ''')

        # 创建索引优化查询
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_ip ON ntp_records(client_ip)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON ntp_records(timestamp)')

        conn.commit()
        conn.close()
        logger.info("数据库初始化完成")

    def _ntp_to_system_time(self, ntp_time: int) -> float:
        """将NTP时间戳转换为系统时间"""
        if ntp_time == 0:
            return 0.0
        # NTP epoch is 1900-01-01, Unix epoch is 1970-01-01
        # Difference is 70 years = 2208988800 seconds
        return ntp_time / (2 ** 32) - 2208988800

    def _parse_ntp_packet(self, data: bytes) -> Optional[NTPPacket]:
        """解析NTP数据包"""
        if len(data) < 48:
            return None

        try:
            # 解包NTP数据
            unpacked = struct.unpack('!BBBbIIIQQQQ', data[:48])

            packet = NTPPacket()
            packet.li_vn_mode = unpacked[0]
            packet.stratum = unpacked[1]
            packet.poll = unpacked[2]
            packet.precision = unpacked[3]
            packet.root_delay = unpacked[4]
            packet.root_dispersion = unpacked[5]
            packet.reference_id = unpacked[6]
            packet.reference_timestamp = self._ntp_to_system_time(unpacked[7])
            packet.origin_timestamp = self._ntp_to_system_time(unpacked[8])
            packet.receive_timestamp = self._ntp_to_system_time(unpacked[9])
            packet.transmit_timestamp = self._ntp_to_system_time(unpacked[10])

            return packet
        except struct.error:
            return None

    def _calculate_metrics(self, packet: NTPPacket, t4: float) -> tuple:
        """计算网络延迟和时间偏移"""
        t1 = packet.origin_timestamp
        t2 = packet.receive_timestamp
        t3 = packet.transmit_timestamp

        if t1 == 0 or t2 == 0 or t3 == 0:
            return 0.0, 0.0

        # 网络延迟 = ((T4-T1) - (T3-T2)) / 2
        delay = ((t4 - t1) - (t3 - t2)) / 2

        # 时间偏移 = ((T2-T1) + (T3-T4)) / 2
        offset = ((t2 - t1) + (t3 - t4)) / 2

        return delay, offset

    def _update_client_stats(self, client_ip: str, interface: str,
                             delay: float, offset: float, stratum: int):
        """更新客户端统计信息"""
        with self.cache_lock:
            now = datetime.now()

            if client_ip not in self.client_cache:
                self.client_cache[client_ip] = ClientStats(
                    client_ip=client_ip,
                    interface=interface,
                    first_seen=now,
                    last_seen=now,
                    stratum_requests=defaultdict(int)
                )

            stats = self.client_cache[client_ip]
            stats.last_seen = now
            stats.request_count += 1
            stats.total_delay += delay
            stats.total_offset += offset
            stats.min_delay = min(stats.min_delay, delay)
            stats.max_delay = max(stats.max_delay, delay)
            stats.stratum_requests[stratum] += 1

    def _process_ntp_request(self, data: bytes, client_addr: tuple, server_addr: tuple):
        """处理NTP请求"""
        packet = self._parse_ntp_packet(data)
        if not packet:
            return

        client_ip = client_addr[0]
        server_ip = server_addr[0]
        interface = self.interface_map.get(server_ip, "unknown")

        # 计算T4（客户端接收时间，这里用当前时间近似）
        t4 = time.time()

        # 计算延迟和偏移
        delay, offset = self._calculate_metrics(packet, t4)

        # 更新统计信息
        self._update_client_stats(client_ip, interface, delay, offset, packet.stratum)

        # 添加详细记录到待写入队列
        record = {
            'timestamp': datetime.now(),
            'client_ip': client_ip,
            'interface': interface,
            'stratum': packet.stratum,
            'poll_interval': packet.poll,
            'precision': packet.precision,
            'root_delay': packet.root_delay / (2 ** 16),  # 转换为秒
            'root_dispersion': packet.root_dispersion / (2 ** 16),
            'network_delay': delay,
            'time_offset': offset,
            't1': packet.origin_timestamp,
            't2': packet.receive_timestamp,
            't3': packet.transmit_timestamp,
            't4': t4
        }

        with self.cache_lock:
            self.pending_records.append(record)

    def _database_worker(self):
        """数据库写入工作线程"""
        while self.running:
            try:
                time.sleep(self.flush_interval)
                self._flush_to_database()
            except Exception as e:
                logger.error(f"数据库写入错误: {e}")

    def _flush_to_database(self):
        """批量写入数据库"""
        with self.cache_lock:
            if not self.pending_records and not self.client_cache:
                return

            # 获取待写入数据
            records_to_write = list(self.pending_records)
            self.pending_records.clear()

            # 获取客户端统计数据
            stats_to_write = {}
            for client_ip, stats in self.client_cache.items():
                stats_to_write[client_ip] = {
                    'client_ip': stats.client_ip,
                    'interface': stats.interface,
                    'first_seen': stats.first_seen,
                    'last_seen': stats.last_seen,
                    'request_count': stats.request_count,
                    'avg_delay': stats.total_delay / stats.request_count if stats.request_count > 0 else 0,
                    'avg_offset': stats.total_offset / stats.request_count if stats.request_count > 0 else 0,
                    'min_delay': stats.min_delay if stats.min_delay != float('inf') else 0,
                    'max_delay': stats.max_delay,
                    'stratum_distribution': json.dumps(dict(stats.stratum_requests))
                }

        # 执行数据库写入
        if records_to_write or stats_to_write:
            self._write_to_database(records_to_write, stats_to_write)

    def _write_to_database(self, records: List[dict], stats: Dict[str, dict]):
        """写入数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 写入详细记录
            if records:
                cursor.executemany('''
                    INSERT INTO ntp_records 
                    (timestamp, client_ip, interface, stratum, poll_interval, precision,
                     root_delay, root_dispersion, network_delay, time_offset, t1, t2, t3, t4)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', [
                    (r['timestamp'], r['client_ip'], r['interface'], r['stratum'],
                     r['poll_interval'], r['precision'], r['root_delay'], r['root_dispersion'],
                     r['network_delay'], r['time_offset'], r['t1'], r['t2'], r['t3'], r['t4'])
                    for r in records
                ])
                logger.info(f"写入 {len(records)} 条详细记录")

            # 更新客户端统计
            if stats:
                cursor.executemany('''
                    INSERT OR REPLACE INTO client_stats
                    (client_ip, interface, first_seen, last_seen, request_count,
                     avg_delay, avg_offset, min_delay, max_delay, stratum_distribution)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', [
                    (s['client_ip'], s['interface'], s['first_seen'], s['last_seen'],
                     s['request_count'], s['avg_delay'], s['avg_offset'], s['min_delay'],
                     s['max_delay'], s['stratum_distribution'])
                    for s in stats.values()
                ])
                logger.info(f"更新 {len(stats)} 个客户端统计")

            conn.commit()

        except Exception as e:
            logger.error(f"数据库写入失败: {e}")
            conn.rollback()
        finally:
            conn.close()

    def start_monitoring(self, ntp_port: int = 123):
        """开始监控NTP流量"""
        self.running = True

        # 启动数据库工作线程
        self.db_thread = threading.Thread(target=self._database_worker)
        self.db_thread.daemon = True
        self.db_thread.start()

        # 创建UDP socket监听NTP端口
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            sock.bind(('', ntp_port))
            logger.info(f"开始监控NTP端口 {ntp_port}")

            while self.running:
                try:
                    data, addr = sock.recvfrom(1024)
                    # 获取本地socket地址作为服务器地址
                    server_addr = sock.getsockname()
                    self._process_ntp_request(data, addr, server_addr)

                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"处理NTP请求错误: {e}")

        except Exception as e:
            logger.error(f"监控启动失败: {e}")
        finally:
            sock.close()
            self.stop_monitoring()

    def stop_monitoring(self):
        """停止监控"""
        self.running = False
        logger.info("正在停止监控...")

        # 最后一次刷新数据
        self._flush_to_database()

        if self.db_thread and self.db_thread.is_alive():
            self.db_thread.join(timeout=5)

        logger.info("监控已停止")

    def get_client_stats(self, client_ip: str = None) -> List[dict]:
        """获取客户端统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if client_ip:
            cursor.execute('SELECT * FROM client_stats WHERE client_ip = ?', (client_ip,))
        else:
            cursor.execute('SELECT * FROM client_stats ORDER BY last_seen DESC')

        columns = [description[0] for description in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]

        conn.close()
        return results

    def get_records(self, client_ip: str = None, hours: int = 24) -> List[dict]:
        """获取详细记录"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        since = datetime.now() - timedelta(hours=hours)

        if client_ip:
            cursor.execute('''
                SELECT * FROM ntp_records 
                WHERE client_ip = ? AND timestamp > ?
                ORDER BY timestamp DESC
            ''', (client_ip, since))
        else:
            cursor.execute('''
                SELECT * FROM ntp_records 
                WHERE timestamp > ?
                ORDER BY timestamp DESC
            ''', (since,))

        columns = [description[0] for description in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]

        conn.close()
        return results


def signal_handler(signum, frame):
    """信号处理器"""
    logger.info("收到停止信号")
    if hasattr(signal_handler, 'monitor'):
        signal_handler.monitor.stop_monitoring()
    sys.exit(0)


def main():
    """主程序"""
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 创建监控实例
    monitor = NTPMonitor(
        db_path="ntp_monitor.db",
        batch_size=100,
        flush_interval=30
    )

    # 存储到信号处理器中
    signal_handler.monitor = monitor

    logger.info("NTP客户端监控程序启动")

    try:
        # 开始监控
        monitor.start_monitoring()
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"程序异常: {e}")
    finally:
        monitor.stop_monitoring()


if __name__ == "__main__":
    main()