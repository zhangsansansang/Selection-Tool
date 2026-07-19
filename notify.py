#!/usr/bin/env python3
"""
竞品更新通知模块
支持渠道:
  免费/个人可用: Server酱(微信) / PushPlus(微信) / Telegram Bot
  企业版: 飞书机器人 / 企业微信机器人 / 钉钉机器人 / 邮件
用法:
  python notify.py --server-chan SCT123456... --title "发现新型号" --message "..."
  python notify.py --pushplus token123 --title "发现新型号" --message "..."
  python notify.py --feishu https://open.feishu.cn/open-apis/bot/v2/hook/xxx --message "..."
"""

import json
import sys
import os
import argparse
import smtplib
from email.mime.text import MIMEText
from datetime import datetime


# ============================================================
# Server酱 (微信推送) — 免费, 个人可用, 无需企业认证
# 注册: https://sct.ftqq.com → 获取 SendKey
# ============================================================

def send_server_chan(send_key, title, content_lines):
    """通过 Server酱 推送到微信"""
    try:
        import urllib.request
    except ImportError:
        return False

    content = "\n".join(content_lines)
    payload = json.dumps({
        "title": title,
        "desp": content.replace("\n", "\n\n"),
    }).encode("utf-8")

    url = f"https://sctapi.ftqq.com/{send_key}.send"
    try:
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("code") == 0:
                return True
            print(f"[Server酱] 发送失败: {result.get('message', 'unknown')}")
            return False
    except Exception as e:
        print(f"[Server酱] 发送异常: {e}")
        return False


# ============================================================
# PushPlus (微信推送) — 免费, 个人可用
# 注册: https://www.pushplus.plus → 获取 Token
# ============================================================

def send_pushplus(token, title, content_lines):
    """通过 PushPlus 推送到微信"""
    try:
        import urllib.request
    except ImportError:
        return False

    content = "\n".join(content_lines)
    payload = json.dumps({
        "token": token,
        "title": title,
        "content": content.replace("\n", "<br>"),
        "template": "txt",
    }).encode("utf-8")

    url = "https://www.pushplus.plus/send"
    try:
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("code") == 200:
                return True
            print(f"[PushPlus] 发送失败: {result.get('msg', 'unknown')}")
            return False
    except Exception as e:
        print(f"[PushPlus] 发送异常: {e}")
        return False


# ============================================================
# Telegram Bot — 免费
# 创建: @BotFather → 获取 token → 获取 chat_id
# ============================================================

def send_telegram(bot_token, chat_id, title, content_lines):
    """通过 Telegram Bot 发送通知"""
    try:
        import urllib.request
    except ImportError:
        return False

    text = f"*{title}*\n\n" + "\n".join(content_lines[:30])
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }).encode("utf-8")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        print(f"[Telegram] 发送异常: {e}")
        return False


# ============================================================
# 飞书机器人通知 (需企业管理员权限)
# ============================================================

def send_feishu(webhook_url, title, content_lines):
    """
    发送飞书卡片消息
    webhook_url: 飞书群机器人 Webhook 地址
    """
    try:
        import urllib.request
    except ImportError:
        return False

    # 构建 Markdown 内容
    md_content = f"**{title}**\n\n"
    for line in content_lines[:30]:  # 飞书消息有长度限制
        md_content += f"{line}\n"

    payload = json.dumps({
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "轮廓仪竞品更新通知"},
                "template": "orange"
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": md_content
                },
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text",
                         "content": f"自动监控 · {datetime.now().strftime('%Y-%m-%d %H:%M')}"}
                    ]
                }
            ]
        }
    }, ensure_ascii=False).encode("utf-8")

    try:
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("code") == 0:
                return True
            else:
                print(f"[飞书] 发送失败: {result.get('msg', 'unknown')}")
                return False
    except Exception as e:
        print(f"[飞书] 发送异常: {e}")
        return False


# ============================================================
# 企业微信机器人通知
# ============================================================

def send_wecom(webhook_url, title, content_lines):
    """发送企业微信 Markdown 消息"""
    try:
        import urllib.request
    except ImportError:
        return False

    md = f"## {title}\n\n"
    for line in content_lines[:25]:
        md += f"> {line}\n"

    payload = json.dumps({
        "msgtype": "markdown",
        "markdown": {
            "content": md
        }
    }, ensure_ascii=False).encode("utf-8")

    try:
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("errcode") == 0
    except Exception as e:
        print(f"[企业微信] 发送异常: {e}")
        return False


# ============================================================
# 钉钉机器人通知
# ============================================================

def send_dingtalk(webhook_url, title, content_lines):
    """发送钉钉 Markdown 消息"""
    try:
        import urllib.request
    except ImportError:
        return False

    md = f"## {title}\n\n"
    for line in content_lines[:25]:
        md += f"- {line}\n"

    payload = json.dumps({
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": md
        }
    }, ensure_ascii=False).encode("utf-8")

    try:
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("errcode") == 0
    except Exception as e:
        print(f"[钉钉] 发送异常: {e}")
        return False


# ============================================================
# 邮件通知 (SMTP)
# ============================================================

