#!/usr/bin/env bash

# Abort at the first error.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Make sure that environment variables are set properly
source /opt/rh/devtoolset-7/enable
export PATH="${CURA_BUILD_ENV_PATH}/bin:${PATH}"
export PKG_CONFIG_PATH="${CURA_BUILD_ENV_PATH}/lib/pkgconfig:${PKG_CONFIG_PATH}"

cd "${PROJECT_DIR}"

#
# Clone Uranium and set PYTHONPATH first
#
URANIUM_BRANCH="steslicer"
output="$(git ls-remote --heads https://gitlab.com/stereotech/steslicer/Uranium.git "${URANIUM_BRANCH}")"
if [ -z "${output}" ]; then
    echo "Could not find Uranium banch ${URANIUM_BRANCH}, fallback to use master."
    URANIUM_BRANCH="master"
fi

echo "Using Uranium branch ${URANIUM_BRANCH} ..."
git clone --depth=1 -b "${URANIUM_BRANCH}" https://gitlab.com/stereotech/steslicer/Uranium.git "${PROJECT_DIR}"/Uranium
export PYTHONPATH="${PROJECT_DIR}/Uranium:.:${PYTHONPATH}"

cd build
ctest3 --output-on-failure -T Test
