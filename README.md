# Daily-Bonus

<p>
    <a href="https://github.com/jckling/Daily-Bonus/stargazers"><img src="https://img.shields.io/github/stars/jckling/Daily-Bonus" alt="GitHub stars"></a>
    <a href="https://github.com/jckling/Daily-Bonus/network/members"><img src="https://img.shields.io/github/forks/jckling/Daily-Bonus" alt="GitHub forks"></a>
    <a href="https://github.com/jckling/Daily-Bonus/issues"><img src="https://img.shields.io/github/issues/jckling/Daily-Bonus" alt="GitHub issues"></a>
</p>

自动签到脚本，通过 GitHub Actions 定时执行，支持 Telegram 推送签到结果。

> 如果觉得有用，右上角点个 ⭐ Star 支持一下，感谢！

## 功能

| 站点 | 方式 | 奖励 |
|------|------|------|
| V2EX | Cookie | 铜币 |
| Bilibili | Cookie | 硬币 |
| Yamibo（百合会 / 300） | 账号密码 | 对象 |
| Yurifans | 账号密码 | 积分 |
| 赛马娘 | Cookie | 游戏内道具 + 积分 |
| 哔咔漫画 | 账号密码 | 经验 |
| 网易云音乐 | Cookie | 云贝签到 |
| GLaDOS | Cookie | 签到积分及剩余天数查询 |
| ~~FF14 商城~~ | ~~账号密码~~ | ~~积分~~ |

> ⚠️ **FF14 商城签到已废弃**。SDO 登录接口接入了 Geetest 风控，脚本登录会触发滑块验证码，无法自动绕过。

Telegram 推送：

![](screenshots/telegram.jpeg)

## 快速开始

1. **Fork** 本仓库
2. 添加环境变量：Settings → Secrets and variables → Actions → New repository secret
3. 默认使用 GitHub-hosted runner（`ubuntu-latest`），北京时间每天 07:30 自动运行

更新：打开自己 fork 的仓库，点击 `Sync fork → Update branch` 即可同步

![](screenshots/update.jpg)

签到结果示例：

| GitHub-hosted | Self-hosted |
|---------------|-------------|
| ![](screenshots/ubuntu.jpeg) | ![](screenshots/self-hosted.jpeg) |

## Runner 说明

项目提供两个 workflow 文件：

| 文件 | Runner | 说明 |
|------|--------|------|
| `checkin.yml` | `ubuntu-latest` | fork 直接使用，无需额外配置 |
| `checkin-self-hosted.yml` | `self-hosted` | 需自建 runner，纯 shell 步骤不依赖 action 下载 |

### GitHub-hosted（`ubuntu-latest`）

Fork 后开箱即用。Yamibo 论坛有百度 WAF 防护，脚本通过 Playwright 解决 JS 挑战。

### Self-hosted

