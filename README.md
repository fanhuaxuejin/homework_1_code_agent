# 代码解释 Agent

一个基于 **DeepSeek** 的代码解释助手：给它一个文件或一个问题，它会**自己去读代码、检索调用链、必要时实际运行代码验证**，然后给出带行号引用的结构化解释。

> 软件工程课程 Homework 1 —— 方向：**代码解释 Agent**
> 核心 Agent 循环自行实现。

---

## 一、它解决什么问题

把代码丢进聊天窗口问"这段什么意思"，模型只能靠猜测。实测中最典型的表现是：

| 场景 | 普通对话式提问 | 本 Agent |
|------|--------------|---------|
| 解释一个 3000 行文件 | 只能粘贴部分内容，其余靠猜 | 先 `list_symbols` 建骨架，再按行号区间精读相关部分 |
| "这个函数在哪被调用？" | 答"我看不到其他文件"，然后把搜索命令丢回给用户 | `search_code` 实际检索全仓库，给出 `文件:行号` |
| "这段位运算到底做什么？" | 用自然语言描述推测 | `run_python` 实际执行，用真实输出作为依据 |
| 文件是 GBK 编码 | 报编码错误 | 自动尝试 utf-8 / gbk / latin-1 |
| 文件有语法错误 | 崩溃或硬答 | 如实报告"第 22 行括号未闭合，无法完整解析" |

**核心区别**：模型不是被动接受一段文本，而是**具备自主获取信息的能力**。

### 实测效果

**跨文件调用链问题**：

```powershell
python main.py "demo/utils.py 里的 normalize_record 在哪里被调用了？"
```

实测结果：**7 步、8 次工具调用、16.5 秒**。

它的行动序列是：
1. `list_symbols` 找到 `normalize_record` 的定义位置
2. `search_code` 检索全仓库，定位到 `demo/app.py` 的调用点
3. **`run_python` 实际跑了一遍 `demo/app.py`**，发现直接运行会报 `ModuleNotFoundError`
4. 正确指出应该用 `python -m demo.app` 运行

**这就是"用执行结果验证"和"复述代码"的区别。**

**解释埋雷文件**：

```powershell
python main.py "解释 demo/sample_buggy.py 这个文件，重点找出其中的 Bug"
```

实测结果：**2 步、1 次工具调用、21.9 秒**，输入 2600 / 输出 4469 tokens。

它找全了文件里预埋的 8 个问题，并额外发现：
- 裸 `except:` 捕获的是 `BaseException` 而非 `Exception`（会吞掉 Ctrl-C）
- `open(path)` 未指定 `encoding`，跨平台读 UTF-8 文件会抛 `UnicodeDecodeError`
- `cursor` 未关闭的资源泄漏
- 函数名说"计算总价"却返回均值（职责不单一）

---

## 二、快速开始

### 环境要求

- Python 3.10+（开发环境为 3.12.6）
- 一个 DeepSeek API Key：[platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)

### 安装

```powershell
python -m pip install -r requirements.txt
copy .env.example .env
notepad .env          # 把 LLM_API_KEY 换成你的真实 Key
```

也可以直接用环境变量：

```powershell
$env:LLM_API_KEY = "sk-你的Key"
```

> ⚠️ `.env` 必须放在**项目根目录**（与 `config.py` 同级）。程序只读 `.env`，**不读 `.env.example`**。

### 环境自检（不消耗 API 额度）

```powershell
python main.py --check
```

它会列出 6 个已装载工具，逐个做冒烟测试，并**实际发起一次路径越权攻击**来验证安全防护是否生效。

**建议第一次务必先跑这一步**——它能在不花钱的前提下，把"环境问题"和"Agent 逻辑问题"分开。

### 开始使用

```powershell
python main.py                                    # 交互模式（推荐）
python main.py "解释 demo/sample_buggy.py"         # 单次提问
python main.py --verbose "解释 demo/utils.py"      # 显示工具完整输出
```

---

## 三、交互模式与命令

进入 `python main.py` 后：

```
解释 demo/sample_buggy.py                直接提问（Agent 自己决定调哪些工具）
demo/utils.py 第 20-40 行是什么意思        追问具体区间
normalize_record 在哪里被调用了？          跨文件问题，会触发 search_code
把 sample_good.py 的解释写成文档           会触发 write_report

/symbols demo/sample_good.py             查看文件结构（本地执行，不发请求）
/files [目录]                            列出目录（本地执行，不发请求）
/tools                                   查看已装载工具
/usage                                   查看 token 用量
/full                                    切换"显示工具完整输出"
/clear                                   清空对话记忆
/quit                                    退出（自动保存会话）
```

### 命令行参数

| 参数 | 说明 |
|------|------|
| `-w, --workspace PATH` | 指定工作目录，同时作为**路径安全边界** |
| `--max-steps N` | 单次提问最大推理步数（默认 12），防死循环 |
| `--verbose` | 打印工具调用的完整返回内容 |
| `--no-persist` | 不把会话写入 `.agent_memory/` |
| `--check` | 只做环境自检后退出（不调用 API） |

