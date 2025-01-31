#!/usr/bin/env bash

source_root=$1
output=$(realpath "$2")

cd "$source_root" || exit 1

make -j

cp src/charon/charon "$output"



