---
name: pi-extension-dev
description: 开发 pi (pi-coding-agent) 的 extension，或在本项目的 pi-configs 下创建/修改 pi 启动配置版本。当用户要求编写、调试 pi extension，或管理 pi 配置时使用。
---

# pi Extension 开发

本 skill 不重复讲解如何开发 extension——本仓库内有 pi 上游源码的 clone（`references/repos/pi`，gitignored），自带完整文档，开发时**直接引用这些文档**作为权威依据，不要凭记忆写 API。

使用前确认 clone 与本机 pi 版本一致：`git -C references/repos/pi log -1` 对比 `pi --version`，落后就 `git -C references/repos/pi pull`（远程是上游 `earendil-works/pi`）。pi 的 npm 安装包也自带同版本文档，位于 `$(npm root -g)/@earendil-works/pi-coding-agent/docs/`，可作为 clone 未同步时的备选。

## 权威文档（开发时必读）

主文档（extension API、事件、工具、UI）：

- `references/repos/pi/packages/coding-agent/docs/extensions.md`

配套文档（按需查阅）：

- `references/repos/pi/packages/coding-agent/docs/mcp.md` — MCP 服务器配置（`pi mcp` 命令、`mcp.json`、exposure）
- `references/repos/pi/packages/coding-agent/docs/codemode.md` — codemode 工具：模型写 JS 脚本在沙箱中调用其他工具
- `references/repos/pi/packages/coding-agent/docs/custom-provider.md` — 自定义模型 provider
- `references/repos/pi/packages/coding-agent/docs/packages.md` — 把 extension 打包成 npm/git 包分发
- `references/repos/pi/packages/coding-agent/docs/tui.md` — TUI 组件 API（自定义渲染、overlay）
- `references/repos/pi/packages/coding-agent/docs/rpc.md` — RPC 模式与 extension UI 协议（细分主题见 rpc-commands.md、rpc-extension-ui.md）
- `references/repos/pi/packages/coding-agent/docs/session-format.md` — Session 存储与 SessionManager
- `references/repos/pi/packages/coding-agent/docs/keybindings.md` — 快捷键 id 列表
- `references/repos/pi/packages/coding-agent/docs/skills.md`、`slash-commands.md`、`configuration.md` — skills / 斜杠命令 / 配置

## 示例库

`references/repos/pi/packages/coding-agent/examples/extensions/` 下有 80 个可运行示例（hello、todo、permission-gate、plan-mode、ssh、subagent 等）。写新 extension 时优先找相近示例参考，不要从零发明结构。

## 1.0 起的新 API 面（extensions.md 中有详解）

- `pi.registerMcpServer()` / `pi.unregisterMcpServer()` / `pi.getMcpServers()`，及 `mcp_servers_change` 事件——extension 可注册会话级 MCP 服务器
- 工具 `exposure` 分级（`codemode` / `deferred` / callable）与 `namespace` 分组，控制工具对模型和 codemode 脚本的可见性
- 工具声明 `outputSchema` 并返回 `structuredContent` 后，codemode 脚本等程序化调用方能拿到结构化结果
- 工具 `annotations`（`readOnlyHint` 等 MCP 语义），供权限类 extension 做审批判断

## 加载与测试位置

- 本项目的扩展开发位置：`pi-configs/<版本>/extensions/`，可用单文件 `<名称>.ts` 或子目录 `<名称>/index.ts`。
- 通过 `./pi-configs/<版本>/start.sh` 加载；启动脚本把配置目录作为本地 pi 资源包传给 `--extension`，并用 `--no-extensions` 限定自动加载的扩展集合。
- 全局 `~/.pi/agent/extensions/` 和项目 `.pi/extensions/` 不会自动加载；额外扩展可显式传入 `-e ./path.ts`。
- 配置目录内的扩展支持 `/reload`，包括重新发现新增的扩展文件。

## 与本项目的关系：pi-configs 配置版本

本项目根目录有 `pi-configs/`，用于存放 pi 的启动配置版本（现有 `default/`）。约定见 `pi-configs/README.md`：

- 每个子目录是一套配置版本，含 `start.sh`（保留调用时 cwd，透传额外参数）、`SYSTEM.md`（可编辑的提示词主体）、`extensions/`（该配置的扩展源码）和 `sessions/`（本地会话，Git 忽略）；AGENTS.md 和 skills 仍由 pi 动态追加
- 从仓库根目录用 `./pi-configs/<版本>/start.sh` 启动
- 新增配置版本：复制 `default/` 中的启动脚本、提示词和需要的扩展源码到新目录，不复制 `sessions/` 历史记录
- 模型、登录态和内置工具配置沿用本机 pi；会话通过 `--session-dir` 保存到对应配置的 `sessions/`，可用同一启动脚本的 `--continue` / `--resume` 恢复
- 配置目录还可添加 `skills/`、`prompts/`、`themes/`，按 pi 本地资源包约定额外加载；这些类型的全局和项目资源仍按 pi 的规则发现

开发/调试 extension 时，如需隔离环境验证（自定义 system prompt、指定 extension 集合等），就在 `pi-configs/` 下新建一个配置版本来跑，不要改动 `default/` 或全局 `~/.pi/agent/` 的现役配置。