### 解释其他仓库

```powershell
python main.py -w "E:\some\repo" "解释 src/main.py"
```

目标目录会同时成为路径安全边界，Agent 无法读取该目录之外的文件。

---

## 四、工具清单

Agent 的能力边界由这 6 个工具决定：

| 工具 | 作用 | 关键设计 |
|------|------|---------|
| `list_dir` | 查看目录结构（递归 1–4 层） | 让 Agent 先建立全局视图，避免盲猜路径；跳过 `.git`/`node_modules` 等 |
| `list_symbols` | 提取类/函数/方法骨架与**行号区间** | Python 用 `ast` 精确解析，还原签名与 docstring 摘要；其他语言用正则粗提取 |
| `read_code` | 按行号区间读取代码，**输出带行号** | 支持分段读取；自动尝试 4 种编码；支持 37 种源码后缀 |
| `search_code` | 正则检索全仓库，返回 `文件:行号` 与上下文 | 支撑跨文件调用链分析；命中行用 `>>` 标记 |
| `run_python` | 在受控子进程中执行小段代码 | 硬超时 + 输出截断 + 剔除含密钥的环境变量 |
| `write_report` | 把结论写成 Markdown 到 `reports/` | 文件名白名单化，防路径穿越 |

### 安全边界

| 措施 | 位置 | 说明 |
|------|------|------|
| 路径限制 | 所有工具 | 文件访问被限制在 `--workspace` 内，`../` 越权被拒绝 |
| 编码容错 | `read_code` | utf-8 → utf-8-sig → gbk → latin-1 依次尝试 |
| 执行超时 | `run_python` | 默认 10 秒硬超时，`while True: pass` 会被强制终止 |
| 输出截断 | 各工具 | `run_python` 6000 字符、`read_code` 24000 字符、`search_code` 20000 字符 |
| 凭据隔离 | `run_python` | 剔除含 `API_KEY`/`TOKEN`/`SECRET`/`PASSWORD` 的环境变量 |
| 写入限制 | `write_report` | 只允许写 `reports/` 子目录，文件名白名单化 |
| 步数上限 | `agent/core.py` | 单次提问最多 12 轮，单轮最多 6 个工具调用 |

---

## 五、演示样例

`demo/` 目录下的文件都是**刻意设计的**，用来展示 Agent 在不同情况下的表现：

| 文件 | 用途 |
|------|------|
| `sample_buggy.py` | **埋了 8 个真实 Bug**（可变默认参数、浮点精度、除零、宽泛 `except`、闭包晚绑定、SQL 注入、时区混用等），检验问题发现能力 |
| `sample_good.py` | 正常代码，看它能否讲清设计意图与隐式假设 |
| `app.py` + `utils.py` | 跨文件调用链，验证 `search_code` 的定位能力 |
| `sample_frontend.js` | 非 Python 文件，验证通用解析分支 |
| `sample_syntax_error.py` | 语法错误文件（第 22 行括号未闭合），验证边界处理 |
| `sample_gbk_中文.py` | GBK 编码 + 中文文件名，验证编码容错 |
| `2026 online_1 L.cpp` | 竞赛代码（trie 树 + 位运算），作为真实复杂度代码的压力测试 |

### 演示

```powershell
python main.py --check                                  # 1. 环境就绪（免费，3 秒）
python main.py "解释 demo/sample_buggy.py"               # 2. 发现埋的 Bug（40 秒，核心亮点）
python main.py "normalize_record 在哪里被调用？"          # 3. 跨文件检索（15 秒，体现自主性）
```

### 其他实用问法

```powershell
python main.py "demo/utils.py 第 11-15 行做什么"
python main.py "demo/sample_good.py 里有哪些潜在问题"
python main.py "把 demo/app.py 的调用链讲清楚"
python main.py "解释 demo/2026 online_1 L.cpp 里 trie 的 insert 逻辑"
```

---

## 六、项目结构

```
code-agent/
├─ main.py                  CLI 入口：参数解析、事件渲染、交互循环、自检
├─ config.py                配置层：provider 可插拔、Key 与参数读取
├─ requirements.txt
├─ .env.example             Key 配置模板（复制为 .env 使用）
├─ README.md                本文件：安装与使用
├─ Design.md                设计文档：架构、循环、Prompt、安全、取舍
├─ agent/
│  ├─ core.py               ★ Agent 核心循环（输入→推理→工具调用→输出）
│  ├─ llm.py                LLM 封装层：分类重试、超时、思考模式、用量统计
│  ├─ memory.py             上下文记忆：滑窗裁剪 + 会话落盘
│  └─ prompts.py            提示词层：角色、工具策略、输出规范
├─ tools/
│  ├─ __init__.py           工具注册表导出
│  ├─ registry.py           注册机制、invoke 调度、路径安全校验
│  ├─ loader.py             工具装载器
│  ├─ read_code.py          读取代码（编码容错、分段）
│  ├─ list_symbols.py       结构提取（ast / 正则）
│  ├─ search_code.py        全仓库正则检索
│  ├─ list_dir.py           目录浏览
│  ├─ run_python.py         受限代码执行
│  └─ write_report.py       生成 Markdown 报告
├─ tests/
│  └─ offline_test.py       离线测试（不消耗 API 额度）
└─ demo/                    演示样例
```

