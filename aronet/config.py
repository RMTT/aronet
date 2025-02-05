import os

ENV_CHARON_PATH = "CHARON_PATH"
ENV_SWANCTL_PATH = "SWANCTL_PATH"
ENV_BIRD_PATH = "BIRD_PATH"
ENV_BIRDC_PATH = "BIRDC_PATH"
ENV_UPDOWN_PATH = "UPDOWN_PATH"
ENV_RUNTIME_DIR = "RUNTIME_DIR"


class Config:

    def __init__(self, libexec_path) -> None:
        self.__libexec_path = libexec_path
        self.__custom_config = None
        self.__route_networks = None

    @property
    def charon_path(self) -> str:
        return os.getenv(ENV_CHARON_PATH, os.path.join(self.__libexec_path, "charon"))

    @property
    def swanctl_path(self) -> str:
        return os.getenv(ENV_SWANCTL_PATH, os.path.join(self.__libexec_path, "swanctl"))

    @property
    def bird_path(self) -> str:
        return os.getenv(ENV_BIRD_PATH, os.path.join(self.__libexec_path, "bird"))

    @property
    def birdc_path(self) -> str:
        return os.getenv(ENV_BIRDC_PATH, os.path.join(self.__libexec_path, "birdcl"))

    @property
    def updown_path(self) -> str:
        return os.getenv(ENV_UPDOWN_PATH, os.path.join(self.__libexec_path, "_updown"))

    @property
    def runtime_dir(self) -> str:
        return os.getenv(ENV_RUNTIME_DIR, "/var/run/aronet")

    @property
    def vici_socket_path(self) -> str:
        return "/var/run/aronet.vici"

    @property
    def custom_config(self):
        """The custom_config property."""
        return self.__custom_config

    @custom_config.setter
    def custom_config(self, value):
        self.__custom_config = value

    @property
    def route_table(self) -> int:
        return 128

    @property
    def route_networks(self):
        return self.__route_networks

    @route_networks.setter
    def route_networks(self, value):
        self.__route_networks = value
