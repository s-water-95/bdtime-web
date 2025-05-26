# NTP客户端监控程序部署指南

## 系统要求

- Python 3.6+
- SQLite3
- root权限（监听NTP端口需要）
- 可选：netifaces库（用于网络接口检测）

## 安装步骤

### 1. 安装依赖
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip sqlite3

# CentOS/RHEL
sudo yum install python3 python3-pip sqlite3

# 安装Python依赖
pip3 install netifaces
```

### 2. 创建工作目录
```bash
sudo mkdir -p /opt/ntp-monitor
sudo chown $(whoami):$(whoami) /opt/ntp-monitor
cd /opt/ntp-monitor
```

### 3. 部署程序文件
将以下文件保存到 `/opt/ntp-monitor/` 目录：
- `ntp_monitor.py` - 主监控程序
- `ntp_query.py` - 查询工具
- `config.json` - 配置文件

### 4. 创建配置文件
```json
{
    "database": {
        "path": "/opt/ntp-monitor/ntp_monitor.db",
        "batch_size": 100,
        "flush_interval": 30
    },
    "monitoring": {
        "ntp_port": 123,
        "log_level": "INFO",
        "log_file": "/opt/ntp-monitor/ntp_monitor.log"
    },
    "performance": {
        "max_cache_size": 10000,
        "cleanup_interval": 3600,
        "retention_days": 30
    }
}
```

## 运行方式

### 方式一：直接运行（测试用）
```bash
cd /opt/ntp-monitor
sudo python3 ntp_monitor.py
```

### 方式二：使用systemd服务（推荐）

#### 创建systemd服务文件
```bash
sudo vim /etc/systemd/system/ntp-monitor.service
```

内容如下：
```ini
[Unit]
Description=NTP Client Monitor
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/ntp-monitor
ExecStart=/usr/bin/python3 /opt/ntp-monitor/ntp_monitor.py
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=ntp-monitor

[Install]
WantedBy=multi-user.target
```

#### 启动服务
```bash
sudo systemctl daemon-reload
sudo systemctl enable ntp-monitor
sudo systemctl start ntp-monitor
sudo systemctl status ntp-monitor
```

### 方式三：使用Docker（可选）

#### Dockerfile
```dockerfile
FROM python:3.9-alpine

RUN apk add --no-cache sqlite gcc musl-dev linux-headers

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ntp_monitor.py .
COPY config.json .

EXPOSE 123/udp

CMD ["python", "ntp_monitor.py"]
```

#### requirements.txt
```
netifaces>=0.11.0
```

#### 构建和运行
```bash
docker build -t ntp-monitor .
docker run -d --name ntp-monitor -p 123:123/udp -v /opt/ntp-monitor/data:/app/data ntp-monitor
```

## 使用查询工具

### 基本查询命令

#### 列出所有客户端
```bash
python3 ntp_query.py list
```

#### 列出活跃客户端（最近24小时）
```bash
python3 ntp_query.py list --active --hours 24
```

#### 查看客户端详情
```bash
python3 ntp_query.py detail 192.168.1.100
```

#### 显示统计信息
```bash
python3 ntp_query.py stats --hours 48
```

#### 异常检测
```bash
python3 ntp_query.py anomalies --delay-threshold 0.1 --offset-threshold 0.05
```

#### 导出数据
```bash
# 导出所有数据为JSON
python3 ntp_query.py export --hours 24 --format json

# 导出特定客户端数据为CSV
python3 ntp_query.py export --client-ip 192.168.1.100 --format csv
```

## 性能优化建议

### 1. 数据库优化
```sql
-- 定期清理旧数据
DELETE FROM ntp_records WHERE timestamp < datetime('now', '-30 days');

-- 重建索引
REINDEX;

-- 分析表统计信息
ANALYZE;
```

### 2. 日志轮转配置
创建 `/etc/logrotate.d/ntp-monitor`：
```
/opt/ntp-monitor/ntp_monitor.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
```

### 3. 系统资源限制
在systemd服务文件中添加：
```ini
[Service]
MemoryLimit=512M
CPUQuota=50%
```

## 监控和维护

### 1. 检查服务状态
```bash
sudo systemctl status ntp-monitor
journalctl -u ntp-monitor -f
```

### 2. 监控数据库大小
```bash
du -h /opt/ntp-monitor/ntp_monitor.db
```

### 3. 监控内存使用
```bash
ps aux | grep ntp_monitor
```

### 4. 数据库维护脚本
```bash
#!/bin/bash
# /opt/ntp-monitor/maintenance.sh

DB_PATH="/opt/ntp-monitor/ntp_monitor.db"
RETENTION_DAYS=30

# 清理旧数据
sqlite3 $DB_PATH "DELETE FROM ntp_records WHERE timestamp < datetime('now', '-${RETENTION_DAYS} days');"

# 优化数据库
sqlite3 $DB_PATH "VACUUM;"
sqlite3 $DB_PATH "REINDEX;"
sqlite3 $DB_PATH "ANALYZE;"

echo "数据库维护完成: $(date)"
```

添加到crontab：
```bash
# 每天凌晨2点执行维护
0 2 * * * /opt/ntp-monitor/maintenance.sh >> /opt/ntp-monitor/maintenance.log 2>&1
```

## 安全考虑

### 1. 文件权限
```bash
sudo chown -R root:root /opt/ntp-monitor
sudo chmod 755 /opt/ntp-monitor
sudo chmod 644 /opt/ntp-monitor/*.py
sudo chmod 600 /opt/ntp-monitor/config.json
```

### 2. 网络安全
- 确保NTP服务器配置正确，防止放大攻击
- 考虑使用防火墙限制NTP访问
- 定期检查异常流量

### 3. 数据库安全
- 定期备份数据库
- 考虑加密敏感数据
- 限制数据库文件访问权限

## 故障排除

### 常见问题

#### 1. 权限被拒绝
```bash
sudo setcap 'cap_net_bind_service=+ep' /usr/bin/python3
```

#### 2. 端口已被占用
检查是否有其他NTP服务运行：
```bash
sudo netstat -ulnp | grep :123
sudo ss -ulnp | grep :123
```

#### 3. 数据库锁定
```bash
sudo fuser /opt/ntp-monitor/ntp_monitor.db
```

#### 4. 内存不足
调整配置文件中的batch_size和flush_interval

### 调试模式
```bash
# 启用详细日志
python3 ntp_monitor.py --debug

# 查看实时日志
tail -f /opt/ntp-monitor/ntp_monitor.log
```

## API接口（可扩展）

程序可以很容易扩展为提供REST API：

```python
# 添加Flask API接口示例
from flask import Flask, jsonify, request

app = Flask(__name__)
monitor = NTPMonitor()

@app.route('/api/clients')
def get_clients():
    active_only = request.args.get('active', 'false').lower() == 'true'
    hours = int(request.args.get('hours', 24))
    # 返回客户端列表
    return jsonify(monitor.get_client_stats())

@app.route('/api/stats')
def get_stats():
    hours = int(request.args.get('hours', 24))
    # 返回统计信息
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

## 总结

这个NTP监控程序具有以下特点：

1. **低开销**：批量写入、内存缓存、异步处理
2. **可扩展**：模块化设计，易于添加新功能
3. **持久化**：SQLite数据库存储所有数据
4. **实时性**：即时监控和统计
5. **易维护**：详细日志、查询工具、自动清理

程序已针对生产环境进行优化，可以稳定运行在高负载的NTP服务器上。