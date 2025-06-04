#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NTP数据包分析工作脚本
负责单个网卡的NTP数据包捕获和分析
作为独立进程运行，接收命令行参数
"""

import subprocess
import sys
import signal
import re
import json
import time
import os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
import argparse

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/ntp_worker.log', mode='a')
    ]
)

logger = logging.getLogger(__name__)


class SingleInterfaceNTPAnalyzer:
    """单网卡NTP分析器 - 专注于单个网卡的监控"""

    def __init__(self, interface: str, port: int = 123, output_file: Optional[str] = None,
                 pairing_timeout: float = 2.0):
        """
        初始化NTP分析器

        Args:
            interface: 网卡名称
            port: NTP端口
            output_file: 输出文件路径
            pairing_timeout: 配对超时时间
        """
        self.interface = interface
        self.port = port
        self.output_file = output_file
        self.pairing_timeout = pairing_timeout
        self.running = False
        self.packet_count = 0
        self.session_count = 0

        # 存储待配对的请求和响应
        self.pending_requests = {}
        self.completed_sessions = []
        self.unmatched_packets = []

        # 网卡信息
        self.interface_info = self.get_interface_info()

    def get_interface_info(self) -> Dict[str, Any]:
        """获取指定网卡的信息"""
        try:
            result = subprocess.run(['ip', 'addr', 'show', self.interface],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return self.parse_interface_info(result.stdout)
        except Exception as e:
            logger.warning(f"获取网卡 {self.interface} 信息失败: {e}")

        return {
            'name': self.interface,
            'ip_addresses': [],
            'description': '信息获取失败'
        }

    def parse_interface_info(self, ip_output: str) -> Dict[str, Any]:
        """解析网卡信息"""
        interface_info = {
            'name': self.interface,
            'ip_addresses': [],
            'description': ''
        }

        for line in ip_output.split('\n'):
            # 解析IP地址
            if 'inet ' in line:
                ip_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)', line)
                if ip_match:
                    ip_addr = ip_match.group(1)
                    prefix = ip_match.group(2)
                    interface_info['ip_addresses'].append({
                        'ip': ip_addr,
                        'prefix': prefix,
                        'network': self.calculate_network(ip_addr, int(prefix))
                    })

        return interface_info

    def calculate_network(self, ip_addr: str, prefix_len: int) -> str:
        """计算网络地址"""
        try:
            ip_parts = [int(x) for x in ip_addr.split('.')]
            mask = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF

            ip_int = (ip_parts[0] << 24) + (ip_parts[1] << 16) + (ip_parts[2] << 8) + ip_parts[3]
            network_int = ip_int & mask

            network_parts = [
                (network_int >> 24) & 0xFF,
                (network_int >> 16) & 0xFF,
                (network_int >> 8) & 0xFF,
                network_int & 0xFF
            ]

            return f"{'.'.join(map(str, network_parts))}/{prefix_len}"
        except:
            return f"{ip_addr}/{prefix_len}"

    def parse_packet(self, lines: List[str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """解析单个数据包"""
        packet_info = {}
        ntp_info = {}

        for line in lines:
            line = line.strip()

            # 解析时间戳
            timestamp_match = re.match(r'(\d+:\d+:\d+\.\d+)', line)
            if timestamp_match:
                packet_info['timestamp'] = timestamp_match.group(1)
                packet_info['capture_time'] = time.time()

            # 解析客户端请求
            client_match = re.search(r'(\d+\.\d+\.\d+\.\d+)\.(\d+) > (\d+\.\d+\.\d+\.\d+)\.123: NTPv(\d+), Client',
                                     line)
            if client_match:
                packet_info.update({
                    'src_ip': client_match.group(1),
                    'src_port': int(client_match.group(2)),
                    'dst_ip': client_match.group(3),
                    'dst_port': 123,
                    'ntp_version': int(client_match.group(4)),
                    'packet_type': 'request'
                })

            # 解析服务器响应
            server_match = re.search(r'(\d+\.\d+\.\d+\.\d+)\.123 > (\d+\.\d+\.\d+\.\d+)\.(\d+): NTPv(\d+), Server',
                                     line)
            if server_match:
                packet_info.update({
                    'src_ip': server_match.group(1),
                    'src_port': 123,
                    'dst_ip': server_match.group(2),
                    'dst_port': int(server_match.group(3)),
                    'ntp_version': int(server_match.group(4)),
                    'packet_type': 'response'
                })

            # 解析NTP协议字段
            self.parse_ntp_fields(line, ntp_info)

        return packet_info, ntp_info

    def parse_ntp_fields(self, line: str, ntp_info: Dict[str, Any]) -> None:
        """解析NTP协议字段"""
        # 数据长度
        length_match = re.search(r'length (\d+)', line)
        if length_match:
            ntp_info['length'] = int(length_match.group(1))

        # 闰秒指示器
        leap_match = re.search(r'Leap indicator: ([^,]+)', line)
        if leap_match:
            leap_text = leap_match.group(1).strip()
            ntp_info['leap_indicator'] = leap_text
            leap_num_match = re.search(r'\((\d+)\)', leap_text)
            if leap_num_match:
                ntp_info['leap_value'] = int(leap_num_match.group(1))

        # 层级
        stratum_match = re.search(r'Stratum (\d+) \(([^)]+)\)', line)
        if stratum_match:
            ntp_info.update({
                'stratum': int(stratum_match.group(1)),
                'stratum_desc': stratum_match.group(2)
            })

        # 轮询间隔
        poll_match = re.search(r'poll (\d+) \(([^)]+)\)', line)
        if poll_match:
            ntp_info.update({
                'poll': int(poll_match.group(1)),
                'poll_desc': poll_match.group(2)
            })

        # 精度
        precision_match = re.search(r'precision (-?\d+)', line)
        if precision_match:
            ntp_info['precision'] = int(precision_match.group(1))

        # 根延迟和根离散
        root_match = re.search(r'Root Delay: ([0-9.]+), Root dispersion: ([0-9.]+)', line)
        if root_match:
            ntp_info.update({
                'root_delay': float(root_match.group(1)),
                'root_dispersion': float(root_match.group(2))
            })

        # 参考ID
        ref_id_match = re.search(r'Reference-ID: ([A-Za-z0-9]+)', line)
        if ref_id_match:
            ntp_info['reference_id'] = ref_id_match.group(1)

        # 时间戳
        timestamps = {
            'reference': r'Reference Timestamp:\s+([0-9.]+)',
            'originate': r'Originator Timestamp: ([0-9.]+)',
            'receive': r'Receive Timestamp:\s+([0-9.]+)',
            'transmit': r'Transmit Timestamp:\s+([0-9.]+)'
        }

        for ts_name, pattern in timestamps.items():
            ts_match = re.search(pattern, line)
            if ts_match:
                ntp_info[f'{ts_name}_timestamp'] = float(ts_match.group(1))

    def get_session_key(self, packet_info: Dict[str, Any]) -> Tuple[str, int, str]:
        """生成会话键"""
        if packet_info['packet_type'] == 'request':
            return (packet_info['src_ip'], packet_info['src_port'], packet_info['dst_ip'])
        else:  # response
            return (packet_info['dst_ip'], packet_info['dst_port'], packet_info['src_ip'])

    def try_pair_packet(self, packet_info: Dict[str, Any], ntp_info: Dict[str, Any]) -> None:
        """尝试配对数据包"""
        session_key = self.get_session_key(packet_info)

        if packet_info['packet_type'] == 'request':
            # 存储请求，等待响应
            self.pending_requests[session_key] = {
                'packet_info': packet_info,
                'ntp_info': ntp_info,
                'timestamp': time.time()
            }

        elif packet_info['packet_type'] == 'response':
            # 查找对应的请求
            if session_key in self.pending_requests:
                request_data = self.pending_requests.pop(session_key)

                # 创建完整的会话记录
                session = {
                    'session_id': self.session_count + 1,
                    'interface': self.interface,
                    'request': request_data,
                    'response': {
                        'packet_info': packet_info,
                        'ntp_info': ntp_info,
                        'timestamp': time.time()
                    }
                }

                self.session_count += 1
                self.completed_sessions.append(session)
                self.display_paired_session(session)

            else:
                # 没有找到对应的请求，记录为未匹配
                self.unmatched_packets.append({
                    'type': 'orphaned_response',
                    'packet_info': packet_info,
                    'ntp_info': ntp_info
                })

    def merge_session_data(self, req_ntp: Dict[str, Any], resp_ntp: Dict[str, Any]) -> Dict[str, Any]:
        """合并请求和响应的NTP信息"""
        merged = {}

        # 优先使用响应中的信息
        merged['leap_indicator'] = resp_ntp.get('leap_indicator', req_ntp.get('leap_indicator', '未知'))
        merged['leap_value'] = resp_ntp.get('leap_value', req_ntp.get('leap_value', -1))
        merged['stratum'] = resp_ntp.get('stratum', req_ntp.get('stratum', 0))
        merged['poll'] = resp_ntp.get('poll', req_ntp.get('poll', 0))
        merged['precision'] = resp_ntp.get('precision', req_ntp.get('precision', 0))
        merged['root_delay'] = resp_ntp.get('root_delay', req_ntp.get('root_delay', 0))
        merged['root_dispersion'] = resp_ntp.get('root_dispersion', req_ntp.get('root_dispersion', 0))
        merged['reference_id'] = resp_ntp.get('reference_id', req_ntp.get('reference_id', '未知'))

        # 时间戳信息
        merged['reference_timestamp'] = resp_ntp.get('reference_timestamp', 0)
        merged['originate_timestamp'] = resp_ntp.get('originate_timestamp', req_ntp.get('transmit_timestamp', 0))
        merged['receive_timestamp'] = resp_ntp.get('receive_timestamp', 0)
        merged['transmit_timestamp'] = resp_ntp.get('transmit_timestamp', 0)

        return merged

    def display_paired_session(self, session: Dict[str, Any]) -> None:
        """显示配对的NTP会话"""
        req = session['request']
        resp = session['response']
        req_info = req['packet_info']
        resp_info = resp['packet_info']

        # 合并NTP数据
        merged_ntp = self.merge_session_data(req['ntp_info'], resp['ntp_info'])

        logger.info("=" * 80)
        logger.info(f"NTP会话 #{session['session_id']} - {req_info['timestamp']} [网卡: {self.interface}]")
        logger.info("=" * 80)

        # 会话基本信息
        logger.info("会话信息:")
        logger.info(f"  监控网卡: {self.interface}")
        logger.info(f"  客户端: {req_info['src_ip']}:{req_info['src_port']}")
        logger.info(f"  服务器: {req_info['dst_ip']}:{req_info['dst_port']}")
        logger.info(f"  NTP版本: v{req_info['ntp_version']}")
        logger.info(f"  数据长度: {req['ntp_info'].get('length', 48)} bytes")

        # NTP协议信息
        logger.info("NTP协议信息:")

        # 闰秒指示器
        leap_desc = self.get_leap_description(merged_ntp['leap_value'])
        logger.info(f"  闰秒指示器: {leap_desc}")

        # 层级
        stratum_desc = self.get_stratum_description(merged_ntp['stratum'])
        logger.info(f"  时间层级: {merged_ntp['stratum']} ({stratum_desc})")

        # 轮询间隔
        if merged_ntp['poll'] > 0:
            poll_seconds = 2 ** merged_ntp['poll']
            logger.info(f"  轮询间隔: {poll_seconds} 秒")

        # 时钟精度
        if merged_ntp['precision'] != 0:
            precision_val = 2 ** merged_ntp['precision']
            logger.info(f"  时钟精度: ±{precision_val:.9f} 秒")

        # 根延迟和根离散
        if merged_ntp['root_delay'] > 0:
            logger.info(f"  根延迟: {merged_ntp['root_delay']:.6f} 秒")
        if merged_ntp['root_dispersion'] > 0:
            logger.info(f"  根离散: {merged_ntp['root_dispersion']:.6f} 秒")

        # 参考标识
        if merged_ntp['reference_id'] != '未知':
            logger.info(f"  参考标识: {merged_ntp['reference_id']}")

        # 关键时间戳
        logger.info("关键时间戳:")
        if merged_ntp['reference_timestamp'] > 0:
            ref_time = self.ntp_timestamp_to_datetime(merged_ntp['reference_timestamp'])
            logger.info(f"  参考时间: {ref_time}")

        if merged_ntp['originate_timestamp'] > 0:
            orig_time = self.ntp_timestamp_to_datetime(merged_ntp['originate_timestamp'])
            logger.info(f"  发起时间: {orig_time}")

        if merged_ntp['receive_timestamp'] > 0:
            recv_time = self.ntp_timestamp_to_datetime(merged_ntp['receive_timestamp'])
            logger.info(f"  接收时间: {recv_time}")

        if merged_ntp['transmit_timestamp'] > 0:
            trans_time = self.ntp_timestamp_to_datetime(merged_ntp['transmit_timestamp'])
            logger.info(f"  传输时间: {trans_time}")

        # 时间性能分析
        self.display_timing_analysis(merged_ntp)

        logger.info("=" * 80)

    def display_timing_analysis(self, merged_ntp: Dict[str, Any]) -> None:
        """显示时间分析"""
        logger.info("性能分析:")

        # 获取关键时间戳
        t1 = merged_ntp.get('originate_timestamp', 0)  # 客户端发送时间
        t2 = merged_ntp.get('receive_timestamp', 0)  # 服务器接收时间
        t3 = merged_ntp.get('transmit_timestamp', 0)  # 服务器发送时间

        if t1 > 0 and t2 > 0 and t3 > 0:
            network_delay = t2 - t1  # 网络延迟
            server_processing = t3 - t2  # 服务器处理时间

            if network_delay > 0:
                logger.info(f"  网络延迟: {network_delay:.6f} 秒")
            else:
                logger.info(f"  网络延迟: {abs(network_delay):.6f} 秒 (时钟不同步)")

            logger.info(f"  服务器处理: {server_processing:.6f} 秒")

            total_time = abs(network_delay) + server_processing
            logger.info(f"  总响应时间: {total_time:.6f} 秒")
        else:
            logger.warning("  时间戳不完整，无法计算性能指标")

    def get_leap_description(self, leap_value: int) -> str:
        """获取闰秒指示器描述"""
        descriptions = {
            0: "无警告",
            1: "最后一分钟有61秒",
            2: "最后一分钟有59秒",
            3: "时钟未同步"
        }
        return descriptions.get(leap_value, "未知状态")

    def get_stratum_description(self, stratum: int) -> str:
        """获取层级描述"""
        descriptions = {
            0: "未指定/无效",
            1: "主参考源",
            2: "二级参考源",
            3: "三级参考源"
        }
        return descriptions.get(stratum, f"{stratum}级参考源")

    def ntp_timestamp_to_datetime(self, ntp_timestamp: float) -> str:
        """将NTP时间戳转换为可读时间"""
        if ntp_timestamp == 0:
            return "未设置"
        try:
            unix_timestamp = ntp_timestamp - 2208988800
            dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
            return dt.strftime('%Y-%m-%d %H:%M:%S.%f UTC')[:-3]
        except (ValueError, OSError):
            return f"解析错误: {ntp_timestamp}"

    def cleanup_old_requests(self) -> None:
        """清理超时的请求"""
        current_time = time.time()
        expired_keys = []

        for key, request_data in self.pending_requests.items():
            if current_time - request_data['timestamp'] > self.pairing_timeout:
                expired_keys.append(key)
                self.unmatched_packets.append({
                    'type': 'orphaned_request',
                    'packet_info': request_data['packet_info'],
                    'ntp_info': request_data['ntp_info']
                })

        for key in expired_keys:
            del self.pending_requests[key]

    def process_packet_block(self, lines: List[str]) -> None:
        """处理数据包块"""
        if not lines:
            return

        packet_info, ntp_info = self.parse_packet(lines)

        if packet_info.get('packet_type'):
            self.try_pair_packet(packet_info, ntp_info)

            # 定期清理超时的请求
            if self.packet_count % 10 == 0:
                self.cleanup_old_requests()

    def run_capture(self) -> None:
        """运行捕获"""
        cmd = ['tcpdump', '-i', self.interface, '-n', '-v', '-l', f'udp port {self.port}']

        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, bufsize=1
            )

            current_block = []

            while self.running:
                line = process.stdout.readline()
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                # 检测新数据包开始
                if re.match(r'\d+:\d+:\d+\.\d+', line):
                    if current_block:
                        self.process_packet_block(current_block)
                    current_block = [line]
                    self.packet_count += 1
                elif current_block:
                    current_block.append(line)

            if current_block:
                self.process_packet_block(current_block)

        except Exception as e:
            logger.error(f"捕获出错: {e}")
        finally:
            if 'process' in locals():
                process.terminate()

    def save_results(self) -> None:
        """保存结果"""
        if self.output_file:
            try:
                summary = {
                    'capture_summary': {
                        'interface': self.interface,
                        'total_packets': self.packet_count,
                        'completed_sessions': len(self.completed_sessions),
                        'pending_requests': len(self.pending_requests),
                        'unmatched_packets': len(self.unmatched_packets),
                        'capture_time': datetime.now().isoformat()
                    },
                    'interface_info': self.interface_info,
                    'sessions': self.completed_sessions,
                    'unmatched_packets': self.unmatched_packets
                }

                with open(self.output_file, 'w', encoding='utf-8') as f:
                    json.dump(summary, f, indent=2, ensure_ascii=False)

                logger.info(f"结果已保存到: {self.output_file}")
            except Exception as e:
                logger.error(f"保存失败: {e}")

    def start_capture(self) -> None:
        """开始捕获 - 后台模式"""
        logger.info(f"启动网卡 {self.interface} 的NTP监控")
        logger.info(f"监听接口: {self.interface}")
        logger.info(f"目标端口: {self.port}")
        logger.info(f"配对超时: {self.pairing_timeout} 秒")
        if self.output_file:
            logger.info(f"输出文件: {self.output_file}")

        # 显示网卡信息
        if self.interface_info['ip_addresses']:
            logger.info("网卡信息:")
            for addr in self.interface_info['ip_addresses']:
                logger.info(f"  {addr['ip']}/{addr['prefix']} (网络: {addr['network']})")

        logger.info("等待NTP会话...")

        self.running = True

        def signal_handler(sig, frame):
            logger.info(f"网卡 {self.interface} 捕获统计:")
            logger.info(f"  总数据包: {self.packet_count}")
            logger.info(f"  完整会话: {len(self.completed_sessions)}")
            logger.info(f"  待配对请求: {len(self.pending_requests)}")
            logger.info(f"  未匹配数据包: {len(self.unmatched_packets)}")
            self.save_results()
            logger.info(f"网卡 {self.interface} 监听已停止")
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        try:
            self.run_capture()
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False


def main_worker_entry():
    """工作脚本入口点"""
    parser = argparse.ArgumentParser(description='NTP数据包分析工作脚本')

    # 必需参数
    parser.add_argument('--interface', required=True, help='网卡名称 (如: eth0, eth1)')

    # 可选参数
    parser.add_argument('--port', type=int, default=123, help='NTP端口 (默认: 123)')
    parser.add_argument('--timeout', type=float, default=2.0, help='配对超时时间（秒，默认: 2.0）')
    parser.add_argument('--output', help='保存结果到JSON文件')
    parser.add_argument('--daemon', action='store_true', help='后台运行模式 (内部使用)')

    args = parser.parse_args()

    # 创建分析器并开始捕获
    analyzer = SingleInterfaceNTPAnalyzer(
        interface=args.interface,
        port=args.port,
        output_file=args.output,
        pairing_timeout=args.timeout
    )
    analyzer.start_capture()


if __name__ == "__main__":
    main_worker_entry()