package main

import (
	"encoding/json"
	"fmt"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

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

func (s *SmartContract) StoreCompany(ctx contractapi.TransactionContextInterface, companyID string, companyName string, taxCode string, status string) error {
	return fmt.Errorf("legacy unsigned writes disabled; use CommitEnterpriseOperation")
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
	return fmt.Errorf("legacy unsigned writes disabled; use CommitEnterpriseOperation")
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
