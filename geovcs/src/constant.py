import os
import posixpath
from string import Template

VERSION = "v0.0.1"
PROVIDER_KEY = "GeoVCS"
SETTINGS_BASE_KEY = posixpath.join("plugins", "geovcs")
SETTINGS_CONNECTION_KEY = "connection"

FORM_DIRECTORY_PATH = os.path.abspath(
    os.path.join((os.path.dirname(__file__)), "..", "asset", "form")
)

# sql
SELECT__DOLT_BRANCHES = """
    SELECT
        name
    FROM
        dolt_branches
    ORDER BY
        name ASC
"""

# sql
SELECT__DOLT_STATUS = """
    SELECT
        table_name,
        status
    FROM
        dolt_status
    ORDER BY
        table_name ASC
"""

CALL__DOLT_COMMIT_HASH_OUT = Template("""
    CALL DOLT_COMMIT_HASH_OUT (@hash, '-A', '-m', '$message')
""")

# sql
SELECT__HASH = """
    SELECT @hash
"""
