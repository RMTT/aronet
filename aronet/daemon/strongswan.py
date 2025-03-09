import asyncio
import concurrent.futures
import ipaddress
import os
import socket
from asyncio.exceptions import CancelledError
from hashlib import sha256
from logging import Logger
from typing import OrderedDict

from pyroute2.netlink import AF_INET6

from aronet.config import Config, CustomConfig
from aronet.daemon import ACTION_LOAD_CONNS, Daemon, InternalMessage
from aronet.netlink import Netlink
from aronet.strongswan.client import Client
from aronet.util import (
    build_id,
    derive_public_key,
    read_stream,
    same_address_family,
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
        self.__vici_listening = None
        self.__tasks = None

        self.__event_handlers = {"ike-updown": self.__updown}

        self.__events = []
        for e, _ in self.__event_handlers.items():
            self.__events.append(e)

    def __vici_connect(self):
        self.__vici = Client(self._config)
        self.__vici_listening = Client(self._config)

    def __listen(self, event_types: list[str]):
        """Listen to event of vici

        Running in the other thread, this function may has race conditions
        """
        if self.__vici_listening:
            try:
                for _type, msg in self.__vici_listening.listen(event_types):
                    _type = bytes(_type).decode()
                    self._logger.debug(
                        f"received event from vici, type: {_type}, data: {msg}"
                    )
                    self.__event_handlers[_type](msg)
            except socket.error as e:
                if not self._config.should_exit:
                    raise e

    async def __async_listen(self, event_types: list[str]):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            await asyncio.get_running_loop().run_in_executor(
                executor, self.__listen, event_types
            )

    def __updown(self, msg: OrderedDict):
        """
        response for ike-updown event

        for creating and up the xfrm interfaces, there is a bash script to do it.
        """
        pass

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
            self._config.custom_registry = registry
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
        env["SWANCTL_DIR"] = self._config.swanctl_dir

        self._logger.info("running charon...")

        self.process = await asyncio.create_subprocess_exec(
            self.__charon_path,
            env=env,
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )

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

        if self._config.custom_registry:
            self.__load_conn(self._config.custom_config, self._config.custom_registry)

        self.__tasks = asyncio.gather(
            read_stream(self.process.stdout, self.__process_output, self._config),
            read_stream(self.process.stderr, self.__process_output, self._config),
            self.__async_listen(self.__events),
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
        self,
        networks: dict[
            ipaddress.IPv6Network : list[ipaddress.IPv4Network | ipaddress.IPv6Network]
        ],
    ):
        nl = Netlink()
        self._logger.info(f"trying to add routes to {self._config.ifname}...")
        for net, prefixs in networks.items():
            for prefix in prefixs:
                extra_args = {}
                self._logger.debug(
                    f"adding route to {prefix.with_prefixlen} from {self._config.ifname}"
                )

                if self._config.use_netns:
                    if prefix.version == 6:
                        extra_args["gateway"] = self._config.netns_peeraddr.ip.exploded
                    else:
                        # FIXME: use **extra_args will fail to add this route, why?
                        nl.create_route(
                            dst=prefix.with_prefixlen,
                            oif=self._config.ifname,
                            via={
                                "family": AF_INET6,
                                "addr": self._config.netns_peeraddr.ip.exploded,
                            },
                        )
                        continue

                nl.create_route(
                    dst=prefix.with_prefixlen,
                    oif=self._config.ifname,
                    **extra_args,
                )

    def __load_conn(self, _config: CustomConfig, registry: dict):
        # config may contains private key data, so we shouldn't keep it in memory for long time
        config = _config.copy()
        if not str(config["private_key"]).startswith("-----BEGIN PRIVATE KEY-----"):
            with open(config["private_key"], "r") as f:
                config["private_key"] = f.read()

        self.__vici.load_key({"type": "any", "data": str(config["private_key"])})

        public_key = derive_public_key(config["private_key"])

        name_set = set()
        connection = {}
        networks = {}

        for local in config["endpoints"]:
            local_id = build_id(config["organization"], config["common_name"], local)
            local_name = f"{config['organization']}-{config['common_name']}"
            local_ip = local["address"]

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
                        remote_ip = remote["address"]

                        if remote_ip is None and local_id is None:
                            continue

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
                            "local_addrs": [local["address"] if local_ip else "%any"],
                            "remote_addrs": [
                                remote["address"] if remote_ip else "%any"
                            ],
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
                                    "start_action": "start|trap",
                                    "close_action": "start|trap",
                                }
                            },
                        }
                        name_set.add(connection_name)

        self.__vici.load_conn(connection)

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
