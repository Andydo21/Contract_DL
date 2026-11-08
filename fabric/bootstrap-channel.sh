#!/bin/bash
set -euo pipefail
cd /fabric
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/fabric/crypto-config/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/fabric/crypto-config/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp
export CORE_PEER_ADDRESS=peer0.org1.example.com:7051
export ORDERER_CA=/fabric/crypto-config/ordererOrganizations/example.com/orderers/orderer.example.com/tls/ca.crt
retry() {
  local attempt
  for attempt in {1..20}; do
    if "$@"; then return 0; fi
    sleep 3
  done
  echo "Fabric operation failed after retries: $1" >&2
  return 1
}
orderer_args=(--orderer-address orderer.example.com:7053 --ca-file "$ORDERER_CA" --client-cert /fabric/crypto-config/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.crt --client-key /fabric/crypto-config/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.key)
retry osnadmin channel list "${orderer_args[@]}" > /tmp/orderer-channels.txt
if ! grep -q '"contracts-channel"' /tmp/orderer-channels.txt; then
  retry osnadmin channel join --channelID contracts-channel --config-block /fabric/contracts-channel.block "${orderer_args[@]}"
fi
retry peer channel list > /tmp/peer-channels.txt
if ! grep -qx 'contracts-channel' /tmp/peer-channels.txt; then
  retry peer channel join -b /fabric/contracts-channel.block
fi
if [ ! -f contract_verify_v2.tar.gz ]; then
  tar cfz /tmp/code.tar.gz -C chaincode connection.json
  cp chaincode/metadata.json /tmp/metadata.json
  tar cfz contract_verify_v2.tar.gz -C /tmp metadata.json code.tar.gz
fi
PACKAGE_ID=$(peer lifecycle chaincode calculatepackageid contract_verify_v2.tar.gz)
peer lifecycle chaincode queryinstalled > /tmp/installed.txt
if ! grep -Fq "$PACKAGE_ID" /tmp/installed.txt; then
  retry peer lifecycle chaincode install contract_verify_v2.tar.gz
fi
printf '%s\n' "$PACKAGE_ID" > chaincode/package_id.txt
common_args=(-o orderer.example.com:7050 --ordererTLSHostnameOverride orderer.example.com --channelID contracts-channel --name ContractVerifyChaincode --version 2.0 --sequence 2 --tls --cafile "$ORDERER_CA")
if peer lifecycle chaincode querycommitted --channelID contracts-channel --name ContractVerifyChaincode > /tmp/committed.txt 2>/dev/null && grep -q 'Sequence: 2' /tmp/committed.txt; then
  echo "Chaincode definition already committed; retained."
else
  retry peer lifecycle chaincode approveformyorg "${common_args[@]}" --package-id "$PACKAGE_ID"
  retry peer lifecycle chaincode commit "${common_args[@]}" --peerAddresses "$CORE_PEER_ADDRESS" --tlsRootCertFiles "$CORE_PEER_TLS_ROOTCERT_FILE"
fi
peer lifecycle chaincode querycommitted --channelID contracts-channel --name ContractVerifyChaincode
echo "Fabric channel and chaincode deployment verified."
