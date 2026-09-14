"""Explicit, recorded, withdrawable consent before any personal data reaches a third-party AI provider.

The AI assistant (and every quick prompt, which uses the same endpoint) sends the typed text and the last turns
of the same conversation to Anthropic's Claude model through the Emergent LLM gateway. Nothing is transmitted
until the signed-in account has granted the CURRENT consent version. Withdrawal stops further transfers at once
and deletes the stored chat history; the in-flight guard in the chat endpoint prevents a response that was already
under way from recreating history after a withdrawal.
"""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from . import core as c

router = APIRouter(prefix="/api", tags=["AI consent"])
AI_CONSENT_VERSION = "2026-09-14"
AI_MODEL = "claude-sonnet-4-5-20250929"
# Mirrors the provider request built in server.py::ai_chat: system instruction + up to the last 10 stored turns of
# the same conversation + the new message, relayed by the Emergent LLM gateway under the business's gateway
# credential. No phone, name, account ID or session identifier is added to the request - but the user's own text
# is transferred exactly as written, so it CAN contain such details if the user types them.
RECIPIENTS = [{
    "name": "Anthropic PBC",
    "service": f"Claude ({AI_MODEL})",
    "role": "AI model provider (third party)",
    "via": "Emergent LLM gateway (integrations.emergentagent.com), which relays the request to the provider",
    "location": "United States",
    "data_sent": ["The exact text of every message you type and every quick prompt you tap - including any name, phone number, "
                  "address or other detail you choose to write in it",
                  "The earlier messages and replies of the same conversation (up to the last 10 stored), so the assistant has context",
                  "Our fixed instruction describing the assistant's role and your chosen reply language (English / Hindi / Punjabi)",
                  "Our gateway credential, which identifies Yash Trade as the sender - not you"],
    "data_not_sent": ["Your profile fields - name, phone number, shop name, city - are not attached automatically; only what you write "
                      "yourself is transferred",
                      "Your account ID, enquiries, orders, cart, wishlist and reward balance are not attached",
                      "No photo or file is sent - the assistant is text-only"],
    "purpose": "Generate the assistant's reply to your question",
    "retention": "Our copy of the conversation stays in the app until you withdraw consent or delete your account; then it is "
                 "deleted. The gateway and the provider process the request under their own terms. We have no per-user deletion "
                 "request to send them, so we do not claim their copies are erased and we do not state a retention period for them.",
}]
WITHDRAWAL_EFFECTS = ["No further text is sent to the AI provider", "Your stored AI chat history in the app is deleted immediately",
                      "Copies already processed by the provider and its gateway are not erased by this",
                      "Every other part of the app keeps working normally", "You can grant consent again at any time"]


def consent_state(user):
    consent = user.get("ai_consent") or {}
    granted = bool(consent.get("granted")) and consent.get("version") == AI_CONSENT_VERSION
    return {"granted": granted, "version": consent.get("version"), "current_version": AI_CONSENT_VERSION,
            "granted_at": consent.get("granted_at"), "withdrawn_at": consent.get("withdrawn_at"),
            "epoch": int(consent.get("epoch", 0)), "outdated": bool(consent.get("granted")) and not granted}


def describe(user):
    return {**consent_state(user), "recipients": RECIPIENTS, "withdrawal_effects": WITHDRAWAL_EFFECTS,
            "required_for": ["AI assistant conversation", "AI assistant quick prompts"],
            "not_required_for": ["Catalogue, rates, schemes, requests, cart, wishlist, rewards, knowledge articles and every staff screen"]}


async def require_consent(user):
    """The chat endpoint's gate. Returns the consent epoch captured BEFORE the provider call."""
    state = consent_state(user)
    if not state["granted"]:
        c.fail(403, "AI_CONSENT_REQUIRED", "Allow AI data sharing before using the assistant; every other feature works without it")
    return state["epoch"]


async def still_granted(uid, epoch):
    """Re-check after the provider answered: the same consent epoch must still be active for history to be kept."""
    fresh = await c.db.users.find_one({"id": uid}, {"_id": 0, "ai_consent": 1})
    state = consent_state(fresh or {})
    return state["granted"] and state["epoch"] == epoch


def history_query(uid):
    return {"$or": [{"user_id": uid}, {"session_id": f"jeweller-{uid}"}]}


async def purge_history(uid):
    deleted = (await c.db.ai_chat_history.delete_many(history_query(uid))).deleted_count
    await c.db.ai_reports.delete_many({"user_id": uid})
    return deleted


class ConsentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    granted: bool
    source: Literal["assistant", "profile", "quick_prompt"] = "assistant"


@router.get("/ai/consent")
async def read_consent(user=Depends(c.current_user)):
    return describe(user)


@router.post("/ai/consent")
async def decide(req: ConsentDecision, user=Depends(c.current_user)):
    ts = c.stamp()
    event = {"at": ts, "granted": req.granted, "version": AI_CONSENT_VERSION, "source": req.source,
             "recipients": [r["name"] for r in RECIPIENTS]}
    if req.granted:
        fields = {"granted": True, "version": AI_CONSENT_VERSION, "granted_at": ts, "withdrawn_at": None,
                  "recipients": [r["name"] for r in RECIPIENTS]}
        await c.db.users.update_one({"id": user["id"]}, {"$set": {f"ai_consent.{k}": v for k, v in fields.items()},
                                                          "$push": {"ai_consent_events": event}})
        return {**describe(await c.db.users.find_one({"id": user["id"]}, {"_id": 0})), "history_deleted": 0}
    # Withdrawal: bump the epoch FIRST so any in-flight chat sees a changed epoch and discards its own history,
    # then delete everything stored. Order matters: a response landing between the two steps is caught by the epoch.
    await c.db.users.update_one({"id": user["id"]}, {"$set": {"ai_consent.granted": False, "ai_consent.withdrawn_at": ts},
                                                      "$inc": {"ai_consent.epoch": 1}, "$push": {"ai_consent_events": event}})
    deleted = await purge_history(user["id"])
    return {**describe(await c.db.users.find_one({"id": user["id"]}, {"_id": 0})), "history_deleted": deleted,
            "provider_copy": "not erased: copies already processed by the AI provider and its gateway stay under their own terms; "
                             "there is no per-user deletion request we can send (see recipients[].retention)"}
