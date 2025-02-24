import argparse
import asyncio
import ipaddress
import json
import os
import tempfile
from logging import Logger
from stat import S_IXUSR
import subprocess
from typing import Callable

from pyroute2.ndb.source import NetNS

from aronet.cmd.base import BaseCommand
from aronet.config import NFT_INIT_TEMPLATE, UPDOWN_TEMPLATE, Config
from aronet.daemon.backend import BackendDaemon
from aronet.daemon.bird import Bird
from aronet.daemon.strongswan import Strongswan
from aronet.netlink import Netlink


class DaemonCommand(BaseCommand):
    _name = "daemon"
    _help = "run daemon"

    def __init__(
        self, config: Config, parser: argparse.ArgumentParser, logger: Logger
    ) -> None:
        super().__init__(config, parser, logger)

        self.__message_handlers = {}

        self.__strongswan = Strongswan(config, logger)
        self.__add_message_handler(
            self.__strongswan.actions, self.__strongswan.handle_actions
        )

        self.__bird = Bird(config, logger)
        self.__add_message_handler(self.__bird.actions, self.__bird.handle_actions)

        self.__backend = BackendDaemon(config, logger)
        self.__backend.set_message_handlers(self.__message_handlers)

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

    def __add_message_handler(self, actions: int, handler: Callable):
        if actions == 0:
            return

        if actions not in self.__message_handlers:
            self.__message_handlers[actions] = []
        self.__message_handlers[actions].append(handler)

    async def __run_daemon(self):
        await asyncio.gather(
            self.__strongswan.run(),
            self.__bird.run(),
            self.__backend.run(),
            self.__idle(),
        )

    async def __idle(self):
        while not self.config.should_exit:
            await asyncio.sleep(1)

        await self.__strongswan.exit_callback()
        await self.__bird.exit_callback()
        await self.__backend.exit_callback()

        del self.__strongswan
        del self.__bird
        del self.__backend

        if self.config.use_netns:
            self.__ns.close()

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
        """
        Create some resources before running other tools.

        1. basic interfaces, vrf for vrf mode, veth pair for netns mode
        2. write basic routes for vrf mode
        """
        if not os.path.exists(self.config.runtime_dir):
            os.mkdir(self.config.runtime_dir)

        with open(self.__pidfile_path, "w") as f:
            f.write("{}".format(os.getpid()))

        with open(self.config.updown_path, "w") as f:
            f.write(
                UPDOWN_TEMPLATE.format(
                    vrf_statement=""
                    if self.config.use_netns
                    else f'ip link set "$LINK" master {self.config.ifname}',
                    prefix=self.config.tunnel_if_prefix,
                )
            )
        os.chmod(self.config.updown_path, S_IXUSR)

        route_networks = []
        for prefix in self.config.custom_config["daemon"]["prefixs"]:
            net = ipaddress.ip_network(prefix, False)
            route_networks.append(net)
        self.config.route_networks = route_networks

        # TODO: clean up interfaces which existed before
        nl = Netlink()
        target = "localhost"
        old_if = nl.ndb.interfaces.get(self.config.ifname)
        if old_if:
            with old_if:
                old_if.remove()

        if self.config.use_netns:
            self.__ns = NetNS(self.config.netns_name)
            nl.ndb.sources.add(netns=self.config.netns_name)

            # create veth pair for netns
            with nl.ndb.interfaces.create(
                target=target,
                ifname=self.config.ifname,
                peer={
                    "ifname": self.config.ifname,
                    "net_ns_fd": self.config.netns_name,
                },
                kind="veth",
            ) as i:
                i.set(state="up")
                for address in self.config.custom_config["daemon"]["addresses"]:
                    i.add_ip({"address": address, "mask": 32})

            if_id = nl.ndb.interfaces.get(
                {"target": target, "ifname": self.config.ifname}
            )["index"]
            # need use 'scope: link' to let os don't find the nexthop ip
            with nl.ndb.routes.create(
                dst=f"{self.config.netns_peeraddr}/32", target=target
            ) as r:
                r.set(oif=if_id)
                r.set(scope="link")

            target = self.config.netns_name
            with nl.ndb.interfaces.wait(
                target=target, ifname=self.config.ifname
            ) as peer:
                peer.add_ip({"address": self.config.netns_peeraddr, "mask": 32})
                peer.set(state="up")
            if_id = nl.ndb.interfaces.get(
                {"target": target, "ifname": self.config.ifname}
            )["index"]
            # route host ips from netns
            add_v4_gateway = False
            add_v6_gateway = False
            for address in self.config.custom_config["daemon"]["addresses"]:
                ip = ipaddress.ip_address(address)
                with nl.ndb.routes.create(
                    dst=f"{ip}/32", target=target, oif=if_id
                ) as r:
                    r.set(scope="link")
                    r.set(type="unicast")

                if not add_v4_gateway and ip.version == 4:
                    with nl.ndb.routes.create(
                        dst="0.0.0.0/0", target=target, oif=if_id
                    ) as r:
                        r.set(gateway=str(ip))
                    add_v4_gateway = True
                if not add_v6_gateway and ip.version == 6:
                    with nl.ndb.routes.create(
                        dst="::/0", target=target, oif=if_id
                    ) as r:
                        r.set(gateway=str(ip))

                    add_v6_gateway = True

            # create nftable rules to make netns visit internet
            nft_rule_file = tempfile.NamedTemporaryFile()
            nft_rule_file.write(
                NFT_INIT_TEMPLATE.format(
                    ifname=self.config.ifname, peeraddr=self.config.netns_peeraddr
                ).encode()
            )
            nft_rule_file.flush()
            result = subprocess.run(["nft", "-f", nft_rule_file.name])
            nft_rule_file.close()
            if result.returncode != 0:
                raise Exception("creating nftable rules failed")
        else:
            # create vrf device
            with nl.ndb.interfaces.create(
                kind="vrf", ifname=self.config.ifname, target=target
            ) as i:
                i.set(vrf_table=self.config.route_table)
                i.set(state="up")
                for address in self.config.custom_config["daemon"]["addresses"]:
                    i.add_ip({"address": address, "mask": 32})

            with nl.ndb.routes.create(
                table=self.config.route_table,
                dst="0.0.0.0/0",
                priority=4278198272,
                target=target,
            ) as r:
                r.set(type="unreachable")

        self.__clean = True
