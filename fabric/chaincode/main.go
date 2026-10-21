package main

import (
	"log"
	"os"

	"github.com/hyperledger/fabric-chaincode-go/shim"
	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type SmartContract struct {
	contractapi.Contract
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
