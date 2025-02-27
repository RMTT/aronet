from pyroute2 import IPRoute, NetNS, NetlinkError


# Why not use ndb?
# ndb cannot set srv6 route
# ndb will raise meaningless errors


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

    def create_interface(
        self, ifname: str, netns: str = "localhost", addresses: list[str] = [], **kwargs
    ):
        if "state" not in kwargs:
            kwargs["state"] = "up"
        ns = self._netns_dict[netns]
        ns.link("add", ifname=ifname, **kwargs)
        idx = self.get_interface_index(netns=netns, ifname=ifname)

        for addr in addresses:
            ip = addr.split("/")[0]
            len = str(addr.split("/")[1])
            ns.addr("add", index=idx, address=ip, prefixlen=len)

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
        ns.link("set", ifname=ifname, **kwargs)

    def create_route(self, dst: str, netns: str = "localhost", **kwargs):
        if "oif" in kwargs:
            kwargs["oif"] = self.get_interface_index(kwargs["oif"])

        ns = self._netns_dict[netns]
        ns.route("add", dst=dst, **kwargs)

    def get_interface_index(self, ifname: str, netns: str = "localhost"):
        return self._netns_dict[netns].link_lookup(ifname=ifname)[0]

    def remove_interface(self, ifname: str, netns: str = "localhost"):
        ns = self._netns_dict[netns]

        try:
            ns.link("del", ifname=ifname)
        except NetlinkError as e:
            if e.code != 19:
                raise e
