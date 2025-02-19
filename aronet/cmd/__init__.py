import argparse
import logging
import signal
import sys

from aronet.cmd.birdc import BirdcCommand
from aronet.cmd.daemon import DaemonCommand
from aronet.cmd.load import LoadCommand
from aronet.cmd.swanctl import SwanctlCommand
from aronet.config import Config

COMMANDS = [DaemonCommand, LoadCommand, BirdcCommand, SwanctlCommand]


logger = logging.getLogger("aronet")
logging.basicConfig(encoding="utf-8", level=logging.INFO)


class CommandRunner:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.__parser = argparse.ArgumentParser(
            description="Auto routed overlay network."
        )
        self.__sub_parsers = self.__parser.add_subparsers(
            title="subcommands", dest="subcommand"
        )
        self.__commands = {}

        for command in COMMANDS:
            parser = self.__sub_parsers.add_parser(command.name(), help=command.help())
            self.__commands[command.name()] = command(config, parser, logger)

    def handler_signal_for_exit(self, sign, frame):
        logger.info("trying to exit...")

        self.config.should_exit = True

    def run(self) -> None:
        if len(sys.argv) == 1:
            self.__parser.print_help()

        args, unknown = self.__parser.parse_known_args(sys.argv[1:])
        args.unknown = unknown

        # capture sigint and sigterm to release some resources
        signal.signal(signal.SIGINT, self.handler_signal_for_exit)
        signal.signal(signal.SIGTERM, self.handler_signal_for_exit)

        if args.subcommand is not None:
            self.__commands[args.subcommand].run(args)
