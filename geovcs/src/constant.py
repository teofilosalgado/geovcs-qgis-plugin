import os
import posixpath

VERSION = "v0.0.1"
PROVIDER_KEY = "GeoVCS"
SETTINGS_BASE_KEY = posixpath.join("plugins", "geovcs")
SETTINGS_CONNECTION_KEY = "connection"

FORM_DIRECTORY_PATH = os.path.abspath(
    os.path.join((os.path.dirname(__file__)), "..", "asset", "form")
)
