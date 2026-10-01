$ErrorActionPreference = "Stop"

$UpstreamUrl = "https://github.com/Nayan-Bebale/Telegram-Member-Migration-Tool.git"
$UpstreamCommit = "0619887480abe6a19b6652e8a8aafe6ceaa93a66"
$Dest = if ($args.Count -gt 0) { $args[0] } else { "vendor/Nayan-Telegram-Member-Migration-Tool" }

if (Test-Path $Dest) {
    throw "Destination already exists: $Dest"
}

git clone --no-checkout $UpstreamUrl $Dest
git -C $Dest checkout --detach $UpstreamCommit
Write-Host "Pinned upstream checked out at $Dest"
