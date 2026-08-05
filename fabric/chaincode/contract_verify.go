package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/hyperledger/fabric-chaincode-go/shim"
	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type SmartContract struct {
	contractapi.Contract
}

type HashRecord struct {
	ProofID      string `json:"proofId"`
	DocumentHash string `json:"documentHash"`
	MerkleRoot   string `json:"merkleRoot"`
	Timestamp    string `json:"timestamp"`
}

type HistoryQueryResult struct {
	TxID      string      `json:"txId"`
	Value     *HashRecord `json:"value"`
	Timestamp string      `json:"timestamp"`
	IsDelete  bool        `json:"isDelete"`
}

func (s *SmartContract) StoreHash(ctx contractapi.TransactionContextInterface, proofID string, documentHash string, merkleRoot string, timestamp string) error {
	exists, err := s.HashExists(ctx, proofID)
	if err != nil {
		return err
	}
	if exists {
		return fmt.Errorf("the hash for proof %s already exists", proofID)
	}

	record := HashRecord{
		ProofID:      proofID,
		DocumentHash: documentHash,
		MerkleRoot:   merkleRoot,
		Timestamp:    timestamp,
	}

	recordBytes, err := json.Marshal(record)
	if err != nil {
		return err
	}

	return ctx.GetStub().PutState(proofID, recordBytes)
}

func (s *SmartContract) GetHash(ctx contractapi.TransactionContextInterface, proofID string) (*HashRecord, error) {
	recordBytes, err := ctx.GetStub().GetState(proofID)
	if err != nil {
		return nil, fmt.Errorf("failed to read from world state: %v", err)
	}
	if recordBytes == nil {
		return nil, fmt.Errorf("the hash for proof %s does not exist", proofID)
	}

	var record HashRecord
	err = json.Unmarshal(recordBytes, &record)
	if err != nil {
		return nil, err
	}

	return &record, nil
}

func (s *SmartContract) HashExists(ctx contractapi.TransactionContextInterface, proofID string) (bool, error) {
	recordBytes, err := ctx.GetStub().GetState(proofID)
	if err != nil {
		return false, err
	}
	return recordBytes != nil, nil
}

func (s *SmartContract) GetHistory(ctx contractapi.TransactionContextInterface, proofID string) ([]HistoryQueryResult, error) {
	resultsIterator, err := ctx.GetStub().GetHistoryForKey(proofID)
	if err != nil {
		return nil, err
	}
	defer resultsIterator.Close()

	var records []HistoryQueryResult
	for resultsIterator.HasNext() {
		queryResponse, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}

		var record HashRecord
		if !queryResponse.IsDelete {
			err = json.Unmarshal(queryResponse.Value, &record)
			if err != nil {
				return nil, err
			}
		}

		txTimestamp := time.Unix(queryResponse.Timestamp.Seconds, int64(queryResponse.Timestamp.Nanos)).Format(time.RFC3339)

		historicalRecord := HistoryQueryResult{
			TxID:      queryResponse.TxId,
			Value:     &record,
			Timestamp: txTimestamp,
			IsDelete:  queryResponse.IsDelete,
		}
		records = append(records, historicalRecord)
	}

	return records, nil
}

type CompanyRecord struct {
	CompanyID   string `json:"companyId"`
	CompanyName string `json:"companyName"`
	TaxCode     string `json:"taxCode"`
	Status      string `json:"status"`
}

type UserRecord struct {
	UserID    string `json:"userId"`
	Username  string `json:"username"`
	CompanyID string `json:"companyId"`
	Role      string `json:"role"`
	Status    string `json:"status"`
}

type SignatureRecord struct {
	SignatureID       string `json:"signatureId"`
	StepID            string `json:"stepId"`
	UserID            string `json:"userId"`
	CertificateSerial string `json:"certificateSerial"`
	SignatureHash     string `json:"signatureHash"`
	Timestamp         string `json:"timestamp"`
}

func (s *SmartContract) StoreCompany(ctx contractapi.TransactionContextInterface, companyID string, companyName string, taxCode string, status string) error {
	record := CompanyRecord{
		CompanyID:   companyID,
		CompanyName: companyName,
		TaxCode:     taxCode,
		Status:      status,
	}

	recordBytes, err := json.Marshal(record)
	if err != nil {
		return err
	}

	return ctx.GetStub().PutState("COMPANY_"+companyID, recordBytes)
}

func (s *SmartContract) GetCompany(ctx contractapi.TransactionContextInterface, companyID string) (*CompanyRecord, error) {
	recordBytes, err := ctx.GetStub().GetState("COMPANY_"+companyID)
	if err != nil {
		return nil, fmt.Errorf("failed to read from world state: %v", err)
	}
	if recordBytes == nil {
		return nil, fmt.Errorf("company %s does not exist", companyID)
	}

	var record CompanyRecord
	err = json.Unmarshal(recordBytes, &record)
	if err != nil {
		return nil, err
	}

	return &record, nil
}

func (s *SmartContract) StoreUser(ctx contractapi.TransactionContextInterface, userID string, username string, companyID string, role string, status string) error {
	record := UserRecord{
		UserID:    userID,
		Username:  username,
		CompanyID: companyID,
		Role:      role,
		Status:    status,
	}

	recordBytes, err := json.Marshal(record)
	if err != nil {
		return err
	}

	return ctx.GetStub().PutState("USER_"+userID, recordBytes)
}

func (s *SmartContract) GetUser(ctx contractapi.TransactionContextInterface, userID string) (*UserRecord, error) {
	recordBytes, err := ctx.GetStub().GetState("USER_"+userID)
	if err != nil {
		return nil, fmt.Errorf("failed to read from world state: %v", err)
	}
	if recordBytes == nil {
		return nil, fmt.Errorf("user %s does not exist", userID)
	}

	var record UserRecord
	err = json.Unmarshal(recordBytes, &record)
	if err != nil {
		return nil, err
	}

	return &record, nil
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


func main() {
	cc, err := contractapi.NewChaincode(&SmartContract{})
	if err != nil {
		log.Panicf("error creating contract-verify chaincode: %v", err)
	}

	ccid := os.Getenv("CHAINCODE_ID")
	address := os.Getenv("CHAINCODE_SERVER_ADDRESS")

	if ccid != "" && address != "" {
		log.Printf("Starting Chaincode-as-a-Service server on %s with ID %s", address, ccid)
		server := &shim.ChaincodeServer{
			CCID:    ccid,
			Address: address,
			CC:      cc,
			TLSProps: shim.TLSProperties{
				Disabled: true,
			},
		}
		if err := server.Start(); err != nil {
			log.Panicf("error starting contract-verify chaincode server: %v", err)
		}
	} else {
		log.Printf("Starting standard chaincode...")
		if err := cc.Start(); err != nil {
			log.Panicf("error starting contract-verify chaincode: %v", err)
		}
	}
}
