from aronet.config import Config
import socket
import vici


class Client:
    def __init__(self, config: Config):
        self.__socket = socket.socket(socket.AF_UNIX)
        self.__socket.connect(config.vici_socket_path)

        self.__vici = vici.Session(self.__socket)

    def __del__(self):
        if self.__socket:
            self.__socket.close()

    def __getattr__(self, name):
        return getattr(self.__vici, name)
