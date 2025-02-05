from logging import Logger
import os
import tempfile
import asyncio
from typing import OrderedDict
from pyroute2 import IPRoute
from pyroute2.netlink.rtnl.ifinfmsg import IFF_MULTICAST, IFF_UP

from aronet.config import Config
from aronet.daemon import Daemon
from aronet.strongswan.client import Client

from aronet.util import read_stream


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

        self.__charon_path = config.charon_path
        self.__pidfile_path = os.path.join(config.runtime_dir, "charon.pid")
        self.__vici = None

        self.__event_handlers = {"ike-updown": self.__updown}

        self.__events = []
        for e, _ in self.__event_handlers.items():
            self.__events.append(e)

    def __vici_connect(self):
        self.__vici = Client(self._config)

    async def __listen(self, event_types: list[str]):
        if self.__vici:
            for _type, msg in self.__vici.listen(event_types):
                _type = bytes(_type).decode()

                self.__event_handlers[_type](msg)

    def __setup_iface(self, ifname: str, xfrm_id: int, master: int, ipr: IPRoute):
        self._logger.info(f"trying to create xfrm interface {ifname}...")
        ipr.link(
            "add",
            ifname=ifname,
            kind="xfrm",
            xfrm_if_id=xfrm_id,
            master=master,
        )

        iface = ipr.get_links(ifname="aronet")[0]
        old_flags = iface["flags"]
        ipr.link(
            "set",
            ifname=ifname,
            mtu=1400,
            flags=old_flags | IFF_MULTICAST | IFF_UP,
        )

    # response for ike-updown event
    def __updown(self, msg: OrderedDict):
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

        if_name_in = f"aronet-{if_id_in}"
        if_name_out = f"aronet-{if_id_out}"

        with IPRoute() as ipr:
            ifs = ipr.link_lookup(ifname="aronet")

            if not ifs:
                raise Exception("aronet interface failed to find")

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

    async def run(self):
        self._conf = tempfile.NamedTemporaryFile()
        self._conf.write(
            Strongswan.CONF_TEMP.format(self._config.vici_socket_path).encode()
        )
        self._conf.flush()

        env = {}
        env["STRONGSWAN_CONF"] = self._conf.name

        self._logger.info("running charon...")
        self.process = await asyncio.create_subprocess_exec(
            self.__charon_path,
            env=env,
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )

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

        await asyncio.gather(
            read_stream(self.process.stdout, self.__process_output),
            read_stream(self.process.stderr, self.__process_output),
            self.__listen(self.__events),
        )

        await self.process.wait()

    def info(self) -> str:
        pid = None

        if os.path.exists(self.__pidfile_path):
            with open(self.__pidfile_path, "r") as f:
                pid = f.read()

        if pid is not None:
            return f"strongswan is running, pid {pid}"

        return "strongswan is not running"
