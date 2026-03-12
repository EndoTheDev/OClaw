import asyncio
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Manager, Queue


class AgentWorker:

    def __init__(self, num_processes: int = 4, timeout: int = 300):
        self.num_processes = num_processes
        self.timeout = timeout
        self._executor: ProcessPoolExecutor | None = None
        self._manager: Manager | None = None  # type: ignore

    def start(self) -> None:
        self._manager = Manager()
        self._executor = ProcessPoolExecutor(
            max_workers=self.num_processes,
            max_tasks_per_child=1,
        )

    def stop(self, timeout: int | None = None) -> None:
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

    def restart(self) -> None:
        self.stop()
        self.start()

    async def run_agent(self, message: str):
        if not self._executor or not self._manager:
            raise RuntimeError("Worker pool not started. Call start() first.")

        result_queue = self._manager.Queue()

        future = self._executor.submit(
            _execute_agent,
            message,
            result_queue,
        )

        while True:
            try:
                event = await self._queue_get_async(result_queue)
                if event.get("type") == "done":
                    try:
                        future.result(timeout=1)
                    except Exception as e:
                        yield {"type": "error", "message": str(e)}
                    yield event
                    break
                yield event
            except Exception as e:
                yield {"type": "error", "message": f"Worker communication error: {e}"}
                break

    async def _queue_get_async(self, queue):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, queue.get)


def _execute_agent(message: str, result_queue: Queue) -> None:
    async def run_async():
        from core.agent import Agent
        from core.providers.ollama import OllamaProvider
        from core.tools import ToolsManager
        from tools.execute_shell import ExecuteShellTool
        from tools.read_file import ReadFileTool
        from tools.write_file import WriteFileTool

        provider = OllamaProvider()
        tools = ToolsManager()
        tools.register(ExecuteShellTool())
        tools.register(ReadFileTool())
        tools.register(WriteFileTool())

        agent = Agent(provider, tools)

        async for event in agent.stream(message):
            result_queue.put(event)

    try:
        asyncio.run(run_async())
        result_queue.put({"type": "done"})
    except Exception as e:
        result_queue.put({"type": "error", "message": str(e)})
        result_queue.put({"type": "done"})
