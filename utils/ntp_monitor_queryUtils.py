#!/usr/bin/env python3
"""
NTP监控数据查询和分析工具
提供命令行接口查询监控数据
"""

import sqlite3
import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import List, Dict
import statistics


class NTPQueryTool:
    """NTP监控数据查询工具"""

    def __init__(self, db_path: str = "ntp_monitor.db"):
        self.db_path = db_path

    def _connect_db(self):
        """连接数据库"""
        try:
            return sqlite3.connect(self.db_path)
        except sqlite3.Error as e:
            print(f"数据库连接失败: {e}")
            sys.exit(1)

    def list_clients(self, active_only: bool = False, hours: int = 24):
        """列出所有客户端"""
        conn = self._connect_db()
        cursor = conn.cursor()

        if active_only:
            since = datetime.now() - timedelta(hours=hours)
            cursor.execute('''
                SELECT client_ip, interface, request_count, avg_delay, avg_offset,
                       last_seen, stratum_distribution
                FROM client_stats 
                WHERE last_seen > ?
                ORDER BY last_seen DESC
            ''', (since,))
        else:
            cursor.execute('''
                SELECT client_ip, interface, request_count, avg_delay, avg_offset,
                       last_seen, stratum_distribution
                FROM client_stats 
                ORDER BY last_seen DESC
            ''')

        results = cursor.fetchall()
        conn.close()

        if not results:
            print("没有找到客户端数据")
            return

        print(
            f"{'客户端IP':<20} {'接口':<10} {'请求次数':<8} {'平均延迟(ms)':<12} {'平均偏移(ms)':<12} {'最后活动':<20} {'Stratum分布'}")
        print("-" * 120)

        for row in results:
            client_ip, interface, count, delay, offset, last_seen, stratum_dist = row
            delay_ms = f"{delay * 1000:.2f}" if delay else "N/A"
            offset_ms = f"{offset * 1000:.2f}" if offset else "N/A"

            # 解析stratum分布
            try:
                stratum_data = json.loads(stratum_dist) if stratum_dist else {}
                stratum_summary = ", ".join([f"S{k}:{v}" for k, v in stratum_data.items()])
            except:
                stratum_summary = "N/A"

            print(
                f"{client_ip:<20} {interface:<10} {count:<8} {delay_ms:<12} {offset_ms:<12} {last_seen:<20} {stratum_summary}")

    def show_client_detail(self, client_ip: str, hours: int = 24):
        """显示客户端详细信息"""
        conn = self._connect_db()
        cursor = conn.cursor()

        # 获取客户端基本统计
        cursor.execute('SELECT * FROM client_stats WHERE client_ip = ?', (client_ip,))
        stats = cursor.fetchone()

        if not stats:
            print(f"未找到客户端 {client_ip} 的数据")
            conn.close()
            return

        # 显示基本信息
        print(f"\n=== 客户端详细信息: {client_ip} ===")
        print(f"接口: {stats[1]}")
        print(f"首次出现: {stats[2]}")
        print(f"最后活动: {stats[3]}")
        print(f"总请求次数: {stats[4]}")
        print(f"平均延迟: {stats[5] * 1000:.2f} ms")
        print(f"平均偏移: {stats[6] * 1000:.2f} ms")
        print(f"最小延迟: {stats[7] * 1000:.2f} ms")
        print(f"最大延迟: {stats[8] * 1000:.2f} ms")

        # 解析和显示stratum分布
        try:
            stratum_dist = json.loads(stats[9]) if stats[9] else {}
            print(f"Stratum分布: {stratum_dist}")
        except:
            print("Stratum分布: 数据解析失败")

        # 获取最近的详细记录
        since = datetime.now() - timedelta(hours=hours)
        cursor.execute('''
            SELECT timestamp, stratum, network_delay, time_offset, poll_interval
            FROM ntp_records 
            WHERE client_ip = ? AND timestamp > ?
            ORDER BY timestamp DESC
            LIMIT 10
        ''', (client_ip, since))

        records = cursor.fetchall()

        if records:
            print(f"\n=== 最近 {min(len(records), 10)} 条记录 ===")
            print(f"{'时间':<20} {'Stratum':<8} {'延迟(ms)':<10} {'偏移(ms)':<10} {'轮询间隔'}")
            print("-" * 70)

            for record in records:
                timestamp, stratum, delay, offset, poll = record
                delay_ms = f"{delay * 1000:.2f}" if delay else "N/A"
                offset_ms = f"{offset * 1000:.2f}" if offset else "N/A"
                print(f"{timestamp:<20} {stratum:<8} {delay_ms:<10} {offset_ms:<10} {poll}")

        conn.close()

    def show_statistics(self, hours: int = 24):
        """显示总体统计信息"""
        conn = self._connect_db()
        cursor = conn.cursor()

        since = datetime.now() - timedelta(hours=hours)

        # 总体统计
        cursor.execute('SELECT COUNT(*) FROM client_stats')
        total_clients = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM client_stats WHERE last_seen > ?', (since,))
        active_clients = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM ntp_records WHERE timestamp > ?', (since,))
        total_requests = cursor.fetchone()[0]

        # 延迟和偏移统计
        cursor.execute('''
            SELECT network_delay, time_offset 
            FROM ntp_records 
            WHERE timestamp > ? AND network_delay IS NOT NULL AND time_offset IS NOT NULL
        ''', (since,))

        timing_data = cursor.fetchall()

        print(f"\n=== NTP监控统计 (最近 {hours} 小时) ===")
        print(f"总客户端数量: {total_clients}")
        print(f"活跃客户端数量: {active_clients}")
        print(f"总请求数量: {total_requests}")

        if timing_data:
            delays = [d[0] * 1000 for d in timing_data if d[0] is not None]  # 转换为毫秒
            offsets = [d[1] * 1000 for d in timing_data if d[1] is not None]

            if delays:
                print(f"\n延迟统计 (ms):")
                print(f"  平均: {statistics.mean(delays):.2f}")
                print(f"  中位数: {statistics.median(delays):.2f}")
                print(f"  最小: {min(delays):.2f}")
                print(f"  最大: {max(delays):.2f}")
                print(f"  标准差: {statistics.stdev(delays):.2f}")

            if offsets:
                print(f"\n时间偏移统计 (ms):")
                print(f"  平均: {statistics.mean(offsets):.2f}")
                print(f"  中位数: {statistics.median(offsets):.2f}")
                print(f"  最小: {min(offsets):.2f}")
                print(f"  最大: {max(offsets):.2f}")
                print(f"  标准差: {statistics.stdev(offsets):.2f}")

        # Stratum分布统计
        cursor.execute('SELECT stratum, COUNT(*) FROM ntp_records WHERE timestamp > ? GROUP BY stratum', (since,))
        stratum_stats = cursor.fetchall()

        if stratum_stats:
            print(f"\nStratum分布:")
            for stratum, count in stratum_stats:
                print(f"  Stratum {stratum}: {count} 次请求")

        # 接口分布统计
        cursor.execute('''
            SELECT interface, COUNT(DISTINCT client_ip) 
            FROM client_stats 
            WHERE last_seen > ? 
            GROUP BY interface
        ''', (since,))
        interface_stats = cursor.fetchall()

        if interface_stats:
            print(f"\n接口分布:")
            for interface, count in interface_stats:
                print(f"  {interface}: {count} 个客户端")

        conn.close()

    def search_anomalies(self, delay_threshold: float = 0.1, offset_threshold: float = 0.05, hours: int = 24):
        """搜索异常情况"""
        conn = self._connect_db()
        cursor = conn.cursor()

        since = datetime.now() - timedelta(hours=hours)

        print(f"\n=== 异常检测 (最近 {hours} 小时) ===")
        print(f"延迟阈值: {delay_threshold * 1000} ms")
        print(f"偏移阈值: {offset_threshold * 1000} ms")

        # 高延迟请求
        cursor.execute('''
            SELECT client_ip, timestamp, network_delay, time_offset, stratum
            FROM ntp_records 
            WHERE timestamp > ? AND network_delay > ?
            ORDER BY network_delay DESC
            LIMIT 20
        ''', (since, delay_threshold))

        high_delay = cursor.fetchall()

        if high_delay:
            print(f"\n高延迟请求 (>{delay_threshold * 1000} ms):")
            print(f"{'客户端IP':<20} {'时间':<20} {'延迟(ms)':<10} {'偏移(ms)':<10} {'Stratum'}")
            print("-" * 80)
            for record in high_delay:
                client_ip, timestamp, delay, offset, stratum = record
                delay_ms = f"{delay * 1000:.2f}" if delay else "N/A"
                offset_ms = f"{offset * 1000:.2f}" if offset else "N/A"
                print(f"{client_ip:<20} {timestamp:<20} {delay_ms:<10} {offset_ms:<10} {stratum}")

        # 高偏移请求
        cursor.execute('''
            SELECT client_ip, timestamp, network_delay, time_offset, stratum
            FROM ntp_records 
            WHERE timestamp > ? AND ABS(time_offset) > ?
            ORDER BY ABS(time_offset) DESC
            LIMIT 20
        ''', (since, offset_threshold))

        high_offset = cursor.fetchall()

        if high_offset:
            print(f"\n高时间偏移请求 (>{offset_threshold * 1000} ms):")
            print(f"{'客户端IP':<20} {'时间':<20} {'延迟(ms)':<10} {'偏移(ms)':<10} {'Stratum'}")
            print("-" * 80)
            for record in high_offset:
                client_ip, timestamp, delay, offset, stratum = record
                delay_ms = f"{delay * 1000:.2f}" if delay else "N/A"
                offset_ms = f"{offset * 1000:.2f}" if offset else "N/A"
                print(f"{client_ip:<20} {timestamp:<20} {delay_ms:<10} {offset_ms:<10} {stratum}")

        conn.close()

    def export_data(self, client_ip: str = None, hours: int = 24, format: str = "json"):
        """导出数据"""
        conn = self._connect_db()
        cursor = conn.cursor()

        since = datetime.now() - timedelta(hours=hours)

        if client_ip:
            cursor.execute('''
                SELECT * FROM ntp_records 
                WHERE client_ip = ? AND timestamp > ?
                ORDER BY timestamp
            ''', (client_ip, since))
            filename = f"ntp_export_{client_ip}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"
        else:
            cursor.execute('''
                SELECT * FROM ntp_records 
                WHERE timestamp > ?
                ORDER BY timestamp
            ''', (since,))
            filename = f"ntp_export_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"

        columns = [description[0] for description in cursor.description]
        results = cursor.fetchall()

        if format == "json":
            data = [dict(zip(columns, row)) for row in results]
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
        elif format == "csv":
            import csv
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(results)

        print(f"数据已导出到: {filename}")
        print(f"导出记录数: {len(results)}")

        conn.close()


