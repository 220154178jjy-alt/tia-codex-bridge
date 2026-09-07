# TIA Codex Bridge

An MCP bridge for Siemens TIA Portal Openness that lets Codex and other AI assistants inspect PLC projects, import or export programs, and compile with read-only defaults and opt-in writes.

通过 **MCP → Python.NET → Siemens TIA Portal Openness**，让本机 Codex 读取、导入、编译和保存 TIA 工程。使用本地标准输入输出（stdio），桥本身不调用任何 AI API，也不开网络监听端口。

**版本 0.1.0 是需要 Windows/TIA 实机验收的初始实现。** 开发环境没有 TIA Portal；协议、文件保护、适配层替身测试不代表真实 Siemens 接口已经运行成功。默认对齐 V20 官方文档，V19 可配置但未验证。没有实际测试过的 TIA 版本不会标成“已兼容”。

## 能做什么

| 工具 | 作用 |
| --- | --- |
| `status` | 查看真实/模拟后端、写入开关、工程副本和超时状态 |
| `open_project` | 复制完整的已关闭工程文件夹，在新的 TIA UI 实例中打开副本 |
| `list_plcs` | 遍历设备、未分组设备及设备组，返回 PLC 标识 |
| `list_blocks` | 列出普通程序块，包括嵌套用户分组 |
| `export_block` | 将指定块导出成 SimaticML XML，返回文件与 SHA-256 |
| `read_artifact` | 读取 staging/artifacts 中的源码并计算 SHA-256 |
| `import_source` | 导入 SCL 并生成块，或导入 SimaticML 程序块 XML |
| `compile_plc` | 调用 TIA 编译软件，返回错误、警告及递归诊断 |
| `save_project` | 保存工作副本，保留原工程 |

默认禁止导入、编译和保存；启动时加 `--allow-writes` 开启。编译也可能改变离线工程数据，因此按修改操作处理。导出只创建新的本地文件。

本版不提供 PLC 下载、CPU RUN/STOP、强制 I/O、在线变量写入、硬件组态修改、HMI 编辑或任意脚本执行接口。不接管已经打开的 TIA 实例，不自动处理 UMAC/保护密码，不自动放行 Openness 访问提示。

## Windows 安装

需要：

1. 安装 TIA Portal STEP 7 与匹配版本的 Openness，具备相应许可证和项目所需的选件/HSP。
2. 当前 Windows 用户加入 `Siemens TIA Openness` 本地组，重新登录使组成员资格生效。可在“计算机管理 → 本地用户和组”中设置。
3. Python **3.11 x64**（也接受 3.12，Linux 核心层已测；Windows interop 待验收）、.NET Framework 4.8、本机 Codex。
4. 遇到 Siemens 的 Openness 授权提示时，由用户在本机处理。不要关闭安全提示来绕过授权。

