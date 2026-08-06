[CmdletBinding()]
param(
  [switch]$Restart,
  [int]$HealthTimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pathSeparator = [System.IO.Path]::PathSeparator
$pythonPathEntries = @($env:PYTHONPATH -split [regex]::Escape([string]$pathSeparator) | Where-Object { $_ })
if (-not ($pythonPathEntries | Where-Object { $_ -ieq $Root })) {
  $env:PYTHONPATH = (@($Root) + $pythonPathEntries) -join $pathSeparator
}

function Join-RootPath {
  param([string]$ChildPath)
  return Join-Path $Root $ChildPath
}

function Get-CommandPath {
  param([string[]]$Names)
  foreach ($name in $Names) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) {
      return $cmd.Source
    }
  }
  throw "Command not found: $($Names -join ', ')"
}

function Assert-NativeCommandSucceeded {
  param([string]$Name)

  if ($LASTEXITCODE -ne 0) {
    throw "$Name failed with exit code $LASTEXITCODE"
  }
}

function Get-LatestWriteTimeUtc {
  param([string[]]$Paths)

  $latest = [datetime]::MinValue
  foreach ($path in $Paths) {
    if (-not (Test-Path -LiteralPath $path)) {
      continue
    }

    $item = Get-Item -LiteralPath $path
    if ($item.PSIsContainer) {
      $children = Get-ChildItem -LiteralPath $item.FullName -Recurse -File
      foreach ($child in $children) {
        if ($child.LastWriteTimeUtc -gt $latest) {
          $latest = $child.LastWriteTimeUtc
        }
      }
      continue
    }

    if ($item.LastWriteTimeUtc -gt $latest) {
      $latest = $item.LastWriteTimeUtc
    }
  }

  return $latest
}

function Get-MissingBusinessFrontendAssets {
  param(
    [string]$FrontendRoot,
    [string]$DistIndex
  )

  if (-not (Test-Path -LiteralPath $DistIndex -PathType Leaf)) {
    return @("/index.html")
  }

  $distRoot = Join-Path $FrontendRoot "dist"
  $content = Get-Content -LiteralPath $DistIndex -Raw
  $missing = @()

  foreach ($match in [regex]::Matches($content, '["''](/assets/[^"'']+)["'']')) {
    $asset = $match.Groups[1].Value.Split("?")[0]
    $relativeAsset = $asset.TrimStart("/") -replace "/", [System.IO.Path]::DirectorySeparatorChar
    $assetPath = Join-Path $distRoot $relativeAsset
    if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) {
      $missing += $match.Groups[1].Value
    }
  }

  return $missing | Sort-Object -Unique
}

function Update-BusinessFrontendDistIfStale {
  param([switch]$Force)

  $frontendRoot = Join-RootPath "caifuclaw_business_app\frontend"
  $distIndex = Join-Path $frontendRoot "dist\index.html"
  $sourcePaths = @(
    (Join-Path $frontendRoot "src"),
    (Join-Path $frontendRoot "public"),
    (Join-Path $frontendRoot "index.html"),
    (Join-Path $frontendRoot "package.json"),
    (Join-Path $frontendRoot "package-lock.json"),
    (Join-Path $frontendRoot "vite.config.ts"),
    (Join-Path $frontendRoot "tsconfig.json"),
    (Join-Path $frontendRoot "tsconfig.node.json")
  )

  if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "package.json") -PathType Leaf)) {
    throw "Missing package.json for caifuclaw-ai-frontend: $frontendRoot"
  }

  $latestSource = Get-LatestWriteTimeUtc -Paths $sourcePaths
  $needsBuild = $Force -or -not (Test-Path -LiteralPath $distIndex -PathType Leaf)
  $missingAssets = @(Get-MissingBusinessFrontendAssets -FrontendRoot $frontendRoot -DistIndex $distIndex)
  if (-not $needsBuild) {
    $distWriteTime = (Get-Item -LiteralPath $distIndex).LastWriteTimeUtc
    $needsBuild = $latestSource -gt $distWriteTime
  }
  if (-not $needsBuild -and $missingAssets.Count -gt 0) {
    $needsBuild = $true
  }

  if (-not $needsBuild) {
    Write-Host "Business frontend dist is current for port 9999."
    return
  }

  if ($Force) {
    Write-Host "Business frontend dist rebuild forced for port 9999."
  } elseif ($missingAssets.Count -gt 0) {
    Write-Host "Business frontend dist is missing referenced assets. Rebuilding static files for port 9999."
    Write-Host "Missing assets: $($missingAssets -join ' ')"
  } else {
    Write-Host "Business frontend dist is stale. Rebuilding static files for port 9999."
  }
  $npm = Get-CommandPath -Names @("npm.cmd", "npm")
  Push-Location $frontendRoot
  try {
    & $npm run build -- --outDir dist --emptyOutDir
    Assert-NativeCommandSucceeded -Name "Build caifuclaw-ai-frontend dist"
  } finally {
    Pop-Location
  }
}

