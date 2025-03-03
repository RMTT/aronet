FROM debian:12 AS builder

# python env
RUN apt update && apt install -y python3 python3-pip python3-venv && python3 -m venv /venv

# tools for compiling
RUN apt install -y git gcc automake autoconf libtool pkg-config gettext perl gperf flex bison libssl-dev ninja-build libncurses-dev libreadline-dev

COPY . /app

ENV PATH="/venv/bin:$PATH"

WORKDIR /app
RUN pip install .

FROM debian:12 AS runner
RUN apt update && apt install -y python3 iproute2 iputils-ping tcpdump gdb procps curl nftables iperf3 vim systemtap net-tools

COPY --from=builder /venv /venv

ENV PATH="/venv/bin:$PATH"

