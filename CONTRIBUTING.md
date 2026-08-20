# 协作指南（CONTRIBUTING）

本仓库是**钢铁节能减碳数字孪生平台**：后端为 FastAPI 数值仿真引擎（`backend/app/`），前端为 Vue3 + Three.js 数字孪生场景（`frontend/`）。

代码托管在 GitHub：**https://github.com/qiuzhibin/power_simulation.git**，它是**源码的单一真相源**。本文档说明多人如何安全地协作与推送。

---

## 1. 获取权限

1. 联系仓库 owner（qiuzhibin）在 GitHub 仓库 → **Settings → Collaborators** 中把你加为协作者。
2. 配置你自己的鉴权方式（**二选一**）：
   - **SSH（推荐）**：把你的公钥加到 GitHub 账号 → **Settings → SSH and GPG keys**；之后用 `git@github.com:qiuzhibin/power_simulation.git`。
   - **HTTPS + Personal Access Token**：在 GitHub → **Settings → Developer settings → Personal access tokens** 生成 token（勾选 `repo` 权限）；克隆/推送时用 token 作为密码（建议配合 `git config --global credential.helper` 缓存，避免每次输入）。

> 注意：仓库已启用 `.gitignore`，会自动排除 `node_modules/`、`frontend/dist/`、`__pycache__/`、`*.pyc`、`*.log`、`*.png`、`.workbuddy/` 等。**不要**手动提交这些产物。

---

## 2. 本地环境

```bash
# 克隆
git clone https://github.com/qiuzhibin/power_simulation.git
cd power_simulation

# 后端（Python）
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # 如缺此文件，按 backend 内 import 安装依赖
uvicorn app.main:app --reload --port 8010

# 前端（Node）
cd frontend && npm install && npm run dev      # 开发
npm run build                                   # 产出 frontend/dist（仅本地/部署用，不进 GitHub）
```

---

## 3. 分支策略

- `master` 是**受保护的主干**，只接收经过评审的合并。
- 日常开发请基于 `master` 切**功能分支**：
  ```bash
  git checkout -b feature/你的功能简述
  ```
- 完成后推送功能分支，并在 GitHub 发起 **Pull Request** 合并回 `master`。
- 紧急修复可用 `hotfix/xxx`，流程相同。

---

## 4. 提交规范

提交信息建议遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
feat:     新增氢基竖炉设备读数
fix:      修复 h2_dri 单位拿不到设备读数的 bug
docs:     补充 CONTRIBUTING
chore:    清理前端死代码
refactor: 合并冗余计算器
```

也可用简洁中文描述。一次提交只做一件事，便于评审与回滚。

---

## 5. 推送（你只需要关心这一步）

推荐用仓库根目录的 **`push.sh`**（纯 git 操作，**不含服务器部署**）：

```bash
# 仅推送（要求工作树已提交）
./push.sh

# 或一键：先把所有改动提交再推送
./push.sh "fix: 修复 xxx"
```

脚本会自动 `git pull --rebase` 远端最新，避免覆盖他人提交；若产生冲突会提示你手动解决。

也可手动操作（等效）：

```bash
git pull --rebase github <你的分支>
git push github <你的分支>
```

---

## 6. 桌面端自动打包（GitHub Actions）

每次推送代码到 `master` 会自动触发 GitHub Actions 构建桌面安装包：

| 平台 | 产物 |
| --- | --- |
| Windows x64 | `SteelCarbonTwin-windows-x64-setup.exe`（Inno Setup 安装程序） |
| macOS Apple Silicon | `SteelCarbonTwin-macos-arm64.dmg` |

- 构建产物可在仓库 **Actions** 页面下载；
- 打 tag（如 `git tag v1.0.0 && git push github v1.0.0`）会自动发布 **GitHub Release**，附带上述安装包。

---

## 7. 常见问题

- **推送被拒（non-fast-forward）**：先 `git pull --rebase github <分支>` 再推。
- **rebase 冲突**：手动改文件 → `git add <文件>` → `git rebase --continue` → 再跑 `push.sh`。
- **忘了加协作者权限**：推送会报 403，联系 owner 加成员。
- **不小心提交了构建产物**：用 `git rm --cached <文件>` 移除并补一条提交；`.gitignore` 已默认排除，正常不会误提。
