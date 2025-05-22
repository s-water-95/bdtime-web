import unittest
import json
from unittest.mock import patch, MagicMock
from app import create_app
from models.network_models import NetworkInterface, Route


class TestNetworkRoutes(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    @patch('services.network_service.get_all_interfaces')
    def test_get_interfaces(self, mock_get_all_interfaces):
        # Create mock interface data
        mock_interface = NetworkInterface(
            interface_name="eth0",
            config_file="/etc/systemd/network/eth0.network",
            ipv4_addresses=["192.168.1.100/24"],
            ipv6_addresses=["2001:db8::100/64"],
            ipv4_gateway="192.168.1.1",
            ipv6_gateway="fe80::1",
            dns=["8.8.8.8", "1.1.1.1"],
            status="configured"
        )
        mock_get_all_interfaces.return_value = [mock_interface]

        # Make the request
        response = self.client.get('/api/network/interfaces')

        # Check the response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['interface_name'], 'eth0')
        self.assertEqual(data[0]['ipv4_addresses'], ['192.168.1.100/24'])

    @patch('services.network_service.get_interface')
    def test_get_interface_details(self, mock_get_interface):
        # Create mock interface data
        mock_interface = NetworkInterface(
            interface_name="eth0",
            config_file="/etc/systemd/network/eth0.network",
            ipv4_addresses=["192.168.1.100/24"],
            ipv6_addresses=["2001:db8::100/64"],
            ipv4_gateway="192.168.1.1",
            ipv6_gateway="fe80::1",
            dns=["8.8.8.8", "1.1.1.1"],
            status="configured"
        )
        mock_get_interface.return_value = mock_interface

        # Make the request
        response = self.client.get('/api/network/interfaces/eth0')

        # Check the response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['interface_name'], 'eth0')
        self.assertEqual(data['ipv4_addresses'], ['192.168.1.100/24'])

    @patch('services.network_service.get_interface')
    def test_get_interface_not_found(self, mock_get_interface):
        # Mock interface not found
        mock_get_interface.return_value = None

        # Make the request
        response = self.client.get('/api/network/interfaces/nonexistent')

        # Check the response
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        self.assertIn('error', data)

    @patch('services.network_service.configure_interface')
    def test_configure_interface(self, mock_configure_interface):
        # Create mock interface data
        mock_interface = NetworkInterface(
            interface_name="eth0",
            config_file="/etc/systemd/network/eth0.network",
            ipv4_addresses=["192.168.1.100/24"],
            ipv6_addresses=["2001:db8::100/64"],
            ipv4_gateway="192.168.1.1",
            ipv6_gateway="fe80::1",
            dns=["8.8.8.8", "1.1.1.1"],
            status="configured"
        )
        mock_configure_interface.return_value = (True, mock_interface)

        # Make the request
        config_data = {
            "ipv4_addresses": ["192.168.1.100/24"],
            "ipv4_gateway": "192.168.1.1",
            "dns": ["8.8.8.8", "1.1.1.1"]
        }
        response = self.client.post(
            '/api/network/interfaces/eth0',
            data=json.dumps(config_data),
            content_type='application/json'
        )

        # Check the response
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertEqual(data['interface_name'], 'eth0')
        self.assertEqual(data['ipv4_addresses'], ['192.168.1.100/24'])

    @patch('services.network_service.configure_interface')
    def test_configure_interface_failure(self, mock_configure_interface):
        # Mock configuration failure
        mock_configure_interface.return_value = (False, "Invalid configuration")

        # Make the request
        config_data = {
            "ipv4_addresses": ["invalid-ip"],
            "ipv4_gateway": "192.168.1.1",
            "dns": ["8.8.8.8"]
        }
        response = self.client.post(
            '/api/network/interfaces/eth0',
            data=json.dumps(config_data),
            content_type='application/json'
        )

        # Check the response
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('error', data)

    @patch('services.system_service.reload_networkd')
    def test_reload_network(self, mock_reload_networkd):
        # Mock reload success
        mock_reload_networkd.return_value = (True, None)

        # Make the request
        response = self.client.post('/api/network/reload')

        # Check the response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('message', data)

    @patch('services.system_service.reload_networkd')
    def test_reload_network_failure(self, mock_reload_networkd):
        # Mock reload failure
        mock_reload_networkd.return_value = (False, "Failed to restart service")

        # Make the request
        response = self.client.post('/api/network/reload')

        # Check the response
        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertIn('error', data)


if __name__ == '__main__':
    unittest.main()