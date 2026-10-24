@echo off
chcp 65001 >nul
cd /d "C:\Users\peili\knowledge-base"

echo ============================================
echo   推送知识库到 GitHub
echo   仓库：https://github.com/peilin5566/knowledge-base
echo ============================================
echo.

rem 如果还没建过远端的先断开旧配置，重新指向目标仓库
git remote remove origin >nul 2>&1
git remote add origin https://github.com/peilin5566/knowledge-base.git

echo 正在推送 main 分支...
echo （首次会弹出 GitHub 登录窗口，用浏览器登录或用 Personal Access Token 均可）
echo.
git push -u origin main

echo.
if %ERRORLEVEL% EQU 0 (
    echo [成功] 已推送。
    echo.
    echo 下一步：
    echo   1. 打开 https://github.com/peilin5566/knowledge-base/settings/pages
    echo      把 Source 改成 GitHub Actions
    echo   2. 打开 https://github.com/peilin5566/knowledge-base/settings/actions
    echo      把 Workflow permissions 改成 Read and write permissions
    echo   3. 约 1-2 分钟后访问 https://peilin5566.github.io/knowledge-base/
) else (
    echo [失败] 常见原因：
    echo   - 仓库还没在 GitHub 上创建：先去 https://github.com/new 建一个名为 knowledge-base 的 Public 空仓库
    echo   - 网络不通 GitHub：可改用 SSH 地址，或先设置代理
    echo   - 凭据没通过：重新运行并登录
)
echo.
pause
