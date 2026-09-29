<#
.SYNOPSIS
  Implanta uma versão (tag do Git) na VM Windows e guarda a anterior para rollback.

.EXAMPLE
  .\deploy\windows\implantar.ps1 -Tag v0.7.0
  .\deploy\windows\implantar.ps1 -Tag v0.7.0 -Python C:\cm\.venv\Scripts\python.exe

Passos: para as tarefas cm-* do Agendador -> git checkout <tag> -> pip install -r requirements.lock -> manage.py check
-> manage.py migrate -> reinicia as tarefas. Se um passo falhar depois do checkout, REVERTE sozinho para a versão anterior
(o esquema do banco NÃO é revertido: as migrações precisam ser compatíveis com a versão anterior — ver 09_runbook.md).
#>
param(
  [Parameter(Mandatory = $true)][string]$Tag,
  [string]$Python = "python",
  [string]$Raiz = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$PrefixoTarefas = "cm-",
  [switch]$SemTarefas
)
$ErrorActionPreference = "Stop"
Set-Location $Raiz

function Parar-Tarefas {
  if ($SemTarefas) { return }
  $tarefas = @(Get-ScheduledTask -TaskName "$PrefixoTarefas*" -ErrorAction SilentlyContinue)
  foreach ($t in $tarefas) { Stop-ScheduledTask -TaskName $t.TaskName -ErrorAction SilentlyContinue; Disable-ScheduledTask -TaskName $t.TaskName | Out-Null }
  return $tarefas
}
function Iniciar-Tarefas($tarefas) {
  foreach ($t in $tarefas) { Enable-ScheduledTask -TaskName $t.TaskName | Out-Null }
}

$anterior = (git describe --tags --always).Trim()
if (git status --porcelain) { throw "há alterações locais não commitadas em $Raiz; recuse a implantação (git status)" }
git fetch --tags --quiet
git rev-parse --verify --quiet "refs/tags/$Tag" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "a tag $Tag não existe" }

$tarefas = Parar-Tarefas
try {
  Set-Content -Path (Join-Path $Raiz "deploy\.versao_anterior") -Value $anterior -Encoding ascii
  git checkout --quiet $Tag
  if ($LASTEXITCODE -ne 0) { throw "git checkout $Tag falhou" }
  & $Python -m pip install --quiet -r requirements.lock
  if ($LASTEXITCODE -ne 0) { throw "pip install falhou" }
  & $Python manage.py check
  if ($LASTEXITCODE -ne 0) { throw "manage.py check falhou" }
  & $Python manage.py migrate --noinput
  if ($LASTEXITCODE -ne 0) { throw "manage.py migrate falhou" }
  Set-Content -Path (Join-Path $Raiz "deploy\.versao_atual") -Value $Tag -Encoding ascii
  Write-Host "Implantado $Tag (anterior: $anterior)"
}
catch {
  Write-Warning "Falha ao implantar $Tag ($_). Revertendo para $anterior."
  git checkout --quiet $anterior
  & $Python -m pip install --quiet -r requirements.lock
  Iniciar-Tarefas $tarefas
  throw
}
Iniciar-Tarefas $tarefas
