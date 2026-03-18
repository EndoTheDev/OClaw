import asyncio
import time
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Manager
from queue import Empty
from typing import Any
from uuid import uuid4

from core.logger import Logger
from core.agent import ExecutionContext


class AgentWorker:
    def __init__(self, num_processes: int = 4, timeout: int = 300):
        self.logger = Logger.get("worker.py")
        self.num_processes = num_processes
        self.timeout = timeout
        self._executor: ProcessPoolExecutor | None = None
        self._manager: Manager | None = None  # type: ignore
        self.pending_inputs = {}
        self.stream_poll_interval = 0.5

    def start(self) -> None:
        self.logger.info("worker.start", num_processes=self.num_processes)
        self._manager = Manager()
        self._executor = ProcessPoolExecutor(
            max_workers=self.num_processes,
            max_tasks_per_child=1,
        )

    def stop(self, timeout: int | None = None) -> None:
        self.logger.info("worker.stop.start", timeout=timeout)
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

            if timeout is not None and timeout > 0:
                processes = getattr(self._executor, "_processes", {})

                start_time = time.time()
                while any(p.is_alive() for p in processes.values()):
                    elapsed = time.time() - start_time
                    if elapsed >= timeout:
                        break
                    time.sleep(0.05)

            self._executor = None

        if self._manager:
            self._manager.shutdown()
            self._manager = None
        self.logger.info("worker.stop.done")

    def restart(self) -> None:
        self.logger.info("worker.restart")
        self.stop()
        self.start()

    async def run_agent(
        self,
        message: str,
        session_id: str,
        context: ExecutionContext,
    ):
        if not self._executor or not self._manager:
            self.logger.error(
                "worker.run_agent.not_started", request_id=context.request_id
            )
            raise RuntimeError("Worker pool not started. Call start() first.")

        active_request_id = context.request_id or str(uuid4())

        self.logger.info(
            "worker.run_agent.start",
            request_id=context.request_id,
            message_chars=len(message),
        )

        result_queue = self._manager.Queue()
        input_queue = self._manager.Queue()

        self.pending_inputs[active_request_id] = input_queue

        future = self._executor.submit(
            _execute_agent,
            message,
            session_id,
            result_queue,
            input_queue,
            context,
        )

        sequence = 0
        agent_started = False

        def next_event(
            event_type: str,
            payload: dict[str, Any],
            turn_id: str | None = None,
        ) -> dict[str, Any]:
            nonlocal sequence
            sequence += 1
            return {
                "schema_version": "2.0",
                "event_id": str(uuid4()),
                "sequence": sequence,
                "timestamp": datetime.now(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "event_type": event_type,
                "request_id": active_request_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "payload": payload,
            }

        terminal_event_emitted = False

        try:
            while True:
                try:
                    event = await self._queue_get_async(
                        result_queue,
                        timeout=self.stream_poll_interval,
                    )
                    events_to_process: list[dict[str, Any]] = []
                    if event is not None:
                        events_to_process.append(event)
                    elif future.done():
                        while True:
                            drained = await self._queue_get_nowait_async(result_queue)
                            if drained is None:
                                break
                            events_to_process.append(drained)
                    else:
                        continue

                    for current_event in events_to_process:
                        if "sequence" in current_event and isinstance(
                            current_event.get("sequence"), int
                        ):
                            sequence = int(current_event["sequence"])
                        if current_event.get("event_type") == "agent_start":
                            agent_started = True
                        if current_event.get("event_type") == "error":
                            self.logger.error(
                                "worker.run_agent.event_error",
                                request_id=active_request_id,
                                payload=current_event,
                            )
                        if "worker_exception" in current_event:
                            error_message = str(
                                current_event.get("worker_exception", "Worker failure")
                            )
                            if not agent_started:
                                yield next_event("agent_start", {"status": "started"})
                                agent_started = True
                            yield next_event(
                                "error",
                                {"message": error_message, "fatal": True},
                            )
                            yield next_event("agent_end", {"status": "failed"})
                            yield next_event("stream_end", {"status": "failed"})
                            terminal_event_emitted = True
                            break
                        if current_event.get("event_type") == "stream_end":
                            yield current_event
                            terminal_event_emitted = True
                            break
                        yield current_event

                    if terminal_event_emitted:
                        if future.done():
                            try:
                                future.result(timeout=1)
                            except Exception as e:
                                self.logger.error(
                                    "worker.run_agent.future_error",
                                    request_id=active_request_id,
                                    error=str(e),
                                )
                        self.logger.info(
                            "worker.run_agent.done", request_id=active_request_id
                        )
                        break

                    if future.done() and event is None and not events_to_process:
                        exception = future.exception()
                        if exception is not None:
                            error_message = str(exception)
                        else:
                            error_message = (
                                "Worker process ended before terminal stream event"
                            )
                        self.logger.error(
                            "worker.run_agent.future_ended_early",
                            request_id=active_request_id,
                            error=error_message,
                        )
                        if not agent_started:
                            yield next_event("agent_start", {"status": "started"})
                            agent_started = True
                        yield next_event(
                            "error",
                            {"message": error_message, "fatal": True},
                        )
                        yield next_event("agent_end", {"status": "failed"})
                        yield next_event("stream_end", {"status": "failed"})
                        terminal_event_emitted = True
                        break
                except Exception as e:
                    self.logger.error(
                        "worker.run_agent.communication_error",
                        request_id=active_request_id,
                        error=str(e),
                    )
                    if not agent_started:
                        yield next_event("agent_start", {"status": "started"})
                        agent_started = True
                    yield next_event(
                        "error",
                        {"message": f"Worker communication error: {e}", "fatal": True},
                    )
                    yield next_event("agent_end", {"status": "failed"})
                    yield next_event("stream_end", {"status": "failed"})
                    terminal_event_emitted = True
                    break
        finally:
            if not terminal_event_emitted:
                if not agent_started:
                    yield next_event("agent_start", {"status": "started"})
                yield next_event("agent_end", {"status": "failed"})
                yield next_event("stream_end", {"status": "failed"})
            if active_request_id in self.pending_inputs:
                del self.pending_inputs[active_request_id]

    async def _queue_get_async(self, queue, timeout: float | None = None):
        loop = asyncio.get_running_loop()

        def get_with_timeout():
            try:
                if timeout is None:
                    return queue.get()
                return queue.get(timeout=timeout)
            except Empty:
                return None

        return await loop.run_in_executor(None, get_with_timeout)

    async def _queue_get_nowait_async(self, queue):
        loop = asyncio.get_running_loop()

        def get_nowait():
            try:
                return queue.get_nowait()
            except Empty:
                return None

        return await loop.run_in_executor(None, get_nowait)


def _execute_agent(
    message: str,
    session_id: str,
    result_queue: Any,
    input_queue: Any,
    context: ExecutionContext,
) -> None:
    async def run_async():
        from core.agent import Agent
        from core.logger import Logger
        from core.config import Config
        from core.skills import SkillsManager
        from core.tools import ToolsManager
        from core.sessions import SessionsManager
        from core.context import ContextManager
        from core.providers.manager import ProvidersManager

        logger = Logger.get("worker.py")
        logger.info("worker.execute_agent.start", request_id=context.request_id)

        config = Config.load()
        providers = ProvidersManager()
        provider = providers.create(config.provider.active)

        tools = ToolsManager()
        skills = SkillsManager()
        sessions = SessionsManager()
        ctx_manager = ContextManager()

        agent = Agent(provider, tools, skills, sessions, ctx_manager)

        async for event in agent.stream(
            message,
            session_id=session_id,
            context=context,
            input_queue=input_queue,
        ):
            result_queue.put(event)

    try:
        asyncio.run(run_async())
    except Exception as e:
        Logger.get("worker.py").error(
            "worker.execute_agent.error",
            request_id=context.request_id,
            error=str(e),
        )
        result_queue.put({"worker_exception": str(e)})
