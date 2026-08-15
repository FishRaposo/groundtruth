# Local backup and recovery

GroundTruth keeps cloud object storage and hosted backup scheduling out of the
default deployment. The repository includes explicit local PostgreSQL helpers
for operator-controlled backups and recovery drills.

Both commands are dry runs unless `--execute` is supplied. Restore additionally
requires `--confirm` because `pg_restore --clean --if-exists` replaces matching
database objects.

```text
python scripts/backup_postgres.py backups/groundtruth.dump --database-url postgresql://user:password@localhost/groundtruth
python scripts/backup_postgres.py backups/groundtruth.dump --database-url postgresql://user:password@localhost/groundtruth --execute

python scripts/restore_postgres.py backups/groundtruth.dump --database-url postgresql://user:password@localhost/groundtruth
python scripts/restore_postgres.py backups/groundtruth.dump --database-url postgresql://user:password@localhost/groundtruth --execute --confirm
```

The helpers pass credentials directly to PostgreSQL's command-line tools and do
not write them into artifacts. Prefer `DATABASE_URL` in a protected local
environment over shell history. A recovery drill should restore into a disposable
database first, run `alembic current`, and exercise health, document, query,
workflow-history, and version-history reads before replacing a live database.

SQLite remains the credential-free demo/test mode; copying its database file
while the application is stopped is sufficient for a local snapshot.
