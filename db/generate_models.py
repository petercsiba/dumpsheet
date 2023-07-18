import re
import sys

# the 0th argument is the script name itself
file_name = sys.argv[1]

with open(file_name, "r") as file:
    data = file.read()

# Define the regex patterns and replacements
old_line_pattern = r"database = PostgresqlDatabase\(.*?\)"
new_line = "from db.db import database"
data = re.sub(old_line_pattern, new_line, data, flags=re.DOTALL)

# Rename all classes that inherit from BaseModel with 'Base', e.g.:
# class ClassName(BaseModel):
# replace to
# class BaseClassName(BaseModel):
base_model_pattern = r"class (\w*?)(\(BaseModel\))"
replacement = r"class Base\1\2"
data = re.sub(base_model_pattern, replacement, data)

data = data.replace("BaseBaseModel", "BaseModel")

with open(file_name, "w") as file:
    file.write(data)
