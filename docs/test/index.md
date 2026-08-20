# 测试

当代码依赖 Vault 路径、Markdown 双链或论文元数据时，测试应优先创建真实的临时 Vault 目录和文件。保持 `src/` 与 `test/` 解耦：应用代码不能 import 测试 fixture 或 helper。

## 发布前验收

产品发布 / 打 tag / 分发安装包前的完整流程与 Checklist：

- **[发布流程](release.md)** — 桌面版与 iPadOS 版的 bump、tag、Release 资产、签名与公证要求。
- **[iOS TestFlight](ios-testflight.md)** — iOS 签名、上传、App Store Connect 元数据与审核说明（无登录、配对 Notes）。
- **[发布前测试大纲（Checklist）](release-checklist.md)** — 按功能域（Vault、Library、入库、PDF、Agent、远程、CLI、平台矩阵）勾选；含 5 分钟冒烟与明确非目标说明。

## 目录结构

```text
test/
├── helpers/
│   └── create-test-vault.ts
├── scripts/
│   └── create-demo-vault.mjs   # 本地 demo / 手工验收用 Vault
└── *.test.ts
```

- `test/helpers/create-test-vault.ts` 用临时目录创建真实文件形态的 Vault。
- `test/scripts/create-demo-vault.mjs` 生成符合 catalog + 嵌套 paper 文件夹约定的 demo Vault（含 `.agentero/catalog.sqlite`，**schema_version = 3**）。
- 测试文件可以从 `src/` import 生产代码，但生产代码不能从 `test/` import。
- 优先在每个测试内声明最小必要 Vault 文件，让测试数据和断言靠近。

### Demo Vault 脚本

```bash
# 默认写到仓库 tmp/agentero-demo-vault
pnpm demo:vault

# ~/Downloads/agentero-demo-vault（嵌套 papers + catalog 样本数据）
pnpm demo:vault:downloads

# 仅 Create Vault 骨架（无样例论文 / 无 loose media）
pnpm demo:vault:empty -- ~/Downloads/agentero-empty-vault

# 校验已有目录
pnpm demo:vault:verify -- ~/Downloads/agentero-demo-vault
```

Demo 完整包内容（`--empty` 除外）：

| 类别 | 路径示例 | 用途 |
|---|---|---|
| 嵌套 paper 单元 | `papers/nlp/transformers/1706.03762/` | Library / NOTES / 双链 |
| paper 根 PDF | `{paper}/{id}.pdf` | 本地优先 PDF 预览 |
| 非 papers PDF | `assets/sample.pdf`、`notes/attachments/reading-list.pdf` | 任意路径 PDF 预览 |
| 图片 | `assets/figures/*.{png,jpg,gif,webp,svg,bmp,ico}` | 中间栏图片预览 |
| Catalog | `.agentero/catalog.sqlite` | schema v3（含 `is_read` / Translator 列）+ 样例 paper 行 |

每次生成会**重建** `catalog.sqlite`（避免重复跑脚本留下旧 schema）。依赖本机 `sqlite3` CLI。

## macOS 本地隔离验收

需要在安装包形态复测 patch 时，运行：

```bash
pnpm test:macos
```

该命令会先补齐干净工作树中未跟踪的 CLI sidecar / PDFium 构建输入，再依次执行 TypeScript/Rust lint、全量 Vitest、整个 Cargo workspace 测试，重建并校验 `tmp/agentero-test-vault`，然后只构建 `.app`、安装到 `~/Applications/Agentero Test.app`，最后启动该安装包，并通过测试 profile 内的 CLI 请求文件打开 Vault。测试同时校验安装包声明了 `agentero-test://`；实际验收使用 Host 已提供的请求文件通道，避免 Launch Services 在同 ID 的构建产物和已安装副本之间误选。两个带墙钟性能断言的 Vitest 文件各自在隔离进程中运行，其余文件使用默认并发；每项测试仍只执行一次，不放宽阈值。Cargo 基线显式设置 `AGENTERO_SKIP_NETWORK=1`，网络、SSH 和 MinIO 探针继续保留在现有的忽略/手动测试边界内，避免把外部服务波动误判为本地回归。任一步失败都会返回非零退出码。

测试版与正式版的隔离边界：

