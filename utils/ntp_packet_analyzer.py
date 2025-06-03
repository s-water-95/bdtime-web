#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配对式NTP分析器 - 增强版
将NTP请求和响应配对显示，支持网卡标识
"""

import subprocess
import sys
import signal
import re
import json
import time
from datetime import datetime, timezone
from collections import defaultdict


class PairedNTPAnalyzer:
    def __init__(self, interface='any', port=123, output_file=None, pairing_timeout=2.0):
        self.interface = interface
        self.port = port
        self.output_file = output_file
        self.pairing_timeout = pairing_timeout
        self.running = False
        self.packet_count = 0
        self.session_count = 0

        # 存储待配对的请求和响应
        self.pending_requests = {}  # key: (client_ip, client_port) -> request_data
        self.completed_sessions = []
        self.unmatched_packets = []

        # 网卡信息缓存
        self.interface_cache = {}
        # 需要过滤的特殊网卡
        self.filtered_interfaces = {
            'lo', 'sit0', 'teql0', 'tunl0', 'gre0', 'gretap0',
            'ip_vti0', 'ip6_vti0', 'ip6tnl0', 'ip6gre0'
        }
        self.initialize_interface_info()

    def initialize_interface_info(self):
        """初始化网卡信息"""
        try:
            # 获取网卡信息
            result = subprocess.run(['ip', 'addr', 'show'],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.parse_interface_info(result.stdout)
        except Exception as e:
            print(f"⚠️  获取网卡信息失败: {e}")

    def should_filter_interface(self, interface_name):
        """判断是否应该过滤掉该网卡"""
        # 过滤回环接口
        if interface_name in self.filtered_interfaces:
            return True

        # 过滤包含@符号的虚拟接口 (如 sit0@NONE)
        if '@' in interface_name:
            return True

        # 过滤以特定前缀开头的接口
        filtered_prefixes = ['docker', 'br-', 'veth', 'virbr', 'vmnet']
        for prefix in filtered_prefixes:
            if interface_name.startswith(prefix):
                return True

        return False

    def parse_interface_info(self, ip_output):
        """解析网卡信息"""
        current_interface = None

        for line in ip_output.split('\n'):
            # 解析网卡名称 (例如: "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP>")
            interface_match = re.match(r'^\d+:\s+([^:]+):', line)
            if interface_match:
                current_interface = interface_match.group(1).strip()

                # 过滤特殊网卡
                if self.should_filter_interface(current_interface):
                    current_interface = None
                    continue

                if current_interface not in self.interface_cache:
                    self.interface_cache[current_interface] = {
                        'name': current_interface,
                        'ip_addresses': [],
                        'description': ''
                    }

            # 解析IP地址 (例如: "    inet 192.168.1.100/24 brd 192.168.1.255 scope global eth0")
            elif current_interface and 'inet ' in line:
                ip_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)', line)
                if ip_match:
                    ip_addr = ip_match.group(1)
                    prefix = ip_match.group(2)
                    self.interface_cache[current_interface]['ip_addresses'].append({
                        'ip': ip_addr,
                        'prefix': prefix,
                        'network': self.calculate_network(ip_addr, int(prefix))
                    })

    def calculate_network(self, ip_addr, prefix_len):
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

    def determine_interface_for_ip(self, ip_address):
        """根据IP地址确定对应的网卡"""
        try:
            ip_parts = [int(x) for x in ip_address.split('.')]
            ip_int = (ip_parts[0] << 24) + (ip_parts[1] << 16) + (ip_parts[2] << 8) + ip_parts[3]

            for interface_name, interface_info in self.interface_cache.items():
                for addr_info in interface_info['ip_addresses']:
                    try:
                        network_ip, prefix = addr_info['network'].split('/')
                        prefix_len = int(prefix)

                        network_parts = [int(x) for x in network_ip.split('.')]
                        network_int = (network_parts[0] << 24) + (network_parts[1] << 16) + (network_parts[2] << 8) + \
                                      network_parts[3]

                        mask = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF

                        if (ip_int & mask) == network_int:
                            return {
                                'interface': interface_name,
                                'local_ip': addr_info['ip'],
                                'network': addr_info['network']
                            }
                    except:
                        continue

            return {'interface': 'unknown', 'local_ip': 'unknown', 'network': 'unknown'}
        except:
            return {'interface': 'unknown', 'local_ip': 'unknown', 'network': 'unknown'}

    def parse_packet(self, lines):
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
                src_ip = client_match.group(1)
                dst_ip = client_match.group(3)

                # 确定网卡信息
                src_interface_info = self.determine_interface_for_ip(src_ip)
                dst_interface_info = self.determine_interface_for_ip(dst_ip)

                packet_info.update({
                    'src_ip': src_ip,
                    'src_port': int(client_match.group(2)),
                    'dst_ip': dst_ip,
                    'dst_port': 123,
                    'ntp_version': int(client_match.group(4)),
                    'packet_type': 'request',
                    'src_interface_info': src_interface_info,
                    'dst_interface_info': dst_interface_info
                })

            # 解析服务器响应
            server_match = re.search(r'(\d+\.\d+\.\d+\.\d+)\.123 > (\d+\.\d+\.\d+\.\d+)\.(\d+): NTPv(\d+), Server',
                                     line)
            if server_match:
                src_ip = server_match.group(1)
                dst_ip = server_match.group(2)

                # 确定网卡信息
                src_interface_info = self.determine_interface_for_ip(src_ip)
                dst_interface_info = self.determine_interface_for_ip(dst_ip)

                packet_info.update({
                    'src_ip': src_ip,
                    'src_port': 123,
                    'dst_ip': dst_ip,
                    'dst_port': int(server_match.group(3)),
                    'ntp_version': int(server_match.group(4)),
                    'packet_type': 'response',
                    'src_interface_info': src_interface_info,
                    'dst_interface_info': dst_interface_info
                })

            # 解析NTP协议字段（保持原有的解析逻辑）
            self.parse_ntp_fields(line, ntp_info)

        return packet_info, ntp_info

    def parse_ntp_fields(self, line, ntp_info):
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
        ref_id_match = re.search(r'Reference-ID: ([^\s]+)', line)
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

    def get_session_key(self, packet_info):
        """生成会话键"""
        if packet_info['packet_type'] == 'request':
            return (packet_info['src_ip'], packet_info['src_port'], packet_info['dst_ip'])
        else:  # response
            return (packet_info['dst_ip'], packet_info['dst_port'], packet_info['src_ip'])

    def try_pair_packet(self, packet_info, ntp_info):
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

    def display_paired_session(self, session):
        """显示配对的NTP会话"""
        req = session['request']
        resp = session['response']

        print("\n" + "=" * 95)
        print(f"🔄 NTP会话 #{session['session_id']} - 完整交互流程")
        print("=" * 95)

        # 会话概览
        req_info = req['packet_info']
        resp_info = resp['packet_info']

        print("📋 会话概览:")
        print(f"  ├─ 客户端: {req_info['src_ip']}:{req_info['src_port']}")
        print(f"  ├─ 服务器: {req_info['dst_ip']}:{req_info['dst_port']}")
        print(f"  ├─ NTP版本: v{req_info['ntp_version']}")
        print(f"  └─ 数据长度: {req['ntp_info'].get('length', 48)} bytes")

        # 网卡信息 - 只显示服务器网卡
        server_if = req_info.get('dst_interface_info', {})
        print(f"  └─ 服务器网卡: {server_if.get('interface', 'unknown')}")

        # 客户端请求详情
        print(f"\n📤 客户端请求 ({req_info['timestamp']}):")
        self.display_ntp_details(req['ntp_info'], "request")

        # 服务器响应详情
        print(f"\n📥 服务器响应 ({resp_info['timestamp']}):")
        self.display_ntp_details(resp['ntp_info'], "response")

        # 时间分析
        self.display_timing_analysis(req['ntp_info'], resp['ntp_info'])

        print("=" * 95)

    def display_ntp_details(self, ntp_info, packet_type):
        """显示NTP详细信息"""
        if 'leap_indicator' in ntp_info:
            leap_desc = self.get_leap_description(ntp_info.get('leap_value', -1))
            print(f"  ├─ 闰秒指示器: {ntp_info['leap_indicator']} - {leap_desc}")

        if 'stratum' in ntp_info:
            stratum_desc = self.get_stratum_description(ntp_info['stratum'])
            print(f"  ├─ 层级: {ntp_info['stratum']} ({stratum_desc})")

        if 'poll' in ntp_info:
            poll_seconds = 2 ** ntp_info['poll']
            print(f"  ├─ 轮询间隔: {ntp_info['poll']} (每 {poll_seconds} 秒)")

        if 'precision' in ntp_info:
            precision_val = 2 ** ntp_info['precision']
            print(f"  ├─ 时钟精度: {ntp_info['precision']} (±{precision_val:.9f} 秒)")

        if 'root_delay' in ntp_info:
            print(f"  ├─ 根延迟: {ntp_info['root_delay']:.6f} 秒")

        if 'root_dispersion' in ntp_info:
            print(f"  ├─ 根离散: {ntp_info['root_dispersion']:.6f} 秒")

        if 'reference_id' in ntp_info:
            print(f"  └─ 参考标识: {ntp_info['reference_id']}")

        # 时间戳信息
        self.display_timestamps(ntp_info, packet_type)

    def display_timestamps(self, ntp_info, packet_type):
        """显示时间戳信息"""
        print(f"  🕐 时间戳信息 ({packet_type}):")

        timestamp_labels = {
            'reference': '参考时间戳',
            'originate': '发起时间戳',
            'receive': '接收时间戳',
            'transmit': '传输时间戳'
        }

        for ts_key, label in timestamp_labels.items():
            ts_value = ntp_info.get(f'{ts_key}_timestamp', 0)
            readable_time = self.ntp_timestamp_to_datetime(ts_value)
            print(f"    ├─ {label}: {readable_time}")

    def display_timing_analysis(self, req_ntp, resp_ntp):
        """显示时间分析"""
        print(f"\n⏱️  时间性能分析:")

        # 获取关键时间戳
        t1 = req_ntp.get('transmit_timestamp', 0)  # 客户端发送时间
        t2 = resp_ntp.get('receive_timestamp', 0)  # 服务器接收时间
        t3 = resp_ntp.get('transmit_timestamp', 0)  # 服务器发送时间
        # t4 会是客户端接收时间，但我们在抓包中无法获得

        if t1 > 0 and t2 > 0 and t3 > 0:
            network_delay = t2 - t1  # 网络延迟（单向）
            server_processing = t3 - t2  # 服务器处理时间

            print(f"  ├─ 网络传输延迟: {network_delay:.6f} 秒")
            print(f"  ├─ 服务器处理时间: {server_processing:.6f} 秒")
            print(f"  └─ 总响应时间: {(network_delay + server_processing):.6f} 秒")

            # 时钟偏移估算（简化）
            if network_delay > 0:
                estimated_offset = network_delay + (server_processing / 2)
                print(f"  📊 估算时钟偏移: ±{estimated_offset:.6f} 秒")
        else:
            print(f"  ⚠️  时间戳信息不完整，无法计算详细时间分析")

    def get_leap_description(self, leap_value):
        """获取闰秒指示器描述"""
        descriptions = {
            0: "无警告",
            1: "最后一分钟有61秒",
            2: "最后一分钟有59秒",
            3: "时钟未同步"
        }
        return descriptions.get(leap_value, "未知状态")

    def get_stratum_description(self, stratum):
        """获取层级描述"""
        descriptions = {
            0: "未指定/无效",
            1: "主参考源",
            2: "二级参考源",
            3: "三级参考源"
        }
        return descriptions.get(stratum, f"{stratum}级参考源")

    def ntp_timestamp_to_datetime(self, ntp_timestamp):
        """将NTP时间戳转换为可读时间"""
        if ntp_timestamp == 0:
            return "未设置"
        try:
            unix_timestamp = ntp_timestamp - 2208988800
            dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
            return dt.strftime('%Y-%m-%d %H:%M:%S.%f UTC')[:-3]
        except (ValueError, OSError):
            return f"解析错误: {ntp_timestamp}"

    def cleanup_old_requests(self):
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

    def process_packet_block(self, lines):
        """处理数据包块"""
        if not lines:
            return

        packet_info, ntp_info = self.parse_packet(lines)

        if packet_info.get('packet_type'):
            self.try_pair_packet(packet_info, ntp_info)

            # 定期清理超时的请求
            if self.packet_count % 10 == 0:
                self.cleanup_old_requests()

    def run_capture(self):
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
            print(f"❌ 捕获出错: {e}")
        finally:
            if 'process' in locals():
                process.terminate()

    def save_results(self):
        """保存结果"""
        if self.output_file:
            try:
                summary = {
                    'capture_summary': {
                        'total_packets': self.packet_count,
                        'completed_sessions': len(self.completed_sessions),
                        'pending_requests': len(self.pending_requests),
                        'unmatched_packets': len(self.unmatched_packets),
                        'capture_time': datetime.now().isoformat()
                    },
                    'interface_info': self.interface_cache,
                    'sessions': self.completed_sessions,
                    'unmatched_packets': self.unmatched_packets
                }

                with open(self.output_file, 'w', encoding='utf-8') as f:
                    json.dump(summary, f, indent=2, ensure_ascii=False)

                print(f"\n💾 结果已保存到: {self.output_file}")
            except Exception as e:
                print(f"❌ 保存失败: {e}")

    def display_interface_summary(self):
        """显示网卡摘要信息"""
        if self.interface_cache:
            print(f"\n🔌 检测到的网络接口:")
            for interface_name, interface_info in self.interface_cache.items():
                if interface_info['ip_addresses']:  # 只显示有IP地址的接口
                    print(f"  ├─ {interface_name}:")
                    for addr in interface_info['ip_addresses']:
                        print(f"  │   └─ {addr['ip']}/{addr['prefix']} (网络: {addr['network']})")
                else:
                    print(f"  ├─ {interface_name}: (无IP地址)")
            print()

    def start_capture(self):
        """开始捕获"""
        print("🚀 配对式NTP数据包分析器 - 增强版")
        print("智能配对NTP请求和响应，支持网卡标识")
        print("=" * 80)
        print(f"📡 监听接口: {self.interface}")
        print(f"🔍 目标端口: {self.port}")
        print(f"⏱️  配对超时: {self.pairing_timeout} 秒")
        if self.output_file:
            print(f"💾 输出文件: {self.output_file}")

        # 显示网卡信息
        self.display_interface_summary()

        print("=" * 80)
        print("⏳ 等待NTP会话...")
        print("按 Ctrl+C 停止监听")

        self.running = True

        def signal_handler(sig, frame):
            print(f"\n\n📊 捕获统计:")
            print(f"  总数据包: {self.packet_count}")
            print(f"  完整会话: {len(self.completed_sessions)}")
            print(f"  待配对请求: {len(self.pending_requests)}")
            print(f"  未匹配数据包: {len(self.unmatched_packets)}")
            self.save_results()
            print("🛑 监听已停止")
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)

        try:
            self.run_capture()
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False


def main():
    import argparse

    parser = argparse.ArgumentParser(description='配对式NTP数据包分析器 - 增强版')
    parser.add_argument('-i', '--interface', default='any',
                        help='网络接口 (默认: any)')
    parser.add_argument('-p', '--port', type=int, default=123,
                        help='NTP端口 (默认: 123)')
    parser.add_argument('-o', '--output',
                        help='保存结果到JSON文件')
    parser.add_argument('-t', '--timeout', type=float, default=2.0,
                        help='配对超时时间（秒，默认: 2.0）')

    args = parser.parse_args()

    # 权限检查
    import os
    if os.geteuid() != 0:
        print("❌ 需要root权限运行")
        print("请使用: sudo python3 script.py")
        sys.exit(1)

    analyzer = PairedNTPAnalyzer(
        interface=args.interface,
        port=args.port,
        output_file=args.output,
        pairing_timeout=args.timeout
    )

    analyzer.start_capture()


if __name__ == "__main__":
    main()