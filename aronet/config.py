import ipaddress
import os

from jsonschema import validate

ENV_CHARON_PATH = "CHARON_PATH"
ENV_SWANCTL_PATH = "SWANCTL_PATH"
ENV_BIRD_PATH = "BIRD_PATH"
ENV_BIRDC_PATH = "BIRDC_PATH"
ENV_UPDOWN_PATH = "UPDOWN_PATH"
ENV_RUNTIME_DIR = "RUNTIME_DIR"

ARONET_NETWORK_SUFFIX = 0xFFFF000000000000

NETNS_PEER_ADDR = 0x2
MAIN_INTERFACE_ADDR = 0x1

SRV6_ACTION_END = 0xA
SRV6_ACTION_END_DX4 = 0xB

_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "private_key": {"type": "string"},
        "organization": {"type": "string"},
        "common_name": {"type": "string"},
        "daemon": {
            "type": "object",
            "properties": {
                "prefixs": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "network": {"type": "string"},
                "ifname": {"type": "string"},
                "route_table": {"type": "integer"},
                "use_netns": {"type": "boolean"},
            },
            "required": ["prefixs", "network"],
        },
        "endpoints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "address_family": {"type": "string"},
                    "address": {"type": ["string", "null"]},
                    "port": {"type": "integer"},
                    "serial_number": {"type": "integer"},
                },
                "required": ["address", "port"],
            },
        },
    },
    "required": ["private_key", "organization", "common_name", "endpoints"],
}

_REGISTRY_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "public_key": {"type": "string"},
            "organization": {"type": "string"},
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "common_name": {"type": "string"},
                        "endpoints": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "address_family": {"type": "string"},
                                    "address": {"type": ["string", "null"]},
                                    "port": {"type": "integer"},
                                    "serial_number": {"type": "integer"},
                                },
                                "required": ["address", "port"],
                            },
                        },
                        "remarks": {
                            "type": "object",
                            "properties": {
                                "prefixs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "network": {"type": "string"},
                            },
                            "required": ["prefixs", "network"],
                        },
                    },
                    "required": ["common_name", "endpoints"],
                },
            },
        },
        "required": ["public_key", "organization", "nodes"],
    },
}


NFT_INIT_TEMPLATE = """
table inet aronet {{
    chain postrouting {{
        type nat hook postrouting priority 100;
        ip6 saddr {peeraddr_v6} oif != "{ifname}" masquerade
        ip saddr {peeraddr_v4} oif != "{ifname}" masquerade
    }}
}}
"""

NFT_PORT_FORWARD_TEMPLATE = """
table inet aronet {{
	chain prerouting {{
		type nat hook prerouting priority 0; policy accept;
        {commands}
	}}
}}
"""


