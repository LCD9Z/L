# -*- coding: utf-8 -*-
"""credential_scan 测试。

扫描器是发布门禁的一环，若它自己失效（漏报或误报），门禁就是摆设。
因此这里同时覆盖两个方向：
  · 漏报风险——各类泄漏写法必须被抓住
  · 误报风险——模板/引用/掩码必须放行（误报会让人绕过整个检查）
最后两条是集成断言：仓库自身必须干净。

注意：夹具值一律用 `_frag()` 拼接构造。若直接写成完整字面量，
本文件自己就会成为仓库里的一处「明文值」，让仓库自检用例失败。
"""
from pathlib import Path

from credential_scan import (
    ROOT,
    _is_placeholder,
    _looks_like_mask,
    scan,
    scan_assignment_leaks,
    scan_known_literals,
)


def _frag(*parts):
    """拼接片段构造夹具，避免测试文件本身出现连续的可疑明文值。"""
    return "".join(parts)


_FAKE_TOKEN = _frag("abcdef", "1234567890")
_FAKE_ARK = _frag("1a2b3c4d", "-5e6f-7890-abcd-ef1234567890")
_FAKE_TABLE = _frag("tbl0", "abc")
_KNOWN_LITERAL = _frag("LjSlbLUwza", "IPObsoHq0crrdenSe")


def _hits(text):
    return list(scan_assignment_leaks(text))


# --- 必须抓到 -------------------------------------------------------------

def test_plain_assignment_is_flagged():
    hits = _hits(f'FEISHU_BASE_TOKEN = "{_FAKE_TOKEN}"')
    assert [h[1] for h in hits] == ["FEISHU_BASE_TOKEN"]


def test_type_annotated_assignment_is_flagged():
    """带类型标注的赋值不能被漏掉（曾因把空格当成模板字符而漏报）。"""
    hits = _hits(f'ARK_API_KEY: str = "{_FAKE_ARK}"')
    assert [h[1] for h in hits] == ["ARK_API_KEY"]


def test_json_style_assignment_is_flagged():
    """JSON 键名的收尾引号必须被吃掉，否则这类写法整体漏报。"""
    hits = _hits(f'  "TUSHARE_TOKEN": "{_FAKE_TOKEN}"')
    assert [h[1] for h in hits] == ["TUSHARE_TOKEN"]


def test_short_value_is_still_flagged():
    """短值同样要抓，不能因为长度短就放行。"""
    assert _hits(f'FEISHU_TABLE_ID = "{_FAKE_TABLE}"') != []


def test_known_literal_is_caught_even_without_assignment():
    """去掉变量名后，已知泄漏字面量仍应被抓到。"""
    assert list(scan_known_literals(f"随便一句话 {_KNOWN_LITERAL} 结尾")) != []


# --- 必须放行（否则误报会让检查被绕过） -----------------------------------

def test_empty_value_is_not_flagged():
    assert _hits("FEISHU_BASE_TOKEN=") == []
    assert _hits('FEISHU_NOTIFY_USER_ID = ""') == []


def test_angle_bracket_template_is_not_flagged():
    assert _hits('TUSHARE_TOKEN = "<your_token>"') == []
    assert _hits('FEISHU_BASE_URL="https://my.feishu.cn/base/<your_base_token>"') == []


def test_env_reference_is_not_flagged():
    """引用环境变量不是泄漏。"""
    assert _hits('  --base-token "$FEISHU_BASE_TOKEN" \\') == []
    assert _hits("  --table-id \"$FEISHU_TABLE_ID\" \\") == []


def test_mask_style_value_is_not_flagged():
    assert _hits('"FEISHU_NOTIFY_USER_ID": "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"') == []
    assert _hits('FEISHU_BASE_TOKEN = "Lj****Se"') == []


def test_markdown_table_row_is_not_flagged():
    assert _hits("| FEISHU_TABLE_ID | 写入多维表格时使用 |") == []


def test_chinese_description_is_not_flagged():
    """文档里用中文描述填写位置，不是真实凭据。"""
    assert _hits("TUSHARE_TOKEN='你的Token'") == []


def test_env_lookup_value_is_not_flagged():
    assert _hits('FEISHU_BASE_TOKEN = os.getenv("FEISHU_BASE_TOKEN")') == []


def test_python_tuple_of_key_names_is_not_flagged():
    """键名清单（如 SENSITIVE_KEYS）不应自我命中。"""
    assert _hits('SENSITIVE_KEYS = ("FEISHU_BASE_TOKEN", "ARK_API_KEY")') == []


# --- 占位判定单元 ---------------------------------------------------------

def test_placeholder_helper():
    assert _is_placeholder("") is True
    assert _is_placeholder('"<token>"') is True
    assert _is_placeholder('"$VAR"') is True
    assert _is_placeholder('"****"') is True
    assert _is_placeholder('"your_key"') is True
    assert _is_placeholder('"ou_xxxxxxxx"') is True
    assert _is_placeholder('"a1b2c3d4e5"') is False


def test_mask_helper():
    assert _looks_like_mask("ou_xxxxxxxxxxxx") is True
    assert _looks_like_mask("tbl0000") is True
    assert _looks_like_mask("ou_a1b2c3d4e5f6") is False


# --- 集成：仓库自身必须干净 ----------------------------------------------

def test_repository_has_no_plaintext_credentials():
    """仓库当前状态必须通过扫描（新增泄漏会让本用例失败）。"""
    findings, scanned = scan()
    assert findings == [], "检测到疑似明文凭据：\n" + "\n".join(findings)
    assert scanned > 50, "扫描文件数异常，可能扫描范围被误改"


def test_scanner_excluded_from_its_own_scan():
    """扫描器自身包含敏感键名与已知字面量，必须排除，否则自我命中。"""
    findings, _ = scan()
    assert not any(f.startswith("credential_scan.py:") for f in findings)


def test_skip_dirs_are_not_scanned():
    findings, _ = scan()
    for marker in (".git/", ".mypy_cache/", "__pycache__/"):
        assert not any(marker in f for f in findings)


def test_root_points_at_project_directory():
    assert (ROOT / "requirements.txt").exists()
    assert Path(ROOT).is_absolute()
