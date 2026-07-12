# Future Azure deployment

The local MVP does not provision Azure resources. A later deployment can run the
same image on Azure Container Apps or App Service for Containers and use Azure
Database for PostgreSQL Flexible Server.

Recommended production shape:

1. Build the `src/app/Dockerfile` image in CI and push it to Azure Container Registry.
2. Provision PostgreSQL Flexible Server with TLS required, private networking when
   available, backups, and a dedicated least-privilege application role.
3. Configure `DATABASE_URL`, `API_KEY`, `DEFAULT_TIMEZONE`, and
   `USER_DISPLAY_NAME` as application secrets/settings. Store the API key and
   database credential in Key Vault rather than source control.
4. Run `alembic upgrade head` as a release job before shifting traffic. Avoid
   multiple application replicas racing to migrate.
5. Map the platform health probe to `/healthz`, enforce HTTPS, restrict ingress to
   the polling agent where possible, and enable application/database logs.
6. Test task creation, recurrence across a DST boundary, idempotent completion,
   and both export formats before treating the deployment as authoritative.

For a first cloud release, retain one API replica unless completion concurrency has
been load-tested. PostgreSQL row locks already protect task completion updates, but
operational migration and secret-rotation procedures should be established first.

