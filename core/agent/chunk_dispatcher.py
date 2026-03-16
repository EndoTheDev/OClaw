from typing import TYPE_CHECKING, AsyncGenerator

from ..logger import Logger
from ..providers.base import (
    DoneChunk,
    ErrorChunk,
    MetricsChunk,
    ResponseChunk,
    ThinkingChunk,
    ToolCallChunk,
    StreamingChunk,
)
from .types import StreamOutput

if TYPE_CHECKING:
    pass


class ChunkDispatcher:
    def __init__(self, logger: Logger | None = None):
        self.logger = logger or Logger.get("chunk_dispatcher.py")

    async def dispatch(
        self,
        chunk_stream: AsyncGenerator[StreamingChunk, None],
        session_id: str,
        request_id: str | None = None,
        iteration: int = 1,
    ) -> AsyncGenerator[StreamOutput, None]:
        async for chunk in chunk_stream:
            if isinstance(chunk, ResponseChunk):
                self.logger.debug(
                    "assistant.response.chunk",
                    session_id=session_id,
                    request_id=request_id,
                    iteration=iteration,
                    content=chunk.content,
                )
                output: StreamOutput = {"type": "token", "content": chunk.content}
                yield output

            elif isinstance(chunk, ThinkingChunk):
                self.logger.debug(
                    "assistant.thinking.chunk",
                    session_id=session_id,
                    request_id=request_id,
                    iteration=iteration,
                    content=chunk.content,
                )
                output: StreamOutput = {"type": "thinking", "content": chunk.content}
                yield output

            elif isinstance(chunk, ToolCallChunk):
                self.logger.info(
                    "assistant.tool_call",
                    session_id=session_id,
                    request_id=request_id,
                    iteration=iteration,
                    name=chunk.name,
                    id=chunk.id,
                    arguments=chunk.arguments,
                )
                output: StreamOutput = {
                    "type": "tool_call",
                    "name": chunk.name,
                    "id": chunk.id,
                    "args": chunk.arguments,
                }
                yield output

            elif isinstance(chunk, MetricsChunk):
                self.logger.info(
                    "assistant.metrics",
                    session_id=session_id,
                    request_id=request_id,
                    iteration=iteration,
                    data=chunk.data,
                )
                output: StreamOutput = {"type": "metrics", "data": chunk.data}
                yield output

            elif isinstance(chunk, DoneChunk):
                continue

            elif isinstance(chunk, ErrorChunk):
                self.logger.error(
                    "agent.error",
                    session_id=session_id,
                    request_id=request_id,
                    iteration=iteration,
                    message=chunk.error,
                )
                output: StreamOutput = {"type": "error", "message": chunk.error}
                yield output
                return
