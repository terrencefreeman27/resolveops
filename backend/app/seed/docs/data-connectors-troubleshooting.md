# Troubleshooting Data Connectors

## Error codes

| Code | Meaning | First steps |
|---|---|---|
| NS-CONN-401 | Credentials rejected | Re-enter credentials in **Data → Connectors**. |
| NS-CONN-429 | Source rate limit | Reduce sync frequency; syncs resume automatically. |
| NS-CONN-504 | Source warehouse timed out | Confirm the warehouse is running, raise its query timeout to at least 300 seconds, then run a manual sync. |

## When to escalate a connector failure

Escalate to **Engineering — Data Connectors** when a connector keeps failing after the first steps
for its error code have been completed, or when it has failed for more than 2 hours on a Business or
Enterprise account. Include the connector name, error code, time of first failure, and the steps
already tried.

## Stale dashboards

Dashboards built on a failing connector show the last successful sync time in the header. They
refresh automatically after the next successful sync.
