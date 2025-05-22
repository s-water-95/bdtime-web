from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Route:
    destination: str
    gateway: str
    dev: Optional[str] = None


@dataclass
class NetworkInterface:
    interface_name: str
    config_file: Optional[str] = None
    ipv4_addresses: List[str] = field(default_factory=list)
    ipv6_addresses: List[str] = field(default_factory=list)
    ipv4_gateway: Optional[str] = None
    ipv6_gateway: Optional[str] = None
    dns: List[str] = field(default_factory=list)
    systemd_networkd_routes: List[Route] = field(default_factory=list)
    active_system_routes: List[Route] = field(default_factory=list)
    status: str = "unconfigured"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interface_name": self.interface_name,
            "config_file": self.config_file,
            "ipv4_addresses": self.ipv4_addresses,
            "ipv6_addresses": self.ipv6_addresses,
            "ipv4_gateway": self.ipv4_gateway,
            "ipv6_gateway": self.ipv6_gateway,
            "dns": self.dns,
            "systemd_networkd_routes": [
                {"destination": route.destination, "gateway": route.gateway}
                for route in self.systemd_networkd_routes
            ],
            "active_system_routes": [
                {
                    "destination": route.destination,
                    "gateway": route.gateway if route.gateway else None,
                    "dev": route.dev if route.dev else None
                }
                for route in self.active_system_routes
            ],
            "status": self.status
        }


@dataclass
class NetworkConfig:
    interface_name: str
    ipv4_addresses: List[str] = field(default_factory=list)
    ipv6_addresses: List[str] = field(default_factory=list)
    ipv4_gateway: Optional[str] = None
    ipv6_gateway: Optional[str] = None
    dns: List[str] = field(default_factory=list)
    routes: List[Route] = field(default_factory=list)