将仓库下载到例如 `C:\Dev\tia-codex-bridge`，在该目录的 PowerShell 中运行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[windows]"
```

安装仅依赖 Python.NET 调用 CLR。Siemens DLL 使用 TIA 本机安装目录中的文件，仓库不附带也不重新分发原厂 DLL。

准备两个独立、不互相嵌套的目录：

```text
C:\TIA\Projects\Demo\Demo.ap20
C:\TIA\BridgeWork
```

`Demo` 必须是完整、已保存并关闭的工程文件夹，包含伴随文件。不能仅复制 `.ap20` 单个文件，不能把所有项目混放在同一工程文件夹。桥会复制其整个父文件夹，复制前后检查源目录是否变化；这不是对正在编辑工程的事务快照。当前复制上限为 2 GiB / 20,000 个文件及目录，超限直接拒绝。

项目根目录和工作目录使用本地固定磁盘；拒绝 UNC、映射网络盘、符号链接和 Windows junction/reparse point。两个目录都应放在 Git 工作区之外。

## 连接 Codex

将 [config/codex.example.toml](config/codex.example.toml) 中的表合并到本机 `%USERPROFILE%\.codex\config.toml`，修改 Python、工程根目录、工作目录和 TIA PublicAPI 路径。不要覆盖已有 Codex 配置，也不要上传真实配置。

然后重启 Codex，检查 MCP 工具列表。默认使用真实 Openness 后端；仅 `open_project` 第一次执行时加载原厂 DLL 和启动 TIA，因此 MCP 握手不会被 TIA 启动拖住。

这是 **Windows 本机** 的桥。当前云端聊天、手机和纯 Linux/WSL Python 不能直接访问你电脑里的 Openness。此配置使用原生 Windows Python，由运行在同一 Windows 主机上的 Codex 启动。桥不需要 OpenAI API Key；Codex 自身的登录/模型权限照常由 Codex 管理。

## 一次完整操作

先对 Codex 说：

> 使用 tia_openness，先查 status，确认 simulated=false。打开 Demo/Demo.ap20 的工作副本，列出 PLC 和程序块，先不要修改。

`open_project` 返回 `sessions/<本次标识>/Demo.ap20`。这个路径相对于工作目录，是之后保存的目标。原工程一直留在项目根目录中。

要试验 SCL：将 [examples/BridgeDemo.scl](examples/BridgeDemo.scl) 放到 `C:\TIA\BridgeWork\staging\BridgeDemo.scl`；在 Codex MCP 配置的 `args` 中加上 `--allow-writes`，重启桥，再打开一次新副本。

> 在确认的 PLC 中，读取 staging/BridgeDemo.scl，检查代码并记录返回的 sha256；用这个值作为 expected_sha256 导入，allow_replace=true；然后编译，解释所有错误和警告，确认结果后保存工作副本。

工具调用的 `plc_id` 和 `block_id` 必须取自当前会话的列表，不能猜。`expected_sha256` 必须来自实际待导入文件；读取后文件变化会导致导入被拒绝。导入会再生成固定内容的新文件，确保传给 Openness 的是检查过的字节。

SCL 生成可能覆盖同名块/类型，因此必须传 `allow_replace=true`。它不是“绝不覆盖”的新增接口。失败也可能留下部分修改，检查工作副本后决定继续修复或重新从原工程开始。源文件会保留在 TIA 的 External sources 中，不自动删除。

编译结果的 `errors` 大于零时，应先修正。本版没有完整 SCL 解析器、梯形图语义验证器或真实设备仿真器；编译是否通过必须以本机 TIA 结果为准。示例只有布尔逻辑，没有映射物理 I/O。

## 梯形图怎么处理

Openness 通过 SimaticML XML 表达 LAD/FBD 等程序块。先 `export_block`，再 `read_artifact`，让 Codex 根据真实导出结构修改副本 XML，放入 `staging/`，最后导入并编译。

**不会直接把任意自然语言自动转换为已验证的梯形图。** 本版未实现鼠标画图、自动布局或 SCL→LAD 转换。XML 导入只面向普通程序块并导入根块组；若原块在子组，需在 TIA 检查目标分组及引用，不保证原有分组位置不变。Software Units、Safety Units、库类型、特殊保护块不在已实现范围内。

SCL 入口按所查 Openness 文档保守限定为 ASCII；中文注释/标识符请先换成 ASCII，或使用相应版本的合法 UTF-8 SimaticML XML。不会静默改写编码。

## 超时、保存与关闭

Openness 调用在同一个 STA 线程上串行执行。默认操作超时 240 秒，示例 Codex 工具超时为 300 秒；可把 `--operation-timeout` 调整到 10–600 秒，并让 Codex 超时更长。

超时后操作可能仍在 TIA 内完成，桥将拒绝后续 Openness 操作，`status` 会显示 `session_uncertain=true`。不要自动重试导入/保存；先检查 TIA UI 的副本状态，再重启桥。不会声称已回滚，也不会强杀 TIA。

桥退出不自动保存，也不主动关闭 TIA 中打开的项目。因为使用带界面的实例，UI 可保留供你检查或恢复未保存修改。一个桥进程只打开一个工程；需要另一个工程时，先处理当前修改，再重启桥。新的 open 总是创建新的工作副本，不会自动接着之前的副本改。

## 发布前检查

仓库公开意味着代码可以被浏览和复制；敏感信息检查的作用是阻止凭据及内部配置随代码发布，不是阻止爬虫访问公开代码。

上传前先审查 `git status` 和 `git diff --cached`，仅暂存准备发布的源码，然后运行：

```powershell
python scripts/scan_publish.py --staged --history
```

只有退出码为 0 才继续推送。检查的是 **Git 暂存区实际内容与所有本地可达历史**，包括历史里已经删除的文本。扫描失败或无法完成时返回非零；输出只含位置/规则，不打印匹配值。支持 `--report` 将包含文件 SHA-256 清单的报告存到仓库外。

启用本地提交/推送检查：

```powershell
git config core.hooksPath .githooks
```

Git 钩子需要本机 `python3` 或 `python` 命令可用。预提交检查暂存区，预推送再检查历史。任何人都能禁用自己机器的 Git 钩子；这不是不可绕过的访问控制。GitHub Actions 中的扫描发生在上传之后，只提供补充检查，不能代替上传前扫描。

检查规则、剩余风险及 Windows 验收步骤见 [SECURITY.md](SECURITY.md) 与 [docs/windows-acceptance.md](docs/windows-acceptance.md)。

## 开发与测试

核心协议层不依赖外部包，可以在 Linux/Windows 运行：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q tia_bridge scripts
```

`--backend mock` 仅用于无 TIA 环境的协议开发：工具结果始终标注 `simulated=true`，模拟“编译”返回 `MOCK_NOT_COMPILED` 和空错误计数，不伪造“零错误编译成功”。Mock 使用临时测试工程文件，与真实 `.ap20` 内容无关。

GitHub 的 Linux/Windows CI 测协议和文件检查；托管 runner 未安装 TIA，不构成实机验收。已做及未做的验证见 [docs/verification.md](docs/verification.md)。

接口依据仅使用原厂/项目官方资料，链接集中在 [docs/sources.md](docs/sources.md)。
