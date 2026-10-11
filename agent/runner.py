"""Runs one browser-use agent task at a time against the shared headed browser.

States: idle -> running -> (paused | needs_human) -> running -> done | error | cancelled
The human-takeover flow pauses the agent loop; the browser itself keeps running
so the user can click/type in the live noVNC view, then hand control back.
"""
import asyncio
import os
import time
import uuid

# Strong bot-check signals -> auto-pause and ask the human to take over.
# Plain login pages are NOT auto-flagged: the user takes over manually for those.
CHALLENGE_KEYWORDS = (
    "captcha",
    "recaptcha",
    "turnstile",
    "verify you are human",
    "verify you're human",
    "i am not a robot",
    "i'm not a robot",
    "unusual traffic",
    "are you a robot",
    "human verification",
    "security challenge",
    "press & hold",
    "confirm you are human",
)


class BusyError(Exception):
    pass


class TaskRunner:
    def __init__(self, broadcast, cdp_url):
        self._broadcast = broadcast  # async callable taking a dict
        self._cdp_url = cdp_url
        self.max_steps = int(os.environ.get("MAX_STEPS", "40"))
        self.task_id = None
        self.instruction = ""
        self.status = "idle"
        self.steps = []
        self.result = None
        self.error = None
        self.takeover_reason = None
        self.started_at = None
        self.finished_at = None
        self.agent = None
        self._task = None
        self._history = []

    def busy(self):
        return self.status in ("running", "paused", "needs_human")

    def snapshot(self):
        return {
            "task_id": self.task_id,
            "instruction": self.instruction,
            "status": self.status,
            "takeover_reason": self.takeover_reason,
            "steps": self.steps[-30:],
            "step_count": len(self.steps),
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    def history_list(self):
        return list(self._history)

    async def start(self, instruction):
        if self.busy():
            raise BusyError("An agent task is already running. Cancel it or wait for it to finish.")
        instruction = (instruction or "").strip()
        if not instruction:
            raise ValueError("Task instruction is empty.")
        self.task_id = uuid.uuid4().hex[:12]
        self.instruction = instruction
        self.status = "running"
        self.steps = []
        self.result = None
        self.error = None
        self.takeover_reason = None
        self.started_at = time.time()
        self.finished_at = None
        self.agent = None
        await self._broadcast({
            "type": "task_started",
            "task_id": self.task_id,
            "instruction": self.instruction,
        })
        self._task = asyncio.create_task(self._run())
        return self.snapshot()

    async def _run(self):
        try:
            from llm_factory import build_llm
            from browser_use import Agent, Browser

            llm = build_llm()
            # keep_alive=True: agent.close() must NOT kill our persistent browser.
            browser = Browser(cdp_url=self._cdp_url, keep_alive=True)
            self.agent = Agent(
                task=self.instruction,
                llm=llm,
                browser=browser,
                max_steps=self.max_steps,
                register_new_step_callback=self._on_step,
            )
            history = await self.agent.run()
            try:
                self.result = history.final_result() if history else None
            except Exception:
                self.result = None
            if self.status in ("running", "paused", "needs_human"):
                self.status = "done"
                await self._broadcast({
                    "type": "task_finished",
                    "task_id": self.task_id,
                    "result": self.result,
                })
        except asyncio.CancelledError:
            self.status = "cancelled"
            await self._broadcast({"type": "task_cancelled", "task_id": self.task_id})
            raise
        except Exception as e:
            if self.status in ("running", "paused", "needs_human"):
                self.status = "error"
            self.error = f"{type(e).__name__}: {e}"
            await self._broadcast({
                "type": "task_error",
                "task_id": self.task_id,
                "error": self.error,
            })
        finally:
            try:
                if self.agent is not None:
                    await self.agent.close()
            except Exception:
                pass
            self.agent = None
            self.finished_at = time.time()
            self._history.insert(0, {
                "task_id": self.task_id,
                "instruction": self.instruction,
                "status": self.status,
                "result": (self.result or "")[:500],
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            })
            self._history = self._history[:20]

    async def _on_step(self, browser_state, model_output, step_n):
        if self.status == "cancelled":
            return
        url = getattr(browser_state, "url", "") or ""
        title = getattr(browser_state, "title", "") or ""
        summary = self._summarize_action(model_output)
        entry = {
            "n": step_n,
            "url": url,
            "title": title,
            "summary": summary,
            "ts": time.time(),
        }
        self.steps.append(entry)
        await self._broadcast({
            "type": "step",
            "task_id": self.task_id,
            "status": self.status,
            **entry,
        })
        # Auto-pause on likely bot checks so the human can take over.
        if self.status == "running":
            page_text = f"{title} {url}".lower()
            if any(k in page_text for k in CHALLENGE_KEYWORDS):
                await self.takeover(
                    reason=f"Possible bot check on this page ({title or url}). "
                           "Take over the browser to solve it, then hand back to the agent."
                )

    @staticmethod
    def _summarize_action(model_output):
        try:
            parts = []
            actions = getattr(model_output, "action", None) or []
            for a in actions[:3]:
                if hasattr(a, "model_dump"):
                    d = a.model_dump(exclude_none=True)
                else:
                    d = a
                if isinstance(d, dict) and d:
                    name, params = next(iter(d.items()))
                    if isinstance(params, dict):
                        p = ", ".join(f"{k}={v}" for k, v in list(params.items())[:3])
                        parts.append(f"{name}({p})" if p else name)
                    else:
                        parts.append(str(name))
                else:
                    parts.append(str(d)[:60])
            state = getattr(model_output, "current_state", None)
            goal = getattr(state, "next_goal", None) if state else None
            s = "; ".join(parts) if parts else "thinking…"
            if goal:
                s += f" — {str(goal)[:160]}"
            return s[:300]
        except Exception:
            return "working…"

    async def takeover(self, reason="You took over the browser."):
        if self.status not in ("running", "paused"):
            return {"status": self.status}
        if self.agent is not None:
            try:
                self.agent.pause()
            except Exception:
                pass
        self.status = "needs_human"
        self.takeover_reason = reason
        await self._broadcast({
            "type": "needs_human",
            "task_id": self.task_id,
            "reason": reason,
        })
        return {"status": self.status}

    async def resume(self):
        if self.status not in ("paused", "needs_human"):
            return {"status": self.status}
        if self.agent is not None:
            try:
                self.agent.resume()
            except Exception:
                pass
        self.status = "running"
        self.takeover_reason = None
        await self._broadcast({"type": "task_resumed", "task_id": self.task_id})
        return {"status": self.status}

    async def cancel(self):
        if not self.busy():
            return {"status": self.status}
        self.status = "cancelled"
        if self.agent is not None:
            try:
                self.agent.stop()
            except Exception:
                pass
        await self._broadcast({"type": "task_cancelled", "task_id": self.task_id})
        return {"status": self.status}
