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