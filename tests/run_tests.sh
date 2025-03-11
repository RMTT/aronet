#!/usr/bin/env bash

set -e

if [ -z "$DOCKER" ]; then
    DOCKER=docker
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

launch_container() {
    name=$1
    ip=$2
    echo "trying to run aronet in $name node..."
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
        --name "$name" \
        --hostname "$name" \
        --net aronet \
        --ip "$ip" \
        -v "$SCRIPT_DIR"/config:/config \
        aronet:test aronet daemon run -c /config/"$name"/config.json -r /config/registry.json
    echo "done!"
}

setup() {
    echo "trying to create network..."
    eval "$DOCKER" network create --subnet=172.32.0.0/16 aronet
    echo "done!"

    launch_container sun 172.32.0.3

    launch_container moon 172.32.0.2

    launch_container earth 172.32.0.4

    launch_container mars 172.32.0.5
}

cleanup() {
    echo "cleanup..."

    echo "remove container moon.."
    eval "$DOCKER" container rm -f moon || true
    echo "done!"

    echo "remove container sun.."
    eval "$DOCKER" container rm -f sun || true
    echo "done!"

    echo "remove container earth.."
    eval "$DOCKER" container rm -f earth || true
    echo "done!"

    echo "remove container earth.."
    eval "$DOCKER" container rm -f mars || true
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
    eval "$DOCKER" exec earth ping -c 5 192.168.129.1
    eval "$DOCKER" exec moon ping -c 5 192.168.129.1
    eval "$DOCKER" exec sun ping -c 5 192.168.128.1

    eval "$DOCKER" exec moon aronet swanctl --list-sas
    eval "$DOCKER" exec moon aronet swanctl --list-conns

    echo "moon and sun are successfully connectted!"
}

cleanup
setup
sleep 5
test_connectivity
cleanup
