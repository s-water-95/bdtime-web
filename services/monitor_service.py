import psutil
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)


def get_system_stats() -> Tuple[bool, Dict[str, Any]]:
    """
    获取当前系统的CPU和内存使用情况快照数据。

    Returns:
        Tuple containing:
        - bool: Success status
        - Dict[str, Any]: System statistics data or error message
    """
    try:
        # 获取CPU使用率 (1秒采样间隔，获取全局平均值)
        cpu_percent = psutil.cpu_percent(interval=1)

        # 获取内存信息
        memory = psutil.virtual_memory()

        # 转换字节为GB (1GB = 1024^3 bytes)
        memory_total_gb = round(memory.total / (1024 ** 3), 2)
        memory_used_gb = round(memory.used / (1024 ** 3), 2)
        memory_free_gb = round(memory.available / (1024 ** 3), 2)

        # 内存使用率百分比
        memory_percent = round(memory.percent, 2)

        # 生成时间戳 (UTC ISO格式)
        timestamp = datetime.now(timezone.utc).isoformat()

        # 构建响应数据
        stats = {
            "cpu_percent": round(cpu_percent, 1),
            "memory": {
                "total_gb": memory_total_gb,
                "used_gb": memory_used_gb,
                "free_gb": memory_free_gb,
                "percent": memory_percent
            },
            "timestamp": timestamp
        }

        logger.debug(f"System stats collected: CPU {cpu_percent}%, Memory {memory_percent}%")
        return True, stats

    except Exception as e:
        logger.exception("Failed to collect system statistics")
        return False, f"Failed to collect system statistics: {str(e)}"


def get_detailed_cpu_info() -> Tuple[bool, Dict[str, Any]]:
    """
    获取详细的CPU信息（可选功能，为未来扩展保留）。

    Returns:
        Tuple containing:
        - bool: Success status
        - Dict[str, Any]: Detailed CPU information or error message
    """
    try:
        # CPU核心数
        cpu_count_logical = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)

        # CPU频率信息
        cpu_freq = psutil.cpu_freq()

        # 每个CPU核心的使用率
        cpu_per_core = psutil.cpu_percent(interval=1, percpu=True)

        # 构建详细信息
        cpu_info = {
            "logical_cores": cpu_count_logical,
            "physical_cores": cpu_count_physical,
            "frequency": {
                "current": round(cpu_freq.current, 2) if cpu_freq else None,
                "min": round(cpu_freq.min, 2) if cpu_freq else None,
                "max": round(cpu_freq.max, 2) if cpu_freq else None
            },
            "per_core_usage": [round(usage, 1) for usage in cpu_per_core],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        return True, cpu_info

    except Exception as e:
        logger.exception("Failed to collect detailed CPU information")
        return False, f"Failed to collect CPU information: {str(e)}"


def get_detailed_memory_info() -> Tuple[bool, Dict[str, Any]]:
    """
    获取详细的内存信息（可选功能，为未来扩展保留）。

    Returns:
        Tuple containing:
        - bool: Success status
        - Dict[str, Any]: Detailed memory information or error message
    """
    try:
        # 虚拟内存
        virtual_memory = psutil.virtual_memory()

        # 交换分区
        swap_memory = psutil.swap_memory()

        # 构建详细信息
        memory_info = {
            "virtual": {
                "total_gb": round(virtual_memory.total / (1024 ** 3), 2),
                "available_gb": round(virtual_memory.available / (1024 ** 3), 2),
                "used_gb": round(virtual_memory.used / (1024 ** 3), 2),
                "free_gb": round(virtual_memory.free / (1024 ** 3), 2),
                "percent": round(virtual_memory.percent, 2),
                "buffers_gb": round(getattr(virtual_memory, 'buffers', 0) / (1024 ** 3), 2),
                "cached_gb": round(getattr(virtual_memory, 'cached', 0) / (1024 ** 3), 2)
            },
            "swap": {
                "total_gb": round(swap_memory.total / (1024 ** 3), 2),
                "used_gb": round(swap_memory.used / (1024 ** 3), 2),
                "free_gb": round(swap_memory.free / (1024 ** 3), 2),
                "percent": round(swap_memory.percent, 2)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        return True, memory_info

    except Exception as e:
        logger.exception("Failed to collect detailed memory information")
        return False, f"Failed to collect memory information: {str(e)}"