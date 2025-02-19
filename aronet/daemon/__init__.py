from abc import ABCMeta, abstractmethod
from logging import Logger
import os

from aronet.config import Config


class Daemon(metaclass=ABCMeta):
    def __init__(self, config: Config, logger: Logger) -> None:
        self._config = config
        self._logger = logger
        self._clean = False
        self._pidfile_path = None

        self.process = None

    def __del__(self):
        if not self._clean:
            return

        self._logger.debug(f"will delete file: {self._pidfile_path}")
        if self._pidfile_path and os.path.exists(self._pidfile_path):
            os.remove(self._pidfile_path)

    @abstractmethod
    def exit_callback(self):
        pass
