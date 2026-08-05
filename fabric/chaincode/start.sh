#!/bin/sh
echo "Waiting for package_id.txt..."
while [ ! -f /chaincode/package_id.txt ]; do
  sleep 1
done
export CHAINCODE_ID=$(cat /chaincode/package_id.txt)
echo "Starting Chaincode with ID $CHAINCODE_ID"
go mod tidy
go run .
