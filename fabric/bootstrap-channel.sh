#!/bin/bash
set -e

echo "=== Phase 2: Setting up Channel and Deploying Chaincode ==="

# Wait for Orderer and Peer to start up
echo "Waiting 15 seconds for Fabric nodes to start..."
sleep 15
echo "Fabric nodes should be online now."

# Environment variables for Peer CLI
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="Org1MSP"
export CORE_PEER_TLS_ROOTCERT_FILE=/fabric/crypto-config/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/fabric/crypto-config/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp
export CORE_PEER_ADDRESS=peer0.org1.example.com:7051
export ORDERER_CA=/fabric/crypto-config/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem

# 1. Join Orderer to Channel using Channel Participation API
echo "Joining Orderer to channel..."
osnadmin channel join --channelID contracts-channel \
  --config-block /fabric/contracts-channel.block \
  --orderer-address orderer.example.com:7053 \
  --ca-file /fabric/crypto-config/ordererOrganizations/example.com/orderers/orderer.example.com/tls/ca.crt \
  --client-cert /fabric/crypto-config/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.crt \
  --client-key /fabric/crypto-config/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.key || true

# 2. Join Peer to Channel
echo "Joining Peer to channel..."
peer channel join -b /fabric/contracts-channel.block || true

# 3. Package Chaincode as CCAAS
echo "Packaging chaincode as CCAAS..."
cd /fabric/chaincode
tar cfz code.tar.gz connection.json
tar cfz contract_verify.tar.gz metadata.json code.tar.gz
mv contract_verify.tar.gz /fabric/
cd /fabric

# 4. Install Chaincode
echo "Installing chaincode on peer..."
peer lifecycle chaincode install contract_verify.tar.gz || true

# Extract Package ID
echo "Querying installed chaincode to get Package ID..."
peer lifecycle chaincode queryinstalled > log.txt
cat log.txt
PACKAGE_ID=$(sed -n 's/^Package ID: //; s/, Label:.*$//p' log.txt)
echo "Package ID: $PACKAGE_ID"

# Save Package ID for the Chaincode Container to read
echo "$PACKAGE_ID" > /fabric/chaincode/package_id.txt

# 5. Approve Chaincode (with retry loop for Raft leader election)
echo "Approving chaincode definition..."
for i in {1..10}; do
  echo "Attempt $i to approve chaincode..."
  if peer lifecycle chaincode approveformyorg -o orderer.example.com:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --channelID contracts-channel \
    --name ContractVerifyChaincode \
    --version 1.0 \
    --package-id "$PACKAGE_ID" \
    --sequence 1 \
    --tls \
    --cafile "$ORDERER_CA"; then
      echo "Chaincode approved successfully."
      break
  fi
  echo "Approve failed, sleeping 5 seconds..."
  sleep 5
done

# 6. Commit Chaincode (with retry loop)
echo "Committing chaincode definition..."
for i in {1..5}; do
  echo "Attempt $i to commit chaincode..."
  if peer lifecycle chaincode commit -o orderer.example.com:7050 \
    --ordererTLSHostnameOverride orderer.example.com \
    --channelID contracts-channel \
    --name ContractVerifyChaincode \
    --version 1.0 \
    --sequence 1 \
    --tls \
    --cafile "$ORDERER_CA" \
    --peerAddresses peer0.org1.example.com:7051 \
    --tlsRootCertFiles "$CORE_PEER_TLS_ROOTCERT_FILE"; then
      echo "Chaincode committed successfully."
      break
  fi
  echo "Commit failed, sleeping 5 seconds..."
  sleep 5
done

echo "=== Phase 2 Completed Successfully ==="
