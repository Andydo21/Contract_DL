"""
Script seed dữ liệu blockchain cho blockchain_service.
Chạy bên trong container blockchain_service:
  docker exec blockchain_service python scripts/seed_blockchain.py
Hoặc gọi qua HTTP API từ web service container.
"""
import os
import sys
import django
import hashlib
import uuid
import random
import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Nếu chạy trong blockchain_service container thì sys.path cần trỏ đúng
# Thử import blockchain app
try:
    django.setup()
    from blockchain.models import (
        BlockchainNetwork, SmartContract, BlockchainNode,
        HashProof, BlockchainTransaction, BlockchainAudit,
        SignatureCertificate, KeyManagement
    )
    from django.utils import timezone
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)


def seed():
    print("=== Seeding Blockchain Service Database ===")

    # 1. Ensure default network exists (auto-seeded by apps.py already)
    net = BlockchainNetwork.objects.first()
    if not net:
        net = BlockchainNetwork.objects.create(
            network_name="Hyperledger Fabric Mainnet",
            chain_type="Hyperledger",
            rpc_endpoint="http://fabric-peer:7051",
            status="ACTIVE"
        )
        print("Created BlockchainNetwork")
    else:
        print(f"Using existing network: {net.network_name}")

    # 2. Add an Ethereum-based network as second option
    eth_net, created = BlockchainNetwork.objects.get_or_create(
        network_name="Ethereum Sepolia Testnet",
        defaults={
            "chain_type": "Ethereum",
            "rpc_endpoint": "https://rpc.sepolia.org",
            "status": "ACTIVE"
        }
    )
    if created:
        print("Created Ethereum Sepolia network")

    # 3. Ensure SmartContract exists
    sc = SmartContract.objects.filter(network=net).first()
    if not sc:
        sc = SmartContract.objects.create(
            network=net,
            contract_address="cc_contract_verify_v1",
            contract_name="ContractVerifyChaincode",
            version="1.0.0",
            deployed_at=timezone.now()
        )
        print("Created SmartContract")
    else:
        print(f"Using existing SmartContract: {sc.contract_name}")

    # Add Ethereum smart contract
    eth_sc, created = SmartContract.objects.get_or_create(
        contract_address="0xAbC1234567890DEF1234567890abcdef12345678",
        defaults={
            "network": eth_net,
            "contract_name": "ContractHashRegistry",
            "version": "2.1.0",
            "deployed_at": timezone.now()
        }
    )
    if created:
        print("Created Ethereum SmartContract")

    # 4. Ensure Blockchain Nodes
    if not BlockchainNode.objects.filter(network=net).exists():
        for i, (name, org) in enumerate([
            ("Peer0Org1", "Org1MSP"),
            ("Peer1Org1", "Org1MSP"),
            ("Peer0Org2", "Org2MSP"),
        ]):
            BlockchainNode.objects.create(
                network=net,
                node_name=name,
                endpoint=f"fabric-peer{i}:705{i+1}",
                organization=org,
                status="ACTIVE"
            )
        print("Created 3 Blockchain Nodes")

    # 5. Seed SignatureCertificates for mock users (user_id = 1..5)
    user_ids = [1, 2, 3, 4, 5]
    cert_map = {}
    for uid in user_ids:
        serial = f"CERT-ORG1-USER{uid:03d}-2026"
        cert, created = SignatureCertificate.objects.get_or_create(
            serial_number=serial,
            defaults={
                "user_id": uid,
                "issuer": "Antigravity Root CA",
                "valid_from": timezone.now() - datetime.timedelta(days=90),
                "valid_to": timezone.now() + datetime.timedelta(days=275),
                "status": "ACTIVE"
            }
        )
        cert_map[uid] = cert
        if created:
            print(f"  Certificate: {serial}")

    # 6. Seed KeyManagement entries (per company_id)
    for company_id in range(1, 6):
        KeyManagement.objects.get_or_create(
            company_id=company_id,
            key_alias=f"company_{company_id}_signing_key",
            defaults={
                "key_provider": "HSM-SoftToken",
                "key_reference": f"arn:aws:kms:ap-southeast-1:123456789:key/company-{company_id}-rsa",
                "algorithm": "RSA-2048",
                "key_version": 1,
                "status": "ACTIVE"
            }
        )
    print("Created KeyManagement entries for 5 companies")

    # 7. Seed HashProofs and BlockchainTransactions for contract versions
    # version_ids as known from web service seeding
    version_ids = list(range(13, 27))  # IDs 13-26
    contract_codes = [
        "CON-2026-001", "CON-2026-001",
        "CON-2026-002", "CON-2026-003",
        "CON-2026-004", "CON-2026-004",
        "CON-2026-005", "CON-2026-006",
        "CON-2026-007", "CON-2026-008",
        "CON-2026-009", "CON-2026-010",
        "CON-2026-011", "CON-2026-012",
    ]

    networks_list = [net, eth_net, net, net, eth_net, net, net, eth_net, net, net, eth_net, net, net, eth_net]
    sc_list = [sc, eth_sc, sc, sc, eth_sc, sc, sc, eth_sc, sc, sc, eth_sc, sc, sc, eth_sc]

    for i, (version_id, code) in enumerate(zip(version_ids, contract_codes)):
        # Generate document hash from contract metadata
        meta = f"{code}-v{i+1}-verified"
        doc_hash = hashlib.sha256(meta.encode('utf-8')).hexdigest()

        proof, proof_created = HashProof.objects.get_or_create(
            version_id=version_id,
            defaults={
                "hash_algorithm": "SHA-256",
                "document_hash": doc_hash
            }
        )
        if proof_created:
            print(f"  HashProof for version_id={version_id} ({code}): {doc_hash[:16]}...")

        # Only anchor if no existing transaction for this proof
        if not BlockchainTransaction.objects.filter(proof=proof).exists():
            chosen_net = networks_list[i % len(networks_list)]
            chosen_sc = sc_list[i % len(sc_list)]

            tx_hash = "0x" + uuid.uuid4().hex + uuid.uuid4().hex[:16]
            block_hash = "0x" + uuid.uuid4().hex
            block_number = random.randint(15_000_000, 22_000_000)
            gas_fee = round(random.uniform(0.0005, 0.02), 9)

            tx = BlockchainTransaction.objects.create(
                proof=proof,
                network=chosen_net,
                smart_contract=chosen_sc,
                tx_hash=tx_hash,
                block_hash=block_hash,
                block_number=block_number,
                gas_fee=gas_fee,
                status="CONFIRMED",
                created_at=timezone.now() - datetime.timedelta(days=random.randint(1, 30))
            )

            import json
            BlockchainAudit.objects.create(
                transaction=tx,
                event_type="ANCHOR_PROOF",
                event_data=json.dumps({
                    "tx_hash": tx_hash,
                    "document_hash": doc_hash,
                    "contract_code": code,
                    "version_id": version_id,
                    "block_number": block_number,
                    "gas_fee": f"{gas_fee:.9f}",
                    "network": chosen_net.network_name,
                    "anchored_by": "Blockchain Seed Script"
                })
            )
            print(f"  Anchored Tx for {code} v{i+1} on {chosen_net.network_name}")

    print("\n=== Blockchain seeding complete! ===")
    print(f"  Networks: {BlockchainNetwork.objects.count()}")
    print(f"  SmartContracts: {SmartContract.objects.count()}")
    print(f"  Nodes: {BlockchainNode.objects.count()}")
    print(f"  Certificates: {SignatureCertificate.objects.count()}")
    print(f"  HashProofs: {HashProof.objects.count()}")
    print(f"  Transactions: {BlockchainTransaction.objects.count()}")
    print(f"  KeyManagement: {KeyManagement.objects.count()}")


if __name__ == "__main__":
    seed()
