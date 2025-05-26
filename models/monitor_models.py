from dataclasses import dataclass
from typing import Dict, Any
from datetime import datetime


@dataclass
class SystemStats:
    """系统统计信息数据模型"""
    cpu_percent: float
    memory_total: int
    memory_used: int
    memory_free: int
    memory_percent: float
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_percent": self.cpu_percent,
            "memory": {
                "total": self.memory_total,
                "used": self.memory_used,
                "free": self.memory_free,
                "percent": self.memory_percent
            },
            "timestamp": self.timestamp.isoformat()
        }