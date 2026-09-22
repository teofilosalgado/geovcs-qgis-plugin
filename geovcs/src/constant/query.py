from string import Template

# sql
SELECT__VERSION = """
    SELECT dolt_version() AS dolt_version, VERSION() AS mysql_version
"""

# sql
SELECT__DOLT_BRANCHES = """
    SELECT
        name,
        hash,
        latest_author,
        latest_author_date,
        dirty
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

CALL__DOLT_COMMIT_HASH_OUT = Template(
    # sql
    """
    CALL DOLT_COMMIT_HASH_OUT (@hash, '-A', '-m', '$message')
"""
)

# sql
SELECT__HASH = """
    SELECT @hash
"""

CALL__DOLT_CREATE_BRANCH = Template(
    # sql
    """
    CALL DOLT_BRANCH('$branch')
"""
)

CALL__DOLT_DELETE_BRANCH = Template(
    # sql
    """
    CALL DOLT_BRANCH('-D', '$branch')
"""
)


CALL__DOLT_CHECKOUT = Template(
    # sql
    """
    CALL DOLT_CHECKOUT('$branch')
"""
)

# sql
DISABLE__AUTOCOMMIT = """
    SET autocommit = 0
"""

# sql
ENABLE__AUTOCOMMIT = """
    SET autocommit = 1
"""

# sql
COMMIT = """
    COMMIT
"""

CALL__DOLT_MERGE = Template(
    # sql
    """
    CALL DOLT_MERGE('$branch')
"""
)

# sql
SELECT__DOLT_CONFLICTS_TABLES = """
    SELECT
        table_name
    FROM
        dolt_conflicts
    ORDER BY
        table_name ASC
"""

CALL__DOLT_CONFLICTS_RESOLVE = Template(
    # sql
    """
    CALL DOLT_CONFLICTS_RESOLVE('$strategy', '$table_name')
"""
)

# sql
CALL__DOLT_MERGE_ABORT = """
    CALL DOLT_MERGE('--abort')
"""

# sql
CALL__DOLT_RESET_HARD = """
    CALL DOLT_RESET('--hard')
"""

SELECT__DOLT_LOG_BRANCH = Template(
    # sql
    """
    SELECT
        commit_hash,
        committer,
        email,
        date,
        message
    FROM
        dolt_log('$branch')
    ORDER BY
        date DESC
"""
)

SELECT__DOLT_LOG_DELTA = Template(
    # sql
    """
    SELECT
        commit_hash,
        committer,
        email,
        date,
        message
    FROM
        dolt_log('$source_branch..$target_branch')
    ORDER BY
        date DESC
"""
)

SELECT__DOLT_DIFF_STAT = Template(
    # sql
    """
    SELECT
        table_name
    FROM
        DOLT_DIFF_STAT('$commit~', '$commit')
"""
)

SELECT__DOLT_DIFF = Template(
    # sql
    """
    SELECT
        *
    FROM
        DOLT_DIFF('$commit~', '$commit', '$table_name')
"""
)
