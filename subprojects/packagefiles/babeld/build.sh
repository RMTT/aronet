#!/usr/bin/env bash

source_root=$1
output=$(realpath "$2")
os_args=$3

cd "$source_root" || exit 1

make "$os_args"

cp babeld "$output"
