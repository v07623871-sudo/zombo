# ZOMBO production backups

The **zombo-backup** service is a separate Railway cron worker built from
`ops/backup/Dockerfile` (PostgreSQL 18 client + Python + boto3). It is not a
public HTTP service and must not share the game's webhook or domain.

Configure a private S3-compatible bucket (Railway Bucket works). Add the following
service variables as **Railway secret/reference variables**, not as literals in Git:

- `DATABASE_URL=${{Postgres.DATABASE_URL}}`
- `S3_ENDPOINT=${{<YOUR-BUCKET-NAME>.ENDPOINT}}`
- `S3_BUCKET=${{<YOUR-BUCKET-NAME>.BUCKET}}`
- `S3_REGION=${{<YOUR-BUCKET-NAME>.REGION}}`
- `S3_ACCESS_KEY_ID=${{<YOUR-BUCKET-NAME>.ACCESS_KEY_ID}}`
- `S3_SECRET_ACCESS_KEY=${{<YOUR-BUCKET-NAME>.SECRET_ACCESS_KEY}}`
- `BACKUP_RETENTION_DAYS=30`
- `S3_ADDRESSING_STYLE=virtual` (Railway buckets; use `path` for path-style S3)

Set the service root directory to `/ops/backup`, Dockerfile to `Dockerfile`, and cron schedule to
`0 3 * * *` (daily at 03:00 UTC), restart policy NEVER, and no HTTP healthcheck.

The job runs `pg_dump -Fc`, validates with `pg_restore --list`, uploads to the
private bucket and checks object size. It exits nonzero on errors, so configure
Railway deployment-failure notifications. Backups use the `zombo-postgres/`
prefix, with 30-day retention by default. **No backups are created by just
adding this code; the Railway cron service and private bucket are required.**

## Restore drill (must be tested before relying on backups)

1. Download a `.dump` from the backup bucket to a trusted machine.
2. Provision a **separate empty** PostgreSQL database; do not run this against
   production. Use a version compatible with the dump (Postgres 18 recommended).
3. Run `pg_restore --list backup.dump` and then
   `pg_restore --exit-on-error --no-owner --no-acl --dbname "$RESTORE_TEST_URL" backup.dump`.
4. Verify the player count, `payment_reviews`, `star_invoices`, and one test
   character and inventory in the restored database. Never send the file to Git.
5. Log the date, result, and new DB version. If any check fails, investigate
   instead of declaring production protected.

Railway production services should keep `DEMO_MODE=0`. Protect S3 access keys
like payment secrets. Bucket creation, storage and cron executions may incur cost.

### Verified existing Railway deployment — 2026-10-11

A 70 872-byte production dump was successfully uploaded to a private bucket and **restored** into a separate disposable PostgreSQL 18 database; `players`, `star_invoices` and `payment_reviews` were queryable (six players at test time). The temporary database and runner were deleted. Service `zombo-backup` remains scheduled daily at 03:00 UTC; check its Railway deploy logs for successful subsequent runs.
