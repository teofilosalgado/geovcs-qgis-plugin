import os
import posixpath
from collections.abc import Generator
from dataclasses import asdict, dataclass, fields, is_dataclass
from enum import StrEnum
from functools import cached_property
from typing import Any, ClassVar

from osgeo import gdal, ogr
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


def _escape_sql_literal(value: Any) -> str:
    """Escape a value that will be embedded in a single-quoted SQL literal.

    OGR does not expose bind parameters through ``ExecuteSQL`` for the MySQL
    driver, so every value interpolated into a Dolt procedure call must be
    escaped. Backslashes are significant in MySQL and single quotes can be
    escaped either as ``\\'`` or ``''``.
    """
    return str(value).replace("\\", "\\\\").replace("'", "''")


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
    objectid: Any
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
    message: str | None = None


@dataclass
class GeoVCSConnection:
    host: str = ""
    port: str = ""
    database: str = ""
    branch: str = ""
    auth_config_id: str = ""

    # These two values depend on ``branch``, which is updated by
    # ``GeoVCSConnectionManager.checkout``. Caching them would make checkout
    # reconnect to the old branch (a particularly subtle bug).
    @property
    def connection_string(self) -> str:
        value = (
            f"MySQL:{self.database}/{self.branch},"
            f"host={self.host},"
            f"port={self.port}"
        )
        if self.auth_config_id:
            value += f" authcfg='{self.auth_config_id}'"
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

    @property
    def ogr_connection_string(self) -> str | None:
        if not self.username or not self.password:
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
        datasource = None
        result = None

        if not self.ogr_connection_string:
            return GeoVCSConnectionTestResult(
                False, None, None, "Credentials are missing or invalid."
            )

        try:
            gdal.ErrorReset()
            datasource = ogr.Open(self.ogr_connection_string)
            if datasource is None:
                message = gdal.GetLastErrorMsg() or "Unable to open the datasource."
                return GeoVCSConnectionTestResult(False, None, None, message.strip())

            result = datasource.ExecuteSQL(query.SELECT__VERSION)
            if result is None:
                message = gdal.GetLastErrorMsg() or "Unable to query the server version."
                return GeoVCSConnectionTestResult(False, None, None, message.strip())

            dolt_version: str | None = ""
            mysql_version: str | None = ""
            for feature in result:
                dolt_version = feature.GetFieldAsString("dolt_version")
                mysql_version = feature.GetFieldAsString("mysql_version")
            return GeoVCSConnectionTestResult(True, dolt_version, mysql_version)
        except Exception as exception:  # noqa: BLE001 - surfaced to the user
            return GeoVCSConnectionTestResult(
                False, None, None, f"{type(exception).__name__}: {exception}"
            )
        finally:
            if datasource is not None:
                try:
                    if result is not None:
                        datasource.ReleaseResultSet(result)
                finally:
                    datasource.Close()


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

        manager = GeoVCSConnectionManager()
        if manager.is_connected:
            # Keep the password out of the layer URI. QGIS resolves the
            # credentials through the stored auth configuration instead. QGIS
            # expects this suffix in the form `` authcfg='<id>'``.
            auth_param = (
                f" authcfg='{manager.auth_config_id}'"
                if manager.auth_config_id
                else ""
            )
            self.uri = (
                f"MySQL:{manager.database}/{manager.branch},"
                f"host={manager.host},"
                f"port={manager.port},"
                f"user={manager.username or ''},"
                f"tables={self.name}"
                f"{auth_param}"
            )
        else:
            self.uri = ""

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


