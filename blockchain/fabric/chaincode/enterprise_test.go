package main

import (
    "crypto"
    "crypto/rand"
    "crypto/rsa"
    "crypto/sha256"
    "crypto/x509"
    "encoding/base64"
    "encoding/hex"
    "encoding/json"
    "encoding/pem"
    "testing"
)

func TestEnterpriseSignatureBindsCompanyVersionAndApproval(t *testing.T) {
    private, err := rsa.GenerateKey(rand.Reader, 3072)
    if err != nil { t.Fatal(err) }
    der, _ := x509.MarshalPKIXPublicKey(&private.PublicKey)
    fingerprint := sha256.Sum256(der)
    manifest := enterpriseManifest{Schema:"contract-ledger-v1", OperationID:"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", Kind:"SIGN", CompanyID:1, ContractID:2, VersionID:3, VersionNumber:1, SignerID:4, DocumentHash:hex.EncodeToString(fingerprint[:]), CredentialFingerprint:hex.EncodeToString(fingerprint[:])}
    bytes, _ := json.Marshal(manifest)
    digest := sha256.Sum256(bytes)
    signature, _ := rsa.SignPKCS1v15(rand.Reader, private, crypto.SHA256, digest[:])
    approver := int64(5)
    envelope := enterpriseEnvelope{Manifest:string(bytes), Signature:base64.StdEncoding.EncodeToString(signature), PublicKeyPEM:string(pem.EncodeToMemory(&pem.Block{Type:"PUBLIC KEY",Bytes:der})), CredentialOwner:4, CredentialCompany:1, CredentialApprover:&approver}
    raw, _ := json.Marshal(envelope)
    if _,_,err=validateEnterpriseEnvelope(string(raw)); err!=nil { t.Fatal(err) }
    manifest.VersionID=99
    bytes,_=json.Marshal(manifest)
    envelope.Manifest=string(bytes)
    raw,_=json.Marshal(envelope)
    if _,_,err=validateEnterpriseEnvelope(string(raw)); err==nil { t.Fatal("replayed signature accepted for another version") }
    manifest.VersionID=3
    bytes,_=json.Marshal(manifest)
    envelope.Manifest=string(bytes)
    envelope.CredentialCompany=99
    raw,_=json.Marshal(envelope)
    if _,_,err=validateEnterpriseEnvelope(string(raw)); err==nil { t.Fatal("cross-company credential accepted") }
    envelope.CredentialCompany=1
    approver=4
    raw,_=json.Marshal(envelope)
    if _,_,err=validateEnterpriseEnvelope(string(raw)); err==nil { t.Fatal("self-approved credential accepted") }
}

func TestEnterpriseRejectsLegacyUnsignedPayload(t *testing.T) {
    if _,_,err:=validateEnterpriseEnvelope(`{"signature":"random-hash"}`); err==nil {t.Fatal("unsigned legacy payload accepted")}
}
