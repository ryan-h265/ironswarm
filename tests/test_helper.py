import socket
from unittest.mock import MagicMock, patch

from ironswarm.helper import ip_address


def test_ip_address_success():
    with patch("socket.socket") as mock_socket:
        mock_socket_instance = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_socket_instance
        mock_socket_instance.getsockname.return_value = ("192.168.1.1", 420)

        result = ip_address()
        assert result == "192.168.1.1"


def test_ip_address_exception():
    with patch("socket.socket", side_effect=Exception):
        result = ip_address()
        assert result == "127.0.0.1"


def test_ip_address_timeout():
    with patch("socket.socket") as mock_socket:
        mock_socket_instance = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_socket_instance
        mock_socket_instance.connect.side_effect = socket.timeout

        result = ip_address()
        assert result == "127.0.0.1"
