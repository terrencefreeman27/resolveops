# Known Issues

## KI-2031: Snowflake syncs time out with NS-CONN-504

Status: under investigation by Engineering. Some Snowflake connectors fail with NS-CONN-504 even
when the warehouse is running and the query timeout is correct. There is no customer-side
workaround. Escalate affected accounts to Engineering — Data Connectors and reference KI-2031 in the
ticket so they are linked.

## KI-1987: Scheduled reports skip one run after daylight-saving changes

Status: fix scheduled. Affected schedules resume on the following run. No action needed.
