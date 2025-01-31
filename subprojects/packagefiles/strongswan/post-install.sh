#!/usr/bin/env bash

build_dir="$MESON_BUILD_ROOT"/subprojects/strongswan/build/src
destination="$MESON_INSTALL_DESTDIR_PREFIX"/libexec/aronet


# install charon
if [ -f "$build_dir"/charon/charon ]; then
  cp "$build_dir"/charon/charon "$destination"/charon
fi
