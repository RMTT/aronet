from typing import Callable
from pyroute2 import IPRoute, NetNS, NetlinkError


# Why not use ndb?
# ndb cannot set srv6 route
# ndb will raise meaningless errors


def netlink_ignore_exists(callback: Callable, *args, **kwargs):
    try:
        callback(*args, **kwargs)
    except NetlinkError as e:
        # ignore if netlink exists
        if e.code != 17:
            raise e


def netlink_ignore_not_exists(callback: Callable, *args, **kwargs):
    try:
        callback(*args, **kwargs)
    except NetlinkError as e:
        if e.code not in (3, 19):
            raise e


class Netlink:
    _instance = None

    def __init__(self) -> None:
        self._netns_dict = {}
        self._netns_dict["localhost"] = IPRoute()

    def __new__(cls, *args, **kwargs):
        if not Netlink._instance:
            Netlink._instance = object.__new__(cls)
        return Netlink._instance

    def __del__(self):
        for _, ns in self._netns_dict.items():
            ns.close()

    def add_netns(self, ns: str):
        if ns not in self._netns_dict:
            ns_obj = NetNS(ns)
            self._netns_dict[ns] = ns_obj

    def clear_netns(self):
        for name, ns in self._netns_dict.items():
            if name != "localhost":
                ns.remove()

    def create_interface(
        self, ifname: str, netns: str = "localhost", addresses: list[str] = [], **kwargs
    ):
        if "state" not in kwargs:
            kwargs["state"] = "up"
        ns = self._netns_dict[netns]
        r = ns.link("add", ifname=ifname, **kwargs)
        idx = self.get_interface_index(netns=netns, ifname=ifname)

        for addr in addresses:
            ip = addr.split("/")[0]
            len = str(addr.split("/")[1])
            ns.addr("add", index=idx, address=ip, prefixlen=len)

        return r

    def interface_wait_and_set(
        self, ifname: str, netns: str = "localhost", addresses: list[str] = [], **kwargs
    ):
        ns = self._netns_dict[netns]
        i = ns.poll(ns.link, "dump", ifname=ifname)[0]
        idx = i["index"]
        for addr in addresses:
            ip = addr.split("/")[0]
            len = str(addr.split("/")[1])
            ns.addr("add", index=idx, address=ip, prefixlen=len)

        if "state" not in kwargs:
            kwargs["state"] = "up"
        return ns.link("set", ifname=ifname, **kwargs)

    def create_route(self, dst: str, netns: str = "localhost", **kwargs):
        if "oif" in kwargs:
            kwargs["oif"] = self.get_interface_index(kwargs["oif"], netns=netns)

        ns = self._netns_dict[netns]
        return ns.route("replace", dst=dst, **kwargs)

    def remove_route(self, dst: str, netns: str = "localhost", **kwargs):
        if "oif" in kwargs:
            kwargs["oif"] = self.get_interface_index(kwargs["oif"], netns=netns)

        ns = self._netns_dict[netns]
        netlink_ignore_not_exists(lambda: ns.route("del", dst=dst, **kwargs))

    def flush_route_table(self, table: int, netns: str = "localhost"):
        ns = self._netns_dict[netns]
        ns.flush_routes(table=table)

    def get_interface_index(self, ifname: str, netns: str = "localhost") -> None | int:
        ids = self._netns_dict[netns].link_lookup(ifname=ifname)

        if len(ids) == 0:
            return None
        return ids[0]

    def remove_interface(self, ifname: str, netns: str = "localhost"):
        ns = self._netns_dict[netns]

        netlink_ignore_not_exists(lambda: ns.link("del", ifname=ifname))
