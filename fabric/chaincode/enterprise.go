package main

import (
    "bytes"
    "crypto"
    "crypto/rsa"
    "crypto/sha256"
    "crypto/x509"
    "encoding/base64"
    "encoding/hex"
    "encoding/json"
    "encoding/pem"
    "fmt"
    "os"
    "regexp"
    "github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type enterpriseManifest struct {
    Schema string `json:"schema"`
    OperationID string `json:"operation_id"`
    Kind string `json:"kind"`
    CompanyID int64 `json:"company_id"`
    ContractID int64 `json:"contract_id"`
    VersionID int64 `json:"version_id"`
    VersionNumber int64 `json:"version_number"`
    SignerID int64 `json:"signer_id"`
    DocumentHash string `json:"document_hash"`
    CredentialFingerprint string `json:"credential_fingerprint"`
}
type enterpriseEnvelope struct {
    Manifest string `json:"manifest"`
    Signature string `json:"signature"`
    PublicKeyPEM string `json:"public_key_pem"`
    CredentialOwner int64 `json:"credential_owner"`
    CredentialCompany int64 `json:"credential_company"`
    CredentialApprover *int64 `json:"credential_approver"`
}
type EnterpriseRecord struct {
    Payload string `json:"payload"`
    PayloadHash string `json:"payload_hash"`
    TxID string `json:"tx_id"`
    CompanyID int64 `json:"company_id"`
}

func requireEnterpriseGateway(ctx contractapi.TransactionContextInterface) error {
    msp, err := ctx.GetClientIdentity().GetMSPID()
    if err != nil || msp != "Org1MSP" { return fmt.Errorf("unauthorized application MSP") }
    cert, err := ctx.GetClientIdentity().GetX509Certificate()
    if err != nil || cert == nil { return fmt.Errorf("application certificate required") }
    trusted, err := os.ReadFile(os.Getenv("ENTERPRISE_GATEWAY_CERT_PATH"))
    if err != nil { return fmt.Errorf("trusted application certificate unavailable") }
    block, _ := pem.Decode(trusted)
    if block == nil || !bytes.Equal(cert.Raw, block.Bytes) { return fmt.Errorf("unauthorized gateway certificate") }
    return nil
}

func validateEnterpriseEnvelope(raw string) (*enterpriseManifest, *enterpriseEnvelope, error) {
    var envelope enterpriseEnvelope
    var manifest enterpriseManifest
    if err := json.Unmarshal([]byte(raw), &envelope); err != nil { return nil, nil, err }
    if err := json.Unmarshal([]byte(envelope.Manifest), &manifest); err != nil { return nil, nil, err }
    if manifest.Schema != "contract-ledger-v1" || !regexp.MustCompile(`^[0-9a-f-]{36}$`).MatchString(manifest.OperationID) ||
       manifest.CompanyID <= 0 || manifest.ContractID <= 0 || manifest.VersionID <= 0 || manifest.SignerID <= 0 ||
       manifest.VersionNumber <= 0 || !regexp.MustCompile(`^[0-9a-f]{64}$`).MatchString(manifest.DocumentHash) {
        return nil, nil, fmt.Errorf("invalid version-bound manifest")
    }
    if manifest.Kind == "ANCHOR" {
        if envelope.Signature != "" || envelope.PublicKeyPEM != "" { return nil, nil, fmt.Errorf("anchor cannot masquerade as signature") }
        return &manifest, &envelope, nil
    }
    if manifest.Kind != "SIGN" || envelope.CredentialOwner != manifest.SignerID || envelope.CredentialCompany != manifest.CompanyID ||
       envelope.CredentialApprover == nil || *envelope.CredentialApprover <= 0 || *envelope.CredentialApprover == manifest.SignerID {
        return nil, nil, fmt.Errorf("credential owner, company or independent approval mismatch")
    }
    block, _ := pem.Decode([]byte(envelope.PublicKeyPEM))
    if block == nil { return nil, nil, fmt.Errorf("public key required") }
    parsed, err := x509.ParsePKIXPublicKey(block.Bytes)
    if err != nil { return nil, nil, err }
    key, ok := parsed.(*rsa.PublicKey)
    if !ok || key.N.BitLen() < 3072 || key.E != 65537 { return nil, nil, fmt.Errorf("RSA 3072 public key required") }
    fingerprint := sha256.Sum256(block.Bytes)
    if hex.EncodeToString(fingerprint[:]) != manifest.CredentialFingerprint { return nil, nil, fmt.Errorf("credential fingerprint mismatch") }
    signature, err := base64.StdEncoding.DecodeString(envelope.Signature)
    if err != nil { return nil, nil, err }
    digest := sha256.Sum256([]byte(envelope.Manifest))
    if err = rsa.VerifyPKCS1v15(key, crypto.SHA256, digest[:], signature); err != nil { return nil, nil, fmt.Errorf("invalid signature for this company and version") }
    return &manifest, &envelope, nil
}

func (s *SmartContract) CommitEnterpriseOperation(ctx contractapi.TransactionContextInterface, raw string) error {
    if err := requireEnterpriseGateway(ctx); err != nil { return err }
    manifest, envelope, err := validateEnterpriseEnvelope(raw)
    if err != nil { return err }
    key := "OP_" + manifest.OperationID
    existing, err := ctx.GetStub().GetState(key)
    if err != nil { return err }
    digest := sha256.Sum256([]byte(raw))
    payloadHash := hex.EncodeToString(digest[:])
    if existing != nil {
        var record EnterpriseRecord
        if err := json.Unmarshal(existing, &record); err != nil { return err }
        if record.PayloadHash != payloadHash { return fmt.Errorf("operation ID already bound to different payload") }
        return nil
    }
    if manifest.Kind == "SIGN" {
        credentialKey := "CREDENTIAL_" + manifest.CredentialFingerprint
        saved, err := ctx.GetStub().GetState(credentialKey)
        if err != nil { return err }
        binding, _ := json.Marshal(struct{Owner, Company int64; PublicKey string}{envelope.CredentialOwner, envelope.CredentialCompany, envelope.PublicKeyPEM})
        if saved != nil && !bytes.Equal(saved, binding) { return fmt.Errorf("public key already belongs to another company or user") }
        if saved == nil { if err := ctx.GetStub().PutState(credentialKey, binding); err != nil { return err } }
    }
    record, err := json.Marshal(EnterpriseRecord{Payload: raw, PayloadHash: payloadHash, TxID: ctx.GetStub().GetTxID(), CompanyID: manifest.CompanyID})
    if err != nil { return err }
    return ctx.GetStub().PutState(key, record)
}

func (s *SmartContract) GetEnterpriseOperation(ctx contractapi.TransactionContextInterface, operationID string) (*EnterpriseRecord, error) {
    if err := requireEnterpriseGateway(ctx); err != nil { return nil, err }
    value, err := ctx.GetStub().GetState("OP_" + operationID)
    if err != nil { return nil, err }
    if value == nil { return nil, fmt.Errorf("enterprise operation does not exist") }
    var record EnterpriseRecord
    if err = json.Unmarshal(value, &record); err != nil { return nil, err }
    return &record, nil
}
