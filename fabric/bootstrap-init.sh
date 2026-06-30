#!/bin/bash
set -e

echo "=== Phase 1: Generating Crypto Materials and Genesis Block ==="

cd /fabric

# Clean up any old configurations
rm -rf crypto-config
rm -f contracts-channel.block

# 1. Generate crypto materials
cryptogen generate --config=crypto-config.yaml --output=crypto-config

# 2. Generate channel genesis block
configtxgen -profile TwoOrgsChannel -outputBlock contracts-channel.block -channelID contracts-channel -configPath .

# 2.5 Rename admin private key to a fixed name for Explorer
ADMIN_KEY_DIR="crypto-config/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp/keystore"
if [ -d "$ADMIN_KEY_DIR" ]; then
    cp "$ADMIN_KEY_DIR"/*_sk "$ADMIN_KEY_DIR/admin.key"
fi

# 3. Set loose permissions so all containers can read certificates
chmod -R 755 crypto-config
chmod 644 contracts-channel.block

echo "=== Phase 1 Completed Successfully ==="
