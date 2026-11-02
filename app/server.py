"""Minimal GitHub App webhook service.

Registers with a GitHub App configured for pull_request events.
Dispatches a workflow already installed in the target repository.
"""
import hashlib
import hmac
import os
import time

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request

APP_ID = os.getenv("GITHUB_APP_ID", "")
PRIVATE_KEY = os.getenv("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n")
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
WORKFLOW_FILE = "aws-architecture.yml"
API = "https://api.github.com"
app = FastAPI(title="Generate Architectures GitHub App")

@app.get("/health")
def health():
    return {"ok": True}

def verify(body: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET or not signature.startswith("sha256="):
        return False
    digest = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + digest, signature)

def app_jwt() -> str:
    if not APP_ID or not PRIVATE_KEY:
        raise RuntimeError("Missing GitHub App configuration")
    now = int(time.time())
    return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": APP_ID}, PRIVATE_KEY, algorithm="RS256")

@app.post("/webhook")
async def webhook(request: Request):
    raw = await request.body()
    if len(raw) > 1024 * 1024:
        raise HTTPException(413, "Webhook too large")
    if not verify(raw, request.headers.get("X-Hub-Signature-256", "")):
        raise HTTPException(401, "Invalid webhook signature")
    event = request.headers.get("X-GitHub-Event")
    if event == "ping":
        return {"status": "pong"}
    payload = await request.json()
    if event != "pull_request" or payload.get("action") not in ("opened", "reopened", "synchronize"):
        return {"status": "ignored"}
    installation_id = payload.get("installation", {}).get("id")
    repo = payload.get("repository", {}).get("full_name", "")
    if not installation_id or "/" not in repo:
        raise HTTPException(422, "Missing installation or repository")
    if payload.get("pull_request", {}).get("head", {}).get("repo", {}).get("full_name") != repo:
        return {"status": "fork_skipped"}
    headers = {"Authorization": "Bearer " + app_jwt(),
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(API + "/app/installations/" + str(installation_id) + "/access_tokens",
                                           headers=headers)
        if token_response.status_code >= 400:
            raise HTTPException(502, "Unable to request installation token")
        token = token_response.json()["token"]
        dispatch = await client.post(
            API + "/repos/" + repo + "/actions/workflows/" + WORKFLOW_FILE + "/dispatches",
            headers={"Authorization": "Bearer " + token,
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
            json={"ref": payload["repository"]["default_branch"]})
        if dispatch.status_code == 404:
            return {"status": "workflow_not_installed", "required_file": ".github/workflows/" + WORKFLOW_FILE}
        if dispatch.status_code >= 400:
            raise HTTPException(502, "Workflow dispatch failed: HTTP " + str(dispatch.status_code))
    return {"status": "dispatched", "repository": repo}
