#!/usr/bin/env bash

ARONET_IF_PREFIX="aronet"
ARONET_ENABLE_VRF=true
ARONET_IF_NAME="aronet"
ARONET_ENABLE_NETNS=false
ARONET_NETNS_NAME="aronet"

ENV_FILE=/var/run/aronet/updown_env
if [ -f $ENV_FILE ]; then
    source $ENV_FILE
fi

LINK="$ARONET_IF_PREFIX"-$(printf '%08x\n' "$PLUTO_IF_ID_OUT")
case "$PLUTO_VERB" in
up-client)
    ip link add "$LINK" type xfrm if_id "$PLUTO_IF_ID_OUT"
    ip link set "$LINK" multicast on mtu 1400 up

    if [ "$ARONET_ENABLE_VRF" == true ]; then
        ip link set "$LINK" master "$ARONET_IF_NAME"
    else
        ip link set "$LINK" netns "$ARONET_NETNS_NAME" up
    fi
    ;;
down-client)
    if [ "$ARONET_ENABLE_NETNS" == true ]; then
        ip netns exec "$ARONET_NETNS_NAME" ip link del "$LINK"
    else
        ip link del "$LINK"
    fi
    ;;
esac
