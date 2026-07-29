# Stop and remove the Listing2Content container. The DB and photos are
# ephemeral, so stopping discards all data (expected for v1).

$name = "listing2content"

if (docker ps -aq --filter "name=^$name$") {
  docker rm -f $name | Out-Null
  Write-Host "Listing2Content stopped"
} else {
  Write-Host "Listing2Content was not running"
}
