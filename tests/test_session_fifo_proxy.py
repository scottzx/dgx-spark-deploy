"""Exercise the real proxy routes without a GPU or a running llama-server."""

import asyncio
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import httpx


ROOT = Path(__file__).resolve().parents[1]
PROXY_COPIES = (
    ROOT / "scripts/03_start_service/session_fifo_proxy.py",
    ROOT / ".agents/skills/llm-session-cache-optimization/scripts/session_fifo_proxy.py",
)


class RecordedStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


class ProxyStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def request_proxy(self, source, status, payload, content_type):
        stream = RecordedStream([payload])
        saves = []

        def backend(request):
            if request.url.path == "/slots":
                return httpx.Response(200, json=[{"id": 0, "is_processing": False}])
            if request.url.path == "/v1/chat/completions":
                return httpx.Response(
                    status, headers={"content-type": content_type}, stream=stream
                )
            if request.url.path == "/slots/0" and request.url.params["action"] == "save":
                saves.append(json.loads(request.content))
                return httpx.Response(200, json={"saved": True})
            raise AssertionError(f"Unexpected backend request: {request.method} {request.url}")

        with tempfile.TemporaryDirectory() as cache:
            module = types.ModuleType("proxy_under_test")
            with patch.dict(os.environ, {"SLOT_CACHE_DIR": cache}):
                exec(compile(source.read_text(), str(source), "exec"), module.__dict__)
            await module.client.aclose()
            async with httpx.AsyncClient(
                base_url="http://backend", transport=httpx.MockTransport(backend)
            ) as backend_client:
                module.client = backend_client
                async with httpx.AsyncClient(
                    base_url="http://proxy", transport=httpx.ASGITransport(app=module.app)
                ) as frontend_client:
                    response = await frontend_client.post(
                        "/v1/chat/completions",
                        headers={"x-conversation-id": "regression"},
                        json={"stream": True, "messages": [{"role": "user", "content": "hello"}]},
                    )
                    # Let the response's scheduled snapshot request finish.
                    await asyncio.sleep(0)
            return response, stream.closed, saves

    async def test_streaming_backend_errors_keep_http_status_and_json(self):
        payload = b'{"error":{"message":"backend rejected request"}}'
        for source in PROXY_COPIES:
            for status in (400, 500):
                with self.subTest(source=str(source.relative_to(ROOT)), status=status):
                    response, closed, saves = await self.request_proxy(
                        source, status, payload, "application/json"
                    )
                    self.assertEqual(response.status_code, status)
                    self.assertEqual(response.content, payload)
                    self.assertEqual(response.headers["content-type"], "application/json")
                    self.assertTrue(closed)
                    self.assertEqual(saves, [])

    async def test_successful_sse_is_forwarded_and_snapshot_is_saved(self):
        payload = b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\ndata: [DONE]\n\n'
        for source in PROXY_COPIES:
            with self.subTest(source=str(source.relative_to(ROOT))):
                response, closed, saves = await self.request_proxy(
                    source, 200, payload, "text/event-stream"
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, payload)
                self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
                self.assertTrue(closed)
                self.assertEqual(saves, [{"filename": "sess_regression.bin"}])


if __name__ == "__main__":
    unittest.main()
