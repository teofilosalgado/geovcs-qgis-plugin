from string import Template

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

CALL__DOLT_BRANCH = Template(
    # sql
    """
    CALL DOLT_BRANCH('$branch')
"""
)


CALL__DOLT_CHECKOUT = Template(
    # sql
    """
    CALL DOLT_CHECKOUT('$branch')
"""
)

SELECT__DOLT_LOG = Template(
    # sql
    """
    SELECT
        commit_hash,
        committer,
        email,
        date,
        message
    FROM dolt_log('$branch')
"""
)
