#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAMBDA_DIR="${SCRIPT_DIR}/lambda"
BUILD_DIR="${SCRIPT_DIR}/lambda_build"

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

FUNCTIONS=(authoriser credential_validator search_dispatcher)

for func in "${FUNCTIONS[@]}"; do
    echo "==> Packaging ${func}..."
    func_dir="${LAMBDA_DIR}/${func}"
    work_dir="${BUILD_DIR}/${func}"

    mkdir -p "${work_dir}"

    if [[ -f "${func_dir}/requirements.txt" ]]; then
        pip install \
            --quiet \
            --target "${work_dir}" \
            --requirement "${func_dir}/requirements.txt"
    fi

    cp "${func_dir}/handler.py" "${work_dir}/"

    (cd "${work_dir}" && zip -q -r "${BUILD_DIR}/${func}.zip" .)

    echo "    -> ${BUILD_DIR}/${func}.zip"
done

echo ""
echo "All Lambda packages built in ${BUILD_DIR}/"
ls -lh "${BUILD_DIR}"/*.zip
