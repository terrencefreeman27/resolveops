# Troubleshooting Dashboards

## Dashboard loads slowly

Dashboards with more than 30 tiles or tiles querying more than 50 million rows can take longer than
10 seconds. Split large dashboards or enable tile caching in **Dashboard → Settings → Cache**.

## Shared link shows "Access denied"

Shared links respect the viewer's role and account. External links require "Public sharing" to be
enabled by an Admin; it is off by default on all plans.

## Numbers differ from the source system

Dashboards show data as of the last successful connector sync (shown in the header). Check the
sync time before investigating calculation differences.
