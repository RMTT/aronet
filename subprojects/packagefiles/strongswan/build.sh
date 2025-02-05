#!/usr/bin/env bash

source_root=$1
output_dir=$(realpath "$2")

cd "$source_root" || exit 1

make -j

cp src/charon/charon "$output_dir"
cp src/swanctl/swanctl "$output_dir"
cp src/_updown/_updown "$output_dir"
