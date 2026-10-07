# -*- coding: utf-8 -*-
# @File     : yamibo.py
# @Time     : 2021/04/07 15:48
# @Author   : Jckling

import os
import re
import time

from curl_cffi import requests as cffi_requests
from lxml import html
from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, sync_playwright

# info
USERNAME = os.environ.get("YAMIBO_USERNAME")
PASSWORD = os.environ.get("YAMIBO_PASSWORD")
msg = []

BASE_URL = "https://bbs.yamibo.com"

SESSION = cffi_requests.Session()

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "referer": "https://bbs.yamibo.com/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
}


def _forum_ready(status, text):
    """Require a real Discuz page, not just a challenge cookie."""
    return status == 200 and any(marker in text for marker in (
        'id="nv_forum"', 'id="hd"', 'name="formhash"', 'Powered by Discuz!',
    ))


def _verify_forum(url=None):
    response = SESSION.get(
        url or f"{BASE_URL}/forum.php", headers=HEADERS, impersonate="chrome", timeout=15,
    )
    return _forum_ready(response.status_code, response.text)


def _browser_cookies():
    """Keep the authenticated HTTP session when revisiting a challenged page."""
    cookies = []
    for cookie in SESSION.cookies.jar:
        if cookie.domain.lstrip(".") not in ("bbs.yamibo.com", "yamibo.com"):
            continue
        if cookie.name == "nox_jst_v1" or cookie.is_expired():
            continue
        cookies.append({"name": cookie.name, "value": cookie.value,
                        "domain": cookie.domain, "path": cookie.path or "/",
                        "secure": cookie.secure})
    return cookies


def solve_waf(url=None):
    """Wait for browser challenge cookies, then verify the HTTP session works."""
    try:
        url = url or f"{BASE_URL}/forum.php"
        if _verify_forum(url):
            return True
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=HEADERS["user-agent"])
                context.add_cookies(_browser_cookies())
                page = context.new_page()
                # Ads and analytics may never go idle. Cookie creation can also
                # happen after navigation, so neither event defines success.
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeoutError:
                    pass  # The challenge may already be running in the page.
                deadline = time.monotonic() + 30
                last_cookie = None
                while time.monotonic() < deadline:
                    cookies = context.cookies([BASE_URL])
                    nox_cookie = next((c for c in cookies if c["name"] == "nox_jst_v1" and c["value"]), None)
                    if nox_cookie and nox_cookie["value"] != last_cookie:
                        last_cookie = nox_cookie["value"]
                        SESSION.cookies.set(
                            "nox_jst_v1", last_cookie,
                            domain=nox_cookie["domain"], path=nox_cookie.get("path", "/"),
                        )
                        if _verify_forum(url):
                            return True
                    page.wait_for_timeout(500)
                msg.append({"name": "登录信息", "value": "WAF 挑战未通过：未获得可用通行 Cookie，请尝试可正常访问论坛的 self-hosted runner"})
            finally:
                browser.close()
    except PlaywrightError:
        msg.append({"name": "登录信息", "value": "WAF 浏览器运行失败，请检查 Chromium 安装和 runner 网络"})
    except cffi_requests.RequestsError:
        msg.append({"name": "登录信息", "value": "论坛连接失败，请检查 runner 网络"})
    return False


def login():
    """Login via Discuz member.php and return True if successful."""
    global msg

    if not solve_waf():
        return False

    # Step 1: GET login page to extract formhash and loginhash
    r = SESSION.get(
        f"{BASE_URL}/member.php",
        headers=HEADERS,
        params={
            "mod": "logging",
            "action": "login",
            "infloat": "yes",
            "frommessage": "",
            "inajax": "1",
            "ajaxtarget": "messagelogin",
        },
        impersonate="chrome",
    )

    formhash_match = re.search(r'name="formhash"\s+value="([a-f0-9]+)"', r.text)
    loginhash_match = re.search(r'loginhash=([a-zA-Z0-9]+)', r.text)

    if not formhash_match:
        msg.append({"name": "登录信息", "value": "登录失败，无法获取 formhash"})
        return False

    formhash = formhash_match.group(1)
    loginhash = loginhash_match.group(1) if loginhash_match else ""

    # Step 2: POST login
    r2 = SESSION.post(
        f"{BASE_URL}/member.php",
        headers={
            **HEADERS,
            "content-type": "application/x-www-form-urlencoded",
        },
        params={
            "mod": "logging",
            "action": "login",
            "loginsubmit": "yes",
            "frommessage": "",
            "loginhash": loginhash,
            "inajax": "1",
        },
        data={
            "formhash": formhash,
            "referer": f"{BASE_URL}/forum.php",
            "username": USERNAME,
            "password": PASSWORD,
            "questionid": "0",
            "answer": "",
            "cookietime": "2592000",
        },
        impersonate="chrome",
    )

    if "succeedhandle" in r2.text or "succeed" in r2.text:
        msg.append({"name": "登录信息", "value": "登录成功"})
        return True
    elif "登录失败" in r2.text:
        error_match = re.search(r'<p[^>]*>([^<]+)</p>', r2.text)
        error_msg = error_match.group(1) if error_match else "登录失败"
        msg.append({"name": "登录信息", "value": error_msg})
        return False
    else:
        msg.append({"name": "登录信息", "value": f"登录失败，{r2.text[:100]}"})
        return False


