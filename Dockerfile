FROM rust:slim-trixie AS builder

# tools for compiling
RUN apt update && apt install -y git gcc automake autoconf libtool pkg-config gettext perl gperf flex bison libssl-dev ninja-build libncurses-dev libreadline-dev meson

COPY . /app
WORKDIR /app

RUN meson setup build && meson compile -C build && meson install -C build

FROM rust:slim-trixie AS runner
RUN apt update && apt install -y iproute2 iputils-ping tcpdump gdb procps curl nftables iperf3 vim systemtap net-tools

COPY --from=builder /usr/local/bin/aronet /usr/local/bin/aronet
COPY --from=builder /usr/local/libexec /usr/local/libexec