适合需要本地网络环境的场景（例如 Yamibo 签到），使用 [myoung34/docker-github-actions-runner](https://github.com/myoung34/docker-github-actions-runner) 在本地启动 runner：

```bash
docker run -d \
  --name github-runner \
  --net=host \
  --platform linux/amd64 \
  --restart unless-stopped \
  -e ACCESS_TOKEN="<PAT>" \
  -e DEBUG_OUTPUT="true" \
  -e LABELS="self-hosted,linux" \
  -e REPO_URL="https://github.com/jckling/Daily-Bonus" \
  -e RUN_AS_ROOT="true" \
  -e RUNNER_NAME="local-runner" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v runner_work:/_work \
  myoung34/github-runner:latest
```

需要修改的参数：

- `ACCESS_TOKEN`：GitHub Personal Access Token
- `REPO_URL`：fork 的仓库地址

### 问题排查

**Self-hosted runner 卡住没有日志**

检查容器能否连接 `launch.actions.githubusercontent.com`，国内网络可能无法直连。`checkin-self-hosted.yml` 已改为纯 shell 步骤（`git clone` + `curl`），不依赖 external action 下载。如仍有问题，给容器配置代理或使用 `--net=host`。

**Yamibo 签到提示「页面被拦截」**

Yamibo 启用了百度 WAF JS 挑战，curl_cffi 无法执行 JS 会返回 405。脚本通过 Playwright 启动 headless Chromium 解决挑战并提取 `nox_jst_v1` cookie。GitHub-hosted runner 已内置 Playwright 浏览器安装步骤；self-hosted runner 需确保 Docker 容器内有 Chromium 运行依赖。

**签到失败**

在 Actions 页面点击 `Re-run` 重新运行即可。Cookie 可能过期，重新获取后更新 Secrets。

## 配置

在仓库 Settings → Secrets → Actions 中添加以下环境变量，按需配置：

### Telegram 推送

| Name | Description |
|------|-------------|
| TG_BOT_TOKEN | Bot Token，参考 [How Do I Create a Bot?](https://core.telegram.org/bots#how-do-i-create-a-bot) |
| TG_USER_ID | 用户 ID，参考 [How can I send a message to someone with my telegram bot using their Username](https://stackoverflow.com/questions/41664810) |

兼容 Auto_Checkin 的 `TG_CHAT_ID`；同时设置时优先使用 `TG_USER_ID`。

### GLaDOS（整合 Auto_Checkin）

| Name | Description |
|------|-------------|
| GLADOS_COOKIE | 必填，从已登录的 GLaDOS 浏览器请求中复制 Cookie |
| GLADOS_EMAIL | 可选，仅用于在结果中标识账户 |

未设置 `GLADOS_COOKIE` 时跳过。结果合并到 Daily-Bonus 的 Telegram 消息中；未配置 Telegram 时仍输出到运行日志。

从 Auto_Checkin 迁移时，请在 **Daily-Bonus 仓库**重新添加 Secrets（GitHub 不会跨仓库共享 Secrets）。原项目使用 `production` 环境；本项目使用 repository secrets，请将值配置到仓库级别。

GLaDOS 随 Daily-Bonus 于北京时间每天 **07:30** 执行，不再使用原项目的 16:00 调度。验证成功后，可停用旧 Auto_Checkin 工作流以避免重复签到。GitHub-hosted 与 self-hosted 两个工作流按需启用一个。

可在 Actions 页面手动运行 Daily Bonus 验证，或本地执行 `uv run python integrations/auto_checkin/glados_checkin.py`。

独立签到程序及其来源、修改说明和 GPLv3 许可证见 [integrations/auto_checkin](integrations/auto_checkin)。

### 赛马娘网页签到

使用 Cookie 登录，需要 `site`、`joy_jct`、`DedeUserID`、`SESSDATA`

| Name | Description |
|------|-------------|
| UMA_COOKIES | Cookie |

### V2EX

使用 Cookie 登录，需要 `PB3_SESSION`、`A2`、`V2EX_LANG`、`V2EX_TAB`

| Name | Description |
|------|-------------|
| V2EX_COOKIES | Cookie |

### Yamibo

使用账号密码登录，通过 Playwright 解决百度 WAF JS 挑战

| Name | Description |
|------|-------------|
| YAMIBO_USERNAME | 用户名 |
| YAMIBO_PASSWORD | 密码 |

### Yurifans

| Name | Description |
|------|-------------|
| YURIFANS_EMAIL | 邮箱 |
| YURIFANS_PASSWORD | 密码 |

### Bilibili

使用 Cookie 登录，需要 `SESSDATA`、`DedeUserID`

| Name | Description |
|------|-------------|
| BILIBILI_COOKIES | Cookie |

### 哔咔漫画

| Name | Description |
|------|-------------|
| PICA_USERNAME | 用户名或邮箱 |
| PICA_PASSWORD | 密码 |

### 网易云音乐

使用 Cookie 登录，需要 `MUSIC_U`，浏览器登录 [music.163.com](https://music.163.com) 获取

| Name | Description |
|------|-------------|
| NETEASE_MUSIC_COOKIES | Cookie |

## 开发环境

- macOS (Apple Silicon, ARM64)
- Python 3.13
- [uv](https://github.com/astral-sh/uv)（依赖管理）
- [curl_cffi](https://github.com/lexiforest/curl_cffi)（TLS 指纹伪装）
- [Playwright](https://github.com/microsoft/playwright)（WAF JS 挑战）
- Chrome DevTools / HAR 抓包

## 致谢

- [ewigl/picacg-auto-checkin](https://github.com/ewigl/picacg-auto-checkin)
- [Sitoi/dailycheckin](https://github.com/Sitoi/dailycheckin)
- [myoung34/docker-github-actions-runner](https://github.com/myoung34/docker-github-actions-runner)
- [astral-sh/uv](https://github.com/astral-sh/uv)

## 许可证

Daily-Bonus 原有代码及适配器使用 [MIT](LICENSE)。独立程序 `integrations/auto_checkin/glados_checkin.py` 使用其原项目的 [GPLv3](integrations/auto_checkin/LICENSE)，通过子进程调用。
