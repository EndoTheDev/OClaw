import uvicorn

from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel

from fastapi.responses import StreamingResponse

from core.config import Config
from core.sessions import SessionsManager
from server.worker import AgentWorker


class ChatRequest(BaseModel):
    message: str


class AgentGateway:
    def __init__(self, num_workers: int | None = None, timeout: int | None = None):
        config = Config.load()
        self.num_workers = num_workers or config.num_workers
        self.timeout = timeout or config.worker_timeout
        self.worker = AgentWorker(num_processes=self.num_workers, timeout=self.timeout)
        self.sessions_manager = SessionsManager()
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            self.worker.start()
            yield
            self.worker.stop(timeout=self.timeout)

        app = FastAPI(title="OClaw Agent Server", lifespan=lifespan)

        @app.get("/health")
        async def health_check():
            config = Config.load()

            return {
                "status": "healthy",
                "workers": self.num_workers,
                "timeout": self.timeout,
                "ollama_host": config.ollama_host,
                "model": config.model,
            }

        @app.post("/chat/stream")
        async def chat_stream(request: ChatRequest):
            async def generate():
                import json

                async for event in self.worker.run_agent(request.message):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )

        @app.post("/admin/restart")
        async def restart_workers():
            self.worker.restart()
            return {"status": "workers restarted"}

        return app

    def run(self, host: str | None = None, port: int | None = None):
        config = Config.load()

        uvicorn.run(
            self.app, host=host or config.server_host, port=port or config.server_port
        )


if __name__ == "__main__":
    server = AgentGateway()
    server.run()
