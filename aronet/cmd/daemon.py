import argparse
import asyncio
import ipaddress
import json
import os
from logging import Logger
from socket import AF_INET, AF_INET6

from pyroute2 import IPRoute

from aronet.cmd.base import BaseCommand
from aronet.config import Config
from aronet.daemon.bird import Bird
from aronet.daemon.strongswan import Strongswan
from aronet.util import netlink_ignore_exists


class DaemonCommand(BaseCommand):
    _name = "daemon"
    _help = "run daemon"

    def __init__(
        self, config: Config, parser: argparse.ArgumentParser, logger: Logger
    ) -> None:
        super().__init__(config, parser, logger)
        self.__strongswan = Strongswan(config, logger)
        self.__bird = Bird(config, logger)
        self.__pidfile_path = os.path.join(self.config.runtime_dir, "aronet.pid")

        # only clean up files when encounter 'run' action
        self.__clean = False

        parser.add_argument(
            "-c", "--config", help="path of configuration file", type=str
        )
        parser.add_argument("action", help="daemon actions", choices=["run", "info"])

    def __del__(self) -> None:
        if not self.__clean:
            return

        if os.path.exists(self.__pidfile_path):
            os.remove(self.__pidfile_path)

    async def __run_daemon(self):
        await asyncio.gather(self.__strongswan.run(), self.__bird.run(), self.__idle())

    async def __idle(self):
        while not self.config.should_exit:
            await asyncio.sleep(2)

        self.logger.info("will terminate strongswan and bird...")
        await self.__strongswan.exit_callback()
        await self.__bird.exit_callback()

        del self.__strongswan
        del self.__bird

    def run(self, args: argparse.Namespace) -> bool:
        match args.action:
            case "run":
                if args.config is None:
                    self.logger.error("'run' action needs config\n")
                    self.parser.print_help()
                    return False
                with open(args.config, "r") as f:
                    self.config.custom_config = json.loads(f.read())

                self.__init_run()

                loop = asyncio.get_event_loop()
                loop.run_until_complete(self.__run_daemon())
                if not loop.is_closed:
                    loop.close()
            case "info":
                if os.path.exists(self.__pidfile_path):
                    with open(self.__pidfile_path, "r") as f:
                        pid = f.read()
                        self.logger.info("aronet is running, pid {}".format(pid))
                else:
                    self.logger.info("aronet is not running")

                self.logger.info(self.__strongswan.info())
                self.logger.info(self.__bird.info())

        return True

    def __init_run(self) -> None:
        if not os.path.exists(self.config.runtime_dir):
            os.mkdir(self.config.runtime_dir)

        with open(self.__pidfile_path, "w") as f:
            f.write("{}".format(os.getpid()))

        # # create route table
        with IPRoute() as ipr:
            netlink_ignore_exists(
                lambda: ipr.route(
                    "add",
                    table=self.config.route_table,
                    dst="0.0.0.0/0",
                    priority=4278198272,
                    type="unreachable",
                )
            )

        # create vrf device
        with IPRoute() as ipr:
            netlink_ignore_exists(
                lambda: ipr.link(
                    "add",
                    ifname="aronet",
                    kind="vrf",
                    vrf_table=self.config.route_table,
                )
            )

            ifs = ipr.link_lookup(ifname="aronet")

            if not ifs:
                raise Exception("aronet interface failed to create")

            ipr.flush_addr(index=ifs[0], family=AF_INET)
            ipr.flush_addr(index=ifs[0], family=AF_INET6)

            if self.config.custom_config is None:
                raise Exception("seems there is no configuration file")

            route_networks = []
            for prefix in self.config.custom_config["daemon"]["prefixs"]:
                net = ipaddress.ip_network(prefix, False)

                ip = ipaddress.ip_address(str(prefix).split("/")[0])
                if ip not in net:
                    raise Exception(f"{ip} not in {net.with_prefixlen}")

                ipr.addr(
                    "add",
                    address=str(ip),
                    mask=net.prefixlen,
                    index=ifs[0],
                )
                route_networks.append(net)

            ipr.link("set", ifname="aronet", state="up")
            self.config.route_networks = route_networks

        self.__clean = True
