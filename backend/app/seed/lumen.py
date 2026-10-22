"""Lumen Ledger seed data — a second fictional company (B2B invoicing SaaS). All people are synthetic.

Policies deliberately differ from Northstar Analytics:
- Plans are Essentials / Growth / Scale, and reporting ("Insights") is a *plan* feature only on Scale
  (Northstar: Reporting on Pro+, gated by user *role*).
- Upgrades are not prorated: the new plan is charged in full and unused time becomes account credit on
  the next invoice (Northstar: prorated invoices).
- Refunds/credits go to Accounts Receivable at high priority (Northstar: Billing, normal).
- Two current documents deliberately disagree on when a downgrade takes effect (plan-changes vs
  billing-faq) — the seeded conflicting-evidence case.

Facts here are kept consistent with the Markdown docs in ./docs/lumen.
"""
from .northstar import days_ago, now  # noqa: F401  (shared date helpers)

ROLE_PERMISSIONS = {
    "Owner": ["invoicing", "reporting", "manage_users", "manage_billing"],
    "Finance Manager": ["invoicing", "reporting"],
    "Clerk": ["invoicing"],
}
PLAN_FEATURES = {
    "Essentials": ["invoicing", "payment_reminders"],
    "Growth": ["invoicing", "payment_reminders", "recurring_billing", "multi_currency"],
    "Scale": ["invoicing", "payment_reminders", "recurring_billing", "multi_currency", "reporting", "api_access",
              "approval_workflows"],
}
PLAN_PRICE_CENTS = {"Essentials": 1200, "Growth": 2900, "Scale": 4900}
TICKET_GROUPS = ["Customer Care", "Billing Operations", "Accounts Receivable", "Platform Engineering",
                 "Trust & Security"]

WORKSPACE = {
    "slug": "lumen",
    "name": "Lumen Ledger",
    "profile": {
        "tagline": "B2B invoicing and accounts-receivable automation for small finance teams.",
        "industry": "B2B SaaS — invoicing",
        "support_hours": "Mon–Fri 09:00–17:00 GMT",
        "support_signature": "Lumen Ledger Customer Care",
        "fictional": True,
    },
    "settings": {
        "ticket_prefix": "LL",
        "ticket_adapter": "internal",
        "demo_enabled": True,
        "roles": ROLE_PERMISSIONS,
        "admin_roles": ["Owner"],
        "evidence_review_group": "Billing Operations",
        "ticket_groups": TICKET_GROUPS,
        "supported_categories": ["access", "billing", "product_issue"],
        "demo_scenarios": [
            {"key": "access_reporting_after_upgrade", "label": "Access issue",
             "description": "Same wording as Northstar: upgraded yesterday, two employees can't open reporting."},
            {"key": "billing_charged_twice", "label": "Billing question",
             "description": "Same wording as Northstar: \"charged twice this month\"."},
            {"key": "downgrade_timing_conflict", "label": "Conflicting docs",
             "description": "Two current documents disagree on when a downgrade takes effect → escalate."},
        ],
    },
}

# Each customer: subscription facts plus explicit invoices (Lumen's billing rules differ from Northstar's,
# so invoices are written out rather than computed).
CUSTOMERS = [
    {"ref": "LL-2048", "company": "Harbor & Finch Studio", "contact": "Nadia Brennan",
     "email": "nadia.brennan@harborfinch.example", "plan": "Growth", "status": "active", "cycle": "monthly",
     "seats": 8, "used": 6, "period_days_ago": 15, "period_len": 30, "previous_plan": "Essentials", "changed_days_ago": 1,
     "users": [("Nadia Brennan", "Owner"), ("Oskar Hale", "Finance Manager"), ("Tomas Reyes", "Clerk"),
               ("Wen Li", "Clerk")],
     "invoices": [("renewal", "Essentials renewal, 8 seats", 8 * 1200, 15, "paid"),
                  ("upgrade", "Upgrade to Growth, 8 seats, full month from upgrade date", 8 * 2900, 1, "paid")]},
    {"ref": "LL-2051", "company": "Pinecrest Dental Lab", "contact": "Arjun Malhotra",
     "email": "arjun.malhotra@pinecrestlab.example", "plan": "Growth", "status": "active", "cycle": "monthly",
     "seats": 12, "used": 11, "period_days_ago": 12, "period_len": 30, "previous_plan": "Essentials",
     "changed_days_ago": 6,
     "users": [("Arjun Malhotra", "Owner"), ("Lena Fischer", "Finance Manager"), ("Marco Bianchi", "Clerk")],
     "invoices": [("renewal", "Essentials renewal, 12 seats", 12 * 1200, 12, "paid"),
                  ("upgrade", "Upgrade to Growth, 12 seats, full month from upgrade date", 12 * 2900, 6, "paid")]},
    {"ref": "LL-2060", "company": "Northgate Supply Co", "contact": "Helena Varga",
     "email": "helena.varga@northgatesupply.example", "plan": "Scale", "status": "active", "cycle": "annual",
     "seats": 40, "used": 31, "period_days_ago": 200, "period_len": 365, "previous_plan": None, "changed_days_ago": None,
     "users": [("Helena Varga", "Owner"), ("Sean Doyle", "Finance Manager"), ("Ama Owusu", "Clerk")],
     "invoices": [("renewal", "Scale annual renewal, 40 seats", 40 * 4900 * 12, 200, "paid")]},
    {"ref": "LL-2072", "company": "Quarry Lane Bakery", "contact": "Felipe Duarte",
     "email": "felipe.duarte@quarrylane.example", "plan": "Essentials", "status": "active", "cycle": "monthly",
     "seats": 3, "used": 3, "period_days_ago": 9, "period_len": 30, "previous_plan": None, "changed_days_ago": None,
     "users": [("Felipe Duarte", "Owner"), ("Rosa Duarte", "Clerk")],
     "invoices": [("renewal", "Essentials renewal, 3 seats", 3 * 1200, 9, "paid")]},
    {"ref": "LL-2033", "company": "Brightwater Consulting", "contact": "Imogen Clarke",
     "email": "imogen.clarke@brightwater.example", "plan": "Scale", "status": "active", "cycle": "annual",
     "seats": 50, "used": 48, "period_days_ago": 70, "period_len": 365, "previous_plan": None, "changed_days_ago": None,
     "users": [("Imogen Clarke", "Owner"), ("Dev Anand", "Finance Manager")],
     "invoices": [("renewal", "Scale annual renewal, 50 seats", 50 * 4900 * 12, 70, "paid")]},
]

