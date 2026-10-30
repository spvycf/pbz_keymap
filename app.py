"""PBZ 手柄按键自定义工具（本地网页 GUI）。

运行：
    python3 app.py
然后浏览器会自动打开 http://127.0.0.1:8765
"""

import argparse
import base64
import hashlib
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import gvas
import keymap

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, "static")
ASSET = os.path.join(ROOT, "assets", "EnhancedInputUserSettings.sav")

OUTPUT_NAME = "EnhancedInputUserSettings.sav"

_lock = threading.Lock()
_source = {
    "data": open(ASSET, "rb").read(),
    "name": "内置模板 EnhancedInputUserSettings.sav",
}


def _parse_model(data: bytes) -> dict:
    doc = gvas.parse_document(data)
    model = keymap.build_model(doc)
    model["source_name"] = _source["name"]
    model["sha256"] = hashlib.sha256(data).hexdigest()
    model["size"] = len(data)
    return model


def _json(handler, obj, status=200):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _error(handler, message, status=400):
    _json(handler, {"error": str(message)}, status)


class Handler(BaseHTTPRequestHandler):
    server_version = "PBZKeymap/1.0"

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                return self._static("index.html", "text/html; charset=utf-8")
            if path == "/api/state":
                with _lock:
                    return _json(self, _parse_model(_source["data"]))
            if path == "/api/template":
                with _lock:
                    data = _source["data"]
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{OUTPUT_NAME}"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            return _error(self, "not found", 404)
        except Exception as exc:  # noqa: BLE001
            return _error(self, f"{type(exc).__name__}: {exc}", 500)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""
            if path == "/api/upload":
                return self._upload(body)
            if path == "/api/generate":
                return self._generate(body)
            if path == "/api/reset":
                with _lock:
                    _source["data"] = open(ASSET, "rb").read()
                    _source["name"] = "内置模板 EnhancedInputUserSettings.sav"
                    return _json(self, _parse_model(_source["data"]))
            return _error(self, "not found", 404)
        except gvas.FormatError as exc:
            return _error(self, f"文件结构不支持：{exc}", 400)
        except keymap.KeymapError as exc:
            return _error(self, str(exc), 400)
        except Exception as exc:  # noqa: BLE001
            return _error(self, f"{type(exc).__name__}: {exc}", 500)

    def _static(self, name, ctype):
        path = os.path.join(STATIC, name)
        if not os.path.isfile(path):
            return _error(self, "not found", 404)
        with open(path, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _upload(self, body):
        if not body:
            raise keymap.KeymapError("上传内容为空")
        model = _parse_model(body)
        with _lock:
            _source["data"] = body
            _source["name"] = "用户上传的存档"
        model["source_name"] = _source["name"]
        return _json(self, model)

    def _generate(self, body):
        payload = json.loads(body.decode("utf-8"))
        profile_id = payload.get("profileId")
        set_current = bool(payload.get("setCurrent", True))
        bindings = payload.get("bindings", [])
        if not profile_id:
            raise keymap.KeymapError("缺少 profileId")

        with _lock:
            src = _source["data"]

        src_doc = gvas.parse_document(src)
        out_doc = gvas.parse_document(src)
        warnings = keymap.apply_edits(out_doc, profile_id, bindings, set_current)
        out = gvas.serialize_document(out_doc)

        # 自检：重新解析并核对
        check_doc = gvas.parse_document(out)
        if gvas.serialize_document(check_doc) != out:
            raise keymap.KeymapError("自检失败：输出的往返序列化不一致")

        sig_src = keymap.binding_signature(src_doc)
        sig_out = keymap.binding_signature(check_doc)
        for pid, sig in sig_src.items():
            if pid != profile_id and sig_out.get(pid) != sig:
                raise keymap.KeymapError(f"自检失败：非目标档 {pid} 被意外修改")

        target = keymap.get_profile(check_doc, profile_id)
        actual = {(b.action, b.slot): b.key for b in target.bindings}
        for item in bindings:
            got = actual.get((item["action"], item["slot"]))
            if got != item["key"]:
                raise keymap.KeymapError(
                    f"自检失败：{item['action']}/{item['slot']} 期望 {item['key']}，实际 {got}"
                )
        if set_current and keymap.current_profile_id(check_doc) != profile_id:
            raise keymap.KeymapError("自检失败：当前配置档未切换")

        return _json(
            self,
            {
                "filename": OUTPUT_NAME,
                "data_b64": base64.b64encode(out).decode("ascii"),
                "size": len(out),
                "sha256": hashlib.sha256(out).hexdigest(),
                "profile": profile_id,
                "current_profile": keymap.current_profile_id(check_doc),
                "warnings": warnings,
                "header": check_doc.header,
            },
        )


def main():
    parser = argparse.ArgumentParser(description="PBZ 手柄按键自定义工具")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"PBZ 按键工具已启动：{url}")
    print("按 Ctrl+C 停止。")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()