#!/bin/bash

# Define database connection parameters for local
# We will replace it for prod with POSTGRES_LOGIN_URL
host="localhost"
port="54322"
username="postgres"
database="postgres"
MODEL_FILE=db/models.py

# BEWARE: This is a terrible hack to coerce pwiz to create the auth.users model (which is linked so often).
psql -h $host -p $port -U $username -d $database -c \
"CREATE TABLE public.users AS SELECT * FROM auth.users WHERE FALSE;"

# Generate the models using pwiz,
export PGPASSWORD=postgres; python -m pwiz -e postgresql -H $host -p $port -u $username $database > $MODEL_FILE

# BEWARE: Make sure this stays "public.users" and NOT "auth.users".
psql -h $host -p $port -U $username -d $database -c \
"DROP TABLE public.users;"

# We run `black` twice, so the output is close what we are replacing.
black $MODEL_FILE

python db/generate_models.py $MODEL_FILE

black $MODEL_FILE