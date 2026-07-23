# Generates beginner forensics practice files in .\generated\ (Windows-native, no extra tools).
# The Bash version (make-practice.sh) is preferred if you're in WSL/Kali, but this works anywhere.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$out  = Join-Path $here 'generated'
New-Item -ItemType Directory -Force -Path $out | Out-Null

function Rot13([string]$s) {
  -join ($s.ToCharArray() | ForEach-Object {
    $c = [int][char]$_
    if     ($c -ge 65 -and $c -le 90) { [char](((($c-65)+13)%26)+65) }
    elseif ($c -ge 97 -and $c -le 122){ [char](((($c-97)+13)%26)+97) }
    else   { [char]$c }
  })
}

# 1) Wrong extension: a ZIP named .png
$tmp = New-Item -ItemType Directory -Force -Path (Join-Path $env:TEMP 'fx_prac')
Set-Content -Encoding utf8 -Path (Join-Path $tmp '_hint.txt') -Value 'flag{extensions_are_liars}'
$zip = Join-Path $out 'secret.png'   # a zip, deliberately named .png
$zipTmp = Join-Path $tmp '_secret.zip'
if (Test-Path $zip) { Remove-Item $zip -Force }
if (Test-Path $zipTmp) { Remove-Item $zipTmp -Force }
Compress-Archive -Path (Join-Path $tmp '_hint.txt') -DestinationPath $zipTmp -Force
Move-Item $zipTmp $zip -Force        # rename .zip -> .png so the extension lies

# 2) Appended data: minimal PNG bytes + a zip appended
$png = [byte[]](0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A,0x00,0x00,0x00,0x0D,0x49,0x48,0x44,0x52,
  0x00,0x00,0x00,0x01,0x00,0x00,0x00,0x01,0x08,0x06,0x00,0x00,0x00,0x1F,0x15,0xC4,0x89,
  0x00,0x00,0x00,0x0A,0x49,0x44,0x41,0x54,0x78,0x9C,0x63,0x00,0x01,0x00,0x00,0x05,0x00,0x01,
  0x0D,0x0A,0x2D,0xB4,0x00,0x00,0x00,0x00,0x49,0x45,0x4E,0x44,0xAE,0x42,0x60,0x82)
Set-Content -Encoding utf8 -Path (Join-Path $tmp '_appended.txt') -Value 'flag{data_hidden_after_the_image}'
$apzip = Join-Path $tmp '_appended.zip'
if (Test-Path $apzip) { Remove-Item $apzip -Force }
Compress-Archive -Path (Join-Path $tmp '_appended.txt') -DestinationPath $apzip -Force
$catbin = Join-Path $out 'cat_photo.bin'
[System.IO.File]::WriteAllBytes($catbin, $png + [System.IO.File]::ReadAllBytes($apzip))

# 3) ROT13
$rot = "You intercepted this note. It's scrambled:`n" + (Rot13 'flag{rot13_is_not_encryption}')
Set-Content -Encoding utf8 -Path (Join-Path $out 'notes.txt') -Value $rot

# 4) Base64
$b64 = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes('flag{base64_is_not_encryption_either}'))
Set-Content -Encoding ascii -Path (Join-Path $out 'data.b64') -Value $b64

Remove-Item $tmp -Recurse -Force
Write-Output "Done. Practice files are in: $out"
Write-Output "Try to solve them WITHOUT reading solutions.ai.md. (Metadata challenge is bash-only.)"
