#!/usr/bin/env bash
set -euo pipefail

# Keep these tools in a late image layer so DNS/Exchange updates do not rebuild
# the scientific, browser, Rust and coding-agent toolchains.
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends dnsutils libicu72 libgssapi-krb5-2 libunwind8
rm -rf /var/lib/apt/lists/*

version="${POWERSHELL_VERSION:-7.4.20}"
case "$(dpkg --print-architecture)" in
    amd64) arch=x64 ;;
    arm64) arch=arm64 ;;
    *) echo 'Unsupported PowerShell architecture' >&2; exit 1 ;;
esac
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
archive="powershell-${version}-linux-${arch}.tar.gz"
release="https://github.com/PowerShell/PowerShell/releases/download/v${version}"
curl --proto '=https' --tlsv1.2 -fsSL --retry 3 "$release/$archive" -o "$temp/$archive"
curl --proto '=https' --tlsv1.2 -fsSL --retry 3 "$release/hashes.sha256" -o "$temp/hashes.sha256"
# Microsoft publishes this release manifest as UTF-16 with CRLF line endings.
hash="$(iconv -f UTF-16 -t UTF-8 "$temp/hashes.sha256" | tr -d '\r' | awk -v file="$archive" '$2 == file || $2 == "*" file {print $1}')"
test "${#hash}" -eq 64
printf '%s  %s\n' "$hash" "$temp/$archive" | sha256sum --check --strict
mkdir -p /opt/microsoft/powershell/7
tar -xzf "$temp/$archive" -C /opt/microsoft/powershell/7
chmod +x /opt/microsoft/powershell/7/pwsh
ln -sf /opt/microsoft/powershell/7/pwsh /usr/local/bin/pwsh
export EXCHANGE_MODULE_VERSION="${EXCHANGE_MODULE_VERSION:-3.10.1}"
pwsh -NoLogo -NoProfile -NonInteractive -Command '
    $ErrorActionPreference = "Stop"
    Install-Module ExchangeOnlineManagement -RequiredVersion $env:EXCHANGE_MODULE_VERSION -Repository PSGallery -Scope AllUsers -Force -AcceptLicense
    Import-Module ExchangeOnlineManagement
    Get-Command Connect-ExchangeOnline -ErrorAction Stop | Out-Null
'
sudo -H -u safeexecute dig -v
sudo -H -u safeexecute pwsh -NoLogo -NoProfile -NonInteractive -Command '
    $ErrorActionPreference = "Stop"
    Import-Module ExchangeOnlineManagement
    if (-not (Get-Command Connect-ExchangeOnline).Parameters.ContainsKey("AccessToken")) { throw "Exchange module lacks AccessToken authentication" }
    Get-Module ExchangeOnlineManagement | Select-Object Name,Version | ConvertTo-Json -Compress
'
