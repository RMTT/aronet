import asyncio
import json
from logging import Logger

from aronet.config import Config
from aronet.daemon import ACTION_LOAD_CONNS, Daemon, InternalMessage


class BackendDaemon(Daemon):
    """
    Backend will be used to interact the daemons and command line client of aronet by unix domain socket.

    The message format must be json.
    """

    def __init__(self, config: Config, logger: Logger) -> None:
        super().__init__(config, logger)
        self.__message_handlers = None
        self.__server = None

    def __del__(self):
        pass

    def set_message_handlers(self, message_handlers: dict):
        self.__message_handlers = message_handlers

    async def exit_callback(self):
        self._logger.info("terminating backend...")
        if self.__server and self.__server.is_serving():
            self.__server.close()
            await self.__server.wait_closed()

    async def __handle(self, msg: InternalMessage):
        for actions, handlers in self.__message_handlers.items():
            if actions | msg.action:
                for handler in handlers:
                    await handler(msg)

    async def hanlder(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        while True:
            try:
                data = await reader.readuntil()

                self._logger.debug(f"received message: f{data}")

                msg = json.loads(data)

                internal_message = None

                if "action" in msg:
                    if msg["action"] == ACTION_LOAD_CONNS:
                        internal_message = InternalMessage(
                            action=ACTION_LOAD_CONNS, data=msg
                        )

                if internal_message:
                    await self.__handle(internal_message)
            except asyncio.IncompleteReadError:
                writer.close()
                await writer.wait_closed()

                break

    async def run(self):
        self.__server = await asyncio.start_unix_server(
            self.hanlder, self._config.backend_socket_path
        )

        try:
            await self.__server.serve_forever()
        except asyncio.CancelledError:
            self._logger.info("aronet socket will be closed...")
