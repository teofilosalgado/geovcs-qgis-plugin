from string import Template

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
