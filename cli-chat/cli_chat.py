#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行聊天窗口 (cli-chat)
========================
一个支持多模式的轻量命令行聊天工具。纯标准库，无需安装依赖。

模式
----
  chat   默认聊天模式（自然语言闲聊）
  /sty   策略模式  —— 偏分析、拆解、权衡
  /code  代码模式  —— 偏写代码、调试、解释
  /plan  规划模式  —— 偏任务拆解、排期、步骤

通用指令（任意模式可用）
  /sty | /code | /plan   切换到对应模式
  /back                  回到默认聊天模式
  /quit                  退出当前模式（在 chat 模式下则退出程序）
  /help                  列出所有模式与指令
  /clear                 清屏

接入真实大模型（可选）
  设置以下环境变量后即调用 OpenAI 兼容接口，否则用本地人格化应答兜底：
    CHAT_API_BASE  默认 https://api.openai.com/v1（未设时回退用 LLM_BASE_URL）
    CHAT_API_KEY   你的 API key（未设时回退用 LLM_API_KEY）
    CHAT_MODEL     模型名，默认 gpt-4o-mini（未设时回退用 LLM_MODEL）
    CHAT_MAX_TOKENS 单轮最大 token，默认 1500（reasoning 模型需给足）
  即：项目 LLM_* 环境变量可直接驱动本工具，无需额外设置。

运行
    python3 cli_chat.py
