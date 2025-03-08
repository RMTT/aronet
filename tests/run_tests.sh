#!/usr/bin/env bash

set -e

if [ -z "$DOCKER" ]; then
    DOCKER=docker
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

setup() {
    echo "trying to create network..."
    eval "$DOCKER" network create --subnet=172.32.0.0/16 aronet
    echo "done!"

    echo "trying to run aronet in moon node..."
    eval "$DOCKER" run \
        --cap-add NET_ADMIN --cap-add SYS_MODULE --cap-add SYS_ADMIN \
        --security-opt apparmor=unconfined --security-opt seccomp=unconfined \
        --privileged \
        --sysctl net.netfilter.nf_hooks_lwtunnel=1 \
        --sysctl net.ipv6.conf.all.forwarding=1 \
        --sysctl net.ipv4.ip_forward=1 \
        --sysctl net.ipv4.tcp_l3mdev_accept=1 \
        --sysctl net.ipv4.udp_l3mdev_accept=1 \
        -d \
        -it \
        --name moon \
        --hostname moon \
        --net aronet \
        --ip 172.32.0.2 \
        -v "$SCRIPT_DIR"/config:/config \
        aronet:test aronet daemon run -c /config/moon/config.json -r /config/registry.json
    echo "done!"

    echo "trying to run aronet in sun node..."
    eval "$DOCKER" run \
        --cap-add NET_ADMIN --cap-add SYS_MODULE --cap-add SYS_ADMIN \
        --security-opt apparmor=unconfined --security-opt seccomp=unconfined \
        --privileged \
        --sysctl net.netfilter.nf_hooks_lwtunnel=1 \
        --sysctl net.ipv6.conf.all.forwarding=1 \
        --sysctl net.ipv4.ip_forward=1 \
        --sysctl net.ipv4.tcp_l3mdev_accept=1 \
        --sysctl net.ipv4.udp_l3mdev_accept=1 \
        -d \
        -it \
        --name sun \
        --hostname sun \
        --net aronet \
        --ip 172.32.0.3 \
        -v "$SCRIPT_DIR"/config:/config \
        aronet:test aronet daemon run -c /config/sun/config.json -r /config/registry.json
    echo "done!"
}

cleanup() {
    echo "cleanup..."

    echo "remove container moon.."
    eval "$DOCKER" container rm -f moon || true
    echo "done!"

    echo "remove container sun.."
    eval "$DOCKER" container rm -f sun || true
    echo "done!"

    echo "remove network aronet..."
    eval "$DOCKER" network rm aronet || true
    echo "done!"
}

load_conn() {
    echo "trying to load connections in moon..."
    eval "$DOCKER" exec moon aronet load -r /config/registry.json
    echo "done!"

    echo "trying to load connections in sun..."
    eval "$DOCKER" exec sun aronet load -r /config/registry.json
    echo "done!"
}

test_connectivity() {
    eval "$DOCKER" exec moon ping -c 5 192.168.129.1
    eval "$DOCKER" exec sun ping -c 5 192.168.128.1

    eval "$DOCKER" exec moon aronet swanctl --list-sas
    eval "$DOCKER" exec moon aronet swanctl --list-conns

    echo "moon and sun are successfully connectted!"
}

cleanup
setup
sleep 3
test_connectivity
cleanup
