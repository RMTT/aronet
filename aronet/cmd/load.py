import argparse
import ipaddress
import json
from logging import Logger

from pyroute2 import IPRoute
from aronet.cmd.base import BaseCommand
from aronet.config import Config
from aronet.strongswan.client import Client
from aronet.util import build_id, derive_public_key, same_address_family
from hashlib import sha256


class LoadCommand(BaseCommand):
    _name = "load"
    _help = "load configuration and registry"

    def __init__(
        self, config: Config, parser: argparse.ArgumentParser, logger: Logger
    ) -> None:
        super().__init__(config, parser, logger)

        parser.add_argument(
            "-c", "--config", help="path of configuration file", type=str, required=True
        )
        parser.add_argument(
            "-r", "--registry", help="path of registry file", type=str, required=True
        )

    def __setup_route(
        self, networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network]
    ):
        with IPRoute() as ipr:
            for net in networks:
                ipr.route(
                    "add",
                    dst=net.with_prefixlen,
                    oif=ipr.link_lookup(ifname="aronet"),
                )

    def __load_conn(self, config: dict, registry: dict):
        vici_client = Client(self.config)
        vici_client.load_key({"type": "any", "data": str(config["private_key"])})

        public_key = derive_public_key(config["private_key"])

        name_set = set()
        connection = {}
        networks = []

        for local in config["endpoints"]:
            local_id = build_id(config["organization"], config["common_name"], local)
            local_name = f"{config['organization']}-{config['common_name']}"

            for organization in registry:
                for node in organization["nodes"]:
                    node_name = f"{organization['organization']}-{node['common_name']}"

                    if node_name == local_name:
                        continue

                    for prefix in node["remarks"]["prefixs"]:
                        networks.append(ipaddress.ip_network(prefix, False))

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
                            "local_addrs": [local["address"]],
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
                                    "updown": self.config.updown_path,
                                    "dpd_action": "restart",
                                    "start_action": "start",
                                }
                            },
                        }
                        name_set.add(connection_name)

        vici_client.load_conn(connection)

        delete_set = set()
        for conn in vici_client.list_conns():
            for key, _ in conn.items():
                if key not in name_set:
                    delete_set.add(key)
                    break

        # delete redundant connections
        for key in delete_set:
            vici_client.unload_conn({"name": key})

        self.__setup_route(networks)

    def run(self, args: argparse.Namespace) -> bool:
        with open(args.config, "r") as f:
            c = json.loads(f.read())

        with open(args.registry, "r") as f:
            r = json.loads(f.read())

        if not str(c["private_key"]).startswith("-----BEGIN PRIVATE KEY-----"):
            with open(c["private_key"], "r") as f:
                c["private_key"] = f.read()

        self.__load_conn(c, r)
        return True
