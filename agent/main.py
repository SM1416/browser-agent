"""FastAPI backend for the personal browser-agent site.

- Password login (single user, SITE_PASSWORD from env), session cookie.
- POST /api/task      start one agent task (409 if one is already active)
- GET  /api/task      current task snapshot
- GET  /api/tasks     recent task history
- POST /api/task/cancel
- POST /api/takeover   pause agent, user takes over the live browser
- POST /api/resume     hand control back to the agent
- WS   /api/ws        live event stream (steps, status, needs_human, ...)
- GET  /api/auth-check 200/401 — used by Caddy forward_auth to protect /vnc/*
"""
import asyncio
import hmac
import os
import secrets
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from runner import TaskRunner, BusyError

SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "")
if not SITE_PASSWORD:
    raise RuntimeError("SITE_PASSWORD env var is required. Copy .env.example to .env and set it.")

CDP_URL = os.environ.get("BROWSER_CDP_URL", "http://browser:9222")
SESSION_TTL = 7 * 24 * 3600
SESSION_COOKIE = "ba_session"

sessions: dict[str, float] = {}
ws_clients: set[WebSocket] = set()
login_attempts: dict[str, list] = {}


async def broadcast(event: dict):
    dead = []
    for ws in list(ws_clients):
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.discard(ws)


runner = TaskRunner(broadcast=broadcast, cdp_url=CDP_URL)


def _valid(token):
    if not token:
        return False
    exp = sessions.get(token)
    if not exp or exp < time.time():
        sessions.pop(token, None)
        return False
    return True


async def require_auth(request: Request):
    if not _valid(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(status_code=401, detail="not logged in")


def _rate_ok(ip: str) -> bool:
    now = time.time()
    arr = [t for t in login_attempts.get(ip, []) if now - t < 60]
    login_attempts[ip] = arr
    return len(arr) < 8


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.environ.get("LLM_API_KEY"):
        raise RuntimeError(
            "LLM_API_KEY env var is required. Get a free key at "
            "https://aistudio.google.com and put it in your .env file."
        )
    # Wait for the browser's CDP endpoint before accepting tasks.
    async with httpx.AsyncClient() as client:
        for _ in range(90):
            try:
                r = await client.get(CDP_URL + "/json/version", timeout=5)
                if r.status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(2)
    yield


app = FastAPI(title="Browser Agent", lifespan=lifespan)


class LoginBody(BaseModel):
    password: str


class TaskBody(BaseModel):
    instruction: str


class TakeoverBody(BaseModel):
    reason: str = "You took over the browser."


@app.post("/api/login")
async def login(body: LoginBody, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    if not _rate_ok(ip):
        raise HTTPException(status_code=429, detail="Too many login attempts, wait a minute.")
    login_attempts.setdefault(ip, []).append(time.time())
    if not hmac.compare_digest(body.password, SITE_PASSWORD):
        raise HTTPException(status_code=401, detail="Wrong password.")
    token = secrets.token_urlsafe(32)
    sessions[token] = time.time() + SESSION_TTL
    response.set_cookie(
        SESSION_COOKIE, token,
        httponly=True, secure=True, samesite="lax",
        max_age=SESSION_TTL, path="/",
    )
    return {"ok": True}


@app.post("/api/logout")
async def logout(request: Request, response: Response):
    sessions.pop(request.cookies.get(SESSION_COOKIE, ""), None)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me")
async def me(request: Request):
    return {"logged_in": _valid(request.cookies.get(SESSION_COOKIE))}


@app.get("/api/auth-check")
async def auth_check(request: Request):
    # Used by Caddy forward_auth to gate /vnc/*. Status code is the whole contract.
    if not _valid(request.cookies.get(SESSION_COOKIE)):
        return Response(status_code=401)
    return {"ok": True}


@app.post("/api/task", dependencies=[Depends(require_auth)])
async def start_task(body: TaskBody):
    try:
        return JSONResponse(status_code=201, content=await runner.start(body.instruction))
    except BusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/task", dependencies=[Depends(require_auth)])
async def get_task():
    return runner.snapshot()


@app.get("/api/tasks", dependencies=[Depends(require_auth)])
async def get_tasks():
    return {"tasks": runner.history_list()}


@app.post("/api/task/cancel", dependencies=[Depends(require_auth)])
async def cancel_task():
    return await runner.cancel()


@app.post("/api/takeover", dependencies=[Depends(require_auth)])
async def takeover(body: TakeoverBody):
    return await runner.takeover(body.reason)


@app.post("/api/resume", dependencies=[Depends(require_auth)])
async def resume():
    return await runner.resume()


@app.websocket("/api/ws")
async def ws_endpoint(ws: WebSocket):
    token = ws.cookies.get(SESSION_COOKIE) or ws.query_params.get("token")
    if not _valid(token):
        await ws.close(code=4401)
        return
    await ws.accept()
    ws_clients.add(ws)
    try:
        await ws.send_json({"type": "hello", "task": runner.snapshot()})
        while True:
            # Keep-alive; client may send pings.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ws_clients.discard(ws)
