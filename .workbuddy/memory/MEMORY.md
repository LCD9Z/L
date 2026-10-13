# 项目长期记忆

## 本项目的「接口契约」坑（踩过 ≥2 次，务必先查）

### `tdx_native.day_reader.scan_paths()` 返回三元组顺序是 **(code, market, path)**

```python
for code, mkt, p in day_reader.scan_paths('D:/new_tdx/vipdoc'):   # ✅
```

**⚠️ 已踩两次**：
- 2026-10-12：解包顺序写成 `(market, code, path)` → 数据错
- 2026-10-13：`for mkt, code, p in ...` → `code` 实为 `'sh'`，
  筛选 `code.startswith('600')` **恒 False** → 早年股票筛选得 **0 个**（实际 1067 个）
  - **且第一次排查时误以为是 `.day` 文件格式问题**，白费一轮

**教训**：**用任何函数的返回值前，先 `print` 一次样例**确认字段顺序。
「函数名/参数名看起来像什么」≠「返回顺序是什么」。

### 其他已踩过的接口/格式坑

| 项 | 坑 | 正确做法 |
|---|---|---|
| 通达信 `.day` | 32 字节/条，`<IIIIIfII`，价格 ÷100 | **首条=最早**，末条=最新（可直接 seek 读） |
| `.day` 首条日期 | 无「读首根」API，`read_day_tail` 读的是**尾部** | 直接二进制读前 32 字节 |
| 腾讯 secid | 东财是 `1.600000`；**baostock 是 `sh.600000`** | 两库格式不同，勿互抄 |
| 腾讯 volume | **分板块**：`sh688`=股，其余=手（须 ×100） | 见 `AGENTS.md` |
| baostock volume | 与通达信**逐位相同**（都是股） | 不需换算 |
| JSON 落盘 | `open(p,'w')` 在 Windows 会转 **CRLF** → `test_line_endings_are_lf` 失败 | 必须 `newline='\n'` |
| baostock 2000 | 是「**一页**」不是上限；`next()` 失败会**静默返回 False** | 判据 `n % 2000 == 0` ⇒ 须复核 |
