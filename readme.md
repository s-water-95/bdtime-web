# Network Configuration API Service

A Flask-based backend API service for managing systemd-networkd network configurations on Ubuntu 22.04.

## Project Structure

```
project_root/
├── app.py                  # Application entry point
├── config.py               # Configuration settings
├── models/                 # Data structures
│   ├── __init__.py
│   └── network_models.py
├── routes/                 # API route definitions
│   ├── __init__.py
│   └── network_routes.py
├── services/               # Business logic
│   ├── __init__.py
│   ├── file_service.py
│   ├── network_service.py
│   └── system_service.py
├── utils/                  # Helper utilities
│   ├── __init__.py
│   ├── command_executor.py
│   ├── config_parser.py
│   └── validators.py
└── tests/                  # Test files
    ├── __init__.py
    └── test_network_routes.py
```

## Features

- Discover network interfaces on Ubuntu 22.04 systems
- Read and parse existing systemd-networkd configuration files
- Generate and write network configuration files based on JSON input
- Support for both IPv4 and IPv6 addressing, gateways, DNS servers, and routes
- Automatic merging of existing system routes with new configurations
- RESTful API interface for managing network configurations

## API Endpoints

- `GET /api/network/interfaces`: Get information about all network interfaces
- `GET /api/network/interfaces/<interface_name>`: Get detailed information about a specific interface
- `POST /api/network/interfaces/<interface_name>`: Configure a specific interface (JSON body required)
- `POST /api/network/reload`: Reload the systemd-networkd service to apply changes

## Requirements

- Python 3.x
- Flask
- Ubuntu 22.04 with systemd-networkd
- Root privileges (for writing configuration files and reloading services)

## Installation

1. Clone this repository
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment: `source venv/bin/activate`
4. Install dependencies: `pip install flask`
5. Run the application: `sudo python app.py`

## Example Requests

### Get all interfaces

```bash
curl -X GET http://localhost:8000/api/network/interfaces
```

### Get a specific interface

```bash
curl -X GET http://localhost:8000/api/network/interfaces/eth0
```

### Configure an interface

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

### Reload network configuration

```bash
curl -X POST http://localhost:8000/api/network/reload
```

## Running Tests

```bash
python -m unittest discover -s tests
```

## Security Considerations

This API service needs to run with elevated privileges to modify network configuration files and restart system services. Consider implementing proper authentication and authorization if deploying in a production environment.