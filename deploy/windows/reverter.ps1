<#
.SYNOPSIS
  Volta para a versão que estava antes da última implantação (registrada por implantar.ps1).

.EXAMPLE
  .\deploy\windows\reverter.ps1
  .\deploy\windows\reverter.ps1 -Para v0.6.0

NÃO reverte o esquema do banco. Por isso toda migração deve ser compatível com a versão anterior do código
(expandir -> migrar -> contrair); se uma migração destrutiva foi aplicada, restaure o backup do banco (ver 09_runbook.md).
#>
param(
  [string]$Para = "",
  [string]$Python = "python",
  [string]$Raiz = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$PrefixoTarefas = "cm-",
  [switch]$SemTarefas
)
$ErrorActionPreference = "Stop"
Set-Location $Raiz

if (-not $Para) {
  $arquivo = Join-Path $Raiz "deploy\.versao_anterior"
  if (-not (Test-Path $arquivo)) { throw "não há versão anterior registrada; informe -Para <tag>" }
  $Para = (Get-Content $arquivo -Raw).Trim()
}
$tarefas = @()
if (-not $SemTarefas) {
  $tarefas = @(Get-ScheduledTask -TaskName "$PrefixoTarefas*" -ErrorAction SilentlyContinue)
  foreach ($t in $tarefas) { Stop-ScheduledTask -TaskName $t.TaskName -ErrorAction SilentlyContinue; Disable-ScheduledTask -TaskName $t.TaskName | Out-Null }
}
$atual = (git describe --tags --always).Trim()
git checkout --quiet $Para
if ($LASTEXITCODE -ne 0) { throw "git checkout $Para falhou" }
& $Python -m pip install --quiet -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw "pip install falhou" }
& $Python manage.py check
if ($LASTEXITCODE -ne 0) { throw "manage.py check falhou na versão $Para" }
Set-Content -Path (Join-Path $Raiz "deploy\.versao_atual") -Value $Para -Encoding ascii
foreach ($t in $tarefas) { Enable-ScheduledTask -TaskName $t.TaskName | Out-Null }
Write-Host "Revertido de $atual para $Para. O esquema do banco NÃO foi alterado."
