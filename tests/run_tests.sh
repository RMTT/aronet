#!/usr/bin/env bash

#set -e

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

setup() {
    echo "trying to create docker network..."
    docker network create --subnet=172.32.0.0/16 aronet
    echo "done!"

    echo "trying to run aronet in moon node..."
    docker run \
        --cap-add NET_ADMIN --cap-add SYS_MODULE --cap-add SYS_ADMIN \
        --security-opt apparmor=unconfined --security-opt seccomp=unconfined \
        -d \
        --name moon \
        --hostname moon \
        --net aronet \
        --ip 172.32.0.2 \
        -v "$SCRIPT_DIR"/config:/config \
        aronet:test aronet daemon run -c /config/moon/config.json
    echo "done!"

    echo "trying to run aronet in sun node..."
    docker run \
        --cap-add NET_ADMIN --cap-add SYS_MODULE --cap-add SYS_ADMIN \
        --security-opt apparmor=unconfined --security-opt seccomp=unconfined \
        -d \
        --name sun \
        --hostname sun \
        --net aronet \
        --ip 172.32.0.3 \
        -v "$SCRIPT_DIR"/config:/config \
        aronet:test aronet daemon run -c /config/sun/config.json
    echo "done!"
}

cleanup() {
    echo "cleanup..."

    echo "remove container moon.."
    docker container rm -f moon || true
    echo "done!"

    echo "remove container sun.."
    docker container rm -f sun || true
    echo "done!"

    echo "remove network aronet..."
    docker network rm -f aronet || true
    echo "done!"
}

load_conn() {
    echo "trying to load connections in moon..."
    docker exec moon aronet load -c /config/moon/config.json -r /config/registry.json
    docker logs moon
    echo "done!"

    echo "trying to load connections in sun..."
    docker exec sun aronet load -c /config/sun/config.json -r /config/registry.json
    echo "done!"
}

test_connectivity() {
    while ! (docker exec sun ip a | grep 'aronet-.*'); do
        echo "wait connections establised in node sun..."
        sleep 5
    done

    while ! (docker exec moon ip a | grep 'aronet-.*'); do
        echo "wait connections establised in node moon..."
        sleep 5
    done

    docker exec moon ping -c 5 192.168.129.1
    docker exec sun ping -c 5 192.168.128.1

    docker exec moon aronet swanctl --list-sas
    docker exec moon aronet swanctl --list-conns

    echo "moon and sun are successfully connectted!"
}

cleanup
setup
load_conn
test_connectivity
cleanup
