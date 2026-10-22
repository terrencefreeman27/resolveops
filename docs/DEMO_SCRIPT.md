# Recorded demo script (about 3.5 minutes)

Setup before recording: `make reset`, wait for http://localhost:8080 to load, and use a fresh browser window at
1440×900. Demo mode, no keys. Say plainly that the AI in this recording is simulated.

| Time | Do | Say |
|---|---|---|
| 0:00–0:20 | Show the inbox and the yellow banner. | "ResolveOps drafts support resolutions from the customer's account and the company's docs. A human approves before anything happens. This is demo mode: the AI is simulated with fixtures, and everything around it is real: tools, retrieval, rules, approval, tickets and audit." |
| 0:20–1:05 | Click **Access issue**. Point at the account facts (Starter → Pro yesterday, 7 Viewers), the reply, and the Sources. Click citation [1] to open the passage. | "The account facts come from typed tools scoped to this customer, not from the model. The reply explains it isn't a sign-in problem: Viewers never get Reporting, and an Admin has to change them to Analyst. Every citation points to the exact document version that was retrieved for this request." |
| 1:05–1:35 | Click **Edit**, add a line to the reply, then **Save as new version**. Show that v2 needs approval. **Approve version 2**. Show ticket NS-… and the action history. | "Editing creates version 2, and the earlier approval would no longer count. Approval binds to this exact version. One ticket is created, and double clicks or retries can't create a second." |
| 1:35–2:00 | Click **Escalate product issue**. Open the **Activity timeline**: tool names, retrieval queries and scores, timings. | "The escalation rule for connector outages on paid plans forces this to Engineering at high priority, whatever the draft says. The timeline shows each tool call and its result." |
| 2:00–2:30 | Switch the workspace to **Lumen Ledger**. Run **Access issue** (same wording). | "Same words, different company. Lumen's Growth plan doesn't include Insights reporting at all, so the answer is 'you need Scale', with citations from Lumen's own documents." |
| 2:30–2:50 | Run **Conflicting docs**. Show the evidence panel. | "Two current Lumen documents disagree about when a downgrade takes effect. The code detects the conflict and turns the confident draft into an escalation. A reviewer edit can't turn it back into a resolve." |
| 2:50–3:20 | Open **Dashboard**. Show the counts, approval outcomes and the separate simulated and live panels ("pricing not configured"). Scroll to Evaluation results. | "The dashboard shows only my sandbox. The evaluation is labelled by mode. The demo eval is simulated and not evidence of AI performance, and it reports 15 of 50 cases as uncovered rather than counting them as passes. The live eval hasn't been run because there's no API key here. The 64 deterministic backend checks, covering permissions, approval, stale evidence and duplicates, all pass." |
| 3:20–3:35 | Click **Reset my demo**. | "Reset clears only my sandbox; other visitors are unaffected. Setup, evaluation commands and known limitations are in the README." |

Optional, for a reviewer audience (+40 s): sign in as `reviewer@northstar.example` / `northstar-demo`. In
**Workspace setup**, replace *Roles and Permissions* while a proposal that cites it is pending. Back in the inbox,
that proposal is **stale** and Approve is refused, and **Reprocess with current documentation** creates the next version against the new
document.

Don't claim during the recording: that a real model produced these answers, that GitHub is connected, or any
accuracy figure from the demo eval as model performance.
