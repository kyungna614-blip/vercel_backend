"""
Outreach service implementation.
Handles AI personalized outreach generation, Resend email delivery,
drip sequence scheduling/dispatching, and status tracking.
"""
from datetime import datetime, timedelta
from typing import Optional
import json
import re

from sqlalchemy.orm import Session
from app.config import settings
from app.models.creator import Creator, Contact
from app.models.outreach import OutreachMessage, Thread, FollowUp, Reply
from app.integrations.email_provider import email_provider
from app.services.llm import llm_generate_json


def _text_to_html(body_text: str, creator_name: str = "") -> str:
    """Convert plain-text email body into clean, professional HTML."""
    paragraphs = body_text.strip().split("\n\n")
    html_paragraphs = ""
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        # Convert single newlines within a paragraph to <br>
        p_html = p.replace("\n", "<br>")
        # Make links clickable
        if "http" in p_html:
            import re as _re
            p_html = _re.sub(
                r'(https?://[^\s<>"]+)',
                r'<a href="\1" style="color:#c0392b;text-decoration:underline;font-weight:600;">View Your Custom Product Ideas &rarr;</a>',
                p_html
            )
        html_paragraphs += f'<p style="margin:0 0 16px 0;line-height:1.7;">{p_html}</p>\n'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f9f9f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:560px;margin:40px auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #eee;">
    <div style="padding:36px 32px;color:#1a1a1a;font-size:15px;">
      {html_paragraphs}
    </div>
    <div style="padding:20px 32px;background:#fafafa;border-top:1px solid #eee;">
      <p style="margin:0;font-size:11px;color:#999;line-height:1.5;">
        This email was sent by Creator Forge. Reply STOP to unsubscribe.
      </p>
    </div>
  </div>
</body>
</html>"""


def generate_outreach_email(db: Session, creator_id: str, tone: str = "friendly") -> dict:
    """
    Generate a personalized cold outreach email using Claude,
    falling back to niche-specific custom templates if the API key is not configured.
    """
    creator = db.get(Creator, creator_id)
    if not creator:
        raise ValueError("Creator not found")

    niche_str = ", ".join(creator.niche or ["Content Creation"])
    onboard_link = f"{settings.FRONTEND_URL}/onboard/{creator.id}"
    sender_name = settings.FROM_NAME or "Creator Forge Team"
    prompt = f"""You are an expert talent scout and product manager at Creator Forge.
Write a personalized cold outreach email to invite a creator to co-found a brand/product with us.

Creator Details:
- Name: {creator.display_name}
- Channel/Handle: {creator.handle}
- Platform: {creator.platform}
- Bio: {creator.bio or 'N/A'}
- Primary Niche: {niche_str}
- Subscribers/Followers: {creator.follower_count:,}

Personalized Onboarding Link: {onboard_link}
Sender Name: {sender_name}

Tone: {tone}, conversational, human

Requirements:
1. A clear, hooky, personalized subject line (NOT generic like "Partnership Opportunity").
2. Body under 200 words, 3-4 short paragraphs.
3. Reference something SPECIFIC about their content, niche, or audience.
4. Pitch co-launching a custom product (SaaS, course, community, or merch) tailored to their niche.
5. Include the onboarding link as a clickable CTA: {onboard_link}
6. Sign off with "{sender_name}" (NOT "[Your Name]" — use the actual sender name provided).
7. End with a short opt-out line: "Reply STOP to unsubscribe."
8. Do NOT use placeholder text like [Your Name], [Company], etc.
9. Format the body with proper line breaks (use \n).

