import os
from jsonschema import validate

ENV_CHARON_PATH = "CHARON_PATH"
ENV_SWANCTL_PATH = "SWANCTL_PATH"
ENV_BIRD_PATH = "BIRD_PATH"
ENV_BIRDC_PATH = "BIRDC_PATH"
ENV_UPDOWN_PATH = "UPDOWN_PATH"
ENV_RUNTIME_DIR = "RUNTIME_DIR"

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
                }
            },
            "required": ["prefixs"],
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
                                }
                            },
                            "required": ["prefixs"],
                        },
                    },
                    "required": ["common_name", "endpoints"],
                },
            },
        },
        "required": ["public_key", "organization", "nodes"],
    },
}


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
    def runtime_dir(self) -> str:
        return os.getenv(ENV_RUNTIME_DIR, "/var/run/aronet")

    @property
    def vici_socket_path(self) -> str:
        return os.path.join(self.runtime_dir, "charon.vici")

    @property
    def custom_config(self):
        """The custom_config property."""
        return self.__custom_config

    @custom_config.setter
    def custom_config(self, value):
        validate(value, _CONFIG_SCHEMA)
        self.__custom_config = value

    @property
    def custom_registry(self):
        return self.__custom_registry

    @custom_registry.setter
    def custom_registry(self, value):
        validate(value, _REGISTRY_SCHEMA)
        self.__custom_registry = value

    @property
    def route_table(self) -> int:
        return 128

    @property
    def route_networks(self):
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
