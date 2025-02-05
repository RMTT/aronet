#!/usr/bin/env bash

source_root=$1
output_dir=$(realpath "$2")

cd "$source_root" || exit 1

make -j

cp bird "$output_dir"
cp birdcl "$output_dir"
