from abc import abstractmethod
import argparse
from logging import Logger

from aronet.config import Config


class BaseCommand:
    _name = ""
    _help = ""

    def __init__(
        self, config: Config, parser: argparse.ArgumentParser, logger: Logger
    ) -> None:
        self.parser = parser
        self.config = config
        self.logger = logger

    @classmethod
    def name(cls) -> str:
        return cls._name

    @classmethod
    def help(cls) -> str:
        return cls._help

    @abstractmethod
    def run(self, args: argparse.Namespace) -> bool:
        pass
