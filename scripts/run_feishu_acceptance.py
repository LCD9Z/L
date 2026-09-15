# -*- coding: utf-8 -*-
"""飞书 notify 模块真实凭据验收（不接触明文）。

流程：
1. 定位 lark-cli（连接器自带，默认不在 PATH 时回退到已知安装目录）。
2. 从 os.environ 读取 FEISHU_NOTIFY_USER_ID / FEISHU_NOTIFY_CHAT_ID
   （由用户在对话外通过 setx / 系统环境变量设置，不进仓库、不进聊天）。
3. 调 feishu_notifier.is_configured() 检查接线。
4. 若已配置，发送一条无害的验收测试消息，报告 ok/fail（不打印任何明文凭据）。

运行方式（由调用方在 PowerShell 中注入环境变量，本脚本不读取明文）：
    $env:FEISHU_NOTIFY_USER_ID = <用户 openId>
    $env:PATH = "<lark-cli 目录>;$env:PATH"
    python scripts/run_feishu_acceptance.py
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "notify")):
    if p not in sys.path:
        sys.path.insert(0, p)

from notify import feishu_notifier as fn

KNOWN_LARK_CLI_DIRS = [
    r"C:\Users\T430\.workbuddy\binaries\node\cli-connector-packages",
]

TEST_MESSAGE = (
    "【飞书 notify 模块验收测试】\n"
    "若你收到这条消息，说明项目 notify/lark_notify 与 feishu_notifier "
    "已通过真实凭据验收（lark-cli + 连接器授权 + 环境变量配置均生效）。\n"
    "本条为自动化测试，可忽略。"
)


def _resolve_lark_cli() -> "str | None":
    """返回可执行的 lark-cli 路径（带扩展名）。

    项目代码用裸名 `lark-cli` 调用，这在 WorkBuddy 运行时与 PowerShell 下可解析；
    但在本机 Python subprocess 下裸名无法解析到 `lark-cli.cmd`，故此处回退到完整路径。
    仅用于验收环境的二进制定位，不改变项目代码的调用逻辑。
    """
    bare = shutil.which("lark-cli")
    if bare:
        return bare
    for d in KNOWN_LARK_CLI_DIRS:
        for cand in ("lark-cli.cmd", "lark-cli.exe", "lark-cli"):
            p = Path(d) / cand
            if p.exists():
                return str(p)
    return None


def _ensure_lark_cli_on_path() -> "str | None":
    cli = _resolve_lark_cli()
    if cli is None:
        return None
    # 若裸名无法解析，运行时把 subprocess 的首参 `lark-cli` 改写为完整路径，
    # 并把 feishu_notifier.shutil.which("lark-cli") 也固定为本机真实路径
    # （shutil.which 在本沙箱对 .cmd 解析不稳定，属环境问题，不影响项目在运行时表现）。
    if cli.lower().endswith(".cmd") and shutil.which("lark-cli") is None:
        _orig_run = fn.subprocess.run
        _orig_which = fn.shutil.which

        def _patched_run(cmd, *a, **kw):
            if isinstance(cmd, list) and cmd and cmd[0] == "lark-cli":
                cmd = [cli] + cmd[1:]
            return _orig_run(cmd, *a, **kw)

        def _patched_which(name, *a, **kw):
            if name == "lark-cli":
                return cli
            return _orig_which(name, *a, **kw)

        fn.subprocess.run = _patched_run  # type: ignore[assignment]
        fn.shutil.which = _patched_which  # type: ignore[assignment]
    return cli


class _Stub:
    def __init__(self, **kw: object) -> None:
        self.__dict__.update(kw)


def _stub_session() -> _Stub:
    rep = _Stub(score=8, recommendation="验收通过（示例）")
    return _Stub(
        company_name="验收测试标的",
        stock_code="000000",
        analyst_reports={
            "analyst_fundamental": rep,
            "analyst_sentiment": rep,
            "analyst_news": rep,
            "analyst_technical": rep,
        },
        trade_proposal=None,
        final_decision=None,
    )


def main() -> int:
    cli = _ensure_lark_cli_on_path()
    if not cli:
        print("FAIL: lark-cli 不在 PATH 且未找到已知安装目录")
        return 2
    print("lark-cli: %s" % cli)

    cfg = fn._read_config()
    user_set = bool(cfg.get("notify_user_id"))
    chat_set = bool(cfg.get("notify_chat_id"))
    print("is_configured: %s" % fn.is_configured())
    print("target: %s" % ("user_id" if user_set else ("chat_id" if chat_set else "NONE")))

    if not fn.is_configured():
        print("SKIP: 未配置 FEISHU_NOTIFY_USER_ID / FEISHU_NOTIFY_CHAT_ID，跳过真实发送")
        print('       请在对话外设置后重试，例如：setx FEISHU_NOTIFY_USER_ID "ou_你的openId"')
        return 1

    res = fn.send_analysis_summary(_stub_session())
    print("send ok: %s" % res.get("ok"))
    msg = res.get("message", "")
    # 截断输出，且不打印任何可能含凭据的内容
    print("send output (truncated): %s" % msg[:200].replace("\n", " "))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
