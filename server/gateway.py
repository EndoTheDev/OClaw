import uvicorn
import uuid

from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel

from fastapi.responses import StreamingResponse, JSONResponse

from core.config import Config
from core.logger import Logger
from core.sessions import SessionsManager
from server.worker import AgentWorker


class ChatRequest(BaseModel):
    message: str
    session_id: str


class PermitRequest(BaseModel):
    request_id: str
    approved: bool


class AgentGateway:
    def __init__(self, num_workers: int | None = None, timeout: int | None = None):
        self.logger = Logger.get("gateway.py")
        config = Config.load()
        self.num_workers = num_workers or config.worker.num_processes
        self.timeout = timeout or config.worker.timeout
        self.worker = AgentWorker(num_processes=self.num_workers, timeout=self.timeout)
        self.sessions_manager = SessionsManager()
        self.app = self._create_app()
        self.logger.info(
            "gateway.init",
            num_workers=self.num_workers,
            timeout=self.timeout,
        )

    def _create_app(self) -> FastAPI:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            self.logger.info("gateway.lifespan.start")
            self.worker.start()
            yield
            self.worker.stop(timeout=self.timeout)
            self.logger.info("gateway.lifespan.stop")

        app = FastAPI(title="OClaw Agent Server", lifespan=lifespan)

        @app.get("/health")
        async def health_check():
            self.logger.info("gateway.health.request")
            config = Config.load()

            return {
                "status": "healthy",
                "workers": self.num_workers,
                "timeout": self.timeout,
                "provider": config.provider.active,
                "ollama_host": config.provider.ollama_host,
                "openai_host": config.provider.openai_host,
                "model": config.provider.model,
            }

        @app.post("/chat/stream")
        async def chat_stream(request: ChatRequest):
            request_id = str(uuid.uuid4())
            try:
                self.sessions_manager.get_session_by_id(request.session_id)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"error": f"Session not found: {request.session_id}"},
                )
            self.logger.info(
                "gateway.chat_stream.request",
                request_id=request_id,
                session_id=request.session_id,
                message_chars=len(request.message),
            )

            async def generate():
                import json

                async for event in self.worker.run_agent(
                    request.message, request.session_id, request_id=request_id
                ):
                    if event.get("event_type") == "error":
                        self.logger.error(
                            "gateway.chat_stream.error",
                            request_id=request_id,
                            payload=event,
                        )
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )

        @app.get("/sessions/list")
        async def list_sessions():
            sessions = self.sessions_manager.list_sessions()
            return {
                "sessions": [
                    {
                        "session_id": s.metadata.session_id,
                        "file_path": str(s.file_path),
                        "date_created": s.metadata.date_created,
                        "last_updated": s.metadata.last_updated,
                        "message_count": len(s.messages),
                    }
                    for s in sessions
                ]
            }

        @app.post("/sessions/new")
        async def create_session():
            session = self.sessions_manager.create_new_session()
            return {
                "session_id": session.metadata.session_id,
                "file_path": str(session.file_path),
                "date_created": session.metadata.date_created,
            }

        @app.post("/admin/restart")
        async def restart_workers():
            self.logger.info("gateway.admin.restart")
            self.worker.restart()
            return {"status": "workers restarted"}

        @app.post("/chat/permit")
        async def chat_permit(req: PermitRequest):
            self.logger.info(
                "gateway.chat_permit", request_id=req.request_id, approved=req.approved
            )
            if req.request_id in self.worker.pending_inputs:
                self.worker.pending_inputs[req.request_id].put(req.approved)
                return {"status": "ok"}
            return {"status": "error", "message": "Request ID not found or expired"}

        return app

    def run(self, host: str | None = None, port: int | None = None):
        config = Config.load()
        self.logger.info(
            "gateway.run",
            host=host or config.server.host,
            port=port or config.server.port,
        )

        uvicorn.run(
            self.app,
            host=host or config.server.host,
            port=port or config.server.port,
            access_log=False,
            log_level="warning",
        )


if __name__ == "__main__":
    server = AgentGateway()
    server.run()
