!/bin/bash

# TEMPLATE_FILE=sam_app/template.yaml

# Exit early when any step fails (like pytest fails)
set -e

echo "running tests"
python -m pytest sam_app/tests/unit -v

echo "copy new models (including the post-generate modified ones)"
cp -r database/ sam_app/upload_voice/database/

# Cause the (many) limitations of SAM, we have to run it in the root (yeah, --template doesn't help)
echo "cd sam_app"
cd sam_app

echo "build the sam stuff (otherwise it could omitted changes to app.py)"
sam build
echo "deploy it"
yes | sam deploy --profile AdministratorAccess-831154875375

echo "curl the endpoint as test"
curl -X GET https://api.voxana.ai/upload/voice

cd ..