"""
import os
import sys
import json
import urllib.request
from datetime import datetime

# --------------------------------------------------------------------------- #
# 终端颜色（非 tty 时自动关闭，便于管道测试）
# --------------------------------------------------------------------------- #
_USE_COLOR = sys.stdout.isatty()


def c(code: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


RESET = c("0", "")
BOLD = c("1", "")
DIM = c("2", "")
CYAN = c("36", "")
GREEN = c("32", "")
YELLOW = c("33", "")
MAGENTA = c("35", "")
GREY = c("90", "")

# --------------------------------------------------------------------------- #
# 模式定义
# --------------------------------------------------------------------------- #
MODES = {
    "chat": {
        "title": "聊天",
        "cmd": None,
        "color": GREEN,
        "desc": "默认自然语言聊天，随便聊",
        "prompt": "你是一个友好的聊天助手，用自然、口语化的中文和用户闲聊，轻松随意。",
    },
    "sty": {
        "title": "策略",
        "cmd": "/sty",
        "color": MAGENTA,
        "desc": "策略分析与讨论：拆解问题、权衡利弊、给建议",
        "prompt": "你是一个策略顾问。面对用户的输入，先做结构化拆解，再分析利弊与风险，"
                  "最后给出可执行的建议。使用条理清晰的中文，必要时用要点。",
    },
    "code": {
        "title": "代码",
        "cmd": "/code",
        "color": CYAN,
        "desc": "代码助手：写代码、解释、调试",
        "prompt": "你是一个资深程序员助手。优先给出可运行、带注释的代码，"
                  "解释关键思路；遇到报错时帮助定位问题。使用中文说明，代码保持原样。",
    },
    "plan": {
        "title": "规划",
        "cmd": "/plan",
        "color": YELLOW,
        "desc": "任务规划：拆解步骤、排期、列清单",
        "prompt": "你是一个项目规划助手。把用户的诉求拆成有序、可执行的步骤，"
                  "标注依赖与优先级，输出清晰的清单式计划。使用中文。",
    },
}

DEFAULT_MODE = "chat"

# --------------------------------------------------------------------------- #
# 大模型调用（OpenAI 兼容，可选）
# --------------------------------------------------------------------------- #
# 优先用 CHAT_API_*（cli-chat 专用），否则回退到项目统一配置 LLM_*（与 docker-compose 一致）
API_BASE = os.environ.get("CHAT_API_BASE") or os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
API_KEY = os.environ.get("CHAT_API_KEY") or os.environ.get("LLM_API_KEY")
API_MODEL = os.environ.get("CHAT_MODEL") or os.environ.get("LLM_MODEL", "gpt-4o-mini")
# reasoning 类模型（如 deepseek-v4-pro）会先产出 reasoning_content，再产出 content；
# 给足 max_tokens，并优先取 content，content 为空时回退到 reasoning_content。
API_MAX_TOKENS = int(os.environ.get("CHAT_MAX_TOKENS", "1500"))


def llm_respond(system_prompt: str, history: list, user_text: str) -> str | None:
    """尝试调用大模型；不可用或失败时返回 None（由本地兜底接管）。"""
    if not API_KEY:
        return None
    messages = [{"role": "system", "content": system_prompt}]
    for role, text in history:
        messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": user_text})
    body = json.dumps({
        "model": API_MODEL, "messages": messages,
        "temperature": 0.7, "max_tokens": API_MAX_TOKENS,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE.rstrip('/')}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = data["choices"][0]["message"]
        content = (msg.get("content") or "").strip()
        if not content:
            content = (msg.get("reasoning_content") or "").strip()
        if not content:
            return "[模型返回为空]"
        return content
    except Exception as e:  # noqa: BLE001
        return f"[模型调用失败，已切换本地应答] {e}"


# --------------------------------------------------------------------------- #
# 本地人格化兜底应答（无 API key 时）
# --------------------------------------------------------------------------- #
def local_respond(mode: str, text: str) -> str:
    m = MODES[mode]
    name = m["title"]
    t = text.strip()
    if not t:
        return "（说点什么吧~）"
    # 极简的“人格”差异，只为体现模式不同；接入 CHAT_API_KEY 后即走真模型。
    if mode == "chat":
        return f"（聊天模式）收到～你说的是「{t}」。我这儿是本地兜底，没接大模型，" \
               f"设置 CHAT_API_KEY 后就能真聊啦。"
    if mode == "sty":
        return (f"（策略模式）针对「{t}」，建议从三方面入手：\n"
                f"  1. 目标拆解：先明确要达成什么；\n"
                f"  2. 利弊权衡：列出可行路径与风险；\n"
                f"  3. 优先级：先做投入小、收益大的。\n"
                f"需要我针对某一点展开吗？")
    if mode == "code":
        return (f"（代码模式）关于「{t}」，请描述语言/场景或贴上报错，我可以直接给可运行代码。\n"
                f"提示：设置 CHAT_API_KEY 后，这里会由大模型生成真实代码。")
    if mode == "plan":
        return (f"（规划模式）把「{t}」拆成步骤：\n"
                f"  □ 第1步：明确范围与产出；\n"
                f"  □ 第2步：拆子任务并排依赖；\n"
                f"  □ 第3步：排期与验收标准。\n"
                f"要我按这个骨架细化吗？")
    return f"（{name}模式）{t}"


# --------------------------------------------------------------------------- #
# 应用主体
# --------------------------------------------------------------------------- #
class CliChat:
    def __init__(self):
        self.mode = DEFAULT_MODE
        self.history = []  # [(role, text), ...]，跨模式共享上下文
        self.running = True

    # -- 模式切换 ----------------------------------------------------------- #
    def switch_mode(self, mode: str):
        if mode not in MODES:
            return
        if mode == self.mode:
            print(DIM + f"  已在 {MODES[mode]['title']} 模式。" + RESET)
            return
        self.mode = mode
        m = MODES[mode]
        print(m["color"] + BOLD + f"  ➜ 已进入「{m['title']}」模式：{m['desc']}" + RESET)
        print(DIM + "    输入 /quit 退出本模式，/help 查看指令。" + RESET)

    def quit_current(self):
        if self.mode == DEFAULT_MODE:
            self.running = False
            print(GREEN + "  再见 👋" + RESET)
        else:
            prev = MODES[self.mode]["title"]
            self.mode = DEFAULT_MODE
            print(GREEN + f"  ← 已退出「{prev}」模式，回到聊天模式。" + RESET)

    # -- 指令 --------------------------------------------------------------- #
    def handle_command(self, line: str) -> bool:
        """返回 True 表示已处理（不是聊天内容）。"""
        cmd = line.strip().lower()
        if cmd in ("/quit", "/exit"):
            self.quit_current()
            return True
        if cmd in ("/back",):
            if self.mode != DEFAULT_MODE:
                self.quit_current()
            else:
                print(DIM + "  当前已在聊天模式。" + RESET)
            return True
        if cmd in ("/help", "/?", "/h"):
            self.print_help()
            return True
        if cmd in ("/clear",):
            if _USE_COLOR:
                os.system("clear" if os.name != "nt" else "cls")
            return True
        # 模式切换指令
        for key, m in MODES.items():
            if m["cmd"] and cmd == m["cmd"]:
                self.switch_mode(key)
                return True
        if cmd.startswith("/"):
            print(GREY + f"  未知指令：{line}（输入 /help 查看可用指令）" + RESET)
            return True
        return False

    def print_help(self):
        print(BOLD + "\n  可用模式 / 指令：" + RESET)
        for key, m in MODES.items():
            trigger = m["cmd"] if m["cmd"] else "（默认）"
            print(f"    {m['color']}{trigger:<8}{RESET} {m['title']:<4} {DIM}{m['desc']}{RESET}")
        print(DIM + "\n    /back   回到聊天模式      /quit   退出当前模式（chat 下退出程序）" + RESET)
        print(DIM + "    /clear  清屏              /help   显示本帮助\n" + RESET)

    # -- 应答 --------------------------------------------------------------- #
    def respond(self, text: str):
        m = MODES[self.mode]
        reply = llm_respond(m["prompt"], self.history, text)
        if reply is None:
            reply = local_respond(self.mode, text)
        self.history.append(("user", text))
        self.history.append(("assistant", reply))
        # 控制历史长度，避免过长
        if len(self.history) > 24:
            self.history = self.history[-24:]
        print(m["color"] + f"  [{m['title']}] " + RESET + reply)

    # -- 主循环 ------------------------------------------------------------- #
    def run(self):
        m = MODES[self.mode]
        print(BOLD + "\n  ╔══════════════════════════════════════╗" + RESET)
        print(BOLD + "  ║       命令行聊天窗口  cli-chat        ║" + RESET)
        print(BOLD + "  ╚══════════════════════════════════════╝" + RESET)
        print(f"  当前模式：{m['color']}{m['title']}{RESET}  （{m['desc']}）")
        if not API_KEY:
            print(DIM + "  （未检测到 API key（CHAT_API_KEY / LLM_API_KEY），使用本地兜底应答；设置后即为真实大模型）" + RESET)
        else:
            print(DIM + f"  （已接入大模型：{API_MODEL} @ {API_BASE}）" + RESET)
        print(DIM + "  输入 /help 查看所有模式与指令，/quit 退出。\n" + RESET)
        while self.running:
            try:
                m = MODES[self.mode]
                prompt = f"{m['color']}{m['title']}> {RESET}"
                try:
                    line = input(prompt)
                except EOFError:
                    print()
                    self.running = False
                    print(GREEN + "  再见 👋" + RESET)
                    break
                if line == "":
                    continue
                if self.handle_command(line):
                    if not self.running:
                        break
                    continue
                self.respond(line)
            except KeyboardInterrupt:
                print(DIM + "\n  （Ctrl-C，输入 /quit 退出）" + RESET)
                continue


def main():
    CliChat().run()


if __name__ == "__main__":
    main()
