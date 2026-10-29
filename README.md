# 桌面便签 Lite · v0.2

一块贴在桌面上的半透明便签：左边是日历，右边是「今天」。用 **PySide6 原生控件**画出来，没有 Electron，没有浏览器内核，冷启动不到 1 秒。

> 本仓库是 [TODAYmiao/desktop-notes-lite](https://github.com/TODAYmiao/desktop-notes-lite) 的重做版（v0.2）。
> 上游的精简版仍然可用；这一版把「记录一条待办要几秒」「不点开也知道今天还剩什么」当成硬指标重写了交互与数据层。

![今日视图](screenshots/v2-dark-week.png)

<table>
<tr>
<td><img src="screenshots/v2-dark-month.png" width="260" alt="月视图"></td>
<td><img src="screenshots/v2-light-week.png" width="260" alt="浅色主题"></td>
<td><img src="screenshots/v2-light-settings.png" width="260" alt="设置浮层"></td>
</tr>
</table>

---

## 为什么重做

改造前（上游 v0.1）：500×540 固定双栏，左月历右待办。

<img src="screenshots/app.png" width="420" alt="改造前：上游 v0.1">

上游是能用的，但读完全部 2000 行源码后，有几处是「一用就会踩」的实证缺陷，不是风格偏好：

| # | 上游的问题 | 位置 | v0.2 的做法 |
|---|---|---|---|
| 1 | **开机自启必然失败**：写注册表时拼 `pythonw.exe main.py`，却没有 PYTHONPATH，`import PySide6` 直接炸 | `window.py` 自启段 | `main.py` 自己把仓库根和 `.pylibs` 塞进 `sys.path`，命令里不再需要环境变量 |
| 2 | **跨零点不刷新**：`date.today()` 只在渲染时取，挂着不动就永远停在昨天 | `window.py` 渲染入口 | 30 秒一次的 rollover 定时器，跨天自动把「今天」推过去 |
| 3 | **勾一个丢一个字**：勾选/删除走「整列重建」，正在双击编辑的那行会被 `deleteLater` 掉 | `window.py` 列表渲染 | 行对象按 id 复用，只改状态不重建；编辑中的行跳过刷新 |
| 4 | 字数上限三处不一致（输入 200 / 新增 200 / 编辑 500 / sanitize 500） | 多处 | 统一成 `MAX_TEXT = 200`，进出都夹紧 |
| 5 | 删除**没有撤销**、没有确认 | — | 30 步撤销栈（新增/删除/勾选/改字/优先级/移动/顺延/新建重复任务） |
| 6 | 坏 JSON 被**静默丢弃**，`version` 字段从不读 | `store.py` | 坏文件改名留档 `notes.corrupt-<时间戳>.json`；v1 先备份 `notes.v1.bak.json` 再迁移 |
| 7 | `except Exception: pass` 吞异常，`pythonw` 下无 excepthook | — | 全局 excepthook 写 `crash.log`，界面弹 toast |
| 8 | 窗口位置写盘**非原子**，断电可能留下半截 JSON | `store.py` | 全部落盘走 `tmp → flush → fsync → os.replace` |

除此之外补上了上游缺的功能：**顺延**、**重复任务**、**定时提醒**、**跨日期搜索**、**自然语言快速添加**、**全局热键**、**浅色主题**、**月热力图**、**Markdown 导出**。

## 功能

**记录**
- 一句话输入：`评审材料 明天 @15:00 !!` 回车即存 —— 日期、提醒、优先级、重复规则都在这一行里写
- 输入时实时预览解析结果（`→ 明天 · 15:00 · 紧急`），认错了直接改字
- 全局热键 `Ctrl+Alt+N`：任何程序里按一下，便签跳到前台并聚焦输入框
- 右键任意一条：移到今天/明天、改优先级、编辑、删除

**回顾**
- 顶部大日期 + 今日进度环（`3/5`），一眼知道还剩几件
- 周视图 7 格 / 月视图 42 格一键切换，格点区分「有未完成」和「全部完成」
- 顺延条：昨天没做完的，一句「昨天还有 2 项未完成」+ 一键「搬到今天」
- 页脚：本月完成度 + 连续清零天数 + 近 28 天色带

**外观**
- 深/浅两套调色板，7 个预设强调色 + 取色器，背景光晕跟着强调色走
- 半透明 35%–100%、始终置顶、贴边吸附、鼠标离开自动淡化
- 窗口可缩放（360×520 起），支持四边拖拽和位置记忆

**系统**
- 托盘常驻、单实例（重复启动只唤回已有窗口）、开机自启
- 提醒到点弹 toast + 托盘气泡，同一件事一天只提醒一次
- 数据全在本机 JSON，可一键导出 Markdown

## 快速开始

### 直接跑源码

需要 Windows 10/11 + Python 3.11+。

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

环境建好后双击 `start.vbs`（无控制台）或 `debug.bat`（保留控制台看报错）。
`main.py` 会自动把仓库目录和 `.pylibs` 加进 `sys.path`，所以开机自启项不依赖任何环境变量。

### 没有 Python 的机器

Release 里的 `DesktopNotesLite.exe` 单文件版（约 41 MB）双击即用；首次启动会被 SmartScreen 拦一下（未签名），选「更多信息 → 仍要运行」。

### 打包

```bat
.venv\Scripts\pyinstaller.exe --noconfirm --clean --onefile --windowed ^
  --name "DesktopNotesLite" --icon "assets/icon.ico" --add-data "assets;assets" main.py
```

## 快速添加语法

| 写法 | 含义 |
|---|---|
| `今天` `明天` `后天` `大后天` | 相对日期 |
| `下周一` … `下周天` | 下一个自然周 |
| `10月30日` `6月1号` `2026-12-24` | 绝对日期 |
| `+3d` `+2w` `+1m` | 相对天数/周数/月数 |
| `@15:00` `@9点` `@9点半` `@21点30分` | 提醒时间 |
| `!` `!!` | 高 / 紧急 |
| `~每天` `~工作日` `~每周三` `~每月1日` | 重复规则 |

未识别的部分就是正文，顺序随意：`~工作日 @9:00 站会 !!`。

## 键盘与手势

| 操作 | 快捷键 |
|---|---|
| 记录一条 | `Ctrl+Alt+N`（全局） |
| 聚焦输入框 / 打开搜索 | `Ctrl+N` / `Ctrl+F` |
| 撤销 | `Ctrl+Z` |
| 关闭搜索、收起浮层 | `Esc` |
| 移动窗口 | 拖标题栏 |
| 缩放窗口 | 拖任意边角（7px 内） |
| 编辑待办 | 双击文字；`Enter` 保存、`Esc` 取消 |
| 删除 | 悬停出现 × |

## 数据

```
%APPDATA%\DesktopNotesLite\notes.json         任务、重复规则、设置
%APPDATA%\DesktopNotesLite\window-state.json  窗口位置与尺寸
%APPDATA%\DesktopNotesLite\crash.log          崩溃栈（如有）
```

schema v2：

```json
{
  "version": 2,
  "tasks": {
    "2026-10-30": [
      { "id": "a1b2c3d4e5f6", "text": "评审材料", "done": false,
        "createdAt": "2026-10-30T09:12:00", "doneAt": null,
        "priority": 2, "remindAt": "15:00", "rolledFrom": null, "seriesId": null }
    ]
  },
  "series": [
    { "id": "s1", "text": "写日报", "rule": "weekdays", "weekdays": [0,1,2,3,4],
      "dayOfMonth": 1, "priority": 0, "remindAt": null, "active": true }
  ],
  "settings": { "opacity": 80, "alwaysOnTop": true, "accent": "#ffb26b",
                "theme": "dark", "autoFade": false, "snap": true,
                "hotkey": "Ctrl+Alt+N", "autostart": false, "view": "week" }
}
```

- v1 文件（`{"version":1,"todos":{...}}`）启动时自动迁移，原文件备份成 `notes.v1.bak.json`
- 读到坏文件不覆盖：改名 `notes.corrupt-<YYYYmmdd-HHMMSS>.json` 留档，界面照常启动
- 重复任务只物化到「今天 -7 天 ~ +28 天」，不会无限生成

## 项目结构

| 文件 | 行数 | 职责 |
|---|---:|---|
| `main.py` | 120 | 入口：sys.path 自举、`--data/--shot/--view` 参数、excepthook、单实例 |
| `app/store.py` | 632 | schema v2、迁移与留档、原子写、重复任务物化、统计、导出 |
| `app/quickadd.py` | 274 | 自然语言解析（日期/时间/优先级/重复） |
| `app/theme.py` | 374 | 深/浅调色板、强调色联动、全局 QSS |
| `app/widgets.py` | 1049 | 日历格、进度环、勾选动画、开关、色块、热力图、toast、待办行 |
| `app/window.py` | 1571 | 主窗口、日历、列表、搜索、设置浮层、托盘、热键、定时器、缩放吸附 |
| `app/hotkey.py` | 109 | Win32 `RegisterHotKey` + 原生事件过滤 |
| `tests/` | 650 | 48 个 unittest（解析器 / 数据层 / 界面冒烟） |
| `tools/smoke.py` | 133 | 离屏冒烟：造数据 → 渲染 → 截图 → 走一遍交互 |
| `tools/selfcheck.py` | 108 | 逐条核对本 README 的功能承诺是否真的在代码里 |
| `.github/workflows/tests.yml` | 41 | CI：Windows + Linux × Python 3.11/3.12，跑自检与测试 |

## 测试

```bat
python -m unittest discover -s tests -t .
python tools\selfcheck.py
```

48 个用例，覆盖：v1→v2 迁移与备份、坏文件留档、字段夹紧、原子写、顺延与撤销、重复任务不重复物化、连续天数、热力图、窗口状态、快速添加语法、界面构建/增删改/搜索/主题切换。

`selfcheck.py` 是给「功能清单」装的一道闸：它把下面 25 条承诺逐条对着真实符号核一遍（比如「清零庆祝」要同时找到 `class Celebration` 和 `celebration.play` 的调用点），任何一条只剩文档没有代码就返回非零。改代码时顺手跑一次，比看截图靠谱。

截图（README 里那几张）由 `python tools\smoke.py screenshots` 生成，走的是真实渲染路径而不是拼图。

## 已知限制

- 只在 Windows 上验证；托盘、热键、置顶、吸附都用了 Win32 API
- 提醒依赖 30 秒轮询，精确到分钟；程序退出后不会提醒（没有常驻服务）
- 没有云同步、没有富文本、没有多窗口 —— 故意的

## 致谢

上游 [TODAYmiao/desktop-notes-lite](https://github.com/TODAYmiao/desktop-notes-lite) 提供了产品原型与视觉基调（半透明外壳、强调色光晕、自绘日历格）。这一版在其基础上重写了数据层与交互层。

## License

MIT
