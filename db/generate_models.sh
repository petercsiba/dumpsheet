#!/bin/bash

# Define database connection parameters for local
# We will replace it for prod with POSTGRES_LOGIN_URL
host="localhost"
port="54322"
username="postgres"
database="postgres"
MODEL_FILE=db/models.py

# Generate the models using pwiz,
export PGPASSWORD=postgres; python -m pwiz -e postgresql -H $host -p $port -u $username $database > $MODEL_FILE

python db/generate_models.py $MODEL_FILE

black $MODEL_FILE