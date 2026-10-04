# What somebody who downloads the zip actually gets.
#
#     powershell -ExecutionPolicy Bypass -File check_download.ps1 `
#         -Zip C:\path\to\awrbc-windows.zip
#
# Self-contained on purpose: this is meant to run on a machine that has none
# of this repository on it, and ideally no Python either. That is the whole
# point of running it - every "it works" so far has come from the machine the
# bundle was built on, which is the one machine that proves the least.
#
# It extracts, launches, and says whether a real window opened. Pass -Marked
# to stamp the files as downloaded-from-the-internet first, which is what
# Windows does to anything extracted from a downloaded zip, and what broke
# the first release.
param(
  [Parameter(Mandatory = $true)][string]$Zip,
  [string]$To = "$env:TEMP\awrbc-download-test",
  [switch]$Marked,
  [int]$WaitSeconds = 15
)

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class AwrbcDl {
  public delegate bool Proc(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern bool EnumWindows(Proc f, IntPtr p);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, Proc f, IntPtr p);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
"@

if (-not (Test-Path $Zip)) { Write-Output "no such zip: $Zip"; exit 2 }

Write-Output "zip      : $Zip  ($([math]::Round((Get-Item $Zip).Length / 1MB, 1)) MB)"
Write-Output "machine  : $env:COMPUTERNAME"
# Finding python.exe does not mean Python is installed. Windows leaves a
# zero-byte Store alias stub on PATH that is not an interpreter, and after an
# uninstall it is all that remains - so a check that only looks for the file
# reports "installed" on a machine that has none, which is the exact thing
# this run exists to establish. Judged by size and location rather than by
# running it, because running the stub opens the Microsoft Store.
$py = Get-Command python -ErrorAction SilentlyContinue
$stub = $py -and (($py.Source -like '*\WindowsApps\*') -or
                  ((Get-Item $py.Source -ErrorAction SilentlyContinue).Length -eq 0))
Write-Output ("python   : " + $(
  if ($py -and -not $stub) { "installed at $($py.Source) - this machine proves less" }
  elseif ($stub) { 'only the Store alias stub on PATH, not an interpreter - good' }
  else { 'not installed - good, that is the test' }))

if (Test-Path $To) { Remove-Item -Recurse -Force $To }
Expand-Archive -Path $Zip -DestinationPath $To -Force
$exe = Join-Path $To 'awrbc\awrbc.exe'
if (-not (Test-Path $exe)) { Write-Output "no awrbc.exe inside the zip"; exit 2 }

if ($Marked) {
  # Explorer stamps this on every file it extracts from a downloaded zip.
  # Expand-Archive does not, so it is applied by hand to get the real thing.
  $n = 0
  Get-ChildItem -Recurse -File $To | ForEach-Object {
    Set-Content -Path $_.FullName -Stream Zone.Identifier `
      -Value "[ZoneTransfer]`r`nZoneId=3`r`n"
    $n++
  }
  Write-Output "marked   : $n files as downloaded-from-the-internet"
} else {
  Write-Output 'marked   : no - testing the unblocked case'
}

$proc = Start-Process -FilePath $exe -PassThru -ErrorAction SilentlyContinue
if (-not $proc) {
  Write-Output 'verdict  : NOT STARTED - Windows would not launch it at all.'
  Write-Output '           Unsigned and marked as downloaded means SmartScreen'
  Write-Output '           asks first. A downloader sees this too.'
  exit 3
}
Start-Sleep -Seconds $WaitSeconds

$windows = New-Object System.Collections.ArrayList
$onTop = [AwrbcDl+Proc]{
  param($h, $l)
  $owner = 0
  [void][AwrbcDl]::GetWindowThreadProcessId($h, [ref]$owner)
  if ($owner -eq $proc.Id -and [AwrbcDl]::IsWindowVisible($h)) {
    $c = New-Object System.Text.StringBuilder 256
    [void][AwrbcDl]::GetClassName($h, $c, 256)
    [void]$windows.Add(@{ Handle = $h; Class = $c.ToString() })
  }
  return $true
}
[void][AwrbcDl]::EnumWindows($onTop, [IntPtr]::Zero)
foreach ($w in $windows) { Write-Output "window   : $($w.Class)" }

$dialogs = @($windows | Where-Object { $_.Class -eq '#32770' })
if ($dialogs.Count -gt 0) {
  Write-Output 'verdict  : FAILED - it is showing an error dialog, which says:'
  Write-Output ''
  # Collected rather than written from inside the callback: PowerShell drops
  # pipeline output from a delegate that native code invokes, so writing it
  # there prints nothing on the one run where the message is the point.
  $said = New-Object System.Collections.ArrayList
  foreach ($d in $dialogs) {
    $kid = [AwrbcDl+Proc]{
      param($h, $l)
      $t = New-Object System.Text.StringBuilder 8192
      [void][AwrbcDl]::GetWindowTextW($h, $t, 8192)
      if ($t.Length -gt 20) { [void]$said.Add($t.ToString()) }
      return $true
    }
    [void][AwrbcDl]::EnumChildWindows($d.Handle, $kid, [IntPtr]::Zero)
  }
  foreach ($line in $said) { Write-Output $line }
  if ($said.Count -eq 0) { Write-Output '(the dialog had no readable text)' }
  $code = 1
} elseif ($windows.Count -gt 0) {
  Write-Output 'verdict  : WINDOW OPENED'
  $code = 0
} elseif ($proc.HasExited) {
  Write-Output "verdict  : FAILED - exited with $($proc.ExitCode) and no window"
  $code = 1
} else {
  Write-Output 'verdict  : still running with no window - try -WaitSeconds 30'
  $code = 1
}

if (-not $proc.HasExited) {
  Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}
Write-Output ''
Write-Output "extracted to $To - delete it when you are done."
exit $code
