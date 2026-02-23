# MacAgent GitHub 仓库设置指南

用于配合工具自我升级的 Git 版本管理与安全回滚。

---

## 一、在 GitHub 创建仓库

1. 打开 [https://github.com/new](https://github.com/new)
2. 填写：
   - **Repository name**: `MacAgent`（或自定）
   - **Description**: macOS AI Agent with self-upgrading tools
   - **Visibility**: Private（推荐）或 Public
   - **不勾选** "Add a README"（本地已有代码）
3. 点击 **Create repository**

---

## 二、本地初始化并关联

```bash
cd /Users/lzz/Desktop/未命名文件夹/MacAgent

# 若尚未初始化 Git
git init

# 确认 .gitignore 已包含 venv、__pycache__ 等
# 若 .gitignore 不存在，可创建：
# echo -e "venv/\n__pycache__/\n*.pyc\n.env\n.DS_Store\nbackend/data/contexts/*.json" > .gitignore

# 添加并提交
git add .
git commit -m "Initial: MacAgent with upgrade security baseline"

# 关联远程（替换 your-username 为你的 GitHub 用户名）
git remote add origin https://github.com/your-username/MacAgent.git

# 推送
git branch -M main
git push -u origin main
```

---

## 三、SSH 方式（可选）

若已配置 SSH key：

```bash
git remote add origin git@github.com:your-username/MacAgent.git
git push -u origin main
```

---

## 四、.gitignore 建议

确保以下内容在 `.gitignore` 中：

```
venv/
__pycache__/
*.pyc
.env
.env.local
.DS_Store
backend/data/contexts/*.json
backend/data/signatures.json
*.log
```

若 `data/contexts/` 含敏感对话，可整体忽略：

```
backend/data/
```

---

## 五、升级前的首次 Tag

设置完成后，建议打一个稳定 tag，便于回滚：

```bash
git tag -a v1.0-stable -m "Baseline before self-upgrade"
git push origin v1.0-stable
```

---

## 六、回滚示例

若升级出错，可快速回滚：

```bash
# 丢弃工作区所有修改
git checkout -- .

# 或回滚到上一 commit
git reset --hard HEAD~1

# 或回滚到指定 tag
git checkout v1.0-stable
```
