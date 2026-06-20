import os
import posixpath

VERSION = "v0.0.1"
PROVIDER_KEY = "GeoVCS"
SETTINGS_BASE_KEY = posixpath.join("plugins", "geovcs")
SETTINGS_CONNECTION_KEY = "connection"

FORM_DIRECTORY_PATH = os.path.abspath(
    os.path.join((os.path.dirname(__file__)), "..", "asset", "form")
)

QUERY_ALL_BRANCHES = "SELECT name FROM dolt_branches ORDER BY name ASC"
QUERY_STATUS = "SELECT table_name, status FROM dolt_status ORDER BY table_name ASC"
