package main

import (
	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// HashExists is the gateway's health probe: a read that reaches the chaincode and the world state.
func (s *SmartContract) HashExists(ctx contractapi.TransactionContextInterface, proofID string) (bool, error) {
	recordBytes, err := ctx.GetStub().GetState(proofID)
	if err != nil {
		return false, err
	}
	return recordBytes != nil, nil
}
