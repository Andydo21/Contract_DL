#!/bin/sh
set -eu
echo "Waiting for package_id.txt..."
while [ ! -f /chaincode/package_id.txt ]; do
  sleep 1
done
export CHAINCODE_ID=$(cat /chaincode/package_id.txt)
[ -n "$CHAINCODE_ID" ] || { echo "Empty chaincode package ID" >&2; exit 1; }
echo "Starting Chaincode with ID $CHAINCODE_ID"
go mod download
exec go run .
