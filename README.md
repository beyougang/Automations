# Gmail 自动清理工具（Automations）

这是一个可本地运行的 Gmail 自动清理脚本，核心能力包括：

- **AI 判断邮件价值**：结合主题、发件人、摘要、时间等信息打分。
- **自动清理规则**：按邮件年龄、大小、类型（订阅/促销）和 AI 分数执行删除。
- **订阅邮件识别**：优先根据 `List-Unsubscribe`，同时结合发件人与主题关键字。
- **一键释放空间**：运行一次即可批量清理低价值邮件。
- **每月自动清理**：自动生成 cron 表达式，便于定时执行。

---

## 1. 安装依赖

推荐使用项目内脚本（自动回退镜像）：

```bash
bash scripts/install_deps.sh
```

或手动安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Gmail API 准备

1. 在 Google Cloud 控制台启用 Gmail API。
2. 创建 OAuth 客户端（Desktop App）。
3. 下载 `credentials.json` 到项目根目录。

首次运行时会弹浏览器授权，授权后生成 `token.json`。

---

## 3. 初始化配置

```bash
python3 gmail_cleanup_tool.py init --config config.json
```

会生成默认配置：

```json
{
  "days_old": 30,
  "max_messages": 200,
  "min_size_kb": 40,
  "dry_run": true,
  "monthly_day": 1,
  "monthly_hour": 3,
  "ai_provider": "openai",
  "ai_model": "gpt-4o-mini",
  "low_value_threshold": 0.45
}
```

> 建议先保持 `dry_run: true`，观察日志后再改成 `false`。

---

## 4. 运行清理（一键释放空间）

```bash
OPENAI_API_KEY=你的key python3 gmail_cleanup_tool.py run --config config.json
```

如果 `OPENAI_API_KEY` 未设置，工具会自动降级为保守策略（默认尽量保留）。

---

## 5. 每月自动清理

生成 cron 配置：

```bash
python3 gmail_cleanup_tool.py cron --config config.json
```

然后把输出的行复制到：

```bash
crontab -e
```

即可实现每月自动清理。

---

## 6. 功能实现说明

### AI 判断邮件价值
- 使用 OpenAI 对每封候选邮件输出：`score`（0-1）+ `decision`（KEEP/DELETE/UNSUBSCRIBE/ARCHIVE）+ `reason`。
- 低分、广告/通知/过期信息会优先进入清理候选。

### 自动清理规则
- 邮件超过 `days_old`。
- 邮件体积大于 `min_size_kb`。
- 满足订阅邮件条件，或 AI 评分低于 `low_value_threshold`，或 AI 直接建议 DELETE。

### 订阅邮件识别
- 读取邮件头 `List-Unsubscribe`。
- 结合发件人与主题关键字（newsletter/digest/promo/noreply/订阅/促销等）。

### 一键释放空间
- `run` 命令会自动扫描、打分、删除并统计预计释放空间。

### 每月自动清理
- `cron` 命令按配置中的 `monthly_day` / `monthly_hour` 生成可直接使用的 cron 行。

---

## 7. `pip install -r requirements.txt` 失败怎么修复

你之前遇到的是典型网络/代理问题（例如 `Cannot connect to proxy`, `403 Forbidden`）。

### 方案 A（推荐）：使用内置安装脚本

```bash
bash scripts/install_deps.sh
```

脚本会：
1. 先尝试默认 PyPI。
2. 失败后自动回退到清华 / 阿里云镜像。
3. 若仍失败，输出代理与 pip.conf 的修复建议。

### 方案 B：显式指定镜像

```bash
python3 -m pip install -r requirements.txt \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --trusted-host pypi.tuna.tsinghua.edu.cn
```

### 方案 C：配置代理后再安装

```bash
export HTTPS_PROXY=http://<proxy_host>:<proxy_port>
export HTTP_PROXY=http://<proxy_host>:<proxy_port>
python3 -m pip install -r requirements.txt
```

### 方案 D：持久化 pip 镜像配置

```bash
mkdir -p ~/.pip
cat > ~/.pip/pip.conf <<'CONF'
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
timeout = 120
CONF
```

---

## 注意事项

- 删除动作会进入 Gmail 垃圾箱，不是立即永久删除。
- 生产环境建议开启日志并先 dry-run 至少 1-2 周。
- 本工具默认处理 `in:inbox` 且非 `category:primary` 的旧邮件，可按需扩展 query。


## 8. Web 版本（你现在可以直接用网页）

启动方式：

```bash
python3 web_app.py
```

浏览器打开：`http://127.0.0.1:5000`

Web 版提供：
- 参数可视化配置
- 一键执行清理
- 每月自动清理 cron 生成
- 清理结果与日志展示

> 说明：Web 版复用了同一套 Gmail 清理逻辑，首次执行仍会触发 Gmail OAuth 授权。