function Get-ListenerRows {
  param([int]$Port)

  $rows = @()
  $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  foreach ($listener in $listeners) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    $rows += [pscustomobject]@{
      Port = $Port
      ProcessId = $listener.OwningProcess
      Name = $process.Name
      CommandLine = $process.CommandLine
    }
  }
  return $rows
}

function Test-CommandMatch {
  param(
    [string]$CommandLine,
    [string[]]$Tokens
  )

  if ([string]::IsNullOrWhiteSpace($CommandLine)) {
    return $false
  }

  foreach ($token in $Tokens) {
    if ($CommandLine -notlike "*$token*") {
      return $false
    }
  }
  return $true
}

function Test-HttpEndpoint {
  param([string]$Url)

  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
    return [pscustomobject]@{
      Ok = ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
      Status = $response.StatusCode
      Error = ""
    }
  } catch {
    return [pscustomobject]@{
      Ok = $false
      Status = "ERR"
      Error = $_.Exception.Message
    }
  }
}

function Stop-ServicePort {
  param([pscustomobject]$Service)

  $listeners = Get-ListenerRows -Port $Service.Port
  foreach ($listener in $listeners) {
    if (Test-CommandMatch -CommandLine $listener.CommandLine -Tokens $Service.MatchTokens) {
      Write-Host "Stopping $($Service.Name) on port $($Service.Port), PID $($listener.ProcessId)"
      Stop-Process -Id $listener.ProcessId -Force -ErrorAction SilentlyContinue
    } else {
      Write-Warning "Port $($Service.Port) is used by an unknown process. PID=$($listener.ProcessId) CMD=$($listener.CommandLine)"
    }
  }
}

