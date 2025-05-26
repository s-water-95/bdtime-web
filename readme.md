# 网络配置 API 服务

一个基于 Flask 的后端 API 服务，用于在 Ubuntu 22.04 上管理 systemd-networkd 网络配置。

## 项目结构

```
project_root/
├── app.py                  # 应用程序入口
├── config.py               # 配置设置
├── models/                 # 数据结构
│   ├── __init__.py
│   └── network_models.py
├── routes/                 # API 路由定义
│   ├── __init__.py
│   └── network_routes.py
├── services/               # 业务逻辑
│   ├── __init__.py
│   ├── file_service.py
│   ├── network_service.py
│   └── system_service.py
├── utils/                  # 辅助工具
    ├── __init__.py
    ├── command_executor.py
    ├── config_parser.py
    └── validators.py
```

## 功能

- 发现 Ubuntu 22.04 系统上的网络接口
- 读取和解析现有的 systemd-networkd 配置文件
- 根据 JSON 输入生成和写入网络配置文件
- 支持 IPv4 和 IPv6 地址、网关、DNS 服务器和路由
- 自动将现有系统路由与新配置合并
- 用于管理网络配置的 RESTful API 接口

## API 端点

- `GET /api/network/interfaces`：获取所有网络接口的信息
- `GET /api/network/interfaces/<interface>`：获取特定接口的详细信息
- `POST /api/network/interfaces/<interface>`：配置特定接口（需要 JSON 请求体）
- `POST /api/network/reload`：重新加载 systemd-networkd 服务以应用更改

## 要求

- Python 3.x
- Flask
- Ubuntu 22.04 配备 systemd-networkd
- 根权限（用于写入配置文件和重新加载服务）

## 安装

1. 克隆此仓库
2. 创建虚拟环境：`python -m venv venv`
3. 激活虚拟环境：`source venv/bin/activate`
4. 安装依赖项：`pip install flask`
5. 运行应用程序：`sudo python app.py`

## 示例请求

### 获取所有接口

```bash
curl -X GET http://localhost:8000/api/network/interfaces
```

### 获取特定接口

```bash
curl -X GET http://localhost:8000/api/network/interfaces/eth0
```

### 配置接口

```bash
curl -X POST \
  http://localhost:8000/api/network/interfaces/eth0 \
  -H 'Content-Type: application/json' \
  -d '{
    "ipv4_addresses": ["192.168.1.100/24"],
    "ipv4_gateway": "192.168.1.1",
    "ipv6_addresses": ["2001:db8::100/64"],
    "ipv6_gateway": "fe80::1",
    "dns": ["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888"],
    "routes": [
      {
        "destination": "10.0.0.0/8",
        "gateway": "192.168.1.254"
      },
      {
        "destination": "2001:db8:1::/64",
        "gateway": "2001:db8::1"
      }
    ]
  }'
```

### 重新加载网络配置

```bash
curl -X POST http://localhost:8000/api/network/reload
```

## 运行测试

```bash
python -m unittest discover -s tests
```

## 安全注意事项

此 API 服务需要以提升的权限运行，以修改网络配置文件和重启系统服务。如果在生产环境中部署，请考虑实现适当的认证和授权机制。