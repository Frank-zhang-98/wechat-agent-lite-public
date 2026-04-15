param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [ValidateSet("minor", "major")]
  [string]$Bump = "minor"
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$projectName = Split-Path $ProjectRoot -Leaf
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$distDir = Join-Path $ProjectRoot "dist"
$zipPath = Join-Path $distDir "${projectName}-${timestamp}.zip"
$hashPath = "${zipPath}.sha256"
$versionPath = Join-Path $ProjectRoot "VERSION"

$excludeDirNames = @(".git", ".venv", "data", "output", "tmp", "dist", "__pycache__")
$excludeFilePatterns = @("*.pyc", "*.pyo", "*.db", "*.sqlite3", "*.log", ".env", "tmp_*.json")

function Get-BaseVersion {
  param(
    [string]$RawVersion
  )

  $trimmed = ($RawVersion | ForEach-Object { $_.Trim() })
  if (-not $trimmed) {
    return "v0.0"
  }
  if ($trimmed -match '^(v\d+\.\d+(?:\.\d+)?)(?:\+.+)?$') {
    return $Matches[1]
  }
  return $trimmed
}

function Get-NextSemanticVersion {
  param(
    [string]$Version,
    [string]$BumpType
  )

  if ($Version -notmatch '^v(\d+)\.(\d+)(?:\.(\d+))?$') {
    throw "VERSION must use semantic format like v1.1 or v1.2.3"
  }

  $major = [int]$Matches[1]
  $minor = [int]$Matches[2]
  $patch = if ($Matches[3]) { [int]$Matches[3] } else { $null }

  if ($BumpType -eq "major") {
    return "v$($major + 1).0"
  }

  if ($null -ne $patch) {
    return "v$major.$minor.$($patch + 1)"
  }

  return "v$major.$($minor + 1)"
}

function Write-Utf8NoBom {
  param(
    [string]$Path,
    [string]$Value
  )

  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Value, $utf8NoBom)
}

$currentVersion = ""
if (Test-Path $versionPath) {
  $currentVersion = Get-Content $versionPath -Encoding UTF8 -Raw
}
$baseVersion = Get-BaseVersion -RawVersion $currentVersion
$newVersion = Get-NextSemanticVersion -Version $baseVersion -BumpType $Bump
Write-Utf8NoBom -Path $versionPath -Value "$newVersion`n"

New-Item -ItemType Directory -Path $distDir -Force | Out-Null

if (Test-Path $zipPath) {
  Remove-Item -Path $zipPath -Force
}
if (Test-Path $hashPath) {
  Remove-Item -Path $hashPath -Force
}

$rootWithSlash = "$ProjectRoot\"
$files = Get-ChildItem -Path $ProjectRoot -Recurse -File | Where-Object {
  $fullPath = $_.FullName
  $relativePath = $fullPath.Substring($rootWithSlash.Length)
  $segments = $relativePath -split '[\\/]'
  $name = $_.Name

  if ($segments | Where-Object { $excludeDirNames -contains $_ }) {
    return $false
  }
  foreach ($pattern in $excludeFilePatterns) {
    if ($name -like $pattern) {
      return $false
    }
  }
  return $true
}

$zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
  foreach ($file in $files) {
    $relativePath = $file.FullName.Substring($rootWithSlash.Length)
    $entryName = $relativePath -replace '\\','/'
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
      $zip,
      $file.FullName,
      $entryName,
      [System.IO.Compression.CompressionLevel]::Optimal
    ) | Out-Null
  }
}
finally {
  $zip.Dispose()
}

$hash = (Get-FileHash -Algorithm SHA256 -Path $zipPath).Hash.ToLowerInvariant()
Set-Content -Path $hashPath -Value "$hash  $(Split-Path $zipPath -Leaf)" -Encoding ascii

Write-Output "version: $newVersion"
Write-Output "package: $zipPath"
Write-Output "sha256:  $hash"
