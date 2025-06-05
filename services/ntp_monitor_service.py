import os
import signal
import subprocess
import time
import logging
import psutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import config

logger = logging.getLogger(__name__)


class NTPMonitorManager:
    """
    NTP监控管理器 - 负责ntp_worker.py进程的启动、停止、重启和状态管理
    """

    def __init__(self, pid_dir: Optional[str] = None):
        """
        初始化NTP监控管理器

        Args:
            pid_dir: PID文件和日志文件存储目录，默认使用配置中的NTP_PID_DIR
        """
        self.pid_dir = Path(pid_dir or config.NTP_PID_DIR)
        self.pid_dir.mkdir(parents=True, exist_ok=True)

        # 启动时清理无效的PID文件
        self.cleanup_stale_pids()

    def get_pid_file(self, interface: str) -> Path:
        """获取网卡对应的PID文件路径"""
        return self.pid_dir / f"ntp_{interface}.pid"

    def get_log_file(self, interface: str) -> Path:
        """获取网卡对应的日志文件路径"""
        return self.pid_dir / f"ntp_{interface}.log"

    def is_monitoring(self, interface: str) -> bool:
        """
        检查指定网卡是否正在监控

        Args:
            interface: 网卡名称

        Returns:
            bool: True表示正在监控，False表示未监控
        """
        pid_file = self.get_pid_file(interface)
        if not pid_file.exists():
            return False

        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            return psutil.pid_exists(pid)
        except (ValueError, IOError) as e:
            logger.warning(f"读取PID文件失败 {pid_file}: {e}")
            return False

    def get_monitoring_pid(self, interface: str) -> Optional[int]:
        """
        获取监控进程的PID

        Args:
            interface: 网卡名称

        Returns:
            Optional[int]: 进程PID，如果进程不存在返回None
        """
        pid_file = self.get_pid_file(interface)
        if not pid_file.exists():
            return None

        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                return pid
        except (ValueError, IOError) as e:
            logger.warning(f"读取PID文件失败 {pid_file}: {e}")
        return None

    def check_interface_exists(self, interface: str) -> bool:
        """
        检查网卡是否存在

        Args:
            interface: 网卡名称

        Returns:
            bool: True表示网卡存在，False表示不存在
        """
        try:
            result = subprocess.run(['ip', 'link', 'show', interface],
                                    capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.error(f"检查网卡 {interface} 超时")
            return False
        except Exception as e:
            logger.error(f"检查网卡 {interface} 失败: {e}")
            return False

    def start_monitoring(self, interface: str, port: int = 123, timeout: float = 2.0,
                         output_file: Optional[str] = None) -> Tuple[bool, str]:
        """
        启动指定网卡的监控

        Args:
            interface: 网卡名称
            port: NTP端口，默认123
            timeout: 配对超时时间，默认2.0秒
            output_file: 输出文件路径（仅用于摘要，不包含会话数据）

        Returns:
            Tuple[bool, str]: (成功状态, 消息)
        """
        # 检查是否已在监控
        if self.is_monitoring(interface):
            return False, f"网卡 {interface} 已在监控中"

        # 检查网卡是否存在
        if not self.check_interface_exists(interface):
            return False, f"网卡 {interface} 不存在"

        logger.info(f"启动网卡 {interface} 的NTP监控...")

        # 修改：构建监控进程命令，使用数据接收服务参数替代输出文件
        cmd = [
            'python3', config.NTP_WORKER_SCRIPT_PATH,
            '--interface', interface,
            '--port', str(port),
            '--timeout', str(timeout),
            '--daemon',  # 后台运行标志
            '--ingestion-host', config.NTP_INGESTION_HOST,  # 新增：数据接收服务主机
            '--ingestion-port', str(config.NTP_INGESTION_PORT)  # 新增：数据接收服务端口
        ]

        # 如果需要摘要输出文件，仍然传递（仅用于调试和统计）
        if output_file:
            cmd.extend(['--output', output_file])

        try:
            # 启动监控进程，重定向输出到日志文件
            log_file = self.get_log_file(interface)

            with open(log_file, 'w') as log:
                process = subprocess.Popen(
                    cmd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,  # 创建新的进程组
                    cwd=os.path.dirname(config.NTP_WORKER_SCRIPT_PATH)
                )

            # 保存PID
            pid_file = self.get_pid_file(interface)
            with open(pid_file, 'w') as f:
                f.write(str(process.pid))

            # 等待一下确保进程正常启动
            time.sleep(1)

            if self.is_monitoring(interface):
                logger.info(f"网卡 {interface} 监控已启动 (PID: {process.pid})")
                return True, (f"网卡 {interface} 监控已启动，PID: {process.pid}，"
                              f"数据发送到: {config.NTP_INGESTION_HOST}:{config.NTP_INGESTION_PORT}，"
                              f"日志文件: {log_file}")
            else:
                # 检查是否启动失败
                if log_file.exists():
                    try:
                        with open(log_file, 'r') as f:
                            error_log = f.read()
                        logger.error(f"启动失败，日志内容: {error_log}")
                        return False, f"网卡 {interface} 监控启动失败，请检查日志: {log_file}"
                    except:
                        pass
                return False, f"网卡 {interface} 监控启动失败"

        except FileNotFoundError:
            return False, f"未找到ntp_worker.py脚本或python3命令"
        except PermissionError:
            return False, f"权限不足，可能需要tcpdump权限"
        except Exception as e:
            logger.exception(f"启动监控失败")
            return False, f"启动监控失败: {str(e)}"

    def stop_monitoring(self, interface: str) -> Tuple[bool, str]:
        """
        停止指定网卡的监控

        Args:
            interface: 网卡名称

        Returns:
            Tuple[bool, str]: (成功状态, 消息)
        """
        pid = self.get_monitoring_pid(interface)
        if not pid:
            return False, f"网卡 {interface} 未在监控中"

        try:
            logger.info(f"停止网卡 {interface} 的NTP监控...")

            # 发送SIGTERM信号优雅停止
            os.kill(pid, signal.SIGTERM)

            # 等待进程结束
            for _ in range(50):  # 最多等待5秒
                if not psutil.pid_exists(pid):
                    break
                time.sleep(0.1)

            # 如果进程还在运行，强制杀死
            if psutil.pid_exists(pid):
                logger.warning(f"进程 {pid} 未响应SIGTERM，发送SIGKILL")
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.5)

            # 清理PID文件
            pid_file = self.get_pid_file(interface)
            if pid_file.exists():
                pid_file.unlink()

            logger.info(f"网卡 {interface} 监控已停止")
            return True, f"网卡 {interface} 监控已停止"

        except ProcessLookupError:
            # 进程已不存在，清理PID文件
            pid_file = self.get_pid_file(interface)
            if pid_file.exists():
                pid_file.unlink()
            return True, f"网卡 {interface} 监控进程已停止"
        except PermissionError:
            return False, f"权限不足，无法停止进程 {pid}"
        except Exception as e:
            logger.exception(f"停止监控失败")
            return False, f"停止监控失败: {str(e)}"

    def restart_monitoring(self, interface: str, port: int = 123, timeout: float = 2.0,
                           output_file: Optional[str] = None) -> Tuple[bool, str]:
        """
        重启指定网卡的监控

        Args:
            interface: 网卡名称
            port: NTP端口，默认123
            timeout: 配对超时时间，默认2.0秒
            output_file: 输出文件路径（仅用于摘要，不包含会话数据）

        Returns:
            Tuple[bool, str]: (成功状态, 消息)
        """
        logger.info(f"重启网卡 {interface} 的NTP监控...")

        # 先停止
        if self.is_monitoring(interface):
            stop_success, stop_msg = self.stop_monitoring(interface)
            if not stop_success:
                return False, f"停止失败: {stop_msg}"
            time.sleep(1)

        # 再启动
        return self.start_monitoring(interface, port, timeout, output_file)

    def get_monitor_status(self, interface: str) -> Dict[str, Any]:
        """
        获取指定网卡的监控状态

        Args:
            interface: 网卡名称

        Returns:
            Dict[str, Any]: 监控状态信息
        """
        status = {
            'interface': interface,
            'is_monitoring': False,
            'pid': None,
            'cpu_percent': None,
            'memory_mb': None,
            'start_time': None,
            'log_file': str(self.get_log_file(interface)),
            'pid_file': str(self.get_pid_file(interface)),
            'interface_exists': self.check_interface_exists(interface),
            'ingestion_target': f"{config.NTP_INGESTION_HOST}:{config.NTP_INGESTION_PORT}"  # 新增：显示数据发送目标
        }

        pid = self.get_monitoring_pid(interface)
        if pid:
            try:
                proc = psutil.Process(pid)
                status.update({
                    'is_monitoring': True,
                    'pid': pid,
                    'cpu_percent': round(proc.cpu_percent(), 2),
                    'memory_mb': round(proc.memory_info().rss / 1024 / 1024, 2),
                    'start_time': datetime.fromtimestamp(proc.create_time()).isoformat(),
                    'status': 'running',
                    'cmdline': ' '.join(proc.cmdline()) if proc.cmdline() else ''
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                status.update({
                    'status': 'process_not_found',
                    'error': str(e)
                })
                # 清理无效的PID文件
                pid_file = self.get_pid_file(interface)
                if pid_file.exists():
                    pid_file.unlink()
        else:
            status['status'] = 'not_monitoring'

        return status

    def list_all_monitoring_status(self) -> List[Dict[str, Any]]:
        """
        列出所有网卡的监控状态

        Returns:
            List[Dict[str, Any]]: 所有网卡的监控状态列表
        """
        status_list = []

        # 获取所有PID文件对应的网卡
        pid_files = list(self.pid_dir.glob("ntp_*.pid"))
        monitored_interfaces = set()

        for pid_file in pid_files:
            interface = pid_file.stem.replace("ntp_", "")
            monitored_interfaces.add(interface)
            status_list.append(self.get_monitor_status(interface))

        return status_list

    def cleanup_stale_pids(self) -> int:
        """
        清理无效的PID文件

        Returns:
            int: 清理的PID文件数量
        """
        cleaned_count = 0
        pid_files = list(self.pid_dir.glob("ntp_*.pid"))

        for pid_file in pid_files:
            interface = pid_file.stem.replace("ntp_", "")
            if not self.is_monitoring(interface):
                try:
                    pid_file.unlink()
                    cleaned_count += 1
                    logger.info(f"清理无效PID文件: {pid_file}")
                except Exception as e:
                    logger.warning(f"清理PID文件失败 {pid_file}: {e}")

        if cleaned_count > 0:
            logger.info(f"清理了 {cleaned_count} 个无效的PID文件")

        return cleaned_count


# 创建全局管理器实例
ntp_manager = NTPMonitorManager()


def get_ntp_manager() -> NTPMonitorManager:
    """获取NTP监控管理器实例"""
    return ntp_manager


# 便捷函数，用于在routes中调用
def start_monitoring(interface: str, port: int = 123, timeout: float = 2.0,
                     output_file: Optional[str] = None) -> Tuple[bool, str]:
    """启动指定网卡的监控"""
    return ntp_manager.start_monitoring(interface, port, timeout, output_file)


def stop_monitoring(interface: str) -> Tuple[bool, str]:
    """停止指定网卡的监控"""
    return ntp_manager.stop_monitoring(interface)


def restart_monitoring(interface: str, port: int = 123, timeout: float = 2.0,
                       output_file: Optional[str] = None) -> Tuple[bool, str]:
    """重启指定网卡的监控"""
    return ntp_manager.restart_monitoring(interface, port, timeout, output_file)


def get_monitor_status(interface: str) -> Dict[str, Any]:
    """获取指定网卡的监控状态"""
    return ntp_manager.get_monitor_status(interface)


def list_all_monitoring_status() -> List[Dict[str, Any]]:
    """列出所有网卡的监控状态"""
    return ntp_manager.list_all_monitoring_status()


def cleanup_stale_pids() -> int:
    """清理无效的PID文件"""
    return ntp_manager.cleanup_stale_pids()