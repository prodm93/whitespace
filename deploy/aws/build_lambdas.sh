#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAMBDA_DIR="${SCRIPT_DIR}/lambda"
BUILD_DIR="${SCRIPT_DIR}/lambda_build"

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

FUNCTIONS=(authoriser credential_validator search_dispatcher orchestrate_enqueue upload_url durable_dispatcher)

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

# runs_reader: pydantic-core is compiled; build for Linux x86_64 and vendor whitespace
echo "==> Packaging runs_reader..."
runs_reader_work="${BUILD_DIR}/runs_reader"
mkdir -p "${runs_reader_work}"

pip install \
    --quiet \
    --target "${runs_reader_work}" \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.11 \
    --only-binary=:all: \
    --requirement "${LAMBDA_DIR}/runs_reader/requirements.txt"

cp -r "${SCRIPT_DIR}/../../src/whitespace" "${runs_reader_work}/whitespace"
cp "${LAMBDA_DIR}/runs_reader/handler.py" "${runs_reader_work}/"

(cd "${runs_reader_work}" && zip -q -r "${BUILD_DIR}/runs_reader.zip" .)
echo "    -> ${BUILD_DIR}/runs_reader.zip"

echo ""
echo "All Lambda packages built in ${BUILD_DIR}/"
ls -lh "${BUILD_DIR}"/*.zip
