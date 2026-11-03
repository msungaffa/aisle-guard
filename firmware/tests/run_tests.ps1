# Host unit tests for firmware/aisle_cam/{logic,proto}.cpp (g++).
# Run from repo root:  powershell -File firmware/tests/run_tests.ps1
# Comments are ASCII on purpose: Windows PowerShell 5.1 misreads BOM-less UTF-8 scripts.
$ErrorActionPreference = "Stop"
$root = (Resolve-Path "$PSScriptRoot/../..").Path
$out = Join-Path $root "firmware/tests/build"
New-Item -ItemType Directory -Force $out | Out-Null

# PCs whose user folder name is non-ASCII (e.g. Korean) break MinGW: the assembler cannot
# write to %TEMP% and ld cannot open crt2.o / libs under the install path. Work around both:
# temp files go to the ASCII build dir, and for a g++ installed under a non-ASCII path the
# startup files and libs are passed explicitly through a temporary subst drive.
$env:TMPDIR = $out; $env:TMP = $out; $env:TEMP = $out
$gxx = (Get-Command g++ -ErrorAction Stop).Source
$drive = $null
$extra = @()
if ($gxx -match '[^\x00-\x7F]') {
    $prefix = Split-Path (Split-Path $gxx -Parent) -Parent   # ...\mingw64
    $used = (Get-PSDrive -PSProvider FileSystem).Name
    $drive = ('G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','X','Y','Z' | Where-Object { $used -notcontains $_ } | Select-Object -First 1) + ':'
    subst $drive $prefix
    $triplet = (Get-ChildItem "$drive\lib\gcc" -Directory | Select-Object -First 1).Name
    $ver = (Get-ChildItem "$drive\lib\gcc\$triplet" -Directory | Select-Object -First 1).Name
    $extra = @("-B$drive/$triplet/lib/", "-B$drive/lib/gcc/$triplet/$ver/",
               "-L$drive/$triplet/lib", "-L$drive/lib/gcc/$triplet/$ver", "-L$drive/lib")
}
try {
    $src = "$root/firmware/aisle_cam"
    & $gxx @extra -std=c++17 -Wall -Wextra -I $src "$root/firmware/tests/test_logic.cpp" "$src/logic.cpp" -o "$out/test_logic.exe"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $gxx @extra -std=c++17 -Wall -Wextra -I $src "$root/firmware/tests/test_proto.cpp" "$src/proto.cpp" -o "$out/test_proto.exe"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    if ($drive) { subst $drive /D }
}
$fail = 0
foreach ($t in "test_logic", "test_proto") {
    & "$out/$t.exe"
    if ($LASTEXITCODE -ne 0) { $fail = 1 }
}
exit $fail