详细设计说明见 **[Design.md](Design.md)**。

---

## 七、模型配置

主力使用 **DeepSeek**（`deepseek-flash`，1M 上下文，支持 Tool Calls / JSON Output / 思考模式）。

```ini
# .env
LLM_PROVIDER=deepseek
LLM_MODEL=               # 留空则用默认模型 deepseek-flash
LLM_THINKING=1           # 思考模式开关
LLM_TIMEOUT=120          # 单次调用超时（秒）
LLM_MAX_RETRIES=4        # 最大重试次数
RUN_PYTHON_TIMEOUT=10    # run_python 执行超时（秒）
```

### 换模型

`config.py` 里的 `PROVIDERS` 是一张表，因为主流厂商都提供 OpenAI 兼容接口，**换模型 = 改一个环境变量**：

```ini
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-pro    # 换更强的模型
```

> ⚠️ **模型名注意**：DeepSeek 当前可用模型为 `deepseek-flash` 与 `deepseek-v4-pro`。
> 详见 [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。
> 
>选模型时必须确认**支持 Function Calling**。例如阿里云百炼的 `qwen3-coder-next`
> 虽然便宜且专为代码优化，但官方能力表标注不支持工具调用，无法用于本项目。

### 关于思考模式的成本（实测）

同一问题、同一个文件：

| 模式 | prompt tokens | completion tokens |
|------|:---:|:---:|
| 关闭思考 | 861 | 641 |
| 开启思考 | 886 | **804**（多 25%） |

思考内容通过 `reasoning_content` 返回，**与正文共享同一 token 预算**。
如果把 `max_tokens` 设得很小，可能出现"正文为空 + `finish_reason=length`"——**不报错，只是答案被思考吃光了**。

---

## 八、常见问题

**Q：报错说缺少依赖 openai？**
执行 `python -m pip install -r requirements.txt`。

**Q：中文输出乱码？**
PowerShell 默认代码页不是 UTF-8。先执行 `chcp 65001`，或设置 `$env:PYTHONIOENCODING="utf-8"`。

**Q：报 401 / 认证失败？**
三种可能：`LLM_API_KEY` 没填、已失效，或 **`.env` 位置不对**（必须在项目根目录，与 `config.py` 同级）。程序只读 `.env`，不读 `.env.example`。

**Q：报 404 / model not found？**
`LLM_MODEL` 写了已下线的模型名。删掉该行用默认值，或改为 `deepseek-flash`。

**Q：Agent 一直反复读同一个文件？**
把 `--max-steps` 调小（如 6）能更快止损；同时检查问题是否过于笼统——问题越具体，工具调用越高效。

**Q：为什么某些文件读不了？**
`read_code` 只接受代码类后缀（共 37 种）。二进制、图片等会被拒绝并给出提示。

**Q：`demo/sample_buggy.py` 里的注释直接列出了答案，不算作弊吗？**
那个文件的 docstring 本身就是"埋点清单"，用于人工核对 Agent 的输出。**这是测试夹具的设计**，实际使用时应针对真实代码提问。

**Q：想确认 Agent 有没有瞎编怎么办？**
`--check` 和 `tests/offline_test.py` 都不消耗 API 额度。另外对任何行号引用，都可以用 `/symbols` 或直接打开文件核对。

---

## 九、测试

### 离线测试

```powershell
python tests/offline_test.py
```

19 项断言，覆盖：骨架完整性、语法检查、密钥防护、配置层、工具装载与 schema 合法性。

### 环境自检

```powershell
python main.py --check
```

覆盖：配置读取、6 个工具装载、逐个冒烟测试、路径越权防护验证。

**为什么这两步重要**：当出问题时，你需要在"花钱的 API 调用"和"不花钱的本地逻辑"之间划一条线。没有它们，你分不清是 Key 的问题还是代码的问题。

---

## 十、安全与隐私说明

- **只读优先**：Agent 默认不修改用户任何文件。唯一的写操作是 `write_report`，且被限制在工作目录的 `reports/` 子目录内，文件名经过白名单化处理。
- **路径边界**：所有文件访问都被限制在 `--workspace` 指定的目录内，`../../` 之类的越权路径会被拒绝（`--check` 会实际验证这一点）。
- **代码外发**：解释代码时，被读取的代码内容会发送给 DeepSeek API。**请勿用它处理机密代码。**
- **执行隔离**：`run_python` 在独立子进程中执行，带硬超时与输出截断，并剔除含 `API_KEY`/`TOKEN`/`SECRET` 等关键字的环境变量。**但这不是容器级沙箱**，仅适合本地自查；不要拿它执行来路不明的代码。
- **密钥管理**：Key 只从环境变量 / `.env` 读取，代码中无硬编码；`.env` 已被 `.gitignore` 排除。
