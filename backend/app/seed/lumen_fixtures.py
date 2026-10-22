"""Lumen Ledger — simulated-AI fixtures for demo mode (pure data, loaded into sim_fixtures).

The first two scenarios use *the same wording* as Northstar's; the answers differ because the tool
results and the retrieved documents differ. The conflict and insufficient-evidence fixtures draft a
confident "resolve" on purpose: they stand in for an over-confident model, and the server's evidence
check (app/evidence.py) — ordinary code — turns them into escalations.
"""
GREETING = "Hi {first_name},\n\n"
SIGN = "\n\nBest regards,\n{signature}"

FIXTURES = {
    "access_reporting_after_upgrade": {
        "classification": {
            "category": "access", "priority": "normal",
            "justification": "Users can't open a feature after a plan change; access question, not an outage.",
            "summary": "After yesterday's upgrade, two employees still can't open reporting; signing out didn't help.",
            "search_queries": ["users cannot access reporting after plan upgrade",
                               "which plan includes Insights reporting",
                               "roles that can see Insights reporting"]},
        "synthesis": {"variants": [
            {"when": {"plan_lacks_feature": "reporting"}, "next_action": "resolve",
             "reply": GREETING + "Thanks for the details. Signing out won't change this, because it isn't a sign-in "
                      "or permission problem.\n\nYour workspace moved from {previous_plan} to {plan} "
                      "{plan_change_when}. {plan} adds recurring billing and multi-currency invoices, but Insights "
                      "reporting is only included on the Scale plan — so nobody on your account can open reports yet, "
                      "whatever their role.\n\nIf you need reporting, an Owner on your account ({admins}) can move to "
                      "Scale in Settings → Subscription. Insights then turns on immediately for Owners and Finance "
                      "Managers; Clerks don't see Insights on any plan, so anyone who needs reports should be a Finance "
                      "Manager (Team → Members)." + SIGN,
             "citations": [
                 ["plans-and-pricing", "Features by plan", "Insights reporting is only on Scale; Growth does not include it."],
                 ["plans-and-pricing", "Upgrading to get Insights",
                  "Only an Owner changes the plan in Settings → Subscription; Insights turns on immediately."],
                 ["team-roles", "Roles after a plan change", "Clerks never see Insights; Owners and Finance Managers do on Scale."]],
             "ticket_action": {"type": "none"}},
            {"next_action": "resolve",
             "reply": GREETING + "Your workspace is on {plan}, which includes Insights reporting for Owners and Finance "
                      "Managers. Members with the Clerk role ({users_with_role[Clerk]}) can't see Insights on any "
                      "plan. An Owner ({admins}) can change them to Finance Manager in Team → Members; it applies on "
                      "their next page load." + SIGN,
             "citations": [
                 ["team-roles", "Roles after a plan change", "Clerks never see Insights."],
                 ["team-roles", "Changing a member's role", "Owners change roles in Team → Members."]],
             "ticket_action": {"type": "none"}},
        ]},
    },
    "billing_charged_twice": {
        "classification": {
            "category": "billing", "priority": "normal",
            "justification": "Billing explanation; no outage or security impact.",
            "summary": "Customer sees two charges this month and wants them explained.",
            "search_queries": ["charged twice two charges in one month", "upgrade invoice charged in full credit"]},
        "synthesis": {"variants": [
            {"next_action": "resolve",
             "reply": GREETING + "Thanks for asking. Both charges match invoices on your account:\n{invoice_lines}\n\n"
                      "This is expected after a mid-period upgrade. Lumen Ledger doesn't prorate upgrades: when you "
                      "moved from {previous_plan} to {plan} {plan_change_when}, the full monthly price of {plan} was "
                      "charged on a separate upgrade invoice, and your renewal date stays the same. The unused part of "
                      "your {previous_plan} period comes back as an account credit on your next invoice — it isn't "
                      "refunded to your card.\n\nIf a charge on your statement doesn't match one of these invoices, "
                      "reply with its date and amount and we'll look into it." + SIGN,
             "citations": [
                 ["billing-and-charges", "Upgrades are charged in full",
                  "No proration: full upgrade charge; unused time credited on the next invoice."],
                 ["billing-and-charges", "Two charges in one month",
                  "Renewal plus upgrade invoice is expected after a mid-period upgrade."]],
             "ticket_action": {"type": "none"}},
        ]},
    },
    "downgrade_timing_conflict": {
        "classification": {
            "category": "billing", "priority": "normal",
            "justification": "Plan-change timing question; no outage.",
            "summary": "Annual Scale customer asks whether a downgrade to Growth lowers the price immediately or at renewal.",
            "search_queries": ["when does a downgrade take effect", "downgrade in the middle of an annual term credit"]},
        "synthesis": {"variants": [
            {"next_action": "resolve",
             "reply": GREETING + "A downgrade from {plan} to Growth takes effect at the end of your current annual "
                      "term, so the lower price starts at your renewal date." + SIGN,
             "citations": [["plan-changes", "Downgrades", "Downgrades take effect at the end of the term."]],
             "ticket_action": {"type": "none"}},
        ]},
    },
    "peppol_einvoicing": {
        "classification": {
            "category": "product_issue", "priority": "normal",
            "justification": "Feature availability question; no outage.",
            "summary": "Customer asks whether invoices can be sent over the Peppol e-invoicing network.",
            "search_queries": ["Peppol e-invoicing network support", "send invoices to Belgian customers electronically"]},
        "synthesis": {"variants": [
            {"next_action": "resolve",
             "reply": GREETING + "Yes — you can send invoices to your Belgian customers from Lumen Ledger." + SIGN,
             "citations": [], "ticket_action": {"type": "none"}},
        ]},
    },
    "refund_unused_seats": {
        "classification": {
            "category": "billing", "priority": "normal", "justification": "Refund request; billing.",
            "summary": "Customer asks for a refund for 2 unused seats on an annual plan.",
            "search_queries": ["refund request policy", "credits not card refunds"]},
        "synthesis": {"variants": [
            {"next_action": "escalate",
             "reply": GREETING + "Thanks for asking. Lumen Ledger doesn't refund charges to a card; approved "
                      "corrections are applied as account credit. Requests like yours are decided by our Accounts "
                      "Receivable team, so we've passed it to them with your account details. They'll reply within 3 "
                      "business days." + SIGN,
             "citations": [
                 ["refunds-and-credits", "Credits, not card refunds", "No card refunds; credits on the next invoice."],
                 ["refunds-and-credits", "Exceptions are decided by Accounts Receivable", "Only AR decides refunds."]],
             "ticket_action": {
                 "type": "create_ticket", "subject": "Refund request — {company}",
                 "body": "{account_ref}: {plan} {billing_cycle}, {seats_used}/{seats_purchased} seats used. "
                         "Customer requests refund for unused seats.",
                 "priority": "high", "group": "Accounts Receivable", "status": "open"},
             "escalation_reason": "Refunds and credit exceptions are decided by Accounts Receivable."},
        ]},
    },
}
