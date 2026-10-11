"""PostgreSQL advisory lock that serialises `alembic upgrade` across processes.

Backend and worker both run migrations on start; whichever arrives second waits for the
first transaction to commit and then finds nothing left to do.
"""

# Arbitrary, fixed 64-bit key: any process migrating this database must use the same one.
MIGRATION_LOCK_ID = 0x5146_6D69_6772_6174  # "QFmigrat"
