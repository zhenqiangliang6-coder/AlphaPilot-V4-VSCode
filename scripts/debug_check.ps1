$scriptRoot = 'd:\Copilot_Alphapilot\Copilot_Alphapilot'
$venvPath = Join-Path $scriptRoot '.venv_worker'
$activate = Join-Path $venvPath 'Scripts/Activate.ps1'
Write-Host "Activate path: $activate"
Write-Host "Test-Path: " (Test-Path $activate)
Get-ChildItem -Path (Join-Path $venvPath 'Scripts') | ForEach-Object { Write-Host $_.Name }
