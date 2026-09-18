"""响应压缩中间件（gzip / brotli）+ 静态资源缓存头。

为什么自己写而不用 starlette.middleware.gzip.GZipMiddleware：
  1. GZipMiddleware 不区分内容类型 —— 会去压缩已经是「高度压缩格式」的图片
     （PNG/WebP/JPEG）、字体（woff2）与 wasm，白耗 CPU 且体积几乎不降；
  2. 它对所有响应一视同仁，包括 SSE（`text/event-stream`）。BaseHTTPMiddleware 下
     虽然仍是流式转发，但一旦上层把响应整体缓冲（或未来换成其它 ASGI 中间件），
     AI 推理的逐字输出就会变成「等到结束一次性蹦出来」——这是本项目在线上真实
     踩过、且最难复现的一类体验问题，因此这里显式给 SSE 让路。

压缩阈值 512B：小于此值的响应压缩收益为负（gzip 帧头本身就几十字节）。

平台前端是纯静态资源 + JSON 接口，没有任何 nginx 层做压缩，因此这层很关键：
主包 284KB → 传输 99KB，CSS 82KB → 16KB，JSON 接口普遍下降 70%+。
"""
from __future__ import annotations

import gzip as _gzip
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import ASGIApp

try:  # brotli 未安装时自动降级为纯 gzip
    import brotli  # type: ignore

    _HAS_BROTLI = True
except Exception:  # pragma: no cover - 可选依赖
    brotli = None  # type: ignore
    _HAS_BROTLI = False


# 压缩收益明显的类型（文本类；匹配用「子串」而非精确相等，以兼容 charset 后缀）
_COMPRESSIBLE = (
    "text/",
    "application/javascript",
    "application/json",
    "application/xml",
    "application/x-ndjson",
    "image/svg+xml",
    "application/manifest+json",
)
# 零收益 / 负收益：已是压缩格式
_SKIP = (
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/avif",
    "font/woff",
    "font/woff2",
    "font/ttf",
    "font/otf",
    "application/pdf",
    "application/zip",
    "application/gzip",
    "application/octet-stream",
    "video/",
    "audio/",
)
# 流式/实时通道：绝不压缩（压缩会引入缓冲，破坏逐段到达）
_STREAMING = (
    "text/event-stream",
    "multipart/x-mixed-replace",
)

MIN_COMPRESS_SIZE = 512


def _compressible(content_type: str) -> bool:
    c = (content_type or "").lower()
    if not c:
        return False
    if any(s in c for s in _STREAMING):
        return False
    if any(s in c for s in _SKIP):
        return False
    return any(s in c for s in _COMPRESSIBLE)


def _pick_encoding(accept: str) -> str | None:
    a = (accept or "").lower()
    if _HAS_BROTLI and "br" in a:
        return "br"
    if "gzip" in a:
        return "gzip"
    return None


class CompressionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, minimum_size: int = MIN_COMPRESS_SIZE,
                 compressible: Iterable[str] = ()) -> None:
        super().__init__(app)
        self.minimum_size = minimum_size
        # 允许调用方追加自定义类型（预留扩展点）
        self._extra = tuple(compressible)

    @staticmethod
    def _rebuild(response, raw: bytes) -> Response:
        """用已读出的字节重建一个等价响应（headers 去掉长度，交由 Response 自行计算）。"""
        headers = {k: v for k, v in response.headers.items()
                   if k.lower() not in ("content-length", "content-encoding")}
        return Response(
            content=raw,
            status_code=response.status_code,
            headers=headers,
            background=response.background,
        )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # StreamingResponse（SSE / 大文件流）直接放行：不读 body，保持逐段到达。
        # 注意判断必须是类型判断 —— Starlette 的普通 Response 也有 body_iterator 属性，
        # 用 hasattr 会把所有响应都当成流式、导致压缩完全失效（踩过）。
        if isinstance(response, StreamingResponse):
            return response

        headers = response.headers
        ctype = headers.get("content-type", "")
        if "content-encoding" in headers:
            return response
        if not _compressible(ctype) and not any(s in ctype for s in self._extra):
            return response

        # 取原始字节：普通 Response 直接读 .body；BaseHTTPMiddleware 经 call_next 返回的是
        # 它内部的流式包装对象（没有 .body），需要把迭代器收干。注意一旦收干就必须用收干到的
        # 内容重建响应 —— 直接 return 原响应会得到空 body（迭代器只能消费一次，踩过）。
        raw = getattr(response, "body", None)
        streamed = raw is None
        if streamed:
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode())
            raw = b"".join(chunks)
        if not isinstance(raw, (bytes, bytearray)) or len(raw) < self.minimum_size:
            return response if not streamed else self._rebuild(response, raw)

        encoding = _pick_encoding(request.headers.get("accept-encoding", ""))
        if not encoding:
            return response if not streamed else self._rebuild(response, raw)

        payload = brotli.compress(bytes(raw), quality=4) if encoding == "br" \
            else _gzip.compress(bytes(raw), compresslevel=5)

        headers["Content-Encoding"] = encoding
        headers["Content-Length"] = str(len(payload))
        # 同一 URL 可能返回 gzip / br / 明文，必须声明按请求头分派
        vary = headers.get("Vary")
        if not vary or "accept-encoding" not in vary.lower():
            headers["Vary"] = "Accept-Encoding" if not vary else f"{vary}, Accept-Encoding"

        return Response(
            content=payload,
            status_code=response.status_code,
            headers=dict(headers),
            media_type=response.media_type,
            background=response.background,
        )
