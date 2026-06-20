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
QUERY_ALL_BRANCHES = """
    SELECT
        name
    FROM
        dolt_branches
    ORDER BY
        name ASC
"""

# sql
QUERY_STATUS = """
    SELECT
        table_name,
        status
    FROM
        dolt_status
    ORDER BY
        table_name ASC
"""

# sql
QUERY_ADD = """
    CALL DOLT_ADD('--all')
"""

# sql
QUERY_COMMIT = Template("""
    CALL DOLT_COMMIT('-m', '$message');
""")
