"""compression.CompressionMiddleware 行为回归测试。

背景：平台前端全部静态资源由 FastAPI 托管（无 nginx 层），此前是裸传输 —— 首屏主包 284KB、
CSS 76KB 全部原样下发。补压缩中间件后首屏传输量下降约 50%（配合 immutable 缓存）。

本测试锁住中间件最容易出错的四条边界：
1. 文本类大响应必须真的被压缩，且能还原；
2. 图片/字体等二进制类型零开销透传（再压缩无收益，纯耗 CPU）；
3. 小于阈值的响应不压缩（避免为几十字节多花一次 gzip）；
4. **SSE 推理流（text/event-stream）绝不能被缓冲** —— 这是当初没有直接用
   Starlette GZipMiddleware 的唯一原因：它会攒够整个响应才下发，
   前端表现为「点了半天没反应，最后一次性蹦出来」。
"""
import gzip
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI  # noqa: E402
from starlette.responses import Response  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.compression import CompressionMiddleware  # noqa: E402

BIG_JS = b"function hello(){return 1}\n" * 200   # ~5.4KB，明显高于压缩阈值
TINY_JSON = b'{"ok":true}'                        # 11B，低于压缩阈值
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 5000


def _make_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(CompressionMiddleware)

    @app.get("/big.js")
    def big_js():
        return Response(BIG_JS, media_type="application/javascript")

    @app.get("/tiny.json")
    def tiny():
        return Response(TINY_JSON, media_type="application/json")

    @app.get("/img.png")
    def img():
        return Response(FAKE_PNG, media_type="image/png")

    @app.get("/stream")
    def stream():
        from fastapi.responses import StreamingResponse

        def gen():
            yield b"data: one\n\n"
            yield b"data: two\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    return TestClient(app)


c = _make_client()
GZIP = {"Accept-Encoding": "gzip"}


def test_text_response_is_compressed():
    r = c.get("/big.js", headers=GZIP)
    assert r.headers["content-encoding"] == "gzip"
    assert "accept-encoding" in r.headers["vary"].lower()
    # httpx 会自动按 content-encoding 解压，故 r.content 已是还原后的明文
    assert r.content == BIG_JS
    assert int(r.headers["content-length"]) < len(BIG_JS)


def test_client_without_gzip_gets_plain_body():
    r = c.get("/big.js", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in r.headers
    assert r.content == BIG_JS


def test_binary_and_small_responses_are_untouched():
    # 图片：零收益，必须原样直传
    r = c.get("/img.png", headers=GZIP)
    assert "content-encoding" not in r.headers
    assert r.content == FAKE_PNG
    # 小响应：省一次 CPU
    r2 = c.get("/tiny.json", headers=GZIP)
    assert "content-encoding" not in r2.headers
    assert r2.content == TINY_JSON


def test_sse_stream_is_not_buffered():
    with c.stream("GET", "/stream", headers=GZIP) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert "content-encoding" not in resp.headers, "SSE 被压缩会导致整段流式输出延迟到结束才可见"
        chunks = [ch for ch in resp.iter_bytes() if ch]
    joined = b"".join(chunks)
    assert b"one" in joined and b"two" in joined
    # 首块必须就是第一段：若中间件缓冲，这里会变成一次性聚合响应
    assert chunks[0].startswith(b"data: one"), chunks


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("application/javascript", True),
        ("text/css", True),
        ("application/json", True),
        ("image/svg+xml", True),
        ("image/webp", False),
        ("font/woff2", False),
        ("application/wasm", False),
        ("text/event-stream", False),
    ],
)
def test_content_type_decision(content_type, expected):
    from app.compression import _compressible

    assert _compressible(content_type) is expected


def test_minimum_size_threshold():
    """阈值边界：小于阈值不压（省 CPU），超过才压。"""
    app = FastAPI()
    app.add_middleware(CompressionMiddleware, minimum_size=50)

    @app.get("/small")
    def small():
        return Response(b"x" * 40, media_type="text/plain")

    @app.get("/big")
    def big():
        return Response(b"x" * 200, media_type="text/plain")

    cl = TestClient(app)
    r1 = cl.get("/small", headers=GZIP)
    assert "content-encoding" not in r1.headers and r1.content == b"x" * 40
    r2 = cl.get("/big", headers=GZIP)
    assert r2.headers["content-encoding"] == "gzip" and r2.content == b"x" * 200


def test_compressed_payload_is_real_gzip():
    """绕过 httpx 自动解压（httpx 会按 content-encoding 透明解码），确认线上字节流本身是 gzip。
    直接用 gzip 解压中间件产物，防止「只改了响应头、内容仍是明文」这类假压缩。"""
    from app.compression import CompressionMiddleware as CM

    # 直接驱动中间件：构造一个最小 ASGI app，收集原始字节
    import anyio

    async def app(scope, receive, send):
        resp = Response(BIG_JS, media_type="application/javascript")
        await resp(scope, receive, send)

    mw = CM(app)
    captured = {}

    async def send(message):
        if message["type"] == "http.response.start":
            captured["headers"] = dict((k.decode().lower(), v.decode()) for k, v in message["headers"])
        elif message["type"] == "http.response.body":
            captured.setdefault("body", b"")
            captured["body"] += message.get("body", b"")

    async def run():
        await mw({"type": "http", "method": "GET", "path": "/a.js", "headers": [(b"accept-encoding", b"gzip")]},
                 lambda: anyio.sleep(0), send)

    anyio.run(run)
    assert captured["headers"].get("content-encoding") == "gzip"
    assert gzip.decompress(captured["body"]) == BIG_JS
