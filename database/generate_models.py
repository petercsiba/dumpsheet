import re
import sys

# the 0th argument is the script name itself
file_name = sys.argv[1]

with open(file_name, "r") as file:
    data = file.read()

# Define the regex patterns and replacements
old_line_pattern = r"database = PostgresqlDatabase\(.*?\)"
new_line = (
    "# NOTE: this file is fully generated, if you change something, it will go away\n"
    "from database.client import database_proxy"
)
data = re.sub(old_line_pattern, new_line, data, flags=re.DOTALL)

# For BaseModel.Meta.database
data = data.replace("database = database", "database = database_proxy")

# Rename all classes that inherit from BaseModel with 'Base', e.g.:
# class ClassName(BaseModel):
# replace to
# class BaseClassName(BaseModel):
base_model_pattern = r"class (\w*?)(\(BaseModel\))"
replacement = r"class Base\1\2"
data = re.sub(base_model_pattern, replacement, data)

# Replace model=Users with model=BaseUsers (might be too lenient)
model_pattern = r"model=(\w*?)"
model_replacement = r"model=Base\1"
data = re.sub(model_pattern, model_replacement, data)

# Add schema for table_name
table_name_pattern = r"table_name = \"(\w*?)\""
table_name_replacement_public = r'schema = "public"\n        table_name = "\1"'
table_name_replacement_auth = r'schema = "auth"\n        table_name = "\1"'
data = re.sub(table_name_pattern, table_name_replacement_public, data)
data = data.replace(
    'schema = "public"\n        table_name = "users"',
    'schema = "auth"\n        table_name = "users"',
)

data = data.replace("BaseBaseModel", "BaseModel")


# Hacks for circular deps
pattern = re.compile(r"    owner_account = ForeignKeyField\([\s\S]*?\)", re.MULTILINE)

# Text to replace with
replacement_text = """    # To overcome ForeignKeyField circular dependency
    owner_account_id = UUIDField(null=True)"""

# Replace
data = re.sub(pattern, replacement_text, data)

with open(file_name, "w") as file:
    file.write(data)

# NOTE: For reference cycles leading to "Possible reference cycle: account" in comments
#   and "NameError: name 'BaseAccount' is not defined" during run-time there are some workarounds.
# https://docs.peewee-orm.com/en/latest/peewee/models.html#circular-foreign-key-dependencies
# P1(devx): Update model gen to handle these.
if "Possible reference cycle" in data:
    print("WARNING: There are reference cycle your program might NOT run")
