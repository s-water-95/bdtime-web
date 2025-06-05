"""
NTP客户端数据库模型
定义历史NTP客户端数据的SQLAlchemy模型
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from typing import Dict, Any, Optional
from datetime import datetime

Base = declarative_base()


class NTPClient(Base):
    """
    NTP客户端数据模型
    存储从NTP会话中提取的客户端信息和性能指标
    """
    __tablename__ = 'ntp_clients'

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 网络标识信息
    client_ip = Column(String(45), nullable=False, index=True, comment="客户端IP地址，支持IPv4和IPv6")
    client_port = Column(Integer, nullable=False, comment="客户端端口")
    server_ip = Column(String(45), nullable=False, comment="服务器IP地址")
    server_port = Column(Integer, nullable=False, default=123, comment="服务器端口，通常为123")
    interface_name = Column(String(64), nullable=False, index=True, comment="监控网卡名称")

    # NTP协议信息
    ntp_version = Column(Integer, nullable=False, comment="NTP协议版本")
    stratum = Column(Integer, nullable=True, comment="时间层级")
    precision = Column(Integer, nullable=True, comment="时钟精度指数")
    root_delay = Column(Float, nullable=True, comment="根延迟（秒）")
    root_dispersion = Column(Float, nullable=True, comment="根离散（秒）")
    reference_id = Column(String(32), nullable=True, comment="参考标识符")
    leap_indicator = Column(String(64), nullable=True, comment="闰秒指示器描述")
    poll_interval = Column(Integer, nullable=True, comment="轮询间隔指数")

    # 时间戳字段（存储为浮点数，便于计算）
    reference_timestamp = Column(Float, nullable=True, comment="参考时间戳（NTP格式）")
    originate_timestamp = Column(Float, nullable=True, comment="发起时间戳（NTP格式）")
    receive_timestamp = Column(Float, nullable=True, comment="接收时间戳（NTP格式）")
    transmit_timestamp = Column(Float, nullable=True, comment="传输时间戳（NTP格式）")

    # 性能指标（预计算字段）
    client_to_server_latency_seconds = Column(Float, nullable=True, comment="客户端到服务器延迟（秒）")
    server_processing_time_seconds = Column(Float, nullable=True, comment="服务器处理时间（秒）")
    total_process_time_seconds = Column(Float, nullable=True, comment="总处理时间（秒）")

    # 会话元数据
    packet_length = Column(Integer, nullable=True, comment="数据包长度（字节）")
    session_timestamp = Column(DateTime, nullable=False, default=func.now(), comment="会话时间戳")

    # 记录管理字段
    first_seen_timestamp = Column(DateTime, nullable=False, default=func.now(), comment="首次发现时间")
    last_seen_timestamp = Column(DateTime, nullable=False, default=func.now(), comment="最后发现时间")
    session_count = Column(Integer, nullable=False, default=1, comment="会话总数")
    created_at = Column(DateTime, nullable=False, default=func.now(), comment="记录创建时间")
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="记录更新时间")

    # 创建复合索引以优化查询性能
    __table_args__ = (
        Index('idx_client_interface', 'client_ip', 'interface_name'),
        Index('idx_last_seen', 'last_seen_timestamp'),
        Index('idx_interface_last_seen', 'interface_name', 'last_seen_timestamp'),
        Index('idx_client_session_time', 'client_ip', 'session_timestamp'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """
        将模型实例转换为字典格式

        Returns:
            Dict[str, Any]: 包含所有字段的字典
        """
        return {
            'id': self.id,
            'client_ip': self.client_ip,
            'client_port': self.client_port,
            'server_ip': self.server_ip,
            'server_port': self.server_port,
            'interface_name': self.interface_name,
            'ntp_version': self.ntp_version,
            'stratum': self.stratum,
            'precision': self.precision,
            'root_delay': self.root_delay,
            'root_dispersion': self.root_dispersion,
            'reference_id': self.reference_id,
            'leap_indicator': self.leap_indicator,
            'poll_interval': self.poll_interval,
            'reference_timestamp': self.reference_timestamp,
            'originate_timestamp': self.originate_timestamp,
            'receive_timestamp': self.receive_timestamp,
            'transmit_timestamp': self.transmit_timestamp,
            'client_to_server_latency_seconds': self.client_to_server_latency_seconds,
            'server_processing_time_seconds': self.server_processing_time_seconds,
            'total_process_time_seconds': self.total_process_time_seconds,
            'packet_length': self.packet_length,
            'session_timestamp': self.session_timestamp.isoformat() if self.session_timestamp else None,
            'first_seen_timestamp': self.first_seen_timestamp.isoformat() if self.first_seen_timestamp else None,
            'last_seen_timestamp': self.last_seen_timestamp.isoformat() if self.last_seen_timestamp else None,
            'session_count': self.session_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def to_summary_dict(self) -> Dict[str, Any]:
        """
        将模型实例转换为摘要字典格式（用于列表显示）

        Returns:
            Dict[str, Any]: 包含关键字段的精简字典
        """
        return {
            'id': self.id,
            'client_ip': self.client_ip,
            'interface_name': self.interface_name,
            'ntp_version': self.ntp_version,
            'stratum': self.stratum,
            'server_ip': self.server_ip,
            'last_seen_timestamp': self.last_seen_timestamp.isoformat() if self.last_seen_timestamp else None,
            'session_count': self.session_count,
            'client_to_server_latency_seconds': self.client_to_server_latency_seconds,
            'total_process_time_seconds': self.total_process_time_seconds
        }

    @classmethod
    def from_session_data(cls, session_data: Dict[str, Any]) -> 'NTPClient':
        """
        从会话数据创建NTPClient实例

        Args:
            session_data: 从ntp_worker.py接收的会话数据

        Returns:
            NTPClient: 新的NTPClient实例
        """
        # 解析会话时间戳
        session_timestamp = None
        if session_data.get('session_timestamp'):
            try:
                session_timestamp = datetime.fromisoformat(
                    session_data['session_timestamp'].replace('Z', '+00:00')
                )
            except (ValueError, AttributeError):
                session_timestamp = datetime.utcnow()
        else:
            session_timestamp = datetime.utcnow()

        return cls(
            client_ip=session_data.get('client_ip', ''),
            client_port=session_data.get('client_port', 0),
            server_ip=session_data.get('server_ip', ''),
            server_port=session_data.get('server_port', 123),
            interface_name=session_data.get('interface_name', ''),
            ntp_version=session_data.get('ntp_version', 0),
            stratum=session_data.get('stratum'),
            precision=session_data.get('precision'),
            root_delay=session_data.get('root_delay'),
            root_dispersion=session_data.get('root_dispersion'),
            reference_id=session_data.get('reference_id'),
            leap_indicator=session_data.get('leap_indicator'),
            poll_interval=session_data.get('poll_interval'),
            reference_timestamp=session_data.get('reference_timestamp'),
            originate_timestamp=session_data.get('originate_timestamp'),
            receive_timestamp=session_data.get('receive_timestamp'),
            transmit_timestamp=session_data.get('transmit_timestamp'),
            client_to_server_latency_seconds=session_data.get('client_to_server_latency_seconds'),
            server_processing_time_seconds=session_data.get('server_processing_time_seconds'),
            total_process_time_seconds=session_data.get('total_process_time_seconds'),
            packet_length=session_data.get('packet_length'),
            session_timestamp=session_timestamp,
            first_seen_timestamp=session_timestamp,
            last_seen_timestamp=session_timestamp
        )

    def update_from_session_data(self, session_data: Dict[str, Any]) -> None:
        """
        使用新的会话数据更新现有记录

        Args:
            session_data: 从ntp_worker.py接收的新会话数据
        """
        # 解析会话时间戳
        session_timestamp = None
        if session_data.get('session_timestamp'):
            try:
                session_timestamp = datetime.fromisoformat(
                    session_data['session_timestamp'].replace('Z', '+00:00')
                )
            except (ValueError, AttributeError):
                session_timestamp = datetime.utcnow()
        else:
            session_timestamp = datetime.utcnow()

        # 更新最新的NTP协议信息
        self.ntp_version = session_data.get('ntp_version', self.ntp_version)
        self.stratum = session_data.get('stratum', self.stratum)
        self.precision = session_data.get('precision', self.precision)
        self.root_delay = session_data.get('root_delay', self.root_delay)
        self.root_dispersion = session_data.get('root_dispersion', self.root_dispersion)
        self.reference_id = session_data.get('reference_id', self.reference_id)
        self.leap_indicator = session_data.get('leap_indicator', self.leap_indicator)
        self.poll_interval = session_data.get('poll_interval', self.poll_interval)

        # 更新时间戳
        self.reference_timestamp = session_data.get('reference_timestamp', self.reference_timestamp)
        self.originate_timestamp = session_data.get('originate_timestamp', self.originate_timestamp)
        self.receive_timestamp = session_data.get('receive_timestamp', self.receive_timestamp)
        self.transmit_timestamp = session_data.get('transmit_timestamp', self.transmit_timestamp)

        # 更新性能指标
        self.client_to_server_latency_seconds = session_data.get('client_to_server_latency_seconds',
                                                                 self.client_to_server_latency_seconds)
        self.server_processing_time_seconds = session_data.get('server_processing_time_seconds',
                                                               self.server_processing_time_seconds)
        self.total_process_time_seconds = session_data.get('total_process_time_seconds',
                                                           self.total_process_time_seconds)

        # 更新会话元数据
        self.packet_length = session_data.get('packet_length', self.packet_length)
        self.session_timestamp = session_timestamp
        self.last_seen_timestamp = session_timestamp

        # 增加会话计数
        self.session_count += 1

    def __repr__(self) -> str:
        """字符串表示"""
        return (f"<NTPClient(id={self.id}, client_ip='{self.client_ip}', "
                f"interface='{self.interface_name}', sessions={self.session_count}, "
                f"last_seen='{self.last_seen_timestamp}')>")

    def __str__(self) -> str:
        """用户友好的字符串表示"""
        return f"NTP客户端 {self.client_ip} (网卡: {self.interface_name}, 会话: {self.session_count})"