def send_email(smtp_host, smtp_port, user, password, to_addr, subject, body):
    """发送邮件通知"""
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to_addr

        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            server.starttls()

        server.login(user, password)
        server.sendmail(user, [to_addr], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[邮件] 发送异常: {e}")
        return False


# ============================================================
# 通用通知分发
# ============================================================

def build_notification_content(matched_models, pending_models, stats):
    """构建通知内容"""
    lines = []
    lines.append(f"扫描品牌: {stats.get('brands', '全部')}")
    lines.append(f"新增型号: {len(matched_models)} 个已对标 + {len(pending_models)} 个待补充")
    lines.append(f"数据库总量: {stats.get('total_entries', '?')} 条")

    if matched_models:
        lines.append("")
        lines.append("=== 新对标型号 ===")
        for m in matched_models[:10]:
            conf = m.get("_confidence", "?")
            lines.append(
                f"[{conf}] {m['brand']} {m['model']} → {m.get('hikModel', '(非线激光)')}"
            )

    if pending_models:
        lines.append("")
        lines.append("=== 待补充规格 ===")
        for m in pending_models[:5]:
            lines.append(f"[?] {m['brand']} {m['model']}")

    return lines


def dispatch_notifications(config, notification_content):
    """将通知分发到所有配置的渠道"""
    title = f"轮廓仪竞品更新: {len(notification_content) - 1} 条新发现"
    results = {}

    if config.get("server_chan_key"):
        ok = send_server_chan(config["server_chan_key"], title, notification_content)
        results["server_chan"] = "ok" if ok else "failed"

    if config.get("pushplus_token"):
        ok = send_pushplus(config["pushplus_token"], title, notification_content)
        results["pushplus"] = "ok" if ok else "failed"

    if config.get("telegram_token") and config.get("telegram_chat_id"):
        ok = send_telegram(config["telegram_token"], config["telegram_chat_id"],
                          title, notification_content)
        results["telegram"] = "ok" if ok else "failed"

    if config.get("feishu_webhook"):
        ok = send_feishu(config["feishu_webhook"], title, notification_content)
        results["feishu"] = "ok" if ok else "failed"

    if config.get("wecom_webhook"):
        ok = send_wecom(config["wecom_webhook"], title, notification_content)
        results["wecom"] = "ok" if ok else "failed"

    if config.get("dingtalk_webhook"):
        ok = send_dingtalk(config["dingtalk_webhook"], title, notification_content)
        results["dingtalk"] = "ok" if ok else "failed"

    if config.get("email_to"):
        body = "\n".join(notification_content)
        ok = send_email(
            config.get("smtp_host", "smtp.qq.com"),
            config.get("smtp_port", 587),
            config.get("smtp_user", ""),
            config.get("smtp_pass", ""),
            config["email_to"],
            f"[海康轮廓仪] {title}",
            body,
        )
        results["email"] = "ok" if ok else "failed"

    return results


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="竞品更新通知分发")
    parser.add_argument("--server-chan", help="Server酱 SendKey (微信推送, 免费)")
    parser.add_argument("--pushplus", help="PushPlus Token (微信推送, 免费)")
    parser.add_argument("--telegram", help="Telegram Bot Token")
    parser.add_argument("--telegram-chat-id", help="Telegram Chat ID")
    parser.add_argument("--feishu", help="飞书 Webhook URL")
    parser.add_argument("--wecom", help="企业微信 Webhook URL")
    parser.add_argument("--dingtalk", help="钉钉 Webhook URL")
    parser.add_argument("--email", help="邮件接收地址")
    parser.add_argument("--smtp-host", default="smtp.qq.com")
    parser.add_argument("--smtp-port", type=int, default=587)
    parser.add_argument("--smtp-user", help="SMTP 用户名")
    parser.add_argument("--smtp-pass", help="SMTP 密码")
    parser.add_argument("--title", default="轮廓仪竞品自动更新")
    parser.add_argument("--message", help="通知文本 (多行用 \\n 分隔)")
    parser.add_argument("--from-json", help="从 JSON 文件读取匹配结果")
    args = parser.parse_args()

    if args.from_json:
        with open(args.from_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        content = build_notification_content(
            data.get("matched", []),
            data.get("pending", []),
            data.get("stats", {}),
        )
    elif args.message:
        content = args.message.replace("\\n", "\n").split("\n")
    else:
        lines = []
        while True:
            try:
                line = input()
                lines.append(line)
            except EOFError:
                break
        content = lines

    if not content:
        print("无通知内容")
        return

    config = {}
    if args.server_chan:
        config["server_chan_key"] = args.server_chan
    if args.pushplus:
        config["pushplus_token"] = args.pushplus
    if args.telegram:
        config["telegram_token"] = args.telegram
        config["telegram_chat_id"] = args.telegram_chat_id or ""
    if args.feishu:
        config["feishu_webhook"] = args.feishu
    if args.wecom:
        config["wecom_webhook"] = args.wecom
    if args.dingtalk:
        config["dingtalk_webhook"] = args.dingtalk
    if args.email:
        config["email_to"] = args.email
        config["smtp_host"] = args.smtp_host
        config["smtp_port"] = args.smtp_port
        config["smtp_user"] = args.smtp_user or args.email
        config["smtp_pass"] = args.smtp_pass

    if not config:
        print("请至少指定一个通知渠道: --feishu / --wecom / --dingtalk / --email")
        sys.exit(1)

    results = dispatch_notifications(config, content)
    for channel, status in results.items():
        print(f"[通知] {channel}: {status}")


if __name__ == "__main__":
    main()