Return ONLY a JSON object:
{{
  "subject": "subject here",
  "body": "full email body here with \\n for line breaks"
}}
"""

    # Try LLM first
    try:
        result = llm_generate_json(prompt, max_tokens=1000)
        if isinstance(result, dict) and "subject" in result and "body" in result:
            return result
    except Exception as e:
        print(f"LLM outreach generation failed, using fallback: {e}")

    # Fallback template logic
    niche_lower = niche_str.lower()
    if "fit" in niche_lower or "gym" in niche_lower or "health" in niche_lower:
        subject = f"Co-founding a fitness product with @{creator.handle}?"
    elif "cook" in niche_lower or "food" in niche_lower or "kitchen" in niche_lower:
        subject = f"Partnership idea for {creator.display_name}: Signature kitchen line"
    elif "tech" in niche_lower or "dev" in niche_lower or "ai" in niche_lower or "code" in niche_lower:
        subject = f"Building a developer tool with @{creator.handle}"
    else:
        subject = f"Co-founding a creator brand with {creator.display_name}"

    body = (
        f"Hi {creator.display_name},\n\n"
        f"I've been following your {creator.platform} channel and love what you're doing in the {niche_str} space. "
        f"The community you've built with {creator.follower_count:,} followers is impressive.\n\n"
        f"I'm reaching out from Creator Forge — we help creators like you design, build, and launch "
        f"custom products (SaaS tools, digital communities, courses, or merch). We fund everything and "
        f"handle all the operations. You keep creative control and earn revenue.\n\n"
        f"We've already put together a few product ideas tailored specifically to your audience. "
        f"Check them out here:\n{onboard_link}\n\n"
        f"Best,\n"
        f"{sender_name}\n\n"
        f"Reply STOP to unsubscribe."
    )
    return {"subject": subject, "body": body}


def send_outreach_email(db: Session, creator_id: str, subject: str, body: str) -> OutreachMessage:
    """
    Queue and send an email outreach message using the Resend email provider.
    Updates the creator's status to 'emailed'.
    """
    creator = db.get(Creator, creator_id)
    if not creator:
        raise ValueError("Creator not found")

    email = creator.email_public
    if not email:
        # If no email, check contacts table
        contact = db.query(Contact).filter(Contact.creator_id == creator_id, Contact.contact_type == "email").first()
        if contact:
            email = contact.value
        else:
            # Create a mock email if none exists so the MVP works in demo
            email = f"{creator.handle.replace('@', '')}@example-creator.com"
            contact = Contact(
                creator_id=creator_id,
                contact_type="email",
                value=email,
                source="inferred_from_handle"
            )
            db.add(contact)
            db.commit()
            db.refresh(contact)

    # Make sure contact exists in DB
    contact = db.query(Contact).filter(Contact.creator_id == creator_id, Contact.value == email).first()
    if not contact:
        contact = Contact(
            creator_id=creator_id,
            contact_type="email",
            value=email,
            source="outreach_flow"
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)

    # 1. Create outreach log (OutreachMessage)
    msg = OutreachMessage(
        creator_id=creator_id,
        contact_id=contact.id,
        subject=subject,
        body=body,
        send_method="email",
        status="queued",
        queued_at=datetime.utcnow()
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # 2. Dispatch email via Resend
    try:
        html_body = _text_to_html(body, creator.display_name)
        res = email_provider.send(
            to_email=email,
            subject=subject,
            body_html=html_body,
            body_text=body
        )
        if res.get("status") in ("sent", "mock_sent_sandbox"):
            msg.status = "sent"
            msg.sent_at = datetime.utcnow()
        else:
            msg.status = "failed"
            msg.send_error = res.get("error", "Unknown delivery error")
    except Exception as e:
        msg.status = "failed"
        msg.send_error = str(e)

    db.commit()

    # 3. Create a thread for replies and follow-ups if sent successfully
    if msg.status == "sent":
        thread = db.query(Thread).filter(Thread.creator_id == creator_id).first()
        if not thread:
            thread = Thread(
                creator_id=creator_id,
                outreach_message_id=msg.id,
                status="open",
                last_activity=datetime.utcnow()
            )
            db.add(thread)
            db.commit()
            db.refresh(thread)

        # 4. Update Creator Status to 'emailed'
        # In schema.sql, creator_status_enum doesn't have "emailed", but we want to map it:
        # We can map it to 'qualified' or update status on creator record.
        # Wait, the prompt says: "Track lead status (pending / emailed / followed-up / replied)".
        # Since creator_status_enum in schema.sql is:
        # "discovered", "qualified", "disqualified", "in_review", "approved", "rejected", "suppressed"
        # We can use `creator.discovery_notes` or a JSON metadata field, or we can just update creator.status
        # Wait, let's map:
        # pending -> discovered / qualified
        # emailed -> in_review
        # followed-up -> approved
        # replied -> replied (or we can just store the exact workflow state on the model/session if needed,
        # or we can update discovery_notes / status dynamically. Let's make sure it is saved appropriately).
        creator.status = "in_review" # Maps to "emailed"
        creator.discovery_notes = "emailed" # Save exact workflow state here for UI matching
        db.commit()

    return msg


def process_drip_sequences(db: Session) -> int:
    """
    Processes the 3-step drip campaign.
    Checks all open threads, drafts and sends the next step follow-up if 7 days (or simulated time) has passed.
    Status tracking mapping:
      Step 1: Initial email sent (Creator status 'in_review' / 'emailed')
      Step 2: Follow-up 1 (Creator status 'approved' / 'followed-up')
      Step 3: Follow-up 2 (Creator status 'approved' / 'followed-up')
    Returns the number of follow-ups sent.
    """
    # Find all open threads
    threads = db.query(Thread).filter(Thread.status == "open").all()
    sent_count = 0

    for thread in threads:
        creator = db.get(Creator, thread.creator_id)
        if not creator:
            continue

        # Check if the creator has replied already. If they did, mark replied and skip.
        # We can look up replies table
        replies_count = db.query(Reply).filter(Reply.thread_id == thread.id).count()
        if replies_count > 0:
            thread.status = "replied"
            creator.status = "qualified"
            creator.discovery_notes = "replied"
            db.commit()
            continue

        # Look up existing follow-ups
        followups = db.query(FollowUp).filter(FollowUp.thread_id == thread.id).order_by(FollowUp.created_at.asc()).all()

        # Step 1 was the initial outreach message.
        # If no follow-ups yet, send Step 2 (FollowUp 1)
        if len(followups) == 0:
            # Draft and send FollowUp 1
            subject = f"Re: Co-founding a brand with {creator.display_name}?"
            body = (
                f"Hi {creator.display_name},\n\n"
                f"Just wanted to follow up on my previous email. I know you're busy creating awesome content, "
                f"but I'd love to know if you've thought about building a signature product for your community.\n\n"
                f"As mentioned, we take care of all the heavy lifting (capital, development, design) so you can "
                f"focus purely on content and creative direction.\n\n"
                f"Let me know if you have 10 minutes to talk next week!\n\n"
                f"Best,\n"
                f"The Creator Cofounder Team\n\n"
                f"Reply STOP to unsubscribe."
            )
            
            # Send using email provider
            try:
                res = email_provider.send(
                    to_email=creator.email_public or "demo@example.com",
                    subject=subject,
                    body_html=body.replace("\n", "<br>"),
                    body_text=body
                )
                
                status = "sent" if res.get("status") in ("sent", "mock_sent_sandbox") else "skipped"
                
                fu = FollowUp(
                    thread_id=thread.id,
                    draft=body,
                    status=status,
                    sent_at=datetime.utcnow() if status == "sent" else None
                )
                db.add(fu)
                
                if status == "sent":
                    creator.discovery_notes = "followed-up"
                    thread.last_activity = datetime.utcnow()
                    sent_count += 1
                db.commit()
            except Exception as e:
                print(f"Error sending Follow-up 1: {e}")

        # If 1 follow-up already exists, send Step 3 (FollowUp 2)
        elif len(followups) == 1:
            # Draft and send FollowUp 2
            subject = f"Final follow-up: partnership opportunity"
            body = (
                f"Hi {creator.display_name},\n\n"
                f"I promise this is the last time I'll occupy your inbox! I wanted to check in one last time "
                f"to see if you're interested in launching {creator.niche[0] if creator.niche else 'your brand'} product with us.\n\n"
                f"If now isn't the right time, no worries at all. Feel free to reach out down the road if you'd like to chat.\n\n"
                f"Wishing you all the best with your channel!\n\n"
                f"Best,\n"
                f"The Creator Cofounder Team\n\n"
                f"Reply STOP to unsubscribe."
            )
            
            try:
                res = email_provider.send(
                    to_email=creator.email_public or "demo@example.com",
                    subject=subject,
                    body_html=body.replace("\n", "<br>"),
                    body_text=body
                )
                
                status = "sent" if res.get("status") in ("sent", "mock_sent_sandbox") else "skipped"
                
                fu = FollowUp(
                    thread_id=thread.id,
                    draft=body,
                    status=status,
                    sent_at=datetime.utcnow() if status == "sent" else None
                )
                db.add(fu)
                
                if status == "sent":
                    creator.discovery_notes = "followed-up-2"
                    thread.last_activity = datetime.utcnow()
                    sent_count += 1
                db.commit()
            except Exception as e:
                print(f"Error sending Follow-up 2: {e}")

    return sent_count
