import argparse
from logging import Logger
import os
import sys
from aronet.cmd.base import BaseCommand
from aronet.config import Config
import subprocess


class BirdcCommand(BaseCommand):
    _name = "birdc"
    _help = "run bird client to inspect your routing"

    def __init__(
        self, config: Config, parser: argparse.ArgumentParser, logger: Logger
    ) -> None:
        super().__init__(config, parser, logger)

    def run(self, args: argparse.Namespace) -> bool:
        subprocess.run(
            [
                self.config.birdc_path,
                "-s",
                os.path.join(self.config.runtime_dir, "bird.ctl"),
            ],
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        return True
