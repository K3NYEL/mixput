#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:?Usage: build-deb.sh VERSION [BINARY_PATH] [OUTPUT_DIR]}"
BINARY_PATH="${2:-dist/mixput}"
OUTPUT_DIR="${3:-dist/packages}"
PACKAGE_NAME="mixput"
ARCH="amd64"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
STAGING_DIR="$(mktemp -d)"
PACKAGE_ROOT="${STAGING_DIR}/${PACKAGE_NAME}"

cleanup() {
    rm -rf "${STAGING_DIR}"
}
trap cleanup EXIT

if [[ ! -f "${ROOT_DIR}/${BINARY_PATH}" ]]; then
    echo "Executable not found: ${ROOT_DIR}/${BINARY_PATH}" >&2
    exit 1
fi

mkdir -p \
    "${PACKAGE_ROOT}/DEBIAN" \
    "${PACKAGE_ROOT}/usr/bin" \
    "${PACKAGE_ROOT}/usr/share/applications" \
    "${PACKAGE_ROOT}/usr/share/icons/hicolor/256x256/apps" \
    "${OUTPUT_DIR}"

sed "s/^Version: .*/Version: ${VERSION}/" "${SCRIPT_DIR}/control" \
    > "${PACKAGE_ROOT}/DEBIAN/control"
install -m 0755 "${ROOT_DIR}/${BINARY_PATH}" "${PACKAGE_ROOT}/usr/bin/mixput"
install -m 0644 "${SCRIPT_DIR}/mixput.desktop" \
    "${PACKAGE_ROOT}/usr/share/applications/mixput.desktop"
install -m 0644 "${ROOT_DIR}/public/assets/mixput.png" \
    "${PACKAGE_ROOT}/usr/share/icons/hicolor/256x256/apps/mixput.png"

dpkg-deb --root-owner-group --build "${PACKAGE_ROOT}" \
    "${OUTPUT_DIR}/Mixput-v${VERSION}-linux-x64.deb"

echo "Package created: ${OUTPUT_DIR}/Mixput-v${VERSION}-linux-x64.deb"
