import os
import posixpath
from dataclasses import asdict, dataclass
from functools import cached_property
from typing import Any, Generator

from osgeo import ogr
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsAuthMethodConfig,
    QgsSettings,
)
from qgis.utils import iface

from geovcs.src.constant import SETTINGS_BASE_KEY, SETTINGS_CONNECTION_KEY


@dataclass
class GeoVCSConnection:
    host: str
    port: str
    database: str
    branch: str
    auth_config_id: str

    @cached_property
    def connection_string(self) -> str:
        value = (
            f"MySQL:{self.database}/{self.branch},"
            f"host={self.host},"
            f"port={self.port} "
            f"authcfg={self.auth_config_id}"
        )
        return value

    @cached_property
    def username(self) -> str | None:
        auth_manager = QgsApplication.authManager()
        if not auth_manager:
            return None

        auth_method_config = QgsAuthMethodConfig()
        if auth_manager.loadAuthenticationConfig(
            self.auth_config_id, auth_method_config, True
        ):
            config_map = auth_method_config.configMap()
            username = config_map.get("username", "")
            return username
        else:
            return None

    @cached_property
    def password(self) -> str | None:
        auth_manager = QgsApplication.authManager()
        if not auth_manager:
            return None

        auth_method_config = QgsAuthMethodConfig()
        if auth_manager.loadAuthenticationConfig(
            self.auth_config_id, auth_method_config, True
        ):
            config_map = auth_method_config.configMap()
            password = config_map.get("password", "")
            return password
        else:
            return None

    @cached_property
    def ogr_connection_string(self) -> str | None:
        if self.username is None or self.password is None:
            return None

        value = (
            f"MySQL:{self.database}/{self.branch},"
            f"host={self.host},"
            f"port={self.port},"
            f"user={self.username},"
            f"password={self.password}"
        )
        return value


class GeoVCSLayer:
    def __init__(
        self,
        connection: GeoVCSConnection,
        path: str,
        name: str,
        geometry_column: str,
        key_column: str,
        ogr_layer_type,
    ):
        self.connection: GeoVCSConnection = connection
        self.path: str = path
        self.name: str = name
        self.geometry_column: str = geometry_column
        self.key_column: str = key_column

        self.layer_type: Qgis.BrowserLayerType = (
            self._ogr_geometry_type_to_qgis_browser_layer_type(ogr_layer_type)
        )

        self.provider_key: str = "ogr"

        self.uri = (
            f"MySQL:{self.connection.database}/{self.connection.branch},"
            f"host={self.connection.host},"
            f"port={self.connection.port},"
            f"user={self.connection.username}"
            # f"password={self.connection.password}"
        )

    def _ogr_geometry_type_to_qgis_browser_layer_type(
        self,
        ogr_geometry_type,
    ) -> Qgis.BrowserLayerType:
        if ogr_geometry_type in (
            ogr.wkbPoint,
            ogr.wkbPoint25D,
            ogr.wkbMultiPoint,
            ogr.wkbMultiPoint25D,
        ):
            return Qgis.BrowserLayerType.Point
        elif ogr_geometry_type in (
            ogr.wkbLineString,
            ogr.wkbLineString25D,
            ogr.wkbMultiLineString,
            ogr.wkbMultiLineString25D,
        ):
            return Qgis.BrowserLayerType.Line
        elif ogr_geometry_type in (
            ogr.wkbPolygon,
            ogr.wkbPolygon25D,
            ogr.wkbMultiPolygon,
            ogr.wkbMultiPolygon25D,
        ):
            return Qgis.BrowserLayerType.Polygon
        elif ogr_geometry_type == ogr.wkbNone:
            return Qgis.BrowserLayerType.Table
        else:
            return Qgis.BrowserLayerType.NoType


class GeoVCSSettings:
    @staticmethod
    def key_exists(key: str) -> bool:
        settings = QgsSettings()

        final_key = posixpath.join(SETTINGS_BASE_KEY, key)
        has_value = settings.contains(final_key)

        settings.beginGroup(final_key)
        child_keys = settings.childKeys()
        child_groups = settings.childGroups()
        settings.endGroup()

        has_groups = len(child_keys) > 0 or len(child_groups) > 0

        if has_value or has_groups:
            return True
        return False

    @staticmethod
    def remove(key: str):
        settings = QgsSettings()
        final_key = posixpath.join(SETTINGS_BASE_KEY, key)
        settings.remove(final_key)
        settings.sync()

    @staticmethod
    def write_object(key: str, obj):
        settings = QgsSettings()

        for attr_name, attr_value in asdict(obj).items():
            if attr_name.startswith("__") or callable(attr_value):
                continue
            final_key = posixpath.join(SETTINGS_BASE_KEY, key, attr_name)
            settings.setValue(final_key, attr_value)
        settings.sync()

    @staticmethod
    def read_object[T](base_key: str, obj_type: type[T]) -> T:
        settings = QgsSettings()
        settings.beginGroup(posixpath.join(SETTINGS_BASE_KEY, base_key))

        obj: dict[str, Any] = {}
        for key in settings.childKeys():
            value = settings.value(key)
            obj[key] = value
        settings.endGroup()

        return obj_type(**obj)

    @staticmethod
    def iterate_groups(key: str) -> Generator[str, Any, None]:
        base_key = posixpath.join(SETTINGS_BASE_KEY, key)

        settings = QgsSettings()
        settings.beginGroup(base_key)
        groups = settings.childGroups()

        for group in groups:
            yield group
        settings.endGroup()


class GeoVCSConnectionManagerMetaclass(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class GeoVCSConnectionManager(metaclass=GeoVCSConnectionManagerMetaclass):
    def __init__(self) -> None:
        self._connection: GeoVCSConnection | None = None
        if GeoVCSSettings.key_exists(SETTINGS_CONNECTION_KEY):
            self._connection = GeoVCSSettings.read_object(
                SETTINGS_CONNECTION_KEY,
                GeoVCSConnection,
            )

        if self._connection is not None and self._connection.password is not None:
            os.environ["MYSQL_PWD"] = self._connection.password

    def connect(self, connection: GeoVCSConnection):
        self._connection = connection
        if GeoVCSSettings.key_exists(SETTINGS_CONNECTION_KEY):
            iface.messageBar().pushMessage(  # type: ignore
                "GeoVCS - Connection Updated",
                f"Database connection '{self._connection.connection_string}' updated successfully.",
                Qgis.MessageLevel.Success,
            )
        else:
            iface.messageBar().pushMessage(  # type: ignore
                "GeoVCS - Connection Created",
                f"Database connection '{self._connection.connection_string}' created successfully.",
                Qgis.MessageLevel.Success,
            )
        GeoVCSSettings.write_object(SETTINGS_CONNECTION_KEY, self._connection)
        if self._connection.password is not None:
            os.environ["MYSQL_PWD"] = self._connection.password

    def disconnect(self):
        if self._connection:
            iface.messageBar().pushMessage(  # type: ignore
                "GeoVCS - Connection Removed",
                f"Database connection '{self._connection.connection_string}' disconnected successfully.",
                Qgis.MessageLevel.Success,
            )
            self._connection = None
            GeoVCSSettings.remove(SETTINGS_CONNECTION_KEY)
            os.environ.pop("MYSQL_PWD", None)

    def is_connected(self) -> bool:
        return self._connection is not None

    @property
    def connection(self) -> GeoVCSConnection | None:
        return self._connection
