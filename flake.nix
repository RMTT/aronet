{
  description = "Auto routed overlay network based on ipsec and babel.";

  inputs = { flake-utils.url = "github:numtide/flake-utils"; };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let pkgs = import nixpkgs { inherit system; };
      in with pkgs; {
        devShells.default = mkShell {
          inputsFrom = [ strongswan ];
          packages = [ pkgs.python3 ncurses readline ];
          nativeBuildInputs = [ meson ninja ];

          shellHook = ''
            if [ ! -d .venv ]; then
              python -m venv .venv
            fi
            source .venv/bin/activate
          '';
        };
      });
}
