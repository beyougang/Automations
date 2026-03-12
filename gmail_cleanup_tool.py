#!/usr/bin/env python3
"""Gmail 自动清理工具

功能：
1. AI 判断邮件价值
2. 自动清理规则
3. 订阅邮件识别
4. 一键释放空间
5. 每月自动清理（配合 cron）
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import datetime as dt
import json
import os
import re
from typing import Dict, List, Optional, Sequence, Tuple

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


@dataclasses.dataclass
class CleanupConfig:
    days_old: int = 30
    max_messages: int = 200
    min_size_kb: int = 40
    dry_run: bool = True
    monthly_day: int = 1
    monthly_hour: int = 3
    ai_provider: str = "openai"
    ai_model: str = "gpt-4o-mini"
    low_value_threshold: float = 0.45


@dataclasses.dataclass
class EmailRecord:
    message_id: str
    thread_id: str
    subject: str
    sender: str
    snippet: str
    size_estimate: int
    internal_date: dt.datetime
    labels: List[str]
    has_list_unsubscribe: bool


@dataclasses.dataclass
class ScoreResult:
    score: float
    decision: str
    reason: str


def load_config(path: str) -> CleanupConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return CleanupConfig(**data)


def save_template_config(path: str) -> None:
    template = dataclasses.asdict(CleanupConfig())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)


def get_gmail_service(credentials_file: str, token_file: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def list_candidates(service, days_old: int, max_messages: int) -> List[str]:
    before_date = (dt.datetime.utcnow() - dt.timedelta(days=days_old)).strftime("%Y/%m/%d")
    query = f"in:inbox before:{before_date} -category:primary"

    ids: List[str] = []
    next_page_token = None
    while len(ids) < max_messages:
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                pageToken=next_page_token,
                maxResults=min(100, max_messages - len(ids)),
            )
            .execute()
        )
        messages = response.get("messages", [])
        ids.extend(m["id"] for m in messages)
        next_page_token = response.get("nextPageToken")
        if not next_page_token or not messages:
            break
    return ids


def _decode_header_value(value: str) -> str:
    if not value:
        return ""
    try:
        decoded = base64.urlsafe_b64decode(value + "===")
        return decoded.decode("utf-8", errors="ignore")
    except Exception:
        return value


def _extract_headers(payload: Dict) -> Dict[str, str]:
    headers = {}
    for header in payload.get("headers", []):
        headers[header.get("name", "").lower()] = header.get("value", "")
    return headers


def fetch_email(service, message_id: str) -> EmailRecord:
    message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    payload = message.get("payload", {})
    headers = _extract_headers(payload)
    list_unsubscribe = headers.get("list-unsubscribe", "")

    subject = _decode_header_value(headers.get("subject", ""))
    sender = _decode_header_value(headers.get("from", ""))

    return EmailRecord(
        message_id=message["id"],
        thread_id=message["threadId"],
        subject=subject,
        sender=sender,
        snippet=message.get("snippet", ""),
        size_estimate=message.get("sizeEstimate", 0),
        internal_date=dt.datetime.fromtimestamp(int(message["internalDate"]) / 1000),
        labels=message.get("labelIds", []),
        has_list_unsubscribe=bool(list_unsubscribe),
    )


def is_subscription_email(email: EmailRecord) -> bool:
    if email.has_list_unsubscribe:
        return True
    sender_lower = email.sender.lower()
    subject_lower = email.subject.lower()
    rules = [
        r"newsletter",
        r"digest",
        r"promo",
        r"noreply",
        r"notification",
        r"订阅",
        r"促销",
        r"优惠",
    ]
    return any(re.search(pattern, sender_lower) or re.search(pattern, subject_lower) for pattern in rules)


def score_email_by_ai(email: EmailRecord, provider: str, model: str) -> ScoreResult:
    if provider != "openai":
        return ScoreResult(0.5, "KEEP", "未启用 AI 提供方，使用默认保留策略")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return ScoreResult(0.6, "KEEP", "缺少 OPENAI_API_KEY，默认保守保留")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    prompt = (
        "你是邮箱清理助手。根据邮件主题、发件人、摘要判断邮件价值。"
        "输出 JSON：{score:0-1, decision:KEEP|DELETE|UNSUBSCRIBE|ARCHIVE, reason:string}。"
        "低价值广告/过期通知应更接近0；账单、合同、工作邮件应更接近1。"
    )

    content = {
        "subject": email.subject,
        "sender": email.sender,
        "snippet": email.snippet,
        "age_days": (dt.datetime.now() - email.internal_date).days,
        "size_kb": round(email.size_estimate / 1024, 2),
        "is_subscription": is_subscription_email(email),
    }

    result = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(content, ensure_ascii=False)},
        ],
        temperature=0,
    )

    text = result.output_text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return ScoreResult(0.6, "KEEP", f"AI 输出不可解析：{text[:80]}")

    return ScoreResult(
        score=float(parsed.get("score", 0.6)),
        decision=str(parsed.get("decision", "KEEP")).upper(),
        reason=str(parsed.get("reason", "")),
    )


def should_delete(email: EmailRecord, score: ScoreResult, cfg: CleanupConfig) -> bool:
    age_days = (dt.datetime.now() - email.internal_date).days
    large_enough = email.size_estimate >= cfg.min_size_kb * 1024
    old_and_subscription = age_days >= cfg.days_old and is_subscription_email(email)
    low_value = score.score <= cfg.low_value_threshold
    return large_enough and (old_and_subscription or low_value or score.decision == "DELETE")


def trash_message(service, message_id: str, dry_run: bool) -> None:
    if dry_run:
        return
    service.users().messages().trash(userId="me", id=message_id).execute()


def cleanup(service, cfg: CleanupConfig) -> Tuple[int, int, int]:
    candidate_ids = list_candidates(service, cfg.days_old, cfg.max_messages)
    scanned = 0
    deleted = 0
    bytes_freed = 0

    for message_id in candidate_ids:
        scanned += 1
        email = fetch_email(service, message_id)
        score = score_email_by_ai(email, cfg.ai_provider, cfg.ai_model)

        if should_delete(email, score, cfg):
            trash_message(service, email.message_id, cfg.dry_run)
            deleted += 1
            bytes_freed += email.size_estimate
            action = "[DRY-RUN 删除]" if cfg.dry_run else "[已删除]"
            print(f"{action} {email.subject[:50]} | {score.score:.2f} | {score.reason}")
        else:
            print(f"[保留] {email.subject[:50]} | {score.score:.2f} | {score.reason}")

    return scanned, deleted, bytes_freed


def generate_monthly_cron(script_path: str, config_path: str, day: int, hour: int) -> str:
    return f"0 {hour} {day} * * /usr/bin/env python3 {script_path} run --config {config_path} >> ~/gmail_cleanup.log 2>&1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Gmail 自动清理工具")
    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", help="生成配置模板")
    init_cmd.add_argument("--config", default="config.json")

    run_cmd = sub.add_parser("run", help="执行清理")
    run_cmd.add_argument("--config", default="config.json")
    run_cmd.add_argument("--credentials", default="credentials.json")
    run_cmd.add_argument("--token", default="token.json")

    cron_cmd = sub.add_parser("cron", help="生成每月自动清理 cron")
    cron_cmd.add_argument("--config", default="config.json")
    cron_cmd.add_argument("--script", default=os.path.abspath(__file__))

    args = parser.parse_args()

    if args.command == "init":
        save_template_config(args.config)
        print(f"已生成配置模板：{args.config}")
        return

    if args.command == "cron":
        cfg = load_config(args.config)
        line = generate_monthly_cron(args.script, args.config, cfg.monthly_day, cfg.monthly_hour)
        print("将下面这一行加入 crontab -e：")
        print(line)
        return

    if args.command == "run":
        cfg = load_config(args.config)
        try:
            service = get_gmail_service(args.credentials, args.token)
            scanned, deleted, freed = cleanup(service, cfg)
            print("\n===== 清理结果 =====")
            print(f"扫描邮件：{scanned}")
            print(f"删除邮件：{deleted}")
            print(f"预计释放空间：{freed / 1024 / 1024:.2f} MB")
            if cfg.dry_run:
                print("当前为 dry-run 模式，未真正删除邮件。")
        except Exception as e:
            print(f"Gmail API 错误：{e}")


if __name__ == "__main__":
    main()
