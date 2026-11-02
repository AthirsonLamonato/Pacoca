# Fixed publisher code. Remote manifests contain data, never executable commands.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'BelowNormal'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$key = '__PUBLIC_KEY_JSON__' | ConvertFrom-Json
$job = Get-Content -LiteralPath $env:PACOCA_UPDATE_JOB -Raw -Encoding UTF8 | ConvertFrom-Json
$root = [IO.Path]::GetFullPath($job.install_root).TrimEnd('\')
$dataRoot = [IO.Path]::GetFullPath($job.data_root).TrimEnd('\')
$transaction = [IO.Path]::GetFullPath($job.transaction).TrimEnd('\')
if ($root -ne '__TRUSTED_ROOT__' -or $dataRoot -ne '__TRUSTED_DATA__') { throw 'Unexpected installation target' }
if (-not $transaction.StartsWith($dataRoot + '\Updates\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid transaction directory' }
foreach ($source in @($job.archive,$job.manifest)) {
    if (-not [IO.Path]::GetFullPath($source).StartsWith($dataRoot+'\Updates\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected update source' }
}
$receipt = Join-Path $dataRoot 'Updates\last-result.json'
$backup = Join-Path $transaction 'backup'
$stage = Join-Path $transaction 'stage'
$changed = New-Object 'System.Collections.Generic.List[object]'
$archive = $null
$installed = $false
$candidate = $null
$instanceLock = $null
function WaitForGames {
    $names=@($job.game_names | ForEach-Object { [IO.Path]::GetFileNameWithoutExtension($_) })
    while (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $names -contains $_.ProcessName }).Count -gt 0) { Start-Sleep -Seconds 5 }
}
function OwnedPath([string] $base, [string] $relative) {
    if ($relative -match '[:\\]' -or $relative.StartsWith('/') -or -not $relative) { throw 'Unsafe relative path' }
    foreach ($part in $relative.Split('/')) {
        if ($part -eq '' -or $part -eq '.' -or $part -eq '..' -or $part.EndsWith(' ') -or $part.EndsWith('.') -or $part -match '(?i)^(con|prn|aux|nul|com\d|lpt\d)(\.|$)') { throw 'Unsafe path component' }
    }
    if ($relative -notin @('Pacoca.exe','USAR-PACOCA.md','ALEXA.md') -and -not $relative.StartsWith('_internal/')) { throw 'Update outside application files' }
    $target = [IO.Path]::GetFullPath([IO.Path]::Combine($base,$relative.Replace('/','\')))
    if (-not $target.StartsWith($base.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Path escapes destination' }
    $current=$base
    foreach ($part in $relative.Split('/')) {
        if ([IO.Directory]::Exists($current) -and (([IO.File]::GetAttributes($current) -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw 'Update path contains a junction or symbolic link' }
        $current=[IO.Path]::Combine($current,$part)
    }
    if (([IO.File]::Exists($current) -or [IO.Directory]::Exists($current)) -and (([IO.File]::GetAttributes($current) -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw 'Update target is a symbolic link' }
    return $target
}
function WriteResult([string] $status, [string] $message) {
    @{status=$status; version=$job.version; message=$message; transaction=$transaction} | ConvertTo-Json | Set-Content -LiteralPath $receipt -Encoding UTF8
}
function CopyRetry([string] $source,[string] $target) {
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
    for ($attempt=0;$attempt -lt 20;$attempt++) {
        try { [IO.File]::Copy($source,$target,$true); return } catch { if ($attempt -eq 19) { throw }; Start-Sleep -Milliseconds 500 }
    }
}
function FileDigest([string] $path) {
    $algorithm=[Security.Cryptography.SHA256]::Create()
    $stream=[IO.File]::OpenRead($path)
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
try {
    $envelope = Get-Content -LiteralPath $job.manifest -Raw -Encoding UTF8 | ConvertFrom-Json
    $bytes = [Convert]::FromBase64String($envelope.signed)
    $signature = [Convert]::FromBase64String($envelope.signature)
    $rsa = New-Object Security.Cryptography.RSACryptoServiceProvider
    $parameters = New-Object Security.Cryptography.RSAParameters
    $parameters.Modulus = [Convert]::FromBase64String($key.modulus)
    $parameters.Exponent = [Convert]::FromBase64String($key.exponent)
    $rsa.ImportParameters($parameters)
    if (-not $rsa.VerifyData($bytes,'SHA256',$signature)) { throw 'Invalid publisher signature' }
    $payload = [Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json
    if ($payload.schema -ne 1 -or $payload.app_id -ne 'pacoca-desktop' -or $payload.database_schema -ne 1 -or $payload.version -ne $job.version) { throw 'Incompatible release' }
    $packages = @($payload.packages | Where-Object { $_.sha256 -eq $job.package_hash })
    if ($packages.Count -ne 1) { throw 'Package is not signed by this manifest' }
    $package = $packages[0]
    $identityFile=Join-Path $root '_internal\pacoca\runtime-id.txt'
    $identity=if ([IO.File]::Exists($identityFile)) { (Get-Content -LiteralPath $identityFile -Raw -Encoding UTF8).Trim() } else { '' }
    if ($package.from_runtime -ne '*' -and $package.from_runtime -ne $identity) { throw 'Incompatible installed runtime' }
    if ((FileDigest $job.archive) -ne $package.sha256) { throw 'Package checksum mismatch' }
    if ((Get-Item -LiteralPath $job.archive).Length -ne $package.size) { throw 'Package size mismatch' }
    $archive = [IO.Compression.ZipFile]::OpenRead($job.archive)
    $metaEntry = $archive.GetEntry('package.json')
    if ($null -eq $metaEntry -or $metaEntry.Length -gt 2000000 -or $archive.Entries.Count -gt 15000) { throw 'Invalid package metadata' }
    $reader = New-Object IO.StreamReader($metaEntry.Open())
    try { $metadata = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
    if ($metadata.version -ne $job.version -or $metadata.runtime_id -ne $package.runtime_id) { throw 'Package identity mismatch' }
    $declared = @{}
    foreach ($file in $metadata.files) {
        $null = OwnedPath $root $file.path
        if ($declared.ContainsKey($file.path)) { throw 'Duplicate package path' }
        $declared[$file.path] = $file
    }
    if (-not $declared.ContainsKey('Pacoca.exe')) { throw 'Missing executable' }
    foreach ($relative in $metadata.remove) {
        if ($declared.ContainsKey($relative)) { throw 'A file cannot be replaced and removed together' }
    }
    WaitForGames
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    [IO.Directory]::CreateDirectory($backup) | Out-Null
    $total=0; $seen=@{}
    foreach ($entry in $archive.Entries) {
        if ($entry.FullName -eq 'package.json') { continue }
        $target=OwnedPath $stage $entry.FullName
        if ($seen.ContainsKey($entry.FullName) -or -not $declared.ContainsKey($entry.FullName)) { throw 'Unexpected archive member' }
        $seen[$entry.FullName]=$true
        $file=$declared[$entry.FullName]
        $total += $entry.Length
        if ($entry.Length -ne $file.size -or $total -gt 2500000000) { throw 'Invalid archive size' }
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
        $inputStream=$entry.Open(); $outputStream=[IO.File]::Create($target)
        try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose(); $inputStream.Dispose() }
        if ((FileDigest $target) -ne $file.sha256) { throw 'Archive member checksum mismatch' }
    }
    if ($seen.Count -ne $declared.Count) { throw 'Missing archive member' }
    $archive.Dispose(); $archive=$null
    $original=Get-Process -Id $job.pid -ErrorAction SilentlyContinue
    if ($original -and -not $original.WaitForExit(45000)) { throw 'The application did not exit; no files were changed' }
    WaitForGames
    $instanceLock=[IO.File]::Open((Join-Path $dataRoot 'instance.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::ReadWrite)
    if ($instanceLock.Length -eq 0) { $instanceLock.WriteByte(1);$instanceLock.Flush() }
    $instanceLock.Lock(0,1)
    $paths=@($metadata.files | ForEach-Object { $_.path }) + @($metadata.remove)
    foreach ($relative in $paths) {
        $target=OwnedPath $root $relative
        $saved=OwnedPath $backup $relative
        $exists=[IO.File]::Exists($target)
        if ($exists) { CopyRetry $target $saved }
        $changed.Add(@{path=$relative;existed=$exists})
    }
    foreach ($file in $metadata.files) { CopyRetry (OwnedPath $stage $file.path) (OwnedPath $root $file.path) }
    foreach ($relative in $metadata.remove) {
        if ($relative -eq 'Pacoca.exe') { throw 'Cannot remove executable' }
        $target=OwnedPath $root $relative
        if ([IO.File]::Exists($target)) { [IO.File]::Delete($target) }
    }
    $installed=$true
    $instanceLock.Unlock(0,1);$instanceLock.Dispose();$instanceLock=$null
    $health=Join-Path $transaction 'health.json'
    if ([IO.File]::Exists($health)) { [IO.File]::Delete($health) }
    $env:PACOCA_DATA=$dataRoot
    Remove-Item Env:PACOCA_ASSETS -ErrorAction SilentlyContinue
    $candidate=Start-Process -FilePath (Join-Path $root 'Pacoca.exe') -ArgumentList @('--update-health-file',('"'+$health+'"')) -WindowStyle Hidden -PassThru
    $deadline=[DateTime]::UtcNow.AddSeconds(60)
    $healthy=$false
    while ([DateTime]::UtcNow -lt $deadline) {
        if ([IO.File]::Exists($health)) {
            try {
                $state=Get-Content -LiteralPath $health -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($state.rendered -eq $true -and $state.version -eq $job.version -and $state.pid -eq $candidate.Id) { $healthy=$true;break }
            } catch { }
        }
        if ($candidate.HasExited) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $healthy) { throw 'The new native window did not pass its health check' }
    WriteResult 'installed' 'Atualização instalada e janela nativa verificada.'
} catch {
    $reason=$_.Exception.Message
    if ($instanceLock) { try { $instanceLock.Dispose() } catch { } }
    if ($candidate -and -not $candidate.HasExited) { $candidate.Kill(); $candidate.WaitForExit(10000) | Out-Null }
    if ($archive) { $archive.Dispose() }
    $restored=$true
    foreach ($file in $changed) {
        try {
            $target=OwnedPath $root $file.path
            if ($file.existed) { CopyRetry (OwnedPath $backup $file.path) $target }
            elseif ([IO.File]::Exists($target)) { [IO.File]::Delete($target) }
        } catch { $restored=$false }
    }
    WriteResult $(if ($changed.Count -gt 0 -and $restored) {'rolled_back'} else {'failed'}) $reason
    if ($restored -and [IO.File]::Exists((Join-Path $root 'Pacoca.exe'))) {
        $old=Get-Process -Id $job.pid -ErrorAction SilentlyContinue
        if (-not $old -or $old.WaitForExit(10000)) {
            Start-Process -FilePath (Join-Path $root 'Pacoca.exe') -WindowStyle Hidden | Out-Null
        }
    }
    exit 1
}
