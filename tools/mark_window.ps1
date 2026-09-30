<#
.SYNOPSIS
  Print the log lines around a "### MARK n" in every file under logs\, by host wall-clock time.

.EXAMPLE
  powershell -File tools\mark_window.ps1 -Mark 1 > mark1.txt
  (about 1000 lines per mark at full trackball motion; redirect to a file)
#>
param(
  [int]$Mark = 1,
  [double]$Before = 3,
  [double]$After = 1,
  [string]$LogDir = 'logs'
)
$ci = [cultureinfo]::InvariantCulture
function T([string]$line) { [datetime]::ParseExact($line.Substring(0, 12), 'HH:mm:ss.fff', $ci) }
Get-ChildItem (Join-Path $LogDir '*.log') | ForEach-Object {
  $f = $_
  $lines = Get-Content $f.FullName -Encoding utf8
  $m = $lines | Where-Object { $_ -match "^\S+ ### MARK $Mark(\s|$)" } | Select-Object -First 1
  if ($m) {
    $t0 = T $m
    "== $($f.Name)"
    $lines | Where-Object { $_ -match '^\d\d:\d\d:\d\d\.\d{3} ' } | Where-Object {
      $d = ((T $_) - $t0).TotalSeconds
      $d -ge -$Before -and $d -le $After
    }
  }
}