ESCALATION_RULES = [
    {"key": "refunds-to-accounts-receivable", "name": "Refunds and credits go to Accounts Receivable",
     "description": "Refunds, credit exceptions and chargebacks are decided by Accounts Receivable (high priority).",
     "condition": {"keywords_any": ["refund", "chargeback", "money back", "credit back"]},
     "outcome": {"next_action": "escalate", "group": "Accounts Receivable", "priority": "high", "human_only": True}},
    {"key": "fraud-or-unauthorized", "name": "Fraud or unauthorized access",
     "description": "Suspected fraud or unauthorized access goes to Trust & Security as urgent.",
     "condition": {"keywords_any": ["fraud", "phishing", "unauthorized", "compromised", "fake invoice"]},
     "outcome": {"next_action": "escalate", "group": "Trust & Security", "priority": "urgent", "human_only": True}},
    {"key": "integration-failure-scale", "name": "Integration failures on Scale",
     "description": "Persistent sync or API failures on Scale go to Platform Engineering as high priority.",
     "condition": {"categories": ["product_issue"], "keywords_any": ["ll-sync-", "api", "webhook", "sync"],
                   "plans_any": ["Scale"]},
     "outcome": {"next_action": "escalate", "group": "Platform Engineering", "priority": "high", "human_only": False}},
]

# account_ref, subject, category, priority, status, group, days_ago, body
TICKETS = [
    ("LL-2048", "Which plan adds recurring invoices?", "billing", "normal", "solved", "Customer Care", 3,
     "Explained Growth adds recurring billing; Owner upgraded from Essentials."),
    ("LL-2060", "Xero sync LL-SYNC-401 after password change", "product_issue", "normal", "solved",
     "Customer Care", 20, "Owner reconnected Xero; syncs recovered."),
    ("LL-2072", "Payment reminder wording", "product_issue", "low", "open", "Customer Care", 2,
     "Customer wants to customise reminder email text."),
]

# Seeded inbox. The first two use exactly the same wording as Northstar's requests.
REQUESTS = [
    ("access_reporting_after_upgrade", "LL-2048", "Reporting not available after our upgrade",
     "We upgraded yesterday, but two employees still can't access the reporting feature. "
     "We already tried signing out.", 3),
    ("billing_charged_twice", "LL-2051", "Charged twice this month?",
     "Hi — we were charged twice this month and the total is higher than we expected. "
     "Can you explain what these charges are?", 7),
    ("downgrade_timing_conflict", "LL-2060", "Downgrading from Scale",
     "We're on the annual Scale plan. If we downgrade to Growth today, does the lower price start right away, "
     "or only at our renewal date?", 15),
    ("peppol_einvoicing", "LL-2072", "Peppol e-invoicing?",
     "Can Lumen Ledger send our invoices through the Peppol e-invoicing network for our Belgian customers?", 40),
    ("refund_unused_seats", "LL-2033", "Refund for unused seats",
     "We only use 48 of our 50 seats on the annual plan. Can we get a refund for the 2 unused seats?", 60),
]

DOCS = [
    ("plans-and-pricing", "Plans and Pricing"),
    ("team-roles", "Team Roles and Permissions"),
    ("billing-and-charges", "Billing and Charges"),
    ("plan-changes", "Changing Plans"),
    ("billing-faq", "Billing FAQ"),
    ("refunds-and-credits", "Refunds and Credits"),
    ("integrations-troubleshooting", "Troubleshooting Accounting Integrations"),
    ("escalation-and-support", "Escalation and Support Policy"),
]
