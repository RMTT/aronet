#!/usr/bin/env bash

LINK=aronet-$(printf '%08x\n' "$PLUTO_IF_ID_OUT")
case "$PLUTO_VERB" in
up-client)
    ip link add "$LINK" type xfrm if_id "$PLUTO_IF_ID_OUT"
    ip link set "$LINK" master aronet multicast on mtu 1400 up
    ;;
down-client)
    ip link del "$LINK"
    ;;
esac
