"""Run the standalone Auto_Checkin program and collect its plain-text report."""

import os
import subprocess
import sys
from html import escape
from pathlib import Path


def main():
    if not os.environ.get("GLADOS_COOKIE", "").strip():
        return "No GLADOS_COOKIE set"
    script = Path(__file__).resolve().parents[1] / "integrations/auto_checkin/glados_checkin.py"
    # Pass only credentials needed by this independent program.
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME",
                      "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "HTTPS_PROXY", "HTTP_PROXY",
                      "ALL_PROXY", "NO_PROXY", "GLADOS_COOKIE", "GLADOS_EMAIL",
                      "GLADOS_USER_AGENT"}}
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True,
            encoding="utf-8", env=env, timeout=60, check=False,
        )
    except subprocess.TimeoutExpired:
        return "签到程序超时，请稍后重试"
    except OSError:
        return "无法启动 GLaDOS 签到程序"
    if result.returncode:
        return "GLaDOS 签到程序执行失败，请检查配置"
    return escape(result.stdout.strip() or "GLaDOS 未返回签到结果")
