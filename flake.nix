{
  description = "Auto routed overlay network based on ipsec and babel.";

  inputs = { flake-utils.url = "github:numtide/flake-utils"; };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let pkgs = import nixpkgs { inherit system; };
      in with pkgs; {
        devShells.default = mkShell {
          inputsFrom = [ strongswan ];
          packages = [ ncurses readline rustup rust-analyzer-unwrapped lldb ];
          nativeBuildInputs = [ meson ninja ];

          shellHook = ''
            export SHELL=/run/current-system/sw/bin/bash
          '';
        };
      });
}
