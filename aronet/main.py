import os

from aronet.cmd import CommandRunner
from aronet.config import Config

def main() -> int:
    libexec_path = os.path.join(os.path.dirname(__file__), "libexec")


    config = Config(libexec_path=libexec_path)

    CommandRunner(config).run()

    return 0
