#!/usr/bin/env bash

build_type=$1
version=$2
source_root=$3
output_dir=$(realpath "$4")

cd "$source_root" || exit 1

# sync version
sed -i "s/^version *= *\".*\"$/version = \"$version\"/" Cargo.toml

if [ "$build_type" = "release" ]; then
    CARGO_BUILD_TARGET_DIR=$output_dir cargo build --release
else
    CARGO_BUILD_TARGET_DIR=$output_dir cargo build
fi

cp "$output_dir"/"$build_type"/aronet "$output_dir"/aronet
