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

        # cidrs should be routed to this node
        route_networks = [self.config.custom_network]
        for prefix in self.config.custom_config["daemon"]["prefixs"]:
            net = ipaddress.ip_network(prefix, False)
            route_networks.append(net)
        self.config.route_networks = route_networks

        # TODO: clean up interfaces which existed before
        nl = Netlink()
        nl.remove_interface(self.config.ifname)

        if self.config.use_netns:
            netns = self.config.netns_name
            nl.add_netns(netns)

            # create the main interfaces(veth pair in case) for connectivity
            nl.create_interface(
                ifname=self.config.ifname,
                addresses=[self.config.main_if_addr.with_prefixlen],
                kind="veth",
                peer={
                    "ifname": self.config.ifname,
                    "net_ns_fd": self.config.netns_name,
                },
            )
            nl.interface_wait_and_set(
                netns=netns,
                ifname=self.config.ifname,
                addresses=[
                    self.config.netns_peeraddr.with_prefixlen,
                    self.config.netns_peeraddr_v4.with_prefixlen,
                ],
            )

            # create routes in root netns to make aronet netns is accessable
            # use 'scope: link' for v4 to find nexthop
            nl.create_route(
                dst=self.config.netns_peeraddr.with_prefixlen, oif=self.config.ifname
            )
            nl.create_route(
                dst=self.config.netns_peeraddr_v4.with_prefixlen,
                oif=self.config.ifname,
                scope="link",
            )
            for prefix in self.config.custom_config["daemon"]["prefixs"]:
                ip = ipaddress.ip_network(prefix, strict=False)
                if ip.version == 6:
                    nl.create_route(
                        dst=prefix,
                        oif=self.config.ifname,
                        gateway=self.config.netns_peeraddr.ip.exploded,
                    )
                else:
                    pass

            # add routes in aronet netns to make aronet netns can visit outside world
            nl.create_route(
                dst=self.config.main_if_addr.ip.exploded,
                oif=self.config.ifname,
                netns=netns,
            )
            nl.create_route(
                dst="::/0",
                netns=netns,
                gateway=self.config.main_if_addr.ip.exploded,
            )

            # add routes to route ipv4 via srv6
            nl.create_route(
                dst="0.0.0.0/0",
                oif=self.config.ifname,
                netns=netns,
                encap={
                    "type": "seg6",
                    "mode": "encap",
                    "segs": self.config.aronet_srv6_sid_dx4.ip.exploded,
                },
            )

            # create nftable rules to make netns visit internet
            nft_rule_file = tempfile.NamedTemporaryFile()
            nft_rule_file.write(
                NFT_INIT_TEMPLATE.format(
                    ifname=self.config.ifname,
                    peeraddr_v6=self.config.netns_peeraddr.ip.exploded,
                    peeraddr_v4=self.config.netns_peeraddr_v4.ip.exploded,
                ).encode()
            )
            nft_rule_file.flush()
            subprocess.run(["nft", "-f", nft_rule_file.name], check=True)
            nft_rule_file.close()
        else:
            # create main vrf device
            nl.create_interface(
                kind="vrf",
                ifname=self.config.ifname,
                vrf_table=self.config.route_table,
                addresses=[self.config.main_if_addr.with_prefixlen],
            )

        # add srv6 routes in root netns
        nl.create_route(
            dst=self.config.aronet_srv6_sid_dx4.with_prefixlen,
            oif=self.config.ifname,
            encap={"type": "seg6local", "action": "End.DX4", "nh4": "0.0.0.0"},
        )
        nl.create_route(
            dst=self.config.aronet_srv6_sid_end.with_prefixlen,
            oif=self.config.ifname,
            encap={"type": "seg6local", "action": "End"},
        )

        self.__clean = True
