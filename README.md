# holiday-data

中日两国法定节假日数据管道。数据由脚本从官方来源抓取、解析、校验后发布为静态 JSON，供 App 读取。**不要手工编辑 `docs/v1/`。**

## 数据来源

| 国家 | 官方来源 | 更新窗口 | 说明 |
|---|---|---|---|
| 日本 | [内閣府「国民の祝日」](https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html) | 每年 2 月前后追加下一年 | 每次运行都从页面解析 CSV 链接，不写死 URL；CSV 为 CP932 |
| 中国 | [国务院办公厅节假日安排通知](https://www.gov.cn/) | 每年 10–11 月公布次年安排 | 通过 gov.cn 搜索接口发现通知，解析器复用 [NateScarlet/holiday-cn](https://github.com/NateScarlet/holiday-cn)（MIT） |

交叉参考（不作为发布源）：

- 日本：[holidays-jp API](https://holidays-jp.github.io/api/v1/date.json)
- 中国：holiday-cn 已发布的 JSON

## 发布地址

GitHub Pages 从 `docs/` 发布，数据位于 `docs/v1/`：

```
https://<user>.github.io/holiday-data/v1/manifest.json
https://<user>.github.io/holiday-data/v1/jp/2027.json
https://<user>.github.io/holiday-data/v1/cn/2026.json
```

备用源：

```
https://cdn.jsdelivr.net/gh/<user>/holiday-data@main/docs/v1/manifest.json
https://raw.githubusercontent.com/<user>/holiday-data/main/docs/v1/manifest.json
```

## 目录

```
scripts/
  build.py              抓取 -> 校验 -> 事务性写入 docs/v1
  fetch_jp.py           内閣府页面 + CSV 解析、休日分类
  fetch_cn.py           中国通知抓取、跨年分区、pending 状态
  holiday_cn_parser.py  holiday-cn 解析器（MIT，已注明改动）
  jp_local_calc.py      日本本地计算参考实现（2007–2099）
  validate.py           数据/清单校验
  check_published.py    发布后冒烟检查
tests/                  离线测试（fixture，不访问网络）
docs/v1/                发布数据（由脚本生成）
```

## 数据格式

### `manifest.json`

```json
{
  "schemaVersion": 1,
  "dataVersion": 20261103004425,
  "generatedAt": "2026-11-03T00:44:25Z",
  "years": { "jp": [2007, 2008, "…", 2027], "cn": [2008, 2009, "…", 2027] },
  "files": {
    "jp/2027.json": {
      "sha256": "...",
      "updatedAt": "2026-11-03T00:44:25Z",
      "bytes": 1234
    }
  }
}
```

- `dataVersion` 为 14 位整数（UTC `YYYYMMDDHHMMSS`），**只在数据内容变化时递增**；没有变化时保持原值。
- App 先读 manifest，`dataVersion` 有变化才下载文件；下载后校验 `sha256`。
- `years` 方便 App 知道有哪些年份可用。

### `jp/{year}.json`

```json
{
  "schemaVersion": 1,
  "country": "JP",
  "year": 2027,
  "source": "内閣府",
  "sourceUrl": "https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html",
  "csvUrl": "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv",
  "days": [
    { "date": "2027-01-01", "name": "元日", "type": "holiday" },
    { "date": "2027-03-22", "name": "休日", "type": "substitute" }
  ]
}
```

- `type`: `holiday`（国民の祝日）/ `substitute`（振替休日）/ `bridge`（国民の休日）。
- 2007 年起生成。更早年份的振替规则不同，不在此管道范围内。
- CSV 里的 `休日（祝日扱い）` 保留原名，`type` 记为 `holiday`。

### `cn/{year}.json`

```json
{
  "schemaVersion": 1,
  "country": "CN",
  "year": 2026,
  "status": "published",
  "source": "国务院办公厅",
  "papers": ["https://www.gov.cn/..."],
  "days": [
    { "date": "2026-01-01", "name": "元旦", "isOffDay": true },
    { "date": "2026-01-04", "name": "元旦", "isOffDay": false }
  ]
}
```

- `isOffDay: true` = 放假；`false` = 调休补班。
- **按日历年份归档**：通知正文里出现的上一年 12 月日期（例如 2023 年通知里的 2022-12-31）会写入 `cn/2022.json`，不会混入 `cn/2023.json`。
- `status`: `published` 或 `pending`。次年通知尚未发布时，会生成 `days: []` 的 pending 文件，App 应显示“安排尚未公布”，而不是当成没有假期。
- 2008 年起生成。2008 年以前清明、端午、中秋还不是法定假日，且名称格式不同。

## 本地运行

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/python -m scripts.build --output docs/v1
.venv/bin/python -m scripts.validate docs/v1
```

只跑某一国：

```bash
.venv/bin/python -m scripts.build --skip-cn
.venv/bin/python -m scripts.build --skip-jp
```

日常构建只抓中国的当年、次年、以及缺失的年份，避免每天请求 20 次 gov.cn；历史年份已发布后不再重抓。需要回填或重抓全部历史年份：

```bash
.venv/bin/python -m scripts.build --all-cn-years
```

指定年份范围（调试用）：

```bash
.venv/bin/python -m scripts.build --jp-min-year 2020 --cn-min-year 2020 --cn-max-year 2027
```

## 校验规则

构建在临时目录完成并校验通过后才写入 `docs/v1`；失败时不会覆盖已有数据。

日本：

- 年份 >= 2007；1/1 必须是元日；每年 14–24 条。
- 日期唯一、升序、属于该年。
- 每个 `substitute` 必须能回溯到一个周日的祝日；每个 `bridge` 前后都必须是休日。
- 本地计算参考实现与官方 CSV 在 2007–2027 逐年对比（测试覆盖）。

中国：

- 年份 >= 2008；日期唯一、升序、属于该年。
- 已发布年份必须包含元旦、春节、清明节、劳动节、端午节、中秋节、国庆节。
- 放假日 15–40 天，补班日不超过 15 天。
- 补班日必须是周六/周日；唯一例外是 2020-02-03（疫情延长假期）。
- `pending` 文件必须为空，且只允许出现在尚未开始的年份。
- **更新窗口检查**：日本每年 3 月 1 日后仍缺下一年数据 → 失败；中国每年 12 月 1 日后次年通知仍为 `pending` → 失败。调试时可加 `--skip-window-check`。
- 工作流失败会发邮件；期间 App 继续使用旧数据。

## 自动化

| 工作流 | 频率 | 作用 |
|---|---|---|
| `update-data.yml` | 每天 03:17 UTC | 跑测试、抓取、校验、有变化才提交 `docs/v1` |
| `keepalive.yml` | 每月 1 日 | 空提交，防止公开仓库 60 天无活动导致定时任务被停用 |
| `validate.yml` | push / PR | 跑测试并校验已提交的数据 |
| `smoke.yml` | 每天，需手动启用 | 从 GitHub Pages 拉回 manifest 和文件，验证 sha256 |

启用 Pages：Settings → Pages → Source 选 `Deploy from a branch`，分支 `main`，目录 `/docs`。启用后，在 Actions 变量里设置 `PAGES_SMOKE=true` 打开冒烟检查。

keepalive 不依赖第三方 action（`gautamkrishnar/keepalive-workflow` 目前不可访问），用每月空提交实现，确定有效。

## 失败处理

- 官方源解析失败、校验不通过：工作流失败，发邮件；`docs/v1` 不变。
- 中国历史年份抓取失败：跳过该年并保留旧文件；当前年份/次年失败会直接让工作流失败。
- 次年通知尚未发布：生成 `pending` 文件，不算失败。
- 新数据条目比已发布版本减少超过 30%：拒绝发布。

## 出处与许可证

- 日本数据：出典：内閣府「国民の祝日」<https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html>
- 中国数据：国务院办公厅通知，链接见各文件 `papers` 字段。
- 中国通知解析器：复用 [NateScarlet/holiday-cn](https://github.com/NateScarlet/holiday-cn)，MIT License，Copyright (c) 2019 NateScarlet。改动见文件头。
- 本仓库代码：MIT，见 `LICENSE`；完整声明见 `NOTICE`。
