package main

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

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
