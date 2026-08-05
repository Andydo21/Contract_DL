package main

import (
	"encoding/json"
	"fmt"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type SignatureRecord struct {
	SignatureID       string `json:"signatureId"`
	StepID            string `json:"stepId"`
	UserID            string `json:"userId"`
	CertificateSerial string `json:"certificateSerial"`
	SignatureHash     string `json:"signatureHash"`
	Timestamp         string `json:"timestamp"`
}

func (s *SmartContract) StoreSignature(ctx contractapi.TransactionContextInterface, signatureID string, stepID string, userID string, certificateSerial string, signatureHash string, timestamp string) error {
	record := SignatureRecord{
		SignatureID:       signatureID,
		StepID:            stepID,
		UserID:            userID,
		CertificateSerial: certificateSerial,
		SignatureHash:     signatureHash,
		Timestamp:         timestamp,
	}

	recordBytes, err := json.Marshal(record)
	if err != nil {
		return err
	}

	return ctx.GetStub().PutState("SIGNATURE_"+signatureID, recordBytes)
}

func (s *SmartContract) GetSignature(ctx contractapi.TransactionContextInterface, signatureID string) (*SignatureRecord, error) {
	recordBytes, err := ctx.GetStub().GetState("SIGNATURE_"+signatureID)
	if err != nil {
		return nil, fmt.Errorf("failed to read from world state: %v", err)
	}
	if recordBytes == nil {
		return nil, fmt.Errorf("signature %s does not exist", signatureID)
	}

	var record SignatureRecord
	err = json.Unmarshal(recordBytes, &record)
	if err != nil {
		return nil, err
	}

	return &record, nil
}
