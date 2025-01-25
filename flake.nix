{
  description = "Auto routed overlay network based on ipsec and babel.";

  inputs = { flake-utils.url = "github:numtide/flake-utils"; };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let pkgs = import nixpkgs { inherit system; };
      in with pkgs; {
        devShells.default = mkShell {
          inputsFrom = [ strongswan ];
          nativeBuildInputs = [ meson ];
        };
      });
}
