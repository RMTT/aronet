import argparse
from logging import Logger
import os
import sys
from aronet.cmd.base import BaseCommand
from aronet.config import Config
import subprocess


class SwanctlCommand(BaseCommand):
    _name = "swanctl"
    _help = "run swanctl client to inspect your connection"

    def __init__(
        self, config: Config, parser: argparse.ArgumentParser, logger: Logger
    ) -> None:
        super().__init__(config, parser, logger)

    def run(self, args: argparse.Namespace) -> bool:
        subprocess.run(
            [self.config.swanctl_path]
            + args.unknown
            + ["-u", self.config.vici_socket_path],
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        return True
