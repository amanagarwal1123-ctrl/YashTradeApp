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
AI_CONSENT_VERSION = "2026-09-13"
AI_MODEL = "claude-sonnet-4-5-20250929"
RECIPIENTS = [{
    "name": "Anthropic PBC",
    "service": f"Claude ({AI_MODEL})",
    "role": "AI model provider (third party)",
    "via": "Emergent LLM gateway (integrations.emergentagent.com), which relays the request to the provider",
    "location": "United States",
    "data_sent": ["The text you type or the quick prompt you tap",
                  "Up to the last 10 messages of the same conversation, so the assistant has context",
                  "Your chosen reply language (English / Hindi / Punjabi)",
                  "A pseudonymous session identifier that does not contain your phone number, name or account ID"],
    "data_not_sent": ["Your name, phone number, shop name or location", "Your enquiries, orders, cart, wishlist or reward balance",
                      "Any photo or file (the app does not collect customer photos)"],
    "purpose": "Generate the assistant's reply to your question",
    "retention": "Our copy is deleted when you withdraw consent or delete your account. The provider processes the "
                 "request under its own policy; there is no per-user deletion request we can send to the provider, so "
                 "we do not claim its copy is erased.",
}]
WITHDRAWAL_EFFECTS = ["No further text is sent to the AI provider", "Your stored AI chat history in the app is deleted immediately",
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
            "provider_copy": "not erased: the provider offers no per-user deletion request; see recipients[].retention"}
