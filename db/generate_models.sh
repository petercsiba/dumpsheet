#!/bin/bash

# Define database connection parameters
host="localhost"
port="54322"
username="postgres"
database="postgres"

# Generate the models using pwiz,
export PGPASSWORD=postgres; python -m pwiz -e postgresql -H $host -p $port -u $username $database > models.py

# Use sed to prefix all classes that inherit from BaseModel with 'Base', e.g.:
# class ClassName(BaseModel):
# replace to
# class BaseClassName(BaseModel):

# Detect the operating system and use the appropriate sed command
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS sed
    sed -i "" '/class .*BaseModel/ s/\(class \)\(.*\)/\1Base\2/' models.py
else
    # Linux and other UNIX-like systems sed
    sed -i '/class .*BaseModel/ s/\(class \)\(.*\)/\1Base\2/' models.py
fi

# Run black formatter
black models.py