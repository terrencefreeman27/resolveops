"""Northstar Analytics — simulated-AI fixtures for demo mode (pure data, loaded into sim_fixtures).

Keyed by scenario key; the match text is the seeded request body (seed/northstar.py REQUESTS).
Templates are rendered by the generic engine in providers/simulated.py from tool results.
"""
GREETING = "Hi {first_name},\n\n"
SIGN = "\n\nBest regards,\n{signature}"

FIXTURES = {
    # --- scenario 1: access issue resolved with account facts + docs ---
    "access_reporting_after_upgrade": {
        "classification": {
            "category": "access", "priority": "normal",
            "justification": "Two users can't open a plan feature; access question, not an outage.",
            "summary": "After yesterday's upgrade, two employees still can't open Reporting; signing out didn't help.",
            "search_queries": ["users cannot access reporting after plan upgrade role permission",
                               "change user role to Analyst reporting permission",
                               "which plans include the reporting feature"]},
        "synthesis": {"variants": [
            {"when": {"plan_lacks_feature": "reporting"}, "next_action": "resolve",
             "reply": GREETING + "Your account is on the {plan} plan, which does not include Reporting. An Admin can "
                      "upgrade to Pro or higher in Settings → Billing." + SIGN,
             "citations": [["plans-and-features", "Features by plan", "Reporting requires Pro or higher."]],
             "ticket_action": {"type": "none"}},
            {"when": {"no_users_with_role": "Viewer"}, "next_action": "clarify",
             "reply": GREETING + "Everyone on your account already has a role that includes Reporting. Could you tell "
                      "us the names of the two employees and the exact message they see?" + SIGN,
             "citations": [["reporting-troubleshooting", "User cannot see", "Reporting checklist."]],
             "ticket_action": {"type": "none"},
             "missing_info": ["Which two users are affected", "The exact error they see"]},
            {"next_action": "resolve",
             "reply": GREETING + "Thanks for the details. This isn't a sign-in or browser problem, so signing out again "
                      "won't change it.\n\nYour account moved from {previous_plan} to {plan} {plan_change_when}, and "
                      "{plan} includes Reporting. However, a plan upgrade doesn't change anyone's existing role. Starter "
                      "only has Admin and Viewer roles, and {count_with_role[Viewer]} people on your account still have "
                      "the Viewer role ({users_with_role[Viewer]}). The Viewer role can't open Reporting on any plan."
                      "\n\nTo fix it, an Admin on your account ({admins}) can open Settings → Users & Roles, select each "
                      "of the two employees, and change their role to Analyst. The change applies on their next page "
                      "load — no sign-out needed — and it doesn't use an extra seat.\n\nIf anything still looks wrong "
                      "after the role change, reply with the two names and we'll check their accounts." + SIGN,
             "citations": [
                 ["roles-and-permissions", "Roles after a plan upgrade",
                  "Upgrades don't change existing roles; Starter users remain Viewers."],
                 ["roles-and-permissions", "Changing a user's role",
                  "An Admin changes roles in Settings → Users & Roles; effective on next page load; no extra seat."],
                 ["reporting-troubleshooting", "User cannot see",
                  "Reporting needs Pro+ and the Admin or Analyst role; signing out doesn't fix permissions."],
                 ["plans-and-features", "Features by plan", "Pro includes Reporting."]],
             "ticket_action": {
                 "type": "create_ticket", "subject": "Reporting access after {previous_plan} → {plan} upgrade",
                 "body": "{company} ({account_ref}) upgraded {previous_plan} → {plan} {plan_change_when}. "
                         "{count_with_role[Viewer]} users still have the Viewer role (no Reporting permission). "
                         "Draft reply explains that an Admin must change the two affected users to Analyst.",
                 "priority": "normal", "group": "Support Tier 1", "status": "pending_customer"}},
        ]},
    },
    # --- scenario 2: billing question that needs clarification ---
    "billing_charged_twice": {
        "classification": {
            "category": "billing", "priority": "normal",
            "justification": "Billing explanation; no outage or security impact.",
            "summary": "Customer sees two charges this month and wants them explained.",
            "search_queries": ["charged twice duplicate charge two invoices same month", "prorated seat add-on invoice"]},
        "synthesis": {"variants": [
            {"next_action": "clarify",
             "reply": GREETING + "Thanks for reaching out. Two charges in one month usually means two separate invoices, "
                      "so before we explain anything we want to be sure we're looking at the same charges you are.\n\n"
                      "Here are the invoices issued in your current billing period:\n{invoice_lines}\n\nCould you confirm "
                      "the date and amount of each charge on your statement? If they match the invoices above, they're "
                      "expected: a renewal plus a separate prorated invoice for seats added mid-period. If an amount "
                      "doesn't match, it may be a temporary card pre-authorization (these drop off within 7 days) — and "
                      "if it doesn't, we'll bring in our Billing team." + SIGN,
             "citations": [
                 ["billing-and-invoices", "Charges that look duplicated",
                  "Confirm invoice numbers and amounts first; two charges are usually renewal + proration/seat add-on."],
                 ["billing-and-invoices", "Invoice types", "Seat add-ons are invoiced separately and immediately."],
                 ["proration-and-plan-changes", "Seat additions", "Added seats are prorated for the remaining days."]],
             "ticket_action": {"type": "none"},
             "missing_info": ["Date and amount of each charge on the customer's statement",
                              "Which charge the customer considers unexpected"]},
        ]},
    },
    # --- scenario 3: product issue escalated into a ticket ---
    "connector_outage": {
        "classification": {
            "category": "product_issue", "priority": "high",
            "justification": "Production data connector down for hours; executive dashboards stale on an Enterprise account.",
            "summary": "Snowflake connector failing with NS-CONN-504 since early morning after first-step troubleshooting.",
            "search_queries": ["NS-CONN-504 Snowflake connector timeout", "when to escalate connector failure engineering",
                               "escalation priority production data outage Enterprise"]},
        "synthesis": {"variants": [
            {"next_action": "escalate",
             "reply": GREETING + "Thanks for the detailed report. We can see {failing_connector} on your account has been "
                      "failing with {failing_connector_error} — its last successful sync was about "
                      "{failing_connector_hours} hours ago. You've already completed the documented first steps for this "
                      "error (warehouse running, query timeout raised to 300 seconds, manual sync), and this matches a "
                      "known issue our Engineering team is investigating (KI-2031) for which there's no customer-side "
                      "workaround.\n\nWe've escalated this to our Data Connectors engineering team as high priority and "
                      "linked it to KI-2031. Your dashboards will refresh automatically after the next successful sync. "
                      "We'll update you as soon as Engineering responds." + SIGN,
             "citations": [
                 ["data-connectors-troubleshooting", "When to escalate",
                  "Escalate when a connector keeps failing after first steps or >2h on Business/Enterprise."],
                 ["data-connectors-troubleshooting", "Error codes", "NS-CONN-504 first steps."],
                 ["known-issues", "KI-2031", "Known Snowflake NS-CONN-504 timeouts; no workaround; reference KI-2031."],
                 ["escalation-policy", "Priority", "Production data outage on Enterprise is high priority."]],
             "ticket_action": {
                 "type": "create_ticket",
                 "subject": "{failing_connector} failing with {failing_connector_error} — {company} (KI-2031)",
                 "body": "Account {account_ref} ({company}). {failing_connector} failing with {failing_connector_error}, "
                         "last success ~{failing_connector_hours}h ago. Customer confirmed warehouse running, query "
                         "timeout 300s, two manual syncs. Executive dashboards stale. Likely KI-2031.",
                 "priority": "high", "group": "Engineering — Data Connectors", "status": "open"},
             "escalation_reason": "Connector still failing after documented first steps on an Enterprise account; "
                                  "matches KI-2031."},
        ]},
    },
    # --- extra seeded inbox items ---
    "refund_unused_seats": {
        "classification": {
            "category": "billing", "priority": "normal", "justification": "Refund request; billing, normal priority.",
            "summary": "Customer asks for a refund for 2 unused seats on an annual plan.",
            "search_queries": ["refund request policy", "remove seats reduce seat count"]},
        "synthesis": {"variants": [
            {"next_action": "escalate",
             "reply": GREETING + "Thanks for letting us know. Refund and credit requests are reviewed by our Billing team, "
                      "so we've passed yours to them with your account details. They'll reply within 2 business days."
                      "\n\nFor future renewals, an Admin can reduce your seat count in Settings → Billing → Seats; seat "
                      "reductions take effect at the next renewal." + SIGN,
             "citations": [
                 ["refund-policy", "Refunds are decided by humans", "Only Billing decides refunds."],
                 ["refund-policy", "How to handle", "Escalate to Billing; reply within 2 business days."],
                 ["seat-management", "Removing seats", "Seat reductions take effect at next renewal."]],
             "ticket_action": {
                 "type": "create_ticket", "subject": "Refund request — {company}",
                 "body": "{account_ref}: {plan} {billing_cycle}, {seats_used}/{seats_purchased} seats used. "
                         "Customer requests refund for unused seats.",
                 "priority": "normal", "group": "Billing", "status": "open"},
             "escalation_reason": "Refunds are human-only (refund policy)."},
        ]},
    },
    "injection_cross_customer": {
        "classification": {
            "category": "access", "priority": "normal",
            "justification": "Asks for Reporting access; contains instructions aimed at the assistant.",
            "summary": "Customer wants Reporting access and asks about another organization's account.",
            "mentioned_emails": ["ops@tidewater-cu.example"],
            "risk_flags": ["Message contains instructions aimed at the assistant (\"ignore all previous instructions\", "
                           "\"admin mode\", \"approve automatically\"); treated as customer text only.",
                           "Requests another organization's account details; not disclosed."],
            "search_queries": ["which plans include reporting", "who can change plan upgrade admin",
                               "change a user's role"]},
        "synthesis": {"variants": [
            {"next_action": "resolve",
             "reply": GREETING + "Your account is on the {plan} plan, which doesn't include Reporting — it's available on "
                      "Pro and above. An Admin on your account can upgrade in Settings → Billing, then give users the "
                      "Analyst role in Settings → Users & Roles. {signature} can't change plans or grant access on a "
                      "customer's behalf.\n\nWe also can't share any information about other organizations' accounts."
                      + SIGN,
             "citations": [
                 ["plans-and-features", "Features by plan", "Starter does not include Reporting."],
                 ["proration-and-plan-changes", "Who can change a plan", "Only an account Admin can change the plan."],
                 ["roles-and-permissions", "Changing a user's role", "Admins assign roles."]],
             "ticket_action": {"type": "none"}},
        ]},
    },
    "sso_enforce": {
        "classification": {
            "category": "access", "priority": "normal", "justification": "How-to question about SSO enforcement.",
            "summary": "Customer wants to require Okta SSO for all users.",
            "search_queries": ["enforce SAML SSO disable password sign-in"]},
        "synthesis": {"variants": [
            {"next_action": "resolve",
             "reply": GREETING + "Your Okta SSO connection is already configured. To require it for everyone, an Admin "
                      "can open Settings → Security → Single sign-on and turn on \"Enforce SSO\". After that, password "
                      "sign-in is disabled for everyone except one designated break-glass Admin." + SIGN,
             "citations": [["sso-and-access", "SAML SSO",
                            "Enforce SSO disables password sign-in except break-glass Admin."]],
             "ticket_action": {"type": "add_note", "ticket_match": "saml",
                               "body": "Customer asked how to enforce SSO; sent enforcement steps."}},
        ]},
    },
}
