from django.db import models

class SignatureCertificate(models.Model):
    user_id = models.BigIntegerField(verbose_name="User ID")
    serial_number = models.CharField(max_length=255, unique=True, verbose_name="Serial Number")
    issuer = models.CharField(max_length=255, verbose_name="Issuer")
    valid_from = models.DateTimeField(verbose_name="Valid From")
    valid_to = models.DateTimeField(verbose_name="Valid To")
    status = models.CharField(max_length=50, default='ACTIVE', verbose_name="Status")

    class Meta:
        verbose_name = 'Signature Certificate'
        verbose_name_plural = 'Signature Certificates'

    def __str__(self):
        return f"Certificate {self.serial_number} for user {self.user_id}"

class HashProof(models.Model):
    version_id = models.BigIntegerField(unique=True, verbose_name="Version ID")
    hash_algorithm = models.CharField(max_length=50, default='SHA-256', verbose_name="Hash Algorithm")
    document_hash = models.CharField(max_length=64, verbose_name="Document Hash")
    generated_at = models.DateTimeField(auto_now_add=True, verbose_name="Generated At")

    class Meta:
        verbose_name = 'Hash Proof'
        verbose_name_plural = 'Hash Proofs'

    def __str__(self):
        return f"Hash Proof ({self.hash_algorithm}) - v{self.version_id}"

class BlockchainNetwork(models.Model):
    network_name = models.CharField(max_length=100, verbose_name="Network Name")
    chain_type = models.CharField(max_length=50, verbose_name="Chain Type")
    rpc_endpoint = models.CharField(max_length=255, verbose_name="RPC Endpoint")
    status = models.CharField(max_length=50, default='ACTIVE', verbose_name="Status")

    class Meta:
        verbose_name = 'Blockchain Network'
        verbose_name_plural = 'Blockchain Networks'

    def __str__(self):
        return self.network_name

class SmartContract(models.Model):
    network = models.ForeignKey(BlockchainNetwork, on_delete=models.CASCADE, related_name='smart_contracts', verbose_name="Blockchain Network")
    contract_address = models.CharField(max_length=255, verbose_name="Contract Address")
    contract_name = models.CharField(max_length=100, verbose_name="Contract Name")
    version = models.CharField(max_length=50, verbose_name="Version")
    deployed_at = models.DateTimeField(verbose_name="Deployed At")

    class Meta:
        verbose_name = 'Smart Contract'
        verbose_name_plural = 'Smart Contracts'

    def __str__(self):
        return f"{self.contract_name} ({self.contract_address[:10]}...)"

class BlockchainNode(models.Model):
    network = models.ForeignKey(BlockchainNetwork, on_delete=models.CASCADE, related_name='nodes', verbose_name="Blockchain Network")
    node_name = models.CharField(max_length=100, verbose_name="Node Name")
    endpoint = models.CharField(max_length=255, verbose_name="Endpoint")
    organization = models.CharField(max_length=255, verbose_name="Organization")
    status = models.CharField(max_length=50, default='ACTIVE', verbose_name="Status")

    class Meta:
        verbose_name = 'Blockchain Node'
        verbose_name_plural = 'Blockchain Nodes'

    def __str__(self):
        return self.node_name

class BlockchainTransaction(models.Model):
    proof = models.ForeignKey(HashProof, on_delete=models.CASCADE, related_name='transactions', verbose_name="Hash Proof")
    network = models.ForeignKey(BlockchainNetwork, on_delete=models.CASCADE, related_name='transactions', verbose_name="Blockchain Network")
    smart_contract = models.ForeignKey(SmartContract, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', verbose_name="Smart Contract")
    tx_hash = models.CharField(max_length=255, unique=True, verbose_name="Transaction Hash")
    block_hash = models.CharField(max_length=255, blank=True, null=True, verbose_name="Block Hash")
    block_number = models.BigIntegerField(blank=True, null=True, verbose_name="Block Number")
    gas_fee = models.DecimalField(max_digits=18, decimal_places=9, blank=True, null=True, verbose_name="Gas Fee")
    status = models.CharField(max_length=50, default='PENDING', verbose_name="Status")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        verbose_name = 'Blockchain Transaction'
        verbose_name_plural = 'Blockchain Transactions'

    def __str__(self):
        return f"Tx: {self.tx_hash[:10]}... ({self.status})"

class BlockchainAudit(models.Model):
    transaction = models.ForeignKey(BlockchainTransaction, on_delete=models.CASCADE, related_name='audits', verbose_name="Blockchain Transaction")
    event_type = models.CharField(max_length=100, verbose_name="Event Type")
    event_data = models.TextField(verbose_name="Event Data")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        verbose_name = 'Blockchain Audit'
        verbose_name_plural = 'Blockchain Audits'

    def __str__(self):
        return f"Audit for Tx {self.transaction.tx_hash[:8]} - {self.event_type}"

class KeyManagement(models.Model):
    company_id = models.BigIntegerField(verbose_name="Company ID")
    key_alias = models.CharField(max_length=255, verbose_name="Key Alias")
    key_provider = models.CharField(max_length=100, verbose_name="Key Provider")
    key_reference = models.CharField(max_length=512, verbose_name="Key Reference")
    algorithm = models.CharField(max_length=100, verbose_name="Algorithm")
    key_version = models.IntegerField(default=1, verbose_name="Key Version")
    status = models.CharField(max_length=50, default='ACTIVE', verbose_name="Status")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    rotated_at = models.DateTimeField(blank=True, null=True, verbose_name="Rotated At")

    class Meta:
        verbose_name = 'Key Management'
        verbose_name_plural = 'Key Managements'

    def __str__(self):
        return f"Key {self.key_alias} (v{self.key_version})"


