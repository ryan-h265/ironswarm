import socket


def ip_address() -> str:
    """
    Get the local IP address with the default route.

    Uses a UDP socket connection to a reserved IP to determine the local
    IP address. Falls back to localhost if unable to determine.

    Returns:
        str: The local IP address or "127.0.0.1" if unavailable.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0)
            # 192.88.99.0/24 is a reserved range
            # we are using it to find the local IP address
            # which has the default route out
            s.connect(("192.88.99.254", 420))
            ip_address = s.getsockname()[0]
    except Exception:
        ip_address = "127.0.0.1"

    return ip_address
