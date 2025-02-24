import argparse
import asyncio
import json
from logging import Logger


from aronet.cmd.base import BaseCommand
from aronet.config import Config
from aronet.daemon.backend import ACTION_LOAD_CONNS
from aronet.util import dump_message


class LoadCommand(BaseCommand):
    _name = "load"
    _help = "load configuration and registry"

    def __init__(
        self, config: Config, parser: argparse.ArgumentParser, logger: Logger
    ) -> None:
        super().__init__(config, parser, logger)

        parser.add_argument(
            "-c", "--config", help="path of configuration file", type=str
        )
        parser.add_argument("-r", "--registry", help="path of registry file", type=str)

        self.__parser = parser

    async def __run(self, config: dict = None, registry: dict = None):
        reader, writer = await asyncio.open_unix_connection(
            self.config.backend_socket_path
        )

        if registry:
            writer.write(
                dump_message({"action": ACTION_LOAD_CONNS, "registry": registry})
            )

        await writer.drain()

        # result = await reader.read()
        # print(result)
        writer.close()
        await writer.wait_closed()

    def run(self, args: argparse.Namespace) -> bool:
        if args.config is None and args.registry is None:
            self.__parser.print_help()
            return True

        c = None
        if args.config:
            with open(args.config, "r") as f:
                self.config.custom_config = json.loads(f.read())
                c = self.config.custom_config

        r = None
        if args.registry:
            with open(args.registry, "r") as f:
                self.config.custom_registry = json.loads(f.read())
                r = self.config.custom_registry

        asyncio.run(self.__run(c, r))

        return True
