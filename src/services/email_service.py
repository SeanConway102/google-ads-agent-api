"""
Email service — Resend SDK wrapper for HITL proposal emails and weekly digests.
"""
from typing import Any

from src.config import get_settings


def send_proposal_email(
    *,
    to_email: str,
    campaign_name: str,
    proposal_type: str,
    impact_summary: str,
    reasoning: str,
) -> dict[str, Any]:
    """
    Send a proposal approval email via Resend.

    Returns the Resend API response dict (with 'id' field) on success.
    Raises on failure.
    """
    from resend import Emails

    subject = f"[AdsAgent] Action required: {proposal_type} on campaign \"{campaign_name}\""

    html_body = f"""
<!DOCTYPE html>
<html>
<body>
<p>Hi,</p>

<p>The Green Team has proposed a <strong>{proposal_type}</strong> for campaign "{campaign_name}":</p>

<blockquote>
<p><strong>What:</strong> {impact_summary}</p>
<p><strong>Why:</strong> {reasoning}</p>
</blockquote>

<p>To approve: reply with "approve", "yes", or "sounds good"</p>
<p>To reject:  reply with "reject", "no", or "not this time"</p>
<p>To ask:     reply with your question and I'll respond</p>

<p>This proposal will auto-expire in 7 days if no response.</p>

<p>— AdsAgent (autonomous Google Ads optimizer)</p>
</body>
</html>
"""

    try:
        result = Emails.send(
            {
                "subject": subject,
                "to": [to_email],
                "html": html_body,
                "from": "AdsAgent <noreply@adsagent.ai>",
            }
        )
        return dict(result)
    except Exception as exc:
        raise Exception(f"Resend API error: {exc}") from exc


def send_weekly_digest(
    *,
    to_email: str,
    campaign_name: str,
    impressions: int,
    clicks: int,
    spend: float,
    ctr: float,
    n_approved: int,
    n_rejected: int,
    n_pending: int,
) -> dict[str, Any]:
    """
    Send a weekly performance digest email via Resend.

    Returns the Resend API response dict (with 'id' field) on success.
    Raises on failure.
    """
    from resend import Emails

    subject = f"[AdsAgent] Weekly update for {campaign_name}"

    html_body = f"""
<!DOCTYPE html>
<html>
<body>
<p>Hi,</p>

<p>Here's your weekly summary for "{campaign_name}":</p>

<h3>Performance (last 7 days)</h3>
<ul>
<li>Impressions: {impressions:,}</li>
<li>Clicks: {clicks:,}</li>
<li>Spend: ${spend:.2f}</li>
<li>CTR: {ctr:.1f}%</li>
</ul>

<h3>Proposals</h3>
<ul>
<li>&#x2705; Decided: {n_approved} approved, {n_rejected} rejected</li>
<li>&#x23F3; Pending: {n_pending} proposal(s) awaiting your review</li>
</ul>

<p>[Reply "proposals" to see pending items]</p>

<p>— AdsAgent (autonomous Google Ads optimizer)</p>
</body>
</html>
"""

    try:
        result = Emails.send(
            {
                "subject": subject,
                "to": [to_email],
                "html": html_body,
                "from": "AdsAgent <noreply@adsagent.ai>",
            }
        )
        return dict(result)
    except Exception as exc:
        raise Exception(f"Resend API error: {exc}") from exc