function Start-ServiceProcess {
  param([pscustomobject]$Service)

  if (-not (Test-Path -LiteralPath $Service.Cwd -PathType Container)) {
    throw "Missing service directory: $($Service.Cwd)"
  }

  if ($Service.RequiredFile -and -not (Test-Path -LiteralPath $Service.RequiredFile -PathType Leaf)) {
    throw "Missing required file for $($Service.Name): $($Service.RequiredFile)"
  }

  $logDir = Split-Path -Parent $Service.StdOut
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null

  $process = Start-Process `
    -FilePath $Service.Executable `
    -ArgumentList $Service.Arguments `
    -WorkingDirectory $Service.Cwd `
    -RedirectStandardOutput $Service.StdOut `
    -RedirectStandardError $Service.StdErr `
    -WindowStyle Hidden `
    -PassThru

  Write-Host "Started $($Service.Name), launcher PID $($process.Id), port $($Service.Port)"
}

function Wait-ServiceHealthy {
  param([pscustomobject]$Service)

  $deadline = (Get-Date).AddSeconds($HealthTimeoutSeconds)
  $last = $null

  while ((Get-Date) -lt $deadline) {
    $last = Test-HttpEndpoint -Url $Service.HealthUrl
    if ($last.Ok) {
      Write-Host "OK  $($Service.Name) $($Service.HealthUrl)"
      return $true
    }
    Start-Sleep -Seconds 2
  }

  Write-Warning "FAIL $($Service.Name) $($Service.HealthUrl) status=$($last.Status) $($last.Error)"
  Write-Warning "Logs: $($Service.StdOut) / $($Service.StdErr)"
  return $false
}

$python = Get-CommandPath -Names @("python.exe", "python")

$legacyServices = @(
  [pscustomobject]@{
    Name = "legacy-caifuclaw-business-frontend"
    Port = 5173
    MatchTokens = @("vite", "--port 5173")
  },
  [pscustomobject]@{
    Name = "legacy-caifuclaw-business-api"
    Port = 8000
    MatchTokens = @("uvicorn", "app.main:app", "--port 8000")
  }
)

$services = @(
  [pscustomobject]@{
    Name = "connector-runtime-api"
    Port = 8100
    Cwd = Join-RootPath "connector_runtime"
    Executable = $python
    Arguments = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8100")
    RequiredFile = Join-RootPath "connector_runtime\app\main.py"
    HealthUrl = "http://127.0.0.1:8100/health"
    PublicUrl = "http://127.0.0.1:8100"
    StdOut = Join-RootPath "connector_runtime\logs\connector_runtime_api.current.out.log"
    StdErr = Join-RootPath "connector_runtime\logs\connector_runtime_api.current.err.log"
    MatchTokens = @("uvicorn", "app.main:app", "--port 8100")
  },
  [pscustomobject]@{
    Name = "caifuclaw-business-api"
    Port = 9999
    Cwd = Join-RootPath "caifuclaw_business_app"
    Executable = $python
    Arguments = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9999")
    RequiredFile = Join-RootPath "caifuclaw_business_app\app\main.py"
    HealthUrl = "http://127.0.0.1:9999/health"
    PublicUrl = "http://127.0.0.1:9999"
    StdOut = Join-RootPath "caifuclaw_business_app\logs\caifuclaw_business_api.current.out.log"
    StdErr = Join-RootPath "caifuclaw_business_app\logs\caifuclaw_business_api.current.err.log"
    MatchTokens = @("uvicorn", "app.main:app", "--port 9999")
  }
)

Write-Host "CaifuClaw AI startup"
Write-Host "Root: $Root"
Write-Host "Business frontend is served by caifuclaw-business-api on port 9999."

foreach ($legacyService in $legacyServices) {
  Stop-ServicePort -Service $legacyService
}

if ($Restart) {
  Write-Host "Restart requested. Stopping owned processes first."
  foreach ($service in $services) {
    Stop-ServicePort -Service $service
  }
  Start-Sleep -Seconds 2
}

foreach ($service in $services) {
  if ($service.Name -eq "caifuclaw-business-api") {
    Update-BusinessFrontendDistIfStale -Force:$Restart
  }

  $health = Test-HttpEndpoint -Url $service.HealthUrl
  if ($health.Ok) {
    Write-Host "Already running: $($service.Name) $($service.HealthUrl)"
    continue
  }

  $listeners = Get-ListenerRows -Port $service.Port
  if ($listeners.Count -gt 0) {
    foreach ($listener in $listeners) {
      Write-Warning "Port $($service.Port) is busy but health check failed. PID=$($listener.ProcessId) CMD=$($listener.CommandLine)"
    }
    Write-Warning "Skip starting $($service.Name). Use -Restart if this is a CaifuClaw AI process."
    continue
  }

  Start-ServiceProcess -Service $service
}

Write-Host ""
Write-Host "Health checks"
$allHealthy = $true
foreach ($service in $services) {
  if (-not (Wait-ServiceHealthy -Service $service)) {
    $allHealthy = $false
  }
}

Write-Host ""
Write-Host "URLs"
Write-Host "Business app:       http://127.0.0.1:9999"
Write-Host "Business API:       http://127.0.0.1:9999/health"
Write-Host "Connector runtime:  http://127.0.0.1:8100/health"

if (-not $allHealthy) {
  exit 1
}
