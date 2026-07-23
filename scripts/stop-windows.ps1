# Stop and remove the Listing2Content container. The DB is ephemeral, so
# stopping discards all data (expected for v1).
$ErrorActionPreference = "SilentlyContinue"

docker rm -f listing2content | Out-Null
Write-Host "Listing2Content stopped"
