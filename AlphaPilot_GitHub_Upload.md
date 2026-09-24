GitHub 上传步骤指南（AlphaPilot 项目专用）

本指南记录了将本地项目上传到 GitHub 的完整流程，适用于未来所有项目。按照本步骤执行，可确保仓库结构干净、版本可回退、流程专业。

1. 初始化 Git 仓库

在项目根目录执行：

git init

成功后会生成 .git 文件夹，表示当前目录已成为 Git 仓库。

2. 创建 .gitignore

避免上传虚拟环境、node_modules、日志等无关文件。

创建 .gitignore 文件并加入：

.venv/
.venv_worker/
node_modules/
*.log
.env

根据项目需要可继续补充。

3. 添加所有文件到暂存区

git add .

如果 .gitignore 修改过，需要重新执行：

git add .gitignore

4. 提交到本地仓库

git commit -m "初始化项目：添加 .gitignore 并提交全部文件"

5. 绑定 GitHub 仓库

先在 GitHub 创建一个空仓库（不要勾选 README）。

然后绑定远程仓库（私有仓库）：

git remote add origin https://github.com/zhenqiangliang6-coder/AlphaPilot-Backend.git

前端开源项目，例如：

git remote add origin https://github.com/zhenqiangliang6-coder/AlphaPilot-Frontend.git

6. 推送到 GitHub

git push -u origin master

如果 GitHub 默认分支是 main：

git push -u origin main

推送成功后，GitHub 仓库即可看到所有文件。

7. 创建开发分支（可选）

用于前端美化或新功能开发：

git checkout -b dev-ui

8. 后续更新流程

修改代码后：

git add .
git commit -m "描述本次修改"
git push

如果在 dev-ui 分支：

git push -u origin dev-ui

9. 合并分支（可选）

当 dev-ui 开发完成后：

git checkout master
git merge dev-ui
git push

10. 常见问题

● 虚拟环境被上传了怎么办？

git rm -r --cached .venv_worker

然后重新提交。

● 远程仓库地址写错了怎么办？

git remote remove origin

重新添加即可。

结语

本指南适用于所有未来项目。严格按照此流程执行，可确保仓库干净、版本可控、结构专业
AlphaPilot OS — GitHub 国内稳定推送（SSH 版）完整指南
这是你以后在国内稳定推送 GitHub 代码的标准流程。
一次配置，永久稳定。

1. 生成 SSH Key（只需一次）
在 PowerShell 执行：

Code
ssh-keygen -t ed25519 -C "your_email@example.com"
当出现：

Code
Enter file in which to save the key (C:\Users\你的用户名/.ssh/id_ed25519):
直接按回车。

当出现：

Code
Enter passphrase (empty for no passphrase):
两次都直接回车（不设置密码）。

生成的文件：

Code
C:\Users\你的用户名\.ssh\id_ed25519
C:\Users\你的用户名\.ssh\id_ed25519.pub
2. 把公钥加入 GitHub（只需一次）
查看公钥：

Code
cat C:\Users\你的用户名\.ssh\id_ed25519.pub
复制整行内容。

打开：

https://github.com/settings/keys

点击：

New SSH key → 粘贴公钥 → 保存

3. 把仓库远程地址改为 SSH（只需一次）
进入你的项目目录：

Code
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
执行：

Code
git remote set-url origin git@github.com:zhenqiangliang6-coder/AlphaPilot-Backend.git
4. 测试 SSH 是否成功（只需一次）
Code
ssh -T git@github.com
第一次会提示：

Code
Are you sure you want to continue connecting (yes/no/[fingerprint]):
输入：

Code
yes
成功标志：

Code
Hi zhenqiangliang6-coder! You've successfully authenticated, but GitHub does not provide shell access.
5. 以后每天推代码（永久流程）
每次开机后，只需要三步：

Code
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
git add .
git commit -m "描述"
git push
SSH 通道会保证：

不 timeout

不 reset

不卡住

不掉线

永远稳定

6. 常见问题（你以后可能会遇到）
🔹 push 显示 Everything up-to-date
说明没有新提交，正常。

🔹 push 秒完成
说明 SSH 工作正常。

🔹 你换电脑时
只需要重新生成 SSH key 并加入 GitHub。

专业、清晰、可复用、适合放进你项目文档的 Git 回滚操作手册。
这是你刚才成功回到纯 V3（d5c943a）的完整流程，已经整理成正式文档格式。

📘 Git 回滚操作手册（适用于恢复历史版本 / 回到 V3）
📌 适用场景
当你需要：

回到某个历史版本（如 V4 出现前的纯 V3）

撤销错误修改

恢复到稳定版本

查看项目的完整历史时间线

本手册提供完整、可复用的 Git 回滚流程。

1️⃣ 查看完整提交历史（找到目标版本）
使用以下命令查看所有 commit（包含分支、标签、HEAD 指向）：

Code
git log --oneline --graph --decorate --all
示例输出（关键部分）：

Code
* 964f8d0 (HEAD -> main, origin/main) Initial commit for VSCode V4
* ac58d8d 描述V3.5+ UI 测试
* d5c943a 修改4B模型正确运行
* 04990b9 描述local_v3修改
* cec895c 你的提交信息
* 189564d 初始化项目：添加 .gitignore 并提交全部文件
在这里，我们选择回滚到：

Code
d5c943a 修改4B模型正确运行
这是纯 V3 的黄金版本。

2️⃣ 尝试切换到目标版本（可能失败）
Code
git checkout d5c943a
如果出现以下错误：

Code
error: Your local changes to the following files would be overwritten by checkout:
...
Please commit your changes or stash them before you switch branches.
说明当前目录有未提交修改，需要先处理。

3️⃣ 丢弃所有本地修改（恢复干净状态）
如果你确认当前修改不需要保留（如 V4 残留文件），执行：

恢复所有文件到最新提交状态
Code
git restore .
强制丢弃所有修改
Code
git reset --hard
输出示例：

Code
HEAD is now at 964f8d0 Initial commit for VSCode V4
表示当前工作区已干净，可以安全切换版本。

4️⃣ 切换到目标历史版本（成功）
Code
git checkout d5c943a
成功后会看到：

Code
HEAD is now at d5c943a 修改4B模型正确运行
并提示：

Code
You are in 'detached HEAD' state.
这表示你已经成功回到历史版本（纯 V3）。

5️⃣（可选）为历史版本创建一个新分支（推荐）
为了长期保存纯 V3，建议创建一个新分支：

Code
git switch -c v3-clean
以后随时切换：

Code
git switch v3-clean
📌 完整命令清单（可直接复制）
Code
git log --oneline --graph --decorate --all

git checkout d5c943a
# 如果报错，执行：
git restore .
git reset --hard

git checkout d5c943a

# 可选：创建纯 V3 分支
git switch -c v3-clean
🎉 最终效果
执行完以上步骤后，你将成功：

回到 V4 出现前的纯 V3

清除所有 V4 残留

恢复到稳定、干净、可运行的版本

保留完整历史，不破坏 main 分支

如果你愿意，我可以继续帮你写：

Git 分支管理最佳实践（V3 / V4 并行开发）

如何把 v3-clean 推送到 GitHub 保存

如何从 V3 再升级到 V4（安全路线）

