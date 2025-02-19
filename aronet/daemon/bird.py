import asyncio
import os
from logging import Logger

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
            export all;
            import none;
		  }};
        }}

        protocol kernel {{
          kernel table {route_table};
          ipv4 {{
            export all;
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
          vrf "aronet";
          ipv6 sadr {{
            export all;
            import all;
          }};
          ipv4 {{
            export all;
            import all;
          }};
          randomize router id;
          interface "aronet-*" {{
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
        self.__pidfile_path = os.path.join(self._config.runtime_dir, "bird.pid")

    def __process_output(self, line: str):
        self._logger.info(f"[bird]: {line}")

    async def run(self):
        ipv4_networks = ""
        ipv6_networks = ""

        if self._config.route_networks:
            for net in self._config.route_networks:
                if net.version == 4:
                    ipv4_networks += f"\nroute {net.with_prefixlen} unreachable;"
                else:
                    ipv6_networks += (
                        f"\nroute {net.with_prefixlen} from ::/0 unreachable;"
                    )

        with open(self._config.bird_conf_path, "w") as f:
            f.write(
                Bird.CONF_TEMP.format(
                    route_table=self._config.route_table,
                    ipv4_networks=ipv4_networks,
                    ipv6_networks=ipv6_networks,
                )
            )

        self.clean = True
        self._logger.info("running bird...")
        self.process = await asyncio.create_subprocess_exec(
            self._config.bird_path,
            "-c",
            self._config.bird_conf_path,
            "-P",
            self.__pidfile_path,
            "-f",
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )

        if self.process.returncode:
            raise Exception(f"bird exited, returncode: {self.process.returncode}")

        await asyncio.gather(
            read_stream(self.process.stdout, self.__process_output),
            read_stream(self.process.stderr, self.__process_output),
        )

        await self.process.wait()

    def info(self) -> str:
        pid = None

        if os.path.exists(self.__pidfile_path):
            with open(self.__pidfile_path, "r") as f:
                pid = f.read()

        if pid is not None:
            return f"bird is running, pid {pid}"

        return "bird is not running"
