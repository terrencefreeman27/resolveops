# Roles and Permissions

Every user in a Northstar account has exactly one role. Roles decide what a user can do; the plan
decides which roles and features exist.

## Role permissions

| Permission | Admin | Analyst | Viewer |
|---|---|---|---|
| View dashboards | Yes | Yes | Yes |
| Edit dashboards | Yes | Yes | No |
| Reporting (build, schedule, export reports) | Yes | Yes | No |
| Manage users and roles | Yes | No | No |
| Manage billing | Yes | No | No |

The Viewer role never includes Reporting, on any plan.

## Roles after a plan upgrade

Upgrading a plan does **not** change existing users' roles. Starter accounts only have Admin and
Viewer roles, so after an upgrade from Starter to Pro every non-admin user is still a Viewer and
cannot open Reporting until an Admin changes their role to Analyst.

Signing out, signing back in, or clearing the browser cache does not change a user's permissions.

## Changing a user's role

An Admin opens **Settings → Users & Roles**, selects the user, and chooses a new role. The change
takes effect on the user's next page load; the user does not need to sign out. Changing a role does
not consume an additional seat.

Northstar support cannot change roles or grant access on a customer's behalf; an account Admin must
make the change.