class Config:
    _instance = None

    def __init__(self, libexec_path) -> None:
        self.__libexec_path = libexec_path
        self.__custom_config = None
        self.__route_networks = None
        self.__custom_registry = None
        self.__should_exit = False

    def __new__(cls, *args, **kwargs):
        if not Config._instance:
            Config._instance = object.__new__(cls)
        return Config._instance

    @property
    def charon_path(self) -> str:
        return os.getenv(ENV_CHARON_PATH, os.path.join(self.__libexec_path, "charon"))

    @property
    def strongsconf_path(self):
        return os.path.join(self.runtime_dir, "strongswan.conf")

    @property
    def swanctl_path(self) -> str:
        return os.getenv(ENV_SWANCTL_PATH, os.path.join(self.__libexec_path, "swanctl"))

    @property
    def bird_path(self) -> str:
        return os.getenv(ENV_BIRD_PATH, os.path.join(self.__libexec_path, "bird"))

    @property
    def bird_conf_path(self):
        return os.path.join(self.runtime_dir, "bird.conf")

    @property
    def birdc_path(self) -> str:
        return os.getenv(ENV_BIRDC_PATH, os.path.join(self.__libexec_path, "birdcl"))

    @property
    def updown_path(self) -> str:
        return os.getenv(
            ENV_UPDOWN_PATH, os.path.join(self.__libexec_path, "updown.sh")
        )

    @property
    def updown_env_path(self) -> str:
        return os.getenv(ENV_UPDOWN_PATH, os.path.join(self.runtime_dir, "updown_env"))

    @property
    def runtime_dir(self) -> str:
        return os.getenv(ENV_RUNTIME_DIR, "/var/run/aronet")

    @property
    def vici_socket_path(self) -> str:
        return os.path.join(self.runtime_dir, "charon.vici")

    @property
    def custom_config(self):
        """configuration given by user from command line"""
        return self.__custom_config

    @custom_config.setter
    def custom_config(self, value):
        validate(value, _CONFIG_SCHEMA)
        self.__custom_network = ipaddress.ip_network(
            value["daemon"]["network"], strict=False
        )
        if self.__custom_network.version != 6 or self.__custom_network.prefixlen > 64:
            raise Exception(
                "'network' in 'daemon' config must be a ipv6 network with larger than or equal to /64"
            )

        self.__aronet_network = ipaddress.ip_network(
            f"{self.__custom_network.network_address + ARONET_NETWORK_SUFFIX}/80"
        )

        self.__custom_config = value

    @property
    def main_if_addr(self):
        return ipaddress.ip_interface(
            f"{self.__aronet_network.network_address + MAIN_INTERFACE_ADDR}/128"
        )

    @property
    def custom_network(self):
        return self.__custom_network

    @property
    def aronet_network(self):
        return self.__aronet_network.with_prefixlen

    @property
    def custom_registry(self):
        """registry given by user from command line"""
        return self.__custom_registry

    @custom_registry.setter
    def custom_registry(self, value):
        validate(value, _REGISTRY_SCHEMA)
        self.__custom_registry = value

    @property
    def vrf_route_table(self) -> int:
        if (
            self.custom_config
            and "daemon" in self.custom_config
            and "route_table" in self.custom_config["daemon"]
        ):
            return self.custom_config["route_table"]

        return 128

    @property
    def route_networks(self):
        """networks should be routed to current node"""
        return self.__route_networks

    @route_networks.setter
    def route_networks(self, value):
        self.__route_networks = value

    @property
    def should_exit(self):
        return self.__should_exit

    @should_exit.setter
    def should_exit(self, value):
        self.__should_exit = value

    @property
    def ifname(self) -> str:
        if (
            self.custom_config
            and "daemon" in self.custom_config
            and "ifname" in self.custom_config["daemon"]
        ):
            return self.custom_config["ifname"]

        return "aronet"

    @property
    def tunnel_if_prefix(self) -> str:
        return self.ifname

    @property
    def backend_socket_path(self) -> str:
        return os.path.join(self.runtime_dir, "aronet.ctl")

    @property
    def use_netns(self) -> bool:
        return bool(self.custom_config.get("daemon").get("use_netns"))

    @property
    def netns_name(self):
        return "aronet"

    @property
    def netns_peername(self):
        return self.ifname + "-peer"

    @property
    def netns_peeraddr(self):
        return ipaddress.ip_interface(
            f"{self.__aronet_network.network_address + NETNS_PEER_ADDR}/128"
        )

    @property
    def netns_peeraddr_v4(self):
        return ipaddress.ip_interface("192.168.168.168/32")

    @property
    def aronet_srv6_sid_dx4(self):
        return ipaddress.ip_interface(
            f"{self.__aronet_network.network_address + SRV6_ACTION_END_DX4}/128"
        )

    @property
    def aronet_srv6_sid_end(self):
        return ipaddress.ip_interface(
            f"{self.__aronet_network.network_address + SRV6_ACTION_END}/128"
        )

    @property
    def default_route_table(self) -> int:
        return 254
