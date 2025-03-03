import asyncio
import os
from asyncio.exceptions import CancelledError
from logging import Logger

from pyroute2.netns import popns, pushns

from aronet.config import Config
from aronet.daemon import Daemon
from aronet.util import read_stream


class Bird(Daemon):
    CONF_TEMP = """
        log stderr all;
        ipv6 sadr table sadr6;

        protocol device {{
          scan time 5;
        }}

        protocol kernel {{
          kernel table {route_table};
          ipv6 sadr {{
            export where source = RTS_BABEL;
            import none;
		  }};
        }}

        protocol kernel {{
          kernel table {route_table};
          ipv4 {{
            export where source = RTS_BABEL;
            import none;
		  }};
        }}

        protocol static {{
          ipv4;
          {ipv4_networks}
        }}

        protocol static {{
          ipv6 sadr;
          {ipv6_networks}
        }}

        protocol babel {{
          {vrf_statement};
          ipv6 sadr {{
            export all;
            import all;
          }};
          ipv4 {{
            export all;
            import all;
          }};
          randomize router id;
          interface "{prefix}-*" {{
            type tunnel;
            rxcost 32;
            hello interval 20 s;
            rtt cost 1024;
            rtt max 1024 ms;
            rx buffer 2000;
            check link;
          }};
        }}
    """

    def __init__(self, config: Config, logger: Logger) -> None:
        super().__init__(config, logger)
        self._pidfile_path = os.path.join(self._config.runtime_dir, "bird.pid")
        self.__tasks = None

    def __process_output(self, line: str):
        self._logger.info(f"[bird]: {line}")

    async def exit_callback(self):
        self._logger.info("terminating bird...")

        if self.process.returncode is None:
            self.process.terminate()
        if self.process.returncode is None:
            self.process.wait()

        if self.__tasks and not self.__tasks.done:
            self._logger.info("some tasks in bird still running, wait 5 seconds...")
            await asyncio.sleep(5)

            try:
                self.__tasks.cancel()
            except CancelledError:
                pass

    def __del__(self):
        super().__del__()
        self._logger.debug("delete bird object in daemon")

    async def run(self):
        ipv4_networks = ""
        ipv6_networks = ""

        if self._config.route_networks:
            for net in self._config.route_networks:
                if net.version == 4:
                    ipv4_networks += f"\nroute {net.with_prefixlen} unreachable;"
                    pass
                else:
                    ipv6_networks += (
                        f"\nroute {net.with_prefixlen} from ::/0 unreachable;"
                    )

        with open(self._config.bird_conf_path, "w") as f:
            vrf_statement = f'vrf "{self._config.ifname}"'
            route_table = self._config.vrf_route_table
            if self._config.use_netns:
                vrf_statement = ""
                route_table = 254

            f.write(
                Bird.CONF_TEMP.format(
                    route_table=route_table,
                    vrf_statement=vrf_statement,
                    prefix=self._config.tunnel_if_prefix,
                    ipv4_networks=ipv4_networks,
                    ipv6_networks=ipv6_networks,
                )
            )

        self._clean = True
        self._logger.info("running bird...")

        if self._config.use_netns:
            pushns(self._config.netns_name)
        self.process = await asyncio.create_subprocess_exec(
            self._config.bird_path,
            "-c",
            self._config.bird_conf_path,
            "-P",
            self._pidfile_path,
            "-f",
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        if self._config.use_netns:
            popns()

        if self.process.returncode:
            raise Exception(f"bird exited, returncode: {self.process.returncode}")

        self.__tasks = asyncio.gather(
            read_stream(self.process.stdout, self.__process_output, self._config),
            read_stream(self.process.stderr, self.__process_output, self._config),
        )

        await self.__tasks

    def info(self) -> str:
        pid = None

        if os.path.exists(self._pidfile_path):
            with open(self._pidfile_path, "r") as f:
                pid = f.read()

        if pid is not None:
            return f"bird is running, pid {pid}"

        return "bird is not running"