def main():
    """主程序"""
    parser = argparse.ArgumentParser(description="NTP监控数据查询工具")
    parser.add_argument("--db", default="ntp_monitor.db", help="数据库文件路径")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 列出客户端
    list_parser = subparsers.add_parser("list", help="列出客户端")
    list_parser.add_argument("--active", action="store_true", help="只显示活跃客户端")
    list_parser.add_argument("--hours", type=int, default=24, help="活跃时间范围(小时)")

    # 客户端详情
    detail_parser = subparsers.add_parser("detail", help="显示客户端详情")
    detail_parser.add_argument("client_ip", help="客户端IP地址")
    detail_parser.add_argument("--hours", type=int, default=24, help="查询时间范围(小时)")

    # 统计信息
    stats_parser = subparsers.add_parser("stats", help="显示统计信息")
    stats_parser.add_argument("--hours", type=int, default=24, help="统计时间范围(小时)")

    # 异常检测
    anomaly_parser = subparsers.add_parser("anomalies", help="检测异常")
    anomaly_parser.add_argument("--delay-threshold", type=float, default=0.1, help="延迟阈值(秒)")
    anomaly_parser.add_argument("--offset-threshold", type=float, default=0.05, help="偏移阈值(秒)")
    anomaly_parser.add_argument("--hours", type=int, default=24, help="检测时间范围(小时)")

    # 导出数据
    export_parser = subparsers.add_parser("export", help="导出数据")
    export_parser.add_argument("--client-ip", help="指定客户端IP")
    export_parser.add_argument("--hours", type=int, default=24, help="导出时间范围(小时)")
    export_parser.add_argument("--format", choices=["json", "csv"], default="json", help="导出格式")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    tool = NTPQueryTool(args.db)

    try:
        if args.command == "list":
            tool.list_clients(args.active, args.hours)
        elif args.command == "detail":
            tool.show_client_detail(args.client_ip, args.hours)
        elif args.command == "stats":
            tool.show_statistics(args.hours)
        elif args.command == "anomalies":
            tool.search_anomalies(args.delay_threshold, args.offset_threshold, args.hours)
        elif args.command == "export":
            tool.export_data(args.client_ip, args.hours, args.format)
    except Exception as e:
        print(f"执行命令时出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()