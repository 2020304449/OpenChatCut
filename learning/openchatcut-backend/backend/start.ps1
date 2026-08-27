# OpenChatCut 学习后端启动脚本
# 用法（在 backend 目录下）:
#   .\start.ps1              # DeepSeek 模式（默认）
#   .\start.ps1 -Mode mock   # mock 模式，无需 API key
param(
    [ValidateSet('deepseek', 'mock')]
    [string]$Mode = 'deepseek'
)

# ===== 配置区（每次启动前在这里填 API key）=====
$ApiKey = ''          # 填 DeepSeek API key，例如 sk-xxx
$Port   = 8000
$BaseUrl = 'https://api.deepseek.com'
$Model   = 'deepseek-chat'
# ================================================

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# 1. 清理占用端口的旧进程
$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $procIds = $conn | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $procIds) {
        Write-Host "端口 $Port 被进程 $procId 占用，正在结束..."
        Stop-Process -Id $procId -Force
    }
    Start-Sleep -Milliseconds 500
}

# 2. 设置 LLM 环境变量
if ($Mode -eq 'mock') {
    $env:LLM_MOCK = '1'
    Write-Host 'LLM 模式: mock（无需 API key）'
}
else {
    $env:LLM_MOCK     = '0'
    $env:LLM_BASE_URL = $BaseUrl
    $env:LLM_API_KEY  = $ApiKey
    $env:LLM_MODEL    = $Model
    Write-Host "LLM 模式: DeepSeek ($Model)"
    if (-not $ApiKey) {
        Write-Warning 'ApiKey 为空，真实请求会失败。请在脚本顶部配置区填写 $ApiKey，或用 -Mode mock。'
    }
}

# 3. 启动
$python = Join-Path $ScriptDir '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Error "未找到 $python，请先在 backend 目录创建虚拟环境。"
    exit 1
}

Write-Host "启动 uvicorn 于 http://127.0.0.1:$Port（Ctrl+C 停止）..."
& $python -m uvicorn app.main:app --port $Port
