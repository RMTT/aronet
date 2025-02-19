import argparse
from logging import Logger
import sys
from aronet.cmd.base import BaseCommand
from aronet.config import Config
import subprocess


class SwanctlCommand(BaseCommand):
    _name = "swanctl"
    _help = "run swanctl client to inspect your connections"

    def __init__(
        self, config: Config, parser: argparse.ArgumentParser, logger: Logger
    ) -> None:
        super().__init__(config, parser, logger)

    def run(self, args: argparse.Namespace) -> bool:
        env = {}
        env["STRONGSWAN_CONF"] = self.config.strongsconf_path

        subprocess.run(
            [self.config.swanctl_path] + args.unknown,
            env=env,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        return True