| 项 | 正式版 | 本地测试版 |
|---|---|---|
| App 名称 | `Agentero` | `Agentero Test` |
| Bundle identifier | `com.poco-ai.agentero` | `com.poco-ai.agentero.test` |
| Open URL scheme | `agentero://` | `agentero-test://` |
| XDG profile | `agentero` | `agentero-test` |
| 安装位置 | 通常 `/Applications/Agentero.app` | `~/Applications/Agentero Test.app` |
| Updater endpoint | 正式 Release | 空（不会拉取正式版更新） |
| 后台任务详情 | 悬停展开、终态短暂保留 | 有任务时固定展开、终态保留到手动清除 |
| Zotero Connector | 默认关闭 | 新 profile 默认开启（之后可手动关闭） |

脚本在安装前后校验 bundle identifier、测试前端标记、`agentero-test://` 声明、PDFium、内置 CLI 和正式版 `Info.plist` 哈希，并对复制后的测试包执行本地 ad-hoc 全包签名及严格校验。启动验收先等待 `app_ready`，再向 `agentero-test` profile 写入 CLI 请求文件，并从测试版日志确认接收。`tmp/agentero-test-vault` 是一次性测试数据，每次运行都会删除并重建；不要在其中保存需要保留的笔记。

## 前端测试

运行 TypeScript 单元测试：

```bash
pnpm test
```

Vitest 适合覆盖纯 TypeScript 逻辑，例如：

- 双链解析与预览链接重写；
- Vault-relative 路径规范化与目标解析；
- settings、shortcuts、metadata、viewer 等 helper。

测试 Vault 语义时，创建临时 Vault 目录，不要在 `src/` 中引入全局 mock 数据：

```ts
const vault = await createTestVault({
 "notes/Source.md": "See [[notes/Target]].",
 "notes/Target.md": "# Target",
});

try {
 const files = await vault.listMarkdownFiles();
 // assertions
} finally {
 await vault.cleanup();
}
```

## Rust 测试

运行后端测试：

```bash
cargo test --manifest-path src-tauri/Cargo.toml
```

解析器和 resolver 的边界用例可以放在对应 Rust 模块的 `#[cfg(test)]` 中。依赖 Vault 的 graph/index 测试应创建临时目录和文件，不依赖已提交的缓存文件。

## 手动验证

纯逻辑优先用自动化测试覆盖。涉及 UI 或桌面流程时，还需要启动应用检查受影响路径。如果 dev 端口被占用或无法做浏览器/桌面验证，汇报时需要明确说明。

建议用 `pnpm demo:vault` 生成的 Vault 做冒烟：

| 场景 | 预期 |
|---|---|
| 打开 demo vault | catalog 5 篇、Library 可见、tags 可筛 |
| 点 `assets/sample.pdf` / `notes/attachments/*.pdf` | 中间栏 PDF 预览（非 papers 路径） |
| PDF 工具栏：页码 / 适应宽度 / 适应整页 / 大纲 / `⌘F` | 跳页、缩放、书签跳转、命中高亮 |
| PDF 划词 | 平滑蓝色选区 + 操作菜单（高亮/笔记/提问/翻译） |
| 点 `assets/figures/*` 图片 | 中间栏图片预览 |
| Notes / `.md` 中粘贴图片 | 生成 `{mdDir}/assets/*`，正文 `![](./assets/…)`；文件树可见新文件 |
| 选中文档中的图片节点 | 显示 Markdown 源码而非位图；取消选中恢复预览 |
| 删除文档中的图片节点 | 若无其它引用，磁盘 `./assets/` 文件同步删除并刷新树 |
| 文件树删除一项 | 无确认弹窗；项进回收站；Library 下虚拟节点 Trash 打开中间栏可恢复 |
| Library Rescan | 盘上有 catalog 无的 paper 重新出现在表中 |
| 外部编辑器改打开的 `.md` | 应用内编辑器自动重载为磁盘内容 |
| 打开多 tab 后连按 `⌘W` | 无弹层时逐个关 tab；仅剩全库后再按关窗口 |
| 打开设置后 `⌘W` / `Esc` | 先关设置，不关标签 |
| 命令面板 `⌘P` / `⇧⌘P` 打开后再按同键或 `⌘W` | 关闭面板 |
| 触发删除失败 / 无 Vault 操作等 | 右上角 Toast，不出现侧栏 header 错误条 |

## 文档验证

修改 docs 或 `mkdocs.yml` 后运行：

```bash
mkdocs build --strict
```

如果本地未安装 MkDocs，先创建文档环境：

```bash
python3 -m venv .venv-docs
. .venv-docs/bin/activate
pip install mkdocs-material==9.7.1
mkdocs build --strict
```
