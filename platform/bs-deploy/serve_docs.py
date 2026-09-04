"""文档站静态服务（生产容器内运行）。

文档站已并入平台同源访问：浏览器只访问平台（如 http://<host>:40014），
平台后端把 /docs/* 保留前缀转发到本容器（http://<host>:40183/docs/*）。
因此本服务把 /docs 前缀请求映射到 dist 目录（剥除前缀后取文件），
同时兼容根路径直访（/assets/... → dist/assets/...，无前缀剥除）。

用法：python3 serve_docs.py [--port 40183] [--directory /site/dist]
"""
import argparse
import http.server
import os
import posixpath


class DocsHandler(http.server.SimpleHTTPRequestHandler):
    """剥 /docs 前缀后落到 dist 目录的静态处理器。"""

    def translate_path(self, path: str) -> str:
        # 兼容两种入口：/docs/xxx（平台反代入口）与 /xxx（根路径直访）
        segments = [s for s in path.split("/") if s]
        if segments and segments[0] == "docs":
            segments = segments[1:]
        path = posixpath.normpath("/" + "/".join(segments))
        words = [w for w in path.split("/") if w]
        target = self.directory  # type: ignore[attr-defined]
        for w in words:
            target = os.path.join(target, w)
        return target

    def end_headers(self) -> None:
        # 静态产物每次构建 hash 变化，禁止缓存避免旧入口
        if not self.path.startswith("/docs/assets/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="docs-site 静态服务（/docs 前缀兼容）")
    parser.add_argument("--port", type=int, default=40183)
    parser.add_argument("--directory", default="/site/dist")
    args = parser.parse_args()
    os.chdir(args.directory)
    handler = lambda *a, **kw: DocsHandler(*a, directory=args.directory, **kw)  # noqa: E731
    server = http.server.ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    print(f"docs-site serving {args.directory} on :{args.port} (prefix /docs)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
