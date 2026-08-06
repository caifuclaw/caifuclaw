[CmdletBinding()]
param(
  [switch]$SkipFrontend,
  [switch]$SkipBackend,
  [switch]$WriteFrontendDist
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

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

function Invoke-Step {
  param(
    [string]$Name,
    [scriptblock]$Action
  )

  Write-Host ""
  Write-Host "==> $Name"
  & $Action
}

function Invoke-InDirectory {
  param(
    [string]$Path,
    [scriptblock]$Action
  )

  Push-Location $Path
  try {
    & $Action
  } finally {
    Pop-Location
  }
}

function Assert-NativeCommandSucceeded {
  param([string]$Name)

  if ($LASTEXITCODE -ne 0) {
    throw "$Name failed with exit code $LASTEXITCODE"
  }
}

function New-BuildTempDirectory {
  $tempBase = [System.IO.Path]::GetTempPath()
  $tempPath = Join-Path $tempBase "caifuclaw_ai_frontend_build_$PID"

  if (Test-Path -LiteralPath $tempPath) {
    $resolvedTemp = (Resolve-Path -LiteralPath $tempPath).Path
    $resolvedBase = [System.IO.Path]::GetFullPath($tempBase)
    if (-not $resolvedTemp.StartsWith($resolvedBase, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to remove unexpected temp directory: $resolvedTemp"
    }
    Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
  }

  New-Item -ItemType Directory -Force -Path $tempPath | Out-Null
  return $tempPath
}

function Remove-BuildTempDirectory {
  param([string]$Path)

  if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
    return
  }

  $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
  $resolvedBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
  if (-not $resolvedPath.StartsWith($resolvedBase, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove unexpected temp directory: $resolvedPath"
  }

  Remove-Item -LiteralPath $resolvedPath -Recurse -Force
}

function Invoke-FrontendBuilds {
  $npm = Get-CommandPath -Names @("npm.cmd", "npm")
  $tempRoot = $null
  $frontends = @(
    [pscustomobject]@{
      Name = "caifuclaw-ai-frontend"
      Cwd = Join-RootPath "caifuclaw_business_app\frontend"
      TempName = "caifuclaw-ai-frontend"
    }
  )

  if (-not $WriteFrontendDist) {
    $tempRoot = New-BuildTempDirectory
    Write-Host "Frontend build output: $tempRoot"
  }

  try {
    foreach ($frontend in $frontends) {
      if (-not (Test-Path -LiteralPath (Join-Path $frontend.Cwd "package.json") -PathType Leaf)) {
        throw "Missing package.json for $($frontend.Name): $($frontend.Cwd)"
      }

      $npmArgs = @("run", "build")
      if (-not $WriteFrontendDist) {
        $npmArgs += @("--", "--outDir", (Join-Path $tempRoot $frontend.TempName), "--emptyOutDir")
      }

      Invoke-Step "Build $($frontend.Name)" {
        Invoke-InDirectory -Path $frontend.Cwd -Action {
          & $npm @npmArgs
          Assert-NativeCommandSucceeded -Name "npm run build"
        }
      }
    }
  } finally {
    if ($tempRoot) {
      Remove-BuildTempDirectory -Path $tempRoot
    }
  }
}

function Invoke-BackendSyntaxCompile {
  $python = Get-CommandPath -Names @("python.exe", "python")
  $sourceDirs = @(
    "caifuclaw_business_app\app",
    "connector_runtime\app",
    "common"
  )

  $existingDirs = @()
  foreach ($sourceDir in $sourceDirs) {
    $fullPath = Join-RootPath $sourceDir
    if (Test-Path -LiteralPath $fullPath -PathType Container) {
      $existingDirs += $fullPath
    }
  }

  if ($existingDirs.Count -eq 0) {
    throw "No Python source directories found."
  }

  $checkScript = @'
import pathlib
import sys
import tokenize

skip_parts = {".venv", "venv", "node_modules", "__pycache__"}
checked = 0
failed = False

for root_arg in sys.argv[1:]:
    root = pathlib.Path(root_arg)
    for path in root.rglob("*.py"):
        if any(part in skip_parts for part in path.parts):
            continue

        checked += 1
        try:
            with tokenize.open(path) as source_file:
                compile(source_file.read(), str(path), "exec")
        except SyntaxError as exc:
            failed = True
            print(f"{path}:{exc.lineno}:{exc.offset}: SyntaxError: {exc.msg}", file=sys.stderr)
            if exc.text:
                print(exc.text.rstrip(), file=sys.stderr)
                if exc.offset:
                    print(" " * (exc.offset - 1) + "^", file=sys.stderr)
        except UnicodeDecodeError as exc:
            failed = True
            print(f"{path}: UnicodeDecodeError: {exc}", file=sys.stderr)

print(f"Python source files checked: {checked}")
sys.exit(1 if failed else 0)
'@

  Invoke-Step "Compile Python backend sources" {
    $tempScript = Join-Path ([System.IO.Path]::GetTempPath()) "caifuclaw_ai_compile_check_$PID.py"
    try {
      Set-Content -LiteralPath $tempScript -Value $checkScript -Encoding UTF8
      & $python $tempScript $existingDirs
      Assert-NativeCommandSucceeded -Name "Python backend compile check"
    } finally {
      Remove-Item -LiteralPath $tempScript -Force -ErrorAction SilentlyContinue
    }
  }
}

Write-Host "CaifuClaw AI build"
Write-Host "Root: $Root"
if ($WriteFrontendDist) {
  Write-Host "Frontend build output: project dist directories"
}

if (-not $SkipFrontend) {
  Invoke-FrontendBuilds
}

if (-not $SkipBackend) {
  Invoke-BackendSyntaxCompile
}

Write-Host ""
Write-Host "Build checks completed."
