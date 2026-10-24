#!/usr/bin/env bash
set -e # Exit immediately if a command exits with a non-zero status

chsh -s $(which zsh) root || true
if ! command -v starship &> /dev/null; then
  echo "Installing Starship prompt..."
  curl -sS https://starship.rs/install.sh | sh -s -- -y
fi
apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
        build-essential ca-certificates coreutils curl environment-modules \
        gfortran git gpg lsb-release python3 python3-distutils python3-venv python3-pip \
        unzip zip bzip2 xz-utils patch file gnupg2 make tar gzip zstd \
        gmsh python3-gmsh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
python3 -m pip install --upgrade pip
# There are no gmsh wheels on PyPI for linux/aarch64, so expose the Python API
# of the Debian gmsh package (a single gmsh.py loading libgmsh) to this Python
if ! python3 -c "import gmsh" 2> /dev/null; then
  ln -sf /usr/lib/python3/dist-packages/gmsh.py \
    "$(python3 -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')/gmsh.py"
fi
python3 -m pip install -e .[dev]
pre-commit install
# 3. Print success message
echo "Container setup complete!"
