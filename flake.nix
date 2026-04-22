{
  description = "Video Utilities - Fast & Simple Video Processing";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
      pkgsFor = system: import nixpkgs {
        inherit system;
      };
    in
    {
      packages = forAllSystems (system:
        let
          pkgs = pkgsFor system;
          python = pkgs.python3;
          
          runtimeLibs = with pkgs; [
            gtk3
            glib
            zlib
            cairo
            pango
            gdk-pixbuf
            atk
            libnotify
            dbus
            libxcrypt-legacy
            harfbuzz
            freetype
            fontconfig
            libGL
            libX11
            libXcursor
            libXinerama
            libXi
            libXrandr
            gst_all_1.gstreamer
            gst_all_1.gst-plugins-base
            gst_all_1.gst-plugins-good
            mpv
            libepoxy
            libsecret
          ];

          flet-desktop-custom = python.pkgs.buildPythonPackage rec {
            pname = "flet-desktop";
            version = "0.80.2";
            pyproject = true;
            src = python.pkgs.fetchPypi {
              pname = "flet_desktop";
              inherit version;
              sha256 = "8b17523282b36393a3ff1e468db3c7d8a3d96ddec85f95fb5d73e50142cd3d62";
            };
            doCheck = false;
            nativeBuildInputs = [ python.pkgs.setuptools ];
            # Remove flet from runtime deps check to avoid circular dep
            postPatch = ''
               sed -i '/"flet"/d' pyproject.toml
            '';
          };

          flet-custom = python.pkgs.buildPythonPackage rec {
            pname = "flet";
            version = "0.80.2";
            pyproject = true;
            src = python.pkgs.fetchPypi {
              inherit pname version;
              sha256 = "1dm4kvna8i2va69agzvsklbi7a2z1imfm4x4rhmkrcjbbra2s7lc";
            };
            doCheck = false;
            nativeBuildInputs = [ 
              python.pkgs.poetry-core 
              python.pkgs.setuptools 
            ];
            propagatedBuildInputs = with python.pkgs; [
              httpx
              oauthlib
              packaging
              typing-extensions
              websocket-client
              repath
              msgpack
            ];
            postPatch = ''
              # Fix invalid license in pyproject.toml that crashes setuptools
              sed -i '/license = "Apache-2.0"/d' pyproject.toml
              
              if [ -f src/flet/utils/pip.py ]; then
                substituteInPlace src/flet/utils/pip.py \
                  --replace-fail 'install_flet_package("flet-desktop")' 'pass'
              fi
            '';
          };

          flet-video-custom = python.pkgs.buildPythonPackage rec {
            pname = "flet-video";
            version = "0.80.2";
            pyproject = true;
            src = python.pkgs.fetchPypi {
              pname = "flet_video";
              inherit version;
              sha256 = "0zy4f4jz680lzcy8n7qbw4v3hy2yssp8hahjyx1n3v6zvj2fh1js";
            };
            doCheck = false;
            nativeBuildInputs = [ 
              python.pkgs.poetry-core 
              python.pkgs.setuptools 
            ];
            propagatedBuildInputs = [ flet-custom ];
          };

          playsound-custom = python.pkgs.buildPythonPackage rec {
            pname = "playsound";
            version = "1.2.2";
            pyproject = true;
            src = pkgs.fetchurl {
              url = "https://github.com/TaylorSMarks/playsound/archive/907f1fe73375a2156f7e0900c4b42c0a60fa1d00.tar.gz";
              sha256 = "0r2yinha18yk1fr470a3128zakambrvqw1l07aizbm62idsc7wr9";
            };
            doCheck = false;
            nativeBuildInputs = [ python.pkgs.setuptools ];
            postPatch = ''
              cat > setup.py <<EOF
from setuptools import setup
setup(
    name='playsound',
    version='1.2.2',
    py_modules=['playsound'],
)
EOF
            '';
          };
          
          python-env = python.withPackages (ps: [
            flet-custom
            flet-video-custom
            playsound-custom
            ps.pygobject3
            ps.httpx
            ps.httpcore
            flet-desktop-custom
          ]);
        in
        {
          default = pkgs.stdenv.mkDerivation {
            pname = "videoutils";
            version = "1.0.0";
            src = ./.;
            
            nativeBuildInputs = [ pkgs.makeWrapper ];
            
            installPhase = ''
              mkdir -p $out/bin
              mkdir -p $out/share/videoutils
              cp -r . $out/share/videoutils
              
              makeWrapper ${python-env}/bin/python3 $out/bin/videoutils \
                --add-flags "$out/share/videoutils/main.py" \
                --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.ffmpeg ]} \
                --prefix LD_LIBRARY_PATH : "${pkgs.lib.makeLibraryPath runtimeLibs}" \
                --prefix GI_TYPELIB_PATH : "${pkgs.lib.makeSearchPath "lib/girepository-1.0" [ pkgs.gtk3 pkgs.libnotify pkgs.gobject-introspection ]}" \
                --set PYTHONPATH "$PYTHONPATH:$out/share/videoutils"
            '';
          };
        });

      devShells = forAllSystems (system:
        let
          pkgs = pkgsFor system;
          # Reuse the custom packages defined above
          customPkgs = self.packages.${system}.default;
        in
        {
          default = pkgs.mkShell {
            inputsFrom = [ customPkgs ];
          };
        });
    };
}
