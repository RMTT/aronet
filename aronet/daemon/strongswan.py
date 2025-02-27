import asyncio
from hashlib import sha256
import ipaddress
import os
import socket
import concurrent.futures
from asyncio.exceptions import CancelledError
from logging import Logger
import subprocess
import tempfile
from typing import OrderedDict

from pyroute2 import IPRoute
from pyroute2.netlink.rtnl.ifinfmsg import IFF_MULTICAST, IFF_UP
from pyroute2.netns import popns, pushns

from aronet.config import NFT_PORT_FORWARD_TEMPLATE, SRV6_ACTION_END_DX4, Config
from aronet.daemon import ACTION_LOAD_CONNS, Daemon, InternalMessage
from aronet.netlink import Netlink
from aronet.strongswan.client import Client
from aronet.util import (
    build_id,
    derive_public_key,
    read_stream,
    same_address_family,
    srv6_dx4_from_net,
)


class Strongswan(Daemon):
    CONF_TEMP = """
        charon {{
          port = 0
          port_nat_t = 12025
          retransmit_timeout = 30
          retransmit_base = 1

          filelog {{
              stdout {{
                  # to achive realtime log capture
                  flush_line = yes
              }}
              stderr {{
                  # to achive realtime log capture
                  flush_line = yes
              }}
          }}

          plugins {{
            vici {{
              socket = "unix://{}"
            }}
            socket-default {{
              set_source = yes
              set_sourceif = yes
            }}
            dhcp {{
              load = no
            }}
          }}
        }}
    """

    def __init__(self, config: Config, logger: Logger) -> None:
        super().__init__(config, logger)

        self.actions = ACTION_LOAD_CONNS

        self._pidfile_path = os.path.join(config.runtime_dir, "charon.pid")
        self.__charon_path = config.charon_path
        self.__vici = None
        self.__tasks = None

        self.__event_handlers = {}

        self.__events = []
        for e, _ in self.__event_handlers.items():
            self.__events.append(e)

    def __vici_connect(self):
        self.__vici = Client(self._config)

    def __listen(self, event_types: list[str]):
        """
        listen to event of vici
        although vici support 'ike-updown' event to up and down the interfaces(same to updown script),
        the response speed of 'ike-updown' event is much slower than updown script's, so i prefer
        updown script
        """
        if self.__vici:
            try:
                for _type, msg in self.__vici.listen(event_types):
                    _type = bytes(_type).decode()
                    self.__event_handlers[_type](msg)
            except socket.error as e:
                if not self._config.should_exit:
                    raise e

    async def __async_listen(self, event_types: list[str]):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            await asyncio.get_running_loop().run_in_executor(
                executor, self.__listen, event_types
            )

    def __setup_iface(self, ifname: str, xfrm_id: int, master: int, ipr: IPRoute):
        self._logger.info(f"trying to create xfrm interface {ifname}...")
        ipr.link(
            "add",
            ifname=ifname,
            kind="xfrm",
            xfrm_if_id=xfrm_id,
            master=master,
        )

        iface = ipr.get_links(ifname=ifname)[0]
        old_flags = iface["flags"]
        ipr.link(
            "set",
            ifname=ifname,
            mtu=1400,
            flags=old_flags | IFF_MULTICAST | IFF_UP,
        )

    def __updown(self, msg: OrderedDict):
        """
        response for ike-updown event
        """
        up = False
        data = None
        for k, d in msg.items():
            if k == "up":
                up = True
            else:
                data = d
        if data is None:
            return

        if_id_in = int(bytes(data["if-id-in"]).decode())
        if_id_out = int(bytes(data["if-id-out"]).decode())

        if_name_in = f"{self._config.tunnel_if_prefix}-{if_id_in}"
        if_name_out = f"{self._config.tunnel_if_prefix}-{if_id_out}"

        with IPRoute() as ipr:
            ifs = ipr.link_lookup(ifname=self._config.ifname)

            if not ifs:
                raise Exception(f"{self._config.ifname} interface failed to find")

            if up:
                self.__setup_iface(if_name_in, if_id_in, ifs[0], ipr)

                if if_id_in != if_id_out:
                    self.__setup_iface(if_name_out, if_id_out, ifs[0], ipr)
            else:
                self._logger.info(
                    f"trying to delete xfrm interface {if_name_in}{'and ' + if_name_out if if_id_out != if_id_in else ''}..."
                )

                if ipr.link_lookup(ifname=if_name_in):
                    ipr.link("delete", ifname=if_name_in)
                if if_id_in != if_id_out:
                    if ipr.link_lookup(ifname=if_name_out):
                        ipr.link("delete", ifname=if_name_out)

    def __process_output(self, line: str):
        self._logger.info(f"[charon]: {line}")

    async def handle_actions(self, msg: InternalMessage):
        if self.__vici is None:
            self._logger.info(
                "strongswan receives an action, but vici is not prepared..."
            )
            return

        if msg.action == ACTION_LOAD_CONNS:
            registry = msg.data["registry"]
            self._logger.info("tring to add some connections...")
            self.__load_conn(self._config.custom_config, registry)

    async def exit_callback(self):
        self._logger.info("terminating strongswan...")

        if self.process.returncode is None:
            self.process.terminate()
        if self.process.returncode is None:
            await self.process.wait()

        if self.__tasks and not self.__tasks.done:
            self._logger.info(
                "some tasks in strongswan still running, wait 5 seconds..."
            )
            await asyncio.sleep(5)

            try:
                self.__tasks.cancel()
            except CancelledError:
                pass

    def __del__(self):
        super().__del__()
        self._logger.debug("delete strongswan object in daemon")

    async def run(self):
        with open(self._config.strongsconf_path, "w") as f:
            f.write(Strongswan.CONF_TEMP.format(self._config.vici_socket_path))

        env = {}
        env.update(os.environ)
        env["STRONGSWAN_CONF"] = self._config.strongsconf_path

        self._logger.info("running charon...")

        if self._config.use_netns:
            pushns(self._config.netns_name)
        self.process = await asyncio.create_subprocess_exec(
            self.__charon_path,
            env=env,
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        if self._config.use_netns:
            popns()

        self._logger.debug(f"charon is running, pid {self.process.pid}")

        if self.process.returncode:
            raise Exception(f"charon exited, returncode: {self.process.returncode}")

        # wait vici
        await asyncio.sleep(1)
        while True:
            try:
                self._logger.info("trying to connect vici...")
                self.__vici_connect()
                self._logger.info("vici connected.")
                break
            except Exception as e:
                self._logger.warning(
                    f"connect to vici failed, caused by: {e}, will retry..."
                )
                await asyncio.sleep(1)

        self._clean = True

        self.__tasks = asyncio.gather(
            read_stream(self.process.stdout, self.__process_output, self._config),
            read_stream(self.process.stderr, self.__process_output, self._config),
            # self.__async_listen(self.__events),
        )

        await self.__tasks

    def info(self) -> str:
        pid = None

        if os.path.exists(self.__pidfile_path):
            with open(self.__pidfile_path, "r") as f:
                pid = f.read()

        if pid is not None:
            return f"strongswan is running, pid {pid}"

        return "strongswan is not running"

    def __setup_route(
        self, networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network]
    ):
        nl = Netlink()
        self._logger.info(f"trying to add routes to {self._config.ifname}...")
        for net, prefixs in networks.items():
            for prefix in prefixs:
                extra_args = {}
                self._logger.debug(
                    f"adding route to {prefix.with_prefixlen} from {self._config.ifname}"
                )
                if prefix.version == 4:
                    extra_args["encap"] = {
                        "type": "seg6",
                        "mode": "encap",
                        "segs": srv6_dx4_from_net(net, SRV6_ACTION_END_DX4).ip.exploded,
                    }
                else:
                    extra_args["gateway"] = self._config.netns_peeraddr.ip.exploded

                nl.create_route(
                    dst=prefix.with_prefixlen,
                    oif=self._config.ifname,
                    **extra_args,
                )

    def __setup_nftables(self, local_ports: set):
        # configure port-forwarding if we use netns mode
        if self._config.use_netns:
            nft_temp_v4 = 'ip saddr != {peeraddr} iif != "{ifname}" udp dport {port} dnat {peeraddr}:{port}\n'
            nft_temp_v6 = 'ip6 saddr != {peeraddr} iif != "{ifname}" udp dport {port} dnat {peeraddr}:{port}\n'
            nft_commands = ""
            for port in local_ports:
                nft_commands += nft_temp_v4.format(
                    port=port,
                    peeraddr=self._config.netns_peeraddr_v4.ip.exploded,
                    ifname=self._config.ifname,
                )
                nft_commands += nft_temp_v6.format(
                    port=port,
                    peeraddr=self._config.netns_peeraddr.ip.exploded,
                    ifname=self._config.ifname,
                )
            self._logger.debug(f"will add following nftable rules: {nft_commands}")
            nft_tmpfile = tempfile.NamedTemporaryFile()
            nft_tmpfile.write(
                NFT_PORT_FORWARD_TEMPLATE.format(commands=nft_commands).encode()
            )
            nft_tmpfile.flush()
            subprocess.run(["nft", "-f", nft_tmpfile.name], check=True)
            self._logger.debug("nftables added")
            nft_tmpfile.close()

    def __load_conn(self, _config: dict, registry: dict):
        # config contains private key data, so we shouldn't keep it in memory for long time
        config = _config.copy()
        if not str(config["private_key"]).startswith("-----BEGIN PRIVATE KEY-----"):
            with open(config["private_key"], "r") as f:
                config["private_key"] = f.read()

        self.__vici.load_key({"type": "any", "data": str(config["private_key"])})

        public_key = derive_public_key(config["private_key"])

        name_set = set()
        connection = {}
        local_ports = set()
        networks = {}

        for local in config["endpoints"]:
            local_id = build_id(config["organization"], config["common_name"], local)
            local_name = f"{config['organization']}-{config['common_name']}"

            for organization in registry:
                for node in organization["nodes"]:
                    node_name = f"{organization['organization']}-{node['common_name']}"

                    if node_name == local_name:
                        continue

                    net = ipaddress.ip_network(node["remarks"]["network"], False)
                    networks[net] = [net]
                    for prefix in node["remarks"]["prefixs"]:
                        networks[net].append(ipaddress.ip_network(prefix, False))

                    for remote in node["endpoints"]:
                        if not same_address_family(local, remote):
                            continue

                        remote_id = build_id(
                            organization["organization"],
                            node["common_name"],
                            remote,
                        )

                        connection_name = sha256(
                            f"{local_id}-{remote_id}".encode()
                        ).hexdigest()

                        connection[connection_name] = {
                            "version": 2,
                            "remote_addrs": [remote["address"]],
                            "local_port": local["port"],
                            "remote_port": remote["port"],
                            "encap": True,
                            "mobike": False,
                            "unique": "replace",
                            "if_id_in": "%unique",
                            "if_id_out": "%unique",
                            "local": {
                                "id": local_id,
                                "auth": "pubkey",
                                "pubkeys": [public_key],
                            },
                            "remote": {
                                "id": remote_id,
                                "auth": "pubkey",
                                "pubkeys": [organization["public_key"]],
                            },
                            "children": {
                                "default": {
                                    "local_ts": ["0.0.0.0/0", "::/0"],
                                    "remote_ts": ["0.0.0.0/0", "::/0"],
                                    "mode": "tunnel",
                                    "updown": self._config.updown_path,
                                    "dpd_action": "restart",
                                    "start_action": "start",
                                }
                            },
                        }
                        if not self._config.use_netns:
                            connection[connection_name]["local_addrs"] = [
                                local["address"]
                            ]

                        local_ports.add(local["port"])
                        name_set.add(connection_name)

        self.__vici.load_conn(connection)
        self.__setup_nftables(local_ports)

        delete_set = set()
        for conn in self.__vici.list_conns():
            for key, _ in conn.items():
                if key not in name_set:
                    delete_set.add(key)
                    break

        # delete redundant connections
        for key in delete_set:
            self.__vici.unload_conn({"name": key})

        self.__setup_route(networks)
