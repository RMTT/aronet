import ipaddress
import json
from typing import Callable
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from aronet.config import Config


def build_id(organization: str, common_name: str, endpoint: dict) -> str:
    id = f"O={organization},CN={common_name}"
    if "serial_number" in endpoint:
        id += f",serialNumber={endpoint['serial_number']}"
    else:
        address = endpoint["address"]
        addr_desc = ""

        if address is None:
            addr_desc = "0.0.0.0"
        elif address_is_v6(address):
            addr_desc = f"[{address}]"
        elif address_is_v4(address):
            addr_desc = endpoint["address"]

        id += f",D={addr_desc}:{endpoint['port']}"
    return id


def address_is_v4(address: str) -> bool:
    ip_object = ipaddress.ip_address(address)
    return isinstance(ip_object, ipaddress.IPv4Address)


def address_is_v6(address: str) -> bool:
    ip_object = ipaddress.ip_address(address)
    return isinstance(ip_object, ipaddress.IPv6Address)


def derive_public_key(private_key_pem: str) -> str:
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"), password=None, backend=default_backend()
    )
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return public_pem.decode("utf-8")


def get_address_family(endpoint: dict):
    if "address_family" in endpoint:
        if endpoint["address_family"] == "ip4":
            return ipaddress.IPv4Address
        elif endpoint["address_family"] == "ip6":
            return ipaddress.IPv6Address
        else:
            raise Exception(f"unknown address family: {endpoint['address']}")

    if address_is_v4(endpoint["address"]):
        return ipaddress.IPv4Address
    elif address_is_v6(endpoint["address"]):
        return ipaddress.IPv6Address
    else:
        raise Exception(f"unknown address family: {endpoint['address']}")


def same_address_family(local: dict, remote: dict) -> bool:
    local_family = get_address_family(local)
    remote_family = get_address_family(remote)

    return local_family == remote_family


async def read_stream(stream, callback: Callable, config: Config):
    while not config.should_exit:
        line = await stream.readline()
        if not line:
            break
        callback(line.decode().strip())


def dump_message(data: dict) -> bytes:
    return (json.dumps(data) + "\n").encode()


def srv6_dx4_from_net(net: ipaddress.ip_network, suffix: int):
    return ipaddress.ip_interface(f"{net.network_address + suffix}/128")
