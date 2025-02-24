from pyroute2 import NDB


class Netlink:
    _instance = None

    def __init__(self) -> None:
        self.ndb = NDB()

    def __new__(cls, *args, **kwargs):
        if not Netlink._instance:
            Netlink._instance = object.__new__(cls)
        return Netlink._instance

    def __del__(self):
        self.ndb.close()
