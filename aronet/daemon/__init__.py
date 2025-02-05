from logging import Logger
import os

from aronet.config import Config


class Daemon:

    def __init__(self, config: Config, logger: Logger) -> None:
        self._config = config
        self._logger = logger
        self._clean = False
        self._conf = None
        self._pidfile_path = None

        self.process = None

    def __del__(self):
        if not self._clean:
            return

        if self._conf:
            self._conf.close()

        if self.process and self.process.returncode is None:
            self._logger.info("exit")
            self.process.terminate()

        if self._pidfile_path and os.path.exists(self._pidfile_path):
            os.remove(self._pidfile_path)
