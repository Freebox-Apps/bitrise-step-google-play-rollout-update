#!/bin/bash
set -e
set -x

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Updating phase release for: ${package_name}"
if [ -z "$service_account_json_key_content" ] ; then
    echo "Downloading credentials from remote file"
    wget -O "${SCRIPT_DIR}/credentials.json" ${service_account_json_key_path}
else
    echo "Using local content credentials"
    echo "$service_account_json_key_content" > "${SCRIPT_DIR}/credentials.json"
fi

echo "installing deps"

pip3 install virtualenv
virtualenv rollout
source rollout/bin/activate
rollout/bin/pip install google-api-python-client
rollout/bin/pip install oauth2client

echo "Running: ${SCRIPT_DIR}/rollout_update.py ${package_name} ${SCRIPT_DIR}/credentials.json ${track} ${force_rollout} ${rollout_steps} ${max_crash_rate}"
rollout/bin/python "${SCRIPT_DIR}/rollout_update.py" "${package_name}" "${SCRIPT_DIR}/credentials.json" "${track}" "${force_rollout}" "${rollout_steps}" "${max_crash_rate}"

rm "${SCRIPT_DIR}/credentials.json"
