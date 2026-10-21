# Troubleshooting Reporting

## User cannot see or open Reporting

Check, in order:

1. **Plan** — Reporting requires Pro, Business, or Enterprise. Starter accounts do not have it.
2. **Role** — the user needs the Admin or Analyst role. Viewers cannot open Reporting on any plan.
3. **Recent upgrade** — after a Starter → Pro upgrade, existing users keep the Viewer role. An Admin
   must change them to Analyst in **Settings → Users & Roles**.

Signing out or clearing the cache does not fix a missing permission. Do not suggest it as the fix
when the user's role is Viewer.

## Scheduled report did not arrive

Confirm the schedule's recipient list and time zone in **Reporting → Schedules**. Reports larger
than 25 MB are delivered as a download link instead of an attachment.

## Export fails

PDF exports time out for reports over 200 pages; use CSV export instead.