def _is_waf(response):
    return any(marker in response.text for marker in ("window.__nox", "nox_202", "waf-jschallenge"))


def _get_sign_response():
    url = f"{BASE_URL}/plugin.php?id=zqlj_sign"
    response = SESSION.get(url, headers=HEADERS, impersonate="chrome", timeout=15)
    if _is_waf(response) and solve_waf(url):
        # Recover only once, for this read-only page. Never replace auth cookies
        # with cookies from a guest browser context.
        response = SESSION.get(url, headers=HEADERS, impersonate="chrome", timeout=15)
    return response


def get_sign_page():
    """Fetch sign page.

    Returns (sign_hash, already_signed, page_text) or (None, None, None) if not logged in.
    """
    r = _get_sign_response()

    global msg
    if _is_waf(r) or r.status_code in (403, 405):
        msg.append({"name": "签到信息", "value": f"签到页仍被 WAF 拦截（HTTP {r.status_code}），请检查 runner 网络"})
        return None, None, None
    if "需要先登录" in r.text or "请先登录" in r.text:
        msg.append({"name": "登录信息", "value": "登录失败，Cookie 可能已经失效"})
        return None, None, None

    if r.status_code != 200:
        msg.append({"name": "签到信息", "value": f"签到页请求失败（HTTP {r.status_code}）"})
        return None, None, None
    tree = html.fromstring(r.text or "<html></html>")
    sign_hash = None
    for href in tree.xpath('//a/@href'):
        if "zqlj_sign" not in href:
            continue
        match = re.search(r'(?:[?&])sign=([a-f0-9]+)(?:&|$)', href)
        if match:
            sign_hash = match.group(1)
            break
    buttons = tree.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " btna ")]')
    btn_text = " ".join(button.text_content().strip() for button in buttons)
    already_signed = "今日已打卡" in btn_text or "今日已签到" in btn_text
    if not already_signed and not sign_hash:
        msg.append({"name": "签到信息", "value": "签到页已返回，但未识别到打卡链接或已打卡状态，页面结构可能已变更"})
        return None, None, None

    return sign_hash, already_signed, r.text


def check_in(sign_hash):
    """Perform sign-in by visiting the sign URL with the one-time hash."""
    url = f"{BASE_URL}/plugin.php?id=zqlj_sign&sign={sign_hash}"
    r = SESSION.get(url, headers=HEADERS, impersonate="chrome")

    global msg
    if "打卡成功" in r.text:
        msg.append({"name": "签到信息", "value": "签到成功"})
        return True, r.text
    elif "打过卡" in r.text:
        msg.append({"name": "签到信息", "value": "今日已签到"})
        return True, r.text
    elif "需要先登录" in r.text:
        msg.append({"name": "签到信息", "value": "登录失败，Cookie 可能已经失效"})
        return False, r.text
    else:
        msg.append({"name": "签到信息", "value": "签到失败，未能从页面获取结果"})
        return False, r.text


def query_stats(page_text):
    """Query sign stats from sign page HTML and credit info from credit page."""
    global msg

    stats_map = {
        "最近打卡": "签到时间",
        "本月打卡": "本月签到",
        "连续打卡": "连续签到",
        "累计打卡": "累计签到",
        "最近奖励": "最近奖励",
    }
    for kw, name in stats_map.items():
        match = re.search(rf'{kw}：([^<]+)', page_text)
        if match:
            msg.append({"name": name, "value": match.group(1)})

    url = f"{BASE_URL}/home.php?mod=spacecp&ac=credit"
    r = SESSION.get(url, headers=HEADERS, impersonate="chrome")
    tree = html.fromstring(r.content)
    items = tree.xpath('//ul[@class="creditl mtm bbda cl"]/li')

    credit = {}
    for item in items:
        text = item.text_content().strip()
        match = re.match(r'(\S+):\s*(\S+)', text)
        if match:
            name, value = match.group(1), match.group(2)
            if name not in credit:
                credit[name] = value

    if credit:
        parts = [f"{k} {v}" for k, v in credit.items()]
        msg.append({"name": "账户余额", "value": "，".join(parts)})
    else:
        msg.append({"name": "账户余额", "value": "查询余额失败"})


def main():
    global msg
    msg = []
    if not USERNAME or not PASSWORD:
        return "No YAMIBO_USERNAME or YAMIBO_PASSWORD set"

    if not login():
        return "\n".join([f"{one.get('name')}: {one.get('value')}" for one in msg])

    sign_hash, already_signed, page_text = get_sign_page()
    if sign_hash is None and already_signed is None:
        return "\n".join([f"{one.get('name')}: {one.get('value')}" for one in msg])

    if not already_signed and sign_hash:
        check_in(sign_hash)
        r2 = _get_sign_response()
        page_text = r2.text
    else:
        msg.append({"name": "签到信息", "value": "今日已签到，无需重复签到"})

    query_stats(page_text)

    return "\n".join([f"{one.get('name')}: {one.get('value')}" for one in msg])


if __name__ == "__main__":
    print(" Yamibo 签到开始 ".center(60, "="))
    print(main())
    print(" Yamibo 签到结束 ".center(60, "="), "\n")
