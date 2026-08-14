# Enable Chrome AI — Codex 插件

[English](README.md) | [简体中文](README.zh-CN.md)

这是一个 Codex 插件，它封装了
[`lcandy2/enable-chrome-ai`](https://github.com/lcandy2/enable-chrome-ai)
中的字段修改逻辑，并增加了可恢复备份、JSON 原子写入、完整文档写后验证和指定备份恢复功能。

安装插件不会自动修改 Chrome。插件会先进行只读检查；执行修改或恢复前，技能会要求用户明确确认。

## 安装

添加这个 Git marketplace，然后安装插件：

```bash
codex plugin marketplace add hugecheng/enable-chrome-ai-codex-plugin --ref main
codex plugin add enable-chrome-ai@enable-chrome-ai-codex-plugin
```

安装后请新建一个 Codex 任务，以便加载插件，然后输入：

```text
检查我的本地 Chrome 是否已经配置 Gemini 使用资格。
```

## 修改内容

字段修改行为有意与上游 `main.py` 保持一致：

- 递归地把已有的 `is_glic_eligible` 字段改为 `true`；
- 把根级别的 `variations_country` 设置为 `"us"`；
- 当 `variations_permanent_consistency_country` 已经是至少包含两个元素的列表时，把第一个元素更新为 Chrome 的 `Last Version`，把第二个元素更新为 `"us"`，并保留后续元素。

本插件另外提供：

- 检测上游支持的 Stable、Canary、Dev 和 Beta 用户数据路径；
- 写入前关闭上游脚本所选择的 Chrome 进程；
- 每次实际写入前创建经过验证的备份，并在 POSIX 系统上设置为 `0600` 权限；
- 在目标文件同一目录写入临时文件，刷新到磁盘后进行原子替换；
- 重新读取结果，并验证完整 JSON 文档；
- 只列出经过验证的备份，并且只允许恢复已识别 Chrome 通道备份目录中的指定备份；
- 恢复前再次创建安全备份。

备份保存在各 Chrome 通道用户数据目录下：

```text
Codex Backups/enable-chrome-ai/
```

## 重要安全说明

- 应用修改或恢复备份会关闭 Chrome，可能丢失未提交的网页表单、未完成下载或其他浏览器工作。
- 脚本会修改 Chrome 现有的 `Local State` 文件。虽然它会创建备份并使用原子写入，仍建议先审查源码，并对重要的浏览器配置单独备份。
- 请使用拥有 Chrome 配置文件的同一个操作系统用户运行。除非管理员账户本身拥有该配置文件，否则不要使用 `sudo` 或管理员身份运行。
- Windows 上的备份会继承 Chrome 用户数据目录的 ACL，因为 Python 的 POSIX 权限位不能表示 Windows ACL 所有权。请确保该目录只允许你的账户访问。
- Chrome 或 Google 之后可能重新写入这些字段。不要自动循环修改；应先检查当前状态。
- 本工具只修改本地资格和配置字段，不能保证 Gemini 一定出现。账号类型或年龄、组织策略、登录状态、设备地区、产品可用性及分批发布仍可能产生影响。
- 本项目与 Google、Chromium、OpenAI 及上游项目作者没有隶属或背书关系。使用风险由用户自行承担。

## 已测试环境

当前脚本和插件清单已在以下环境完成测试：

- Intel Mac 上的 macOS 15.7.9；
- Google Chrome Stable 151.0.7922.138；
- Python 3.14.3；
- Codex 插件及 marketplace 结构校验。

上述两条安装命令已使用 Codex app 内置的 CLI `0.148.0-alpha.9` 核对语法。目前尚未在一台全新设备上完成 Git marketplace 端到端安装测试。

Windows 和 Linux 用户数据路径及 `psutil` 进程处理路径来自上游实现，但这个派生版本尚未在真实 Windows 或 Linux 设备上测试。没有安装 `psutil` 时，macOS 和 Linux 可以使用本机进程管理后备方案；Windows 需要安装 `psutil`。

建议使用 Python 3.13 或更高版本，与上游项目要求保持一致。

## 备份和恢复

正常的 Codex 工作流会在修改和恢复前要求确认。开发或审查时，也可以直接使用脚本命令：

```bash
python3 plugins/enable-chrome-ai/skills/enable-chrome-ai/scripts/chrome_ai_state.py check
python3 plugins/enable-chrome-ai/skills/enable-chrome-ai/scripts/chrome_ai_state.py apply
python3 plugins/enable-chrome-ai/skills/enable-chrome-ai/scripts/chrome_ai_state.py list-backups
python3 plugins/enable-chrome-ai/skills/enable-chrome-ai/scripts/chrome_ai_state.py restore --backup "/经过验证的备份路径"
```

在未保存的浏览器工作全部处理完毕前，不要执行 `apply` 或 `restore`。

## 开发和验证

运行隔离测试套件不会接触真实 Chrome 配置：

```bash
python3 -m unittest discover -s plugins/enable-chrome-ai/tests -v
```

测试套件会把字段修改行为与冻结的上游 `main.py` 逻辑进行比较，验证数组尾部元素保留，测试备份、应用和恢复的完整往返，检查 POSIX 备份权限，并拒绝识别范围之外的备份路径。Windows 测试会确认文件在继承的配置目录 ACL 下仍可写。

GitHub Actions 会在 macOS、Windows 和 Linux 上运行隔离测试。这些 CI 测试会验证与平台无关的逻辑和模拟工作流，但不能替代各系统上的真实 Chrome 修改和恢复测试。

## 公开前需要补充的内容

- [x] 保留上游署名和 MIT 许可证。
- [x] 提供英文和简体中文文档。
- [x] 说明会关闭 Chrome、备份和恢复方式以及敏感数据注意事项。
- [x] 增加隔离测试和跨平台 CI。
- [ ] 在真实 Windows 和 Linux Chrome 上完成修改与恢复测试。
- [ ] 在全新设备完成安装测试后创建带版本号的 Release。
- [ ] 如果提交到公开插件目录，补充截图或简短演示。

## 署名和许可证

本仓库派生自
[`lcandy2/enable-chrome-ai`](https://github.com/lcandy2/enable-chrome-ai)，
该项目最初由 [`lcandy2`](https://github.com/lcandy2) 调研并编写。上游项目采用 MIT 许可证，并要求派生作品保留署名。

上游版权声明和 MIT 许可文本保存在 [`LICENSE`](LICENSE) 中。其他署名及修改摘要记录在 [`NOTICE.md`](NOTICE.md) 中。

## 报告问题

报告问题时，请勿上传完整的 Chrome `Local State`、配置文件、Cookie、令牌或备份文件。只需提供 Chrome 版本、操作系统、插件版本、执行的命令和经过脱敏的错误信息。涉及安全问题时，请遵循 [`SECURITY.md`](SECURITY.md)。
