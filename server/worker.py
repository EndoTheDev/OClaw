import asyncio
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Manager, Queue

from core.logger import Logger


class AgentWorker:
    def __init__(self, num_processes: int = 4, timeout: int = 300):
        self.logger = Logger.get("worker.py")
        self.num_processes = num_processes
        self.timeout = timeout
        self._executor: ProcessPoolExecutor | None = None
        self._manager: Manager | None = None  # type: ignore
        self.pending_inputs = {}

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

    async def run_agent(self, message: str, request_id: str | None = None):
        if not self._executor or not self._manager:
            self.logger.error("worker.run_agent.not_started", request_id=request_id)
            raise RuntimeError("Worker pool not started. Call start() first.")

        self.logger.info(
            "worker.run_agent.start", request_id=request_id, message_chars=len(message)
        )

        result_queue = self._manager.Queue()
        input_queue = self._manager.Queue()

        if request_id:
            self.pending_inputs[request_id] = input_queue

        future = self._executor.submit(
            _execute_agent,
            message,
            result_queue,
            input_queue,
            request_id,
        )

        try:
            while True:
                try:
                    event = await self._queue_get_async(result_queue)
                    if event.get("type") == "done":
                        try:
                            future.result(timeout=1)
                        except Exception as e:
                            self.logger.error(
                                "worker.run_agent.future_error",
                                request_id=request_id,
                                error=str(e),
                            )
                            yield {"type": "error", "message": str(e)}
                        self.logger.info("worker.run_agent.done", request_id=request_id)
                        yield event
                        break
                    if event.get("type") == "error":
                        self.logger.error(
                            "worker.run_agent.event_error",
                            request_id=request_id,
                            payload=event,
                        )
                    yield event
                except Exception as e:
                    self.logger.error(
                        "worker.run_agent.communication_error",
                        request_id=request_id,
                        error=str(e),
                    )
                    yield {
                        "type": "error",
                        "message": f"Worker communication error: {e}",
                    }
                    break
        finally:
            if request_id and request_id in self.pending_inputs:
                del self.pending_inputs[request_id]

    async def _queue_get_async(self, queue):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, queue.get)


def _execute_agent(
    message: str, result_queue: Queue, input_queue: Queue, request_id: str | None
) -> None:
    async def run_async():
        from core.agent import Agent
        from core.logger import Logger
        from core.config import Config
        from core.tools import ToolsManager

        logger = Logger.get("worker.py")
        logger.info("worker.execute_agent.start", request_id=request_id)

        config = Config.load()
        if config.provider == "openai":
            from core.providers.openai import OpenAIProvider

            provider = OpenAIProvider()
        elif config.provider == "anthropic":
            from core.providers.anthropic import AnthropicProvider

            provider = AnthropicProvider()
        elif config.provider == "ollama":
            from core.providers.ollama import OllamaProvider

            provider = OllamaProvider()

        tools = ToolsManager()

        agent = Agent(provider, tools)

        async for event in agent.stream(
            message, request_id=request_id, input_queue=input_queue
        ):
            result_queue.put(event)

    try:
        asyncio.run(run_async())
        result_queue.put({"type": "done"})
    except Exception as e:
        Logger.get("worker.py").error(
            "worker.execute_agent.error",
            request_id=request_id,
            error=str(e),
        )
        result_queue.put({"type": "error", "message": str(e)})
        result_queue.put({"type": "done"})
