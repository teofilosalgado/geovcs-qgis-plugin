import os
import posixpath
from collections.abc import Generator
from dataclasses import asdict, dataclass
from enum import StrEnum
from functools import cached_property
from typing import Any, ClassVar

from osgeo import gdal, ogr
from osgeo.ogr import Layer
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsAuthMethodConfig,
    QgsMessageLog,
    QgsSettings,
)
from qgis.utils import iface

from geovcs.src.constant import (
    SETTINGS_BASE_KEY,
    SETTINGS_CONNECTION_KEY,
    query,
)


class GeoVCSDeltaAction(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"


@dataclass
class GeoVCSDeltaAttribute:
    name: str
    from_value: Any
    to_value: Any


@dataclass
class GeoVCSDeltaFeature:
    objectid: int
    action: GeoVCSDeltaAction
    attribute_deltas: list[GeoVCSDeltaAttribute]


@dataclass
class GeoVCSDiff:
    table_name: str
    feature_deltas: list[GeoVCSDeltaFeature]


@dataclass
class GeoVCSConnectionTestResult:
    status: bool
    dolt_version: str | None = ""
    mysql_version: str | None = ""


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

    def test(self) -> GeoVCSConnectionTestResult:
        datasource = ogr.Open(self.ogr_connection_string)
        if datasource is None:
            return GeoVCSConnectionTestResult(False, None, None)

        result = datasource.ExecuteSQL(query.SELECT__VERSION)
        dolt_version: str | None = ""
        mysql_version: str | None = ""
        try:
            if result is not None:
                for feature in result:
                    dolt_version = feature.GetFieldAsString("dolt_version")
                    mysql_version = feature.GetFieldAsString("mysql_version")
        finally:
            if datasource and result:
                datasource.ReleaseResultSet(result)
            if datasource:
                datasource = None
        return GeoVCSConnectionTestResult(True, dolt_version, mysql_version)


class GeoVCSLayer:
    def __init__(
        self,
        path: str,
        name: str,
        geometry_column: str,
        key_column: str,
        ogr_layer_type,
    ):
        self.path: str = path
        self.name: str = name
        self.geometry_column: str = geometry_column
        self.key_column: str = key_column

        self.layer_type: Qgis.BrowserLayerType = (
            self._ogr_geometry_type_to_qgis_browser_layer_type(ogr_layer_type)
        )
        self.provider_key: str = "ogr"

        if GeoVCSConnectionManager().is_connected:
            self.uri = (
                f"MySQL:{GeoVCSConnectionManager().database}/{GeoVCSConnectionManager().branch},"
                f"host={GeoVCSConnectionManager().host},"
                f"port={GeoVCSConnectionManager().port},"
                f"user={GeoVCSConnectionManager().username},"
                f"tables={self.name}"
            )
        else:
            self.uri = None

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

        return bool(has_value or has_groups)

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

        yield from groups
        settings.endGroup()


class GeoVCSConnectionManagerMetaclass(type):
    _instances: ClassVar[dict[type[Any], Any]] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


@dataclass
class GeoVCSChange:
    table_name: str
    status: str


@dataclass
class GeoVCSMergeResult:
    hash: str | None
    conflicts: int | None
    message: str | None


@dataclass
class GeoVCSBranch:
    name: str
    hash: str
    latest_author: str
    latest_author_date: str
    dirty: bool


@dataclass
class GeoVCSLog:
    commit_hash: str
    committer: str
    date: str
    message: str


class GeoVCSConnectionManager(metaclass=GeoVCSConnectionManagerMetaclass):
    def __init__(self) -> None:
        self._connection: GeoVCSConnection | None = None
        self._datasource: gdal.Dataset | None = None
        self.dolt_version: str | None = None
        self.mysql_version: str | None = None

        self._is_connected: bool = False

        if GeoVCSSettings.key_exists(SETTINGS_CONNECTION_KEY):
            connection = GeoVCSSettings.read_object(
                SETTINGS_CONNECTION_KEY,
                GeoVCSConnection,
            )
            try:
                self.connect(connection)
            except RuntimeError as e:
                QgsMessageLog.logMessage(
                    f"Failed to establish connection to database '{connection.connection_string}': {e}",
                    "GeoVCS",
                    Qgis.MessageLevel.Critical,
                )
                iface.messageBar().pushMessage(
                    "GeoVCS - Connection Failed",
                    f"Failed to establish connection to database '{connection.connection_string}': {e}",
                    Qgis.MessageLevel.Critical,
                )

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def branch(self) -> str | None:
        if self._connection:
            return self._connection.branch
        return None

    @property
    def database(self) -> str | None:
        if self._connection:
            return self._connection.database
        return None

    @property
    def host(self) -> str | None:
        if self._connection:
            return self._connection.host
        return None

    @property
    def port(self) -> str | None:
        if self._connection:
            return self._connection.port
        return None

    @property
    def username(self) -> str | None:
        if self._connection:
            return self._connection.username
        return None

    @property
    def auth_config_id(self) -> str | None:
        if self._connection:
            return self._connection.auth_config_id
        return None

    def _get_datasource(self) -> gdal.Dataset:
        if not self._datasource:
            raise RuntimeError("No datasource provided")
        return self._datasource

    def _get_connection(self) -> GeoVCSConnection:
        if not self._connection:
            raise RuntimeError("No connection provided")
        return self._connection

    def connect(self, connection: GeoVCSConnection):
        # Configure connection
        test = connection.test()
        if not test.status:
            raise RuntimeError(
                f"Failed to establish connection to database {connection.connection_string}"
            )

        GeoVCSSettings.write_object(SETTINGS_CONNECTION_KEY, self._connection)
        if connection.password is not None:
            os.environ["MYSQL_PWD"] = connection.password

        # Configure datasource
        if not self._datasource:
            self._datasource = None

        datasource = ogr.Open(connection.ogr_connection_string, 1)
        if datasource is None:
            raise RuntimeError(
                f"Failed to create datasource for connection {connection.connection_string}"
            )
        result = datasource.ExecuteSQL(
            query.CALL__DOLT_CHECKOUT.substitute(branch=self.branch)
        )
        if datasource and result:
            datasource.ReleaseResultSet(result)

        # Initialize objects
        self._connection = connection
        self._datasource = datasource
        self.mysql_version = test.mysql_version
        self.dolt_version = test.dolt_version
        self._is_connected = True

    def disconnect(self):
        if self._connection:
            self._connection = None
            GeoVCSSettings.remove(SETTINGS_CONNECTION_KEY)
            os.environ.pop("MYSQL_PWD", None)

    def get_logs(
        self, target_branch: str, source_branch: str | None = None
    ) -> Generator[GeoVCSLog, None, None]:
        sql = (
            query.SELECT__DOLT_LOG_BRANCH.substitute(branch=target_branch)
            if not source_branch
            else query.SELECT__DOLT_LOG_DELTA.substitute(
                source_branch=target_branch, target_branch=source_branch
            )
        )
        result = self._get_datasource().ExecuteSQL(sql)
        try:
            if result is not None:
                for feature in result:
                    yield GeoVCSLog(
                        commit_hash=feature.GetField("commit_hash"),
                        committer=feature.GetField("committer"),
                        date=feature.GetField("date"),
                        message=feature.GetField("message"),
                    )
        finally:
            if result:
                self._get_datasource().ReleaseResultSet(result)

    def get_branches(self) -> Generator[GeoVCSBranch, None, None]:
        result = self._get_datasource().ExecuteSQL(query.SELECT__DOLT_BRANCHES)
        try:
            if result is not None:
                for feature in result:
                    yield GeoVCSBranch(
                        name=feature.GetField("name"),
                        hash=feature.GetField("hash"),
                        latest_author=feature.GetField("latest_author"),
                        latest_author_date=feature.GetField("latest_author_date"),
                        dirty=bool(feature.GetField("dirty")),
                    )
        finally:
            if result:
                self._get_datasource().ReleaseResultSet(result)

    def get_layers(self) -> Generator[Layer, None, None]:
        layer_count = self._get_datasource().GetLayerCount()
        for i in range(layer_count):
            yield self._get_datasource().GetLayer(i)

    def get_changes(self) -> Generator[GeoVCSChange, None, None]:
        result = self._get_datasource().ExecuteSQL(query.SELECT__DOLT_STATUS)
        try:
            if result is not None:
                for feature in result:
                    yield GeoVCSChange(
                        feature.GetFieldAsString("table_name"),
                        feature.GetFieldAsString("status"),
                    )
        finally:
            if result:
                self._get_datasource().ReleaseResultSet(result)

    def get_diffs(self, commit: str) -> Generator[GeoVCSDiff, None, None]:
        # Fetch statistics to discover which tables were modified
        statistics_layer = self._get_datasource().ExecuteSQL(
            query.SELECT__DOLT_DIFF_STAT.substitute(commit=commit)
        )

        if not statistics_layer:
            return

        # Extract table names and release the query result from memory
        table_names = [feature.GetField("table_name") for feature in statistics_layer]
        if statistics_layer:
            self._get_datasource().ReleaseResultSet(statistics_layer)

        for table_name in table_names:
            diff_layer = self._get_datasource().ExecuteSQL(
                query.SELECT__DOLT_DIFF.substitute(commit=commit, table_name=table_name)
            )
            if not diff_layer:
                continue

            # Map column definitions
            layer_definition = diff_layer.GetLayerDefn()
            field_names = [
                layer_definition.GetFieldDefn(index).GetName()
                for index in range(layer_definition.GetFieldCount())
            ]

            # Identify base columns (removing to_ and from_ prefixes)
            base_field_names = set()
            for field_name in field_names:
                if field_name.startswith("from_") and field_name not in (
                    "from_commit",
                    "from_data_length",
                ):
                    base_field_names.add(field_name.replace("from_", "", 1))
                elif field_name.startswith("to_") and field_name not in (
                    "to_commit",
                    "to_data_length",
                ):
                    base_field_names.add(field_name.replace("to_", "", 1))

            feature_deltas = []

            # Iterate over each modified feature (record)
            for feature in diff_layer:
                action_type = feature.GetField("diff_type")

                # Identify the OBJECTID handling additions or deletions
                object_identifier = feature.GetField("to_OBJECTID")
                if object_identifier is None:
                    object_identifier = feature.GetField("from_OBJECTID")

                attribute_deltas = []

                for base_field_name in base_field_names:
                    previous_value = feature.GetField(f"from_{base_field_name}")
                    current_value = feature.GetField(f"to_{base_field_name}")

                    # Filter columns that did not change
                    if previous_value == current_value:
                        continue
                    if base_field_name in ["commit_date", "objectid"]:
                        continue

                    attribute_delta = GeoVCSDeltaAttribute(
                        name=base_field_name,
                        from_value=previous_value,
                        to_value=current_value,
                    )
                    attribute_deltas.append(attribute_delta)

                # The feature is only added if the OBJECTID is valid and processed
                feature_delta = GeoVCSDeltaFeature(
                    objectid=object_identifier,
                    action=GeoVCSDeltaAction(action_type),
                    attribute_deltas=sorted(
                        attribute_deltas, key=lambda item: item.name
                    ),
                )
                feature_deltas.append(feature_delta)
            if diff_layer:
                self._get_datasource().ReleaseResultSet(diff_layer)

            # Yield one table at a time
            yield GeoVCSDiff(
                table_name=table_name,
                feature_deltas=sorted(feature_deltas, key=lambda item: item.objectid),
            )

    def add_all_and_commit(self, message: str) -> str | None:
        result = self._get_datasource().ExecuteSQL(
            query.CALL__DOLT_COMMIT_HASH_OUT.substitute(message=message)
        )
        if result:
            self._get_datasource().ReleaseResultSet(result)

        hash = None
        result = self._get_datasource().ExecuteSQL(query.SELECT__HASH)
        if result is not None:
            for feature in result:
                hash = feature.GetFieldAsString(0)
        if result:
            self._get_datasource().ReleaseResultSet(result)

        return hash

    def create_branch(self, branch: str):
        result = self._get_datasource().ExecuteSQL(
            query.CALL__DOLT_CREATE_BRANCH.substitute(branch=branch)
        )
        if result:
            self._get_datasource().ReleaseResultSet(result)

    def delete_branch(self, branch: str):
        result = self._get_datasource().ExecuteSQL(
            query.CALL__DOLT_DELETE_BRANCH.substitute(branch=branch)
        )
        if result:
            self._get_datasource().ReleaseResultSet(result)

    def checkout(self, branch: str):
        result = self._get_datasource().ExecuteSQL(
            query.CALL__DOLT_CHECKOUT.substitute(branch=branch)
        )
        if result:
            self._get_datasource().ReleaseResultSet(result)

        if not self._connection:
            pass
        self._get_connection().branch = branch
        self.connect(self._get_connection())

    def merge(
        self,
        source_branch: str,
    ) -> GeoVCSMergeResult | None:
        disable_autocommit = self._get_datasource().ExecuteSQL(
            query.DISABLE__AUTOCOMMIT
        )
        if disable_autocommit:
            self._get_datasource().ReleaseResultSet(disable_autocommit)

        merge = self._get_datasource().ExecuteSQL(
            query.CALL__DOLT_MERGE.substitute(branch=source_branch)
        )
        if merge:
            self._get_datasource().ReleaseResultSet(merge)
        return None

    def get_conflict_tables(self) -> list[str]:
        result = self._get_datasource().ExecuteSQL(query.SELECT__DOLT_CONFLICTS_TABLES)
        tables: list[str] = []
        try:
            if result is not None:
                for feature in result:
                    tables.append(feature.GetFieldAsString("table_name"))
        finally:
            if result:
                self._get_datasource().ReleaseResultSet(result)

        return tables

    def resolve_conflicts(self, strategy: str, table_name: str = "."):
        sql = query.CALL__DOLT_CONFLICTS_RESOLVE.substitute(
            strategy=strategy, table_name=table_name
        )
        result = self._get_datasource().ExecuteSQL(sql)
        if result:
            self._get_datasource().ReleaseResultSet(result)

    def abort_merge(self):
        result_abort = self._get_datasource().ExecuteSQL(query.CALL__DOLT_MERGE_ABORT)
        if result_abort:
            self._get_datasource().ReleaseResultSet(result_abort)

        result_reset = self._get_datasource().ExecuteSQL(query.CALL__DOLT_RESET_HARD)
        if result_reset:
            self._get_datasource().ReleaseResultSet(result_reset)
