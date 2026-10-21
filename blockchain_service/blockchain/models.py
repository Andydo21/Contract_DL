from django.db import models

class SignatureCertificate(models.Model):
    user_id = models.BigIntegerField(verbose_name="User ID")
    serial_number = models.CharField(max_length=255, unique=True, verbose_name="Serial Number")
    issuer = models.CharField(max_length=255, verbose_name="Issuer")
    valid_from = models.DateTimeField(verbose_name="Valid From")
    valid_to = models.DateTimeField(verbose_name="Valid To")
    status = models.CharField(max_length=50, default='ACTIVE', verbose_name="Status")
    certificate_pem = models.TextField(blank=True, null=True, verbose_name="Certificate PEM")
    public_key = models.TextField(blank=True, null=True, verbose_name="Public Key")
    signature_algorithm = models.CharField(max_length=50, default="SHA256withRSA", verbose_name="Signature Algorithm")
    revoked = models.BooleanField(default=False, verbose_name="Revoked")
    revoked_at = models.DateTimeField(blank=True, null=True, verbose_name="Revoked At")

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
    file_size = models.IntegerField(null=True, blank=True, verbose_name="File Size (bytes)")
    hash_version = models.IntegerField(default=1, verbose_name="Hash Version")
    previous_hash = models.CharField(max_length=64, blank=True, null=True, verbose_name="Previous Hash")
    merkle_root = models.CharField(max_length=64, blank=True, null=True, verbose_name="Merkle Root")
    verified = models.BooleanField(default=False, verbose_name="Verified")
    verified_at = models.DateTimeField(blank=True, null=True, verbose_name="Verified At")

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


class BlockchainTransaction(models.Model):
    proof = models.ForeignKey(HashProof, on_delete=models.CASCADE, null=True, blank=True, related_name='transactions', verbose_name="Hash Proof")
    network = models.ForeignKey(BlockchainNetwork, on_delete=models.CASCADE, null=True, blank=True, related_name='transactions', verbose_name="Blockchain Network")
    smart_contract = models.ForeignKey(SmartContract, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', verbose_name="Smart Contract")
    tx_hash = models.CharField(max_length=255, unique=True, verbose_name="Transaction Hash")
    block_hash = models.CharField(max_length=255, blank=True, null=True, verbose_name="Block Hash")
    block_number = models.BigIntegerField(blank=True, null=True, verbose_name="Block Number")
    gas_fee = models.DecimalField(max_digits=18, decimal_places=9, blank=True, null=True, verbose_name="Gas Fee")
    status = models.CharField(max_length=50, default='PENDING', verbose_name="Status")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    tx_type = models.CharField(max_length=50, default="INVOKE", verbose_name="Transaction Type")
    sender = models.CharField(max_length=255, blank=True, null=True, verbose_name="Sender")
    endorser = models.CharField(max_length=255, blank=True, null=True, verbose_name="Endorser")
    channel_name = models.CharField(max_length=100, default="contracts-channel", verbose_name="Channel Name")
    chaincode_name = models.CharField(max_length=100, default="ContractVerifyChaincode", verbose_name="Chaincode Name")
    fabric_tx_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="Fabric Transaction ID")
    confirmation_time = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True, verbose_name="Confirmation Time (s)")
    latency = models.DecimalField(max_digits=6, decimal_places=3, blank=True, null=True, verbose_name="Latency (s)")
    retry_count = models.IntegerField(default=0, verbose_name="Retry Count")

    class Meta:
        verbose_name = 'Blockchain Transaction'
        verbose_name_plural = 'Blockchain Transactions'

    def __str__(self):
        return f"Tx: {self.tx_hash[:10]}... ({self.status})"


class BlockchainAudit(models.Model):
    transaction = models.ForeignKey(BlockchainTransaction, on_delete=models.CASCADE, related_name='audits', verbose_name="Blockchain Transaction")
    user_id = models.BigIntegerField(null=True, blank=True, verbose_name="User ID")
    company_id = models.BigIntegerField(null=True, blank=True, verbose_name="Company ID")
    ip = models.CharField(max_length=45, blank=True, null=True, verbose_name="IP Address")
    action = models.CharField(max_length=100, default="Hash Generated", verbose_name="Action")
    resource = models.CharField(max_length=255, default="UNKNOWN", verbose_name="Resource")
    before_state = models.TextField(blank=True, null=True, verbose_name="Before State")
    after_state = models.TextField(blank=True, null=True, verbose_name="After State")
    status = models.CharField(max_length=50, default="SUCCESS", verbose_name="Status")
    error_message = models.TextField(blank=True, null=True, verbose_name="Error Message")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        verbose_name = 'Blockchain Audit'
        verbose_name_plural = 'Blockchain Audits'

    def __str__(self):
        return f"Audit for Tx {self.transaction.tx_hash[:8]} - {self.action}"


class DigitalSignature(models.Model):
    certificate = models.ForeignKey(SignatureCertificate, on_delete=models.CASCADE, related_name='signatures', verbose_name="Certificate")
    hashproof = models.ForeignKey(HashProof, on_delete=models.CASCADE, related_name='signatures', verbose_name="Hash Proof")
    signature = models.TextField(verbose_name="Signature Value")
    algorithm = models.CharField(max_length=50, default="SHA256withRSA", verbose_name="Signing Algorithm")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    verified = models.BooleanField(default=False, verbose_name="Verified")
    verified_at = models.DateTimeField(blank=True, null=True, verbose_name="Verified At")
    tx_hash = models.CharField(max_length=255, blank=True, null=True, verbose_name="Transaction Hash")
    block_number = models.BigIntegerField(blank=True, null=True, verbose_name="Block Number")
    block_hash = models.CharField(max_length=255, blank=True, null=True, verbose_name="Block Hash")

    class Meta:
        verbose_name = 'Digital Signature'
        verbose_name_plural = 'Digital Signatures'

    def __str__(self):
        return f"Sig by Cert {self.certificate.serial_number[:8]} for Proof {self.hashproof.id}"


class VerificationHistory(models.Model):
    version_id = models.BigIntegerField(verbose_name="Version ID")
    verify_time = models.DateTimeField(auto_now_add=True, verbose_name="Verification Time")
    verify_result = models.BooleanField(verbose_name="Verification Result")
    reason = models.TextField(blank=True, null=True, verbose_name="Reason")
    user_id = models.BigIntegerField(null=True, blank=True, verbose_name="User ID")

    class Meta:
        verbose_name = 'Verification History'
        verbose_name_plural = 'Verification Histories'

    def __str__(self):
        return f"Verify v{self.version_id} at {self.verify_time} -> {self.verify_result}"