@dataclass
class GeoVCSLayerInfo:
    """Plain snapshot of an OGR layer.

    The OGR ``Layer`` objects are owned by their dataset. Exposing them beyond
    the connection manager makes it far too easy to keep stale references and
    database locks alive. The browser only needs these four values, so a plain
    snapshot is both safer and cheaper to hold.
    """

    name: str
    geometry_column: str
    key_column: str
    geometry_type: int


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
        try:
            for key in settings.childKeys():
                obj[key] = settings.value(key)
        finally:
            settings.endGroup()

        # Ignore values written by older plugin versions instead of letting a
        # single stale key prevent the plugin from starting.
        if is_dataclass(obj_type):
            valid_names = {field.name for field in fields(obj_type)}
            obj = {key: value for key, value in obj.items() if key in valid_names}

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
        self._merge_in_progress: bool = False

    def restore(self) -> bool:
        """(Re)connect from the persisted settings, if any."""
        if self._is_connected:
            return True
        if not GeoVCSSettings.key_exists(SETTINGS_CONNECTION_KEY):
            return False

        try:
            connection = GeoVCSSettings.read_object(
                SETTINGS_CONNECTION_KEY,
                GeoVCSConnection,
            )
            self.connect(connection)
            return True
        except Exception as e:  # noqa: BLE001 - never break QGIS startup
            QgsMessageLog.logMessage(
                f"Failed to restore the GeoVCS connection: {e}",
                "GeoVCS",
                Qgis.MessageLevel.Critical,
            )
            try:
                iface.messageBar().pushMessage(
                    "GeoVCS - Connection Failed",
                    f"Failed to restore the database connection: {e}",
                    Qgis.MessageLevel.Critical,
                )
            except Exception:  # noqa: BLE001 - iface may not be ready
                pass
            return False

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def merge_in_progress(self) -> bool:
        return self._merge_in_progress

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
        if self._datasource is None:
            raise RuntimeError("No active GeoVCS database connection.")
        return self._datasource

    def _get_connection(self) -> GeoVCSConnection:
        if self._connection is None:
            raise RuntimeError("No active GeoVCS database connection.")
        return self._connection

    @staticmethod
    def _execute_on_datasource(datasource: gdal.Dataset, sql: str):
        """Execute *sql*, releasing any result set and reporting GDAL errors."""
        gdal.ErrorReset()
        result = datasource.ExecuteSQL(sql)
        error_message = gdal.GetLastErrorMsg()
        if result is None and error_message:
            raise RuntimeError(error_message.strip())
        if result is not None:
            datasource.ReleaseResultSet(result)
        return None

    def _execute(self, sql: str) -> None:
        self._execute_on_datasource(self._get_datasource(), sql)

    def _query(self, sql: str):
        """Execute a query and return its result layer.

        The caller is responsible for releasing the result set.
        """
        datasource = self._get_datasource()
        gdal.ErrorReset()
        result = datasource.ExecuteSQL(sql)
        error_message = gdal.GetLastErrorMsg()
        if result is None:
            if error_message:
                raise RuntimeError(error_message.strip())
            raise RuntimeError("The database returned no result for the query.")
        return result

    def _release(self, result) -> None:
        if result is not None:
            self._get_datasource().ReleaseResultSet(result)

    def _close_datasource(self) -> None:
        datasource = self._datasource
        self._datasource = None
        if datasource is not None:
            try:
                datasource.Close()
            except Exception:  # noqa: BLE001 - closing must never fail the UI
                pass

    def _open_datasource(self, connection: GeoVCSConnection) -> gdal.Dataset:
        if not connection.ogr_connection_string:
            raise RuntimeError("Credentials are missing or invalid.")

        gdal.ErrorReset()
        datasource = ogr.Open(connection.ogr_connection_string, 1)
        if datasource is None:
            message = gdal.GetLastErrorMsg() or "Unable to open the datasource."
            raise RuntimeError(message.strip())
        return datasource

    def _set_autocommit(self, enabled: bool) -> None:
        sql = query.ENABLE__AUTOCOMMIT if enabled else query.DISABLE__AUTOCOMMIT
        self._execute(sql)

    def connect(self, connection: GeoVCSConnection):
        # Validate before touching the currently opened datasource.
        test = connection.test()
        if not test.status:
            raise RuntimeError(
                test.message
                or f"Failed to establish connection to database {connection.connection_string}"
            )

        datasource = self._open_datasource(connection)
        try:
            # A fresh OGR connection may not have the requested branch active
            # even though it is part of the connection string.
            self._execute_on_datasource(
                datasource,
                query.CALL__DOLT_CHECKOUT.substitute(
                    branch=_escape_sql_literal(connection.branch)
                ),
            )
        except Exception:
            datasource.Close()
            raise

        # Everything succeeded: persist the settings and swap connections.
        GeoVCSSettings.write_object(SETTINGS_CONNECTION_KEY, connection)
        if connection.password:
            os.environ["MYSQL_PWD"] = connection.password

        self._close_datasource()
        self._connection = connection
        self._datasource = datasource
        self.mysql_version = test.mysql_version
        self.dolt_version = test.dolt_version
        self._is_connected = True
        self._merge_in_progress = False

    def disconnect(self):
        self._close_datasource()
        self._connection = None
        self._is_connected = False
        self._merge_in_progress = False
        self.dolt_version = None
        self.mysql_version = None
        GeoVCSSettings.remove(SETTINGS_CONNECTION_KEY)
        os.environ.pop("MYSQL_PWD", None)

    def close(self):
        """Release database resources without forgetting the saved settings."""
        self._close_datasource()
        self._connection = None
        self._is_connected = False
        self._merge_in_progress = False
        os.environ.pop("MYSQL_PWD", None)

    def get_logs(
        self, target_branch: str, source_branch: str | None = None
    ) -> Generator[GeoVCSLog, None, None]:
        sql = (
            query.SELECT__DOLT_LOG_BRANCH.substitute(
                branch=_escape_sql_literal(target_branch)
            )
            if not source_branch
            else query.SELECT__DOLT_LOG_DELTA.substitute(
                source_branch=_escape_sql_literal(target_branch),
                target_branch=_escape_sql_literal(source_branch),
            )
        )
        result = self._query(sql)
        try:
            for feature in result:
                yield GeoVCSLog(
                    commit_hash=feature.GetField("commit_hash"),
                    committer=feature.GetField("committer"),
                    date=feature.GetField("date"),
                    message=feature.GetField("message"),
                )
        finally:
            self._release(result)

    def get_branches(self) -> Generator[GeoVCSBranch, None, None]:
        result = self._query(query.SELECT__DOLT_BRANCHES)
        try:
            for feature in result:
                yield GeoVCSBranch(
                    name=feature.GetField("name"),
                    hash=feature.GetField("hash"),
                    latest_author=feature.GetField("latest_author"),
                    latest_author_date=feature.GetField("latest_author_date"),
                    dirty=bool(feature.GetField("dirty")),
                )
        finally:
            self._release(result)

    def get_layers(self) -> Generator[GeoVCSLayerInfo, None, None]:
        datasource = self._get_datasource()
        for index in range(datasource.GetLayerCount()):
            layer = datasource.GetLayer(index)
            if layer is None:
                continue
            yield GeoVCSLayerInfo(
                name=layer.GetName(),
                geometry_column=layer.GetGeometryColumn(),
                key_column=layer.GetFIDColumn(),
                geometry_type=layer.GetGeomType(),
            )

    def get_changes(self) -> Generator[GeoVCSChange, None, None]:
        result = self._query(query.SELECT__DOLT_STATUS)
        try:
            for feature in result:
                yield GeoVCSChange(
                    feature.GetFieldAsString("table_name"),
                    feature.GetFieldAsString("status"),
                )
        finally:
            self._release(result)

    def get_diffs(self, commit: str) -> Generator[GeoVCSDiff, None, None]:
        statistics_layer = self._query(
            query.SELECT__DOLT_DIFF_STAT.substitute(
                commit=_escape_sql_literal(commit)
            )
        )

        try:
            table_names = [
                feature.GetField("table_name")
                for feature in statistics_layer
                if feature.GetField("table_name")
            ]
        finally:
            self._release(statistics_layer)

        for table_name in table_names:
            try:
                diff_layer = self._query(
                    query.SELECT__DOLT_DIFF.substitute(
                        commit=_escape_sql_literal(commit),
                        table_name=_escape_sql_literal(table_name),
                    )
                )
            except RuntimeError as exception:
                QgsMessageLog.logMessage(
                    f"Unable to diff table '{table_name}' for commit '{commit}': {exception}",
                    "GeoVCS",
                    Qgis.MessageLevel.Warning,
                )
                continue

            try:
                layer_definition = diff_layer.GetLayerDefn()
                field_names = [
                    layer_definition.GetFieldDefn(index).GetName()
                    for index in range(layer_definition.GetFieldCount())
                ]

                # Identify base columns (removing to_ and from_ prefixes).
                base_field_names: set[str] = set()
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

                # The primary key is not necessarily called OBJECTID; locate it
                # from the generated from_/to_ columns instead of assuming.
                key_field_name = self._find_key_field(field_names)

                feature_deltas: list[GeoVCSDeltaFeature] = []
                for feature in diff_layer:
                    action_type = feature.GetField("diff_type")
                    try:
                        action = GeoVCSDeltaAction(action_type)
                    except ValueError:
                        QgsMessageLog.logMessage(
                            f"Ignoring unknown diff action '{action_type}' in table '{table_name}'",
                            "GeoVCS",
                            Qgis.MessageLevel.Warning,
                        )
                        continue

                    object_identifier = None
                    if key_field_name:
                        object_identifier = feature.GetField(f"to_{key_field_name}")
                        if object_identifier is None:
                            object_identifier = feature.GetField(
                                f"from_{key_field_name}"
                            )

                    attribute_deltas = []
                    for base_field_name in base_field_names:
                        previous_value = feature.GetField(f"from_{base_field_name}")
                        current_value = feature.GetField(f"to_{base_field_name}")

                        if previous_value == current_value:
                            continue
                        if base_field_name in ("commit_date", "objectid"):
                            continue

                        attribute_deltas.append(
                            GeoVCSDeltaAttribute(
                                name=base_field_name,
                                from_value=previous_value,
                                to_value=current_value,
                            )
                        )

                    feature_deltas.append(
                        GeoVCSDeltaFeature(
                            objectid=object_identifier,
                            action=action,
                            attribute_deltas=sorted(
                                attribute_deltas, key=lambda item: item.name
                            ),
                        )
                    )
            finally:
                self._release(diff_layer)

            yield GeoVCSDiff(
                table_name=table_name,
                feature_deltas=sorted(
                    feature_deltas,
                    key=self._object_id_sort_key,
                ),
            )

    @staticmethod
    def _object_id_sort_key(item: GeoVCSDeltaFeature):
        if item.objectid is None:
            return (1, 0, "")
        try:
            return (0, int(item.objectid), "")
        except (TypeError, ValueError):
            return (0, 1, str(item.objectid))

    @staticmethod
    def _find_key_field(field_names: list[str]) -> str | None:
        candidates: list[str] = []
        for field_name in field_names:
            if field_name.startswith("from_"):
                candidates.append(field_name.replace("from_", "", 1))
            elif field_name.startswith("to_"):
                candidates.append(field_name.replace("to_", "", 1))

        for candidate in candidates:
            if candidate.lower() in ("objectid", "fid", "id", "pk"):
                return candidate
        for candidate in candidates:
            if candidate.lower().endswith("objectid"):
                return candidate
        return None

    def add_all_and_commit(self, message: str) -> str:
        message = (message or "").strip()
        if not message:
            raise RuntimeError("A commit message is required.")

        self._execute(
            query.CALL__DOLT_COMMIT_HASH_OUT.substitute(
                message=_escape_sql_literal(message)
            )
        )

        result = self._query(query.SELECT__HASH)
        try:
            hash_value = None
            for feature in result:
                hash_value = feature.GetFieldAsString(0)
        finally:
            self._release(result)

        if not hash_value:
            raise RuntimeError("The server did not return a commit hash.")

        # A merge with conflicts leaves an open transaction. Once the merge is
        # committed the connection must return to autocommit mode. The commit
        # itself already succeeded, so a failure to change the session mode is
        # reported without turning the successful commit into an error.
        if self._merge_in_progress:
            self._merge_in_progress = False
            try:
                self._set_autocommit(True)
            except Exception as exception:  # noqa: BLE001 - commit already succeeded
                QgsMessageLog.logMessage(
                    f"Commit succeeded but autocommit could not be restored: {exception}",
                    "GeoVCS",
                    Qgis.MessageLevel.Warning,
                )

        return hash_value

    def create_branch(self, branch: str):
        branch = (branch or "").strip()
        if not branch:
            raise RuntimeError("A branch name is required.")
        self._execute(
            query.CALL__DOLT_CREATE_BRANCH.substitute(
                branch=_escape_sql_literal(branch)
            )
        )

    def delete_branch(self, branch: str):
        branch = (branch or "").strip()
        if not branch:
            raise RuntimeError("A branch name is required.")
        self._execute(
            query.CALL__DOLT_DELETE_BRANCH.substitute(
                branch=_escape_sql_literal(branch)
            )
        )

    def checkout(self, branch: str):
        branch = (branch or "").strip()
        if not branch:
            raise RuntimeError("A branch name is required.")

        connection = self._get_connection()
        if branch == connection.branch:
            return

        previous_branch = connection.branch
        connection.branch = branch

        # Open the new branch in a fresh datasource and only swap it in after
        # the checkout has succeeded. This keeps the existing session usable if
        # the branch does not exist or the server is unavailable.
        datasource = None
        try:
            datasource = self._open_datasource(connection)
            self._execute_on_datasource(
                datasource,
                query.CALL__DOLT_CHECKOUT.substitute(
                    branch=_escape_sql_literal(branch)
                ),
            )
        except Exception:
            connection.branch = previous_branch
            if datasource is not None:
                datasource.Close()
            raise

        self._close_datasource()
        self._datasource = datasource
        self._is_connected = True
        self._merge_in_progress = False
        GeoVCSSettings.write_object(SETTINGS_CONNECTION_KEY, connection)

    def merge(
        self,
        source_branch: str,
    ) -> GeoVCSMergeResult:
        source_branch = (source_branch or "").strip()
        if not source_branch:
            raise RuntimeError("A source branch is required.")

        # Dolt requires autocommit to be disabled while a conflicted merge is
        # resolved. Re-enable it only after the merge is committed or aborted.
        self._set_autocommit(False)
        merge_result = None

        try:
            result = self._query(
                query.CALL__DOLT_MERGE.substitute(
                    branch=_escape_sql_literal(source_branch)
                )
            )
            try:
                feature = next(iter(result), None)
                if feature is None:
                    raise RuntimeError("The server did not return a merge status.")
                merge_result = GeoVCSMergeResult(
                    feature.GetFieldAsString("hash"),
                    feature.GetFieldAsInteger("conflicts"),
                    feature.GetFieldAsString("message"),
                )
            finally:
                self._release(result)

            if merge_result.conflicts:
                self._merge_in_progress = True
            else:
                self._set_autocommit(True)
                self._merge_in_progress = False

            return merge_result
        except Exception:
            # Never leave the session in autocommit=0 after an unexpected
            # failure. If conflicts were already written, the dialog will abort
            # the merge explicitly.
            if not self._merge_in_progress:
                try:
                    self._set_autocommit(True)
                except Exception:  # noqa: BLE001 - preserve the original error
                    pass
            raise

    def get_conflict_tables(self) -> list[str]:
        result = self._query(query.SELECT__DOLT_CONFLICTS_TABLES)
        tables: list[str] = []
        try:
            for feature in result:
                tables.append(feature.GetFieldAsString("table_name"))
        finally:
            self._release(result)
        return tables

    def resolve_conflicts(self, strategy: str, table_name: str = "."):
        if strategy not in ("--ours", "--theirs"):
            raise RuntimeError(f"Unsupported conflict resolution strategy: {strategy}")

        # Dolt cannot resolve conflicts while autocommit is enabled.
        self._set_autocommit(False)
        self._merge_in_progress = True
        self._execute(
            query.CALL__DOLT_CONFLICTS_RESOLVE.substitute(
                strategy=_escape_sql_literal(strategy),
                table_name=_escape_sql_literal(table_name),
            )
        )

    def abort_merge(self):
        try:
            self._execute(query.CALL__DOLT_MERGE_ABORT)
        finally:
            self._merge_in_progress = False
            try:
                self._set_autocommit(True)
            except Exception as exception:  # noqa: BLE001 - best-effort cleanup
                QgsMessageLog.logMessage(
                    f"Unable to restore autocommit after aborting merge: {exception}",
                    "GeoVCS",
                    Qgis.MessageLevel.Warning,
                )
