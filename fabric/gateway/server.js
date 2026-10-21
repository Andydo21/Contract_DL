const express = require('express');
const grpc = require('@grpc/grpc-js');
const { connect, signers } = require('@hyperledger/fabric-gateway');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const app = express();
app.use(express.json());
app.use((req, res, next) => {
    if (req.path === '/health') return next();
    const expected = process.env.FABRIC_GATEWAY_TOKEN || '';
    const supplied = req.get('X-Contract-Gateway-Token') || '';
    if (!expected || Buffer.byteLength(expected) !== Buffer.byteLength(supplied) ||
        !crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(supplied))) {
        return res.status(401).json({ error: 'Service authentication required' });
    }
    if (!req.path.startsWith('/enterprise/')) return res.status(410).json({ error: 'Legacy unsigned API retired' });
    next();
});

const PORT = process.env.PORT || 5000;

// Path to crypto materials
const mspRoot = path.resolve(__dirname, '..', 'crypto-config', 'peerOrganizations', 'org1.example.com');
const certPath = path.join(mspRoot, 'users', 'User1@org1.example.com', 'msp', 'signcerts', 'User1@org1.example.com-cert.pem');
const keyDirectoryPath = path.join(mspRoot, 'users', 'User1@org1.example.com', 'msp', 'keystore');
const tlsCertPath = path.join(mspRoot, 'peers', 'peer0.org1.example.com', 'tls', 'ca.crt');

const peerEndpoint = process.env.PEER_ENDPOINT || 'localhost:7051';
const channelName = process.env.CHANNEL_NAME || 'contracts-channel';
const chaincodeName = process.env.CHAINCODE_NAME || 'ContractVerifyChaincode';

let gateway;
let client;
let network;
let contract;

async function getIdentity() {
    const credentials = fs.readFileSync(certPath);
    return { mspId: 'Org1MSP', credentials };
}

async function getSigner() {
    const files = fs.readdirSync(keyDirectoryPath);
    const keyPath = path.join(keyDirectoryPath, files[0]);
    const privateKeyPem = fs.readFileSync(keyPath);
    const privateKey = crypto.createPrivateKey(privateKeyPem);
    return signers.newPrivateKeySigner(privateKey);
}

async function initGateway() {
    try {
        console.log('Initializing Fabric Gateway...');
        const tlsCACert = fs.readFileSync(tlsCertPath);
        const credentials = grpc.credentials.createSsl(tlsCACert);
        
        client = new grpc.Client(peerEndpoint, credentials, {
            'grpc.ssl_target_name_override': 'peer0.org1.example.com'
        });

        gateway = connect({
            client,
            identity: await getIdentity(),
            signer: await getSigner(),
            evaluateOptions: () => ({ deadline: Date.now() + 5000 }),
            submitOptions: () => ({ deadline: Date.now() + 5000 }),
            commitStatusOptions: () => ({ deadline: Date.now() + 60000 }),
        });

        network = gateway.getNetwork(channelName);
        contract = network.getContract(chaincodeName);
        console.log('Fabric Gateway connected successfully.');
    } catch (error) {
        console.error('Failed to initialize Fabric Gateway:', error);
    }
}

// Protobuf parser for common.Block to extract BlockHeader fields
function parseBlockBytes(blockBytes) {
    let offset = 0;

    if (blockBytes[offset] !== 0x0a) {
        throw new Error('Invalid block protobuf: expected field 1 (header) tag 0x0a');
    }
    offset++;

    let headerLen = 0;
    let shift = 0;
    while (true) {
        const b = blockBytes[offset++];
        headerLen |= (b & 0x7f) << shift;
        if (!(b & 0x80)) break;
        shift += 7;
    }

    const headerEnd = offset + headerLen;
    let number = 0n;
    let previousHash = null;
    let dataHash = null;

    while (offset < headerEnd) {
        const tag = blockBytes[offset++];
        const fieldNum = tag >> 3;
        const wireType = tag & 0x07;

        if (fieldNum === 1 && wireType === 0) {
            let val = 0n;
            let shift = 0n;
            while (true) {
                const b = blockBytes[offset++];
                val |= BigInt(b & 0x7f) << shift;
                if (!(b & 0x80)) break;
                shift += 7n;
            }
            number = val;
        } else if (fieldNum === 2 && wireType === 2) {
            let len = 0;
            let shift = 0;
            while (true) {
                const b = blockBytes[offset++];
                len |= (b & 0x7f) << shift;
                if (!(b & 0x80)) break;
                shift += 7;
            }
            previousHash = blockBytes.subarray(offset, offset + len);
            offset += len;
        } else if (fieldNum === 3 && wireType === 2) {
            let len = 0;
            let shift = 0;
            while (true) {
                const b = blockBytes[offset++];
                len |= (b & 0x7f) << shift;
                if (!(b & 0x80)) break;
                shift += 7;
            }
            dataHash = blockBytes.subarray(offset, offset + len);
            offset += len;
        } else {
            if (wireType === 0) {
                while (blockBytes[offset++] & 0x80);
            } else if (wireType === 2) {
                let len = 0;
                let shift = 0;
                while (true) {
                    const b = blockBytes[offset++];
                    len |= (b & 0x7f) << shift;
                    if (!(b & 0x80)) break;
                    shift += 7;
                }
                offset += len;
            } else if (wireType === 1) {
                offset += 8;
            } else if (wireType === 5) {
                offset += 4;
            } else {
                throw new Error(`Unsupported wire type ${wireType}`);
            }
        }
    }

    return { number, previousHash, dataHash };
}

// ASN.1 DER Encoder for BlockHeader
function encodeBlockHeader(number, previousHash, dataHash) {
    let numHex = BigInt(number).toString(16);
    if (numHex.length % 2 !== 0) numHex = '0' + numHex;
    let numBuf = Buffer.from(numHex, 'hex');
    if (numBuf[0] & 0x80) {
        numBuf = Buffer.concat([Buffer.from([0x00]), numBuf]);
    }
    const intTag = Buffer.from([0x02, numBuf.length]);
    const intEncoded = Buffer.concat([intTag, numBuf]);

    const prevHashBuf = Buffer.isBuffer(previousHash) ? previousHash : Buffer.from(previousHash, 'hex');
    const prevHashTag = Buffer.from([0x04, prevHashBuf.length]);
    const prevHashEncoded = Buffer.concat([prevHashTag, prevHashBuf]);

    const dataHashBuf = Buffer.isBuffer(dataHash) ? dataHash : Buffer.from(dataHash, 'hex');
    const dataHashTag = Buffer.from([0x04, dataHashBuf.length]);
    const dataHashEncoded = Buffer.concat([dataHashTag, dataHashBuf]);

    const body = Buffer.concat([intEncoded, prevHashEncoded, dataHashEncoded]);
    
    let lenBuf;
    if (body.length < 128) {
        lenBuf = Buffer.from([body.length]);
    } else {
        let lenHex = body.length.toString(16);
        if (lenHex.length % 2 !== 0) lenHex = '0' + lenHex;
        const lenBytes = Buffer.from(lenHex, 'hex');
        lenBuf = Buffer.concat([Buffer.from([0x80 | lenBytes.length]), lenBytes]);
    }

    return Buffer.concat([Buffer.from([0x30]), lenBuf, body]);
}

async function getBlockInfoByTxId(txId) {
    const qsccContract = network.getContract('qscc');
    const blockBytes = await qsccContract.evaluateTransaction('GetBlockByTxID', channelName, txId);
    const parsed = parseBlockBytes(blockBytes);
    const headerEncoded = encodeBlockHeader(parsed.number, parsed.previousHash, parsed.dataHash);
    const blockHash = crypto.createHash('sha256').update(headerEncoded).digest('hex');
    return {
        blockNumber: Number(parsed.number),
        blockHash: blockHash
    };
}

// REST API Endpoints

app.post('/anchor', async (req, res) => {
    try {
        const { proofId, documentHash, merkleRoot } = req.body;
        if (!proofId || !documentHash || !merkleRoot) {
            return res.status(400).json({ error: 'proofId, documentHash, and merkleRoot are required' });
        }

        if (!contract) {
            return res.status(503).json({ error: 'Fabric Gateway not initialized' });
        }

        const timestamp = new Date().toISOString();
        console.log(`Submitting StoreHash for proof ${proofId}...`);
        
        const commit = await contract.submitAsync('StoreHash', {
            arguments: [String(proofId), documentHash, merkleRoot, timestamp]
        });
        console.log(`Transaction submitted to orderer.`);

        // Wait for commit status to be committed by the peers
        const status = await commit.getStatus();
        if (!status.successful) {
            throw new Error(`Transaction validation failed with code: ${status.code}`);
        }
        const txId = status.transactionId;

        console.log(`Transaction ${txId} committed. Querying block info...`);

        // Fetch real block info (including block hash) from the ledger via QSCC using the TxID
        const blockInfo = await getBlockInfoByTxId(txId);
        console.log(`Retrieved real block hash for block ${blockInfo.blockNumber}: ${blockInfo.blockHash}`);
        
        // Return transaction details
        res.json({
            status: 'CONFIRMED',
            tx_hash: txId,
            block_number: blockInfo.blockNumber,
            block_hash: blockInfo.blockHash,
            gas_fee: 0.0,
            latency: 1.2
        });
    } catch (error) {
        console.error('Error anchoring proof:', error);
        res.status(500).json({ error: error.message });
    }
});

app.post('/verify', async (req, res) => {
    try {
        const { version_id } = req.body; // Map version_id to proofId
        if (!version_id) {
            return res.status(400).json({ error: 'version_id is required' });
        }

        if (!contract) {
            return res.status(503).json({ error: 'Fabric Gateway not initialized' });
        }

        console.log(`Evaluating GetHash for proof ${version_id}...`);
        const resultBytes = await contract.evaluateTransaction('GetHash', String(version_id));
        const record = JSON.parse(Buffer.from(resultBytes).toString());
        const historyBytes = await contract.evaluateTransaction('GetHistory', String(version_id));
        const history = JSON.parse(Buffer.from(historyBytes).toString()) || [];
        const anchors = [];
        for (const entry of history.filter(item => !item.isDelete)) {
            const block = await getBlockInfoByTxId(entry.txId);
            anchors.push({ network: 'Hyperledger Fabric', tx_hash: entry.txId,
                block_number: block.blockNumber, block_hash: block.blockHash,
                created_at: entry.timestamp });
        }

        res.json({
            verified: true,
            proof_hash: record.documentHash,
            blockchain_anchored: true,
            anchors
        });
    } catch (error) {
        console.error('Error verifying proof:', error);
        // If it does not exist, return not found
        if (error.message.includes('does not exist')) {
            return res.json({
                verified: false,
                message: 'No hash proof found on ledger.'
            });
        }
        res.status(500).json({ error: error.message });
    }
});

app.get('/history/:proofId', async (req, res) => {
    try {
        const { proofId } = req.params;
        if (!contract) {
            return res.status(503).json({ error: 'Fabric Gateway not initialized' });
        }

        console.log(`Evaluating GetHistory for proof ${proofId}...`);
        const resultBytes = await contract.evaluateTransaction('GetHistory', String(proofId));
        const history = JSON.parse(Buffer.from(resultBytes).toString());

        res.json({ history });
    } catch (error) {
        console.error('Error fetching history:', error);
        res.status(500).json({ error: error.message });
    }
});

app.post('/company/store', async (req, res) => {
    try {
        const { companyId, companyName, taxCode, status: companyStatus } = req.body;
        if (!companyId || !companyName || !taxCode) {
            return res.status(400).json({ error: 'companyId, companyName, and taxCode are required' });
        }

        if (!contract) {
            return res.status(503).json({ error: 'Fabric Gateway not initialized' });
        }

        const finalStatus = companyStatus || 'ACTIVE';
        console.log(`Submitting StoreCompany for company ${companyId}...`);
        
        const commit = await contract.submitAsync('StoreCompany', {
            arguments: [String(companyId), companyName, taxCode, finalStatus]
        });
        console.log(`Transaction submitted to orderer.`);

        const status = await commit.getStatus();
        if (!status.successful) {
            throw new Error(`Transaction validation failed with code: ${status.code}`);
        }
        const txId = status.transactionId;

        console.log(`StoreCompany transaction ${txId} committed. Querying block info...`);
        const blockInfo = await getBlockInfoByTxId(txId);
        
        res.json({
            status: 'CONFIRMED',
            tx_hash: txId,
            block_number: blockInfo.blockNumber,
            block_hash: blockInfo.blockHash,
            gas_fee: 0.0,
            latency: 1.2
        });
    } catch (error) {
        console.error('Error storing company:', error);
        res.status(500).json({ error: error.message });
    }
});

app.post('/user/store', async (req, res) => {
    try {
        const { userId, username, companyId, role, status: userStatus } = req.body;
        if (!userId || !username || !companyId || !role) {
            return res.status(400).json({ error: 'userId, username, companyId, and role are required' });
        }

        if (!contract) {
            return res.status(503).json({ error: 'Fabric Gateway not initialized' });
        }

        const finalStatus = userStatus || 'ACTIVE';
        console.log(`Submitting StoreUser for user ${userId}...`);
        
        const commit = await contract.submitAsync('StoreUser', {
            arguments: [String(userId), username, String(companyId), role, finalStatus]
        });
        console.log(`Transaction submitted to orderer.`);

        const status = await commit.getStatus();
        if (!status.successful) {
            throw new Error(`Transaction validation failed with code: ${status.code}`);
        }
        const txId = status.transactionId;

        console.log(`StoreUser transaction ${txId} committed. Querying block info...`);
        const blockInfo = await getBlockInfoByTxId(txId);
        
        res.json({
            status: 'CONFIRMED',
            tx_hash: txId,
            block_number: blockInfo.blockNumber,
            block_hash: blockInfo.blockHash,
            gas_fee: 0.0,
            latency: 1.2
        });
    } catch (error) {
        console.error('Error storing user:', error);
        res.status(500).json({ error: error.message });
    }
});

app.post('/signature/store', async (req, res) => {
    try {
        const { signatureId, stepId, userId, certificateSerial, signatureHash } = req.body;
        if (!signatureId || !stepId || !userId || !certificateSerial || !signatureHash) {
            return res.status(400).json({ error: 'signatureId, stepId, userId, certificateSerial, and signatureHash are required' });
        }

        if (!contract) {
            return res.status(503).json({ error: 'Fabric Gateway not initialized' });
        }

        const timestamp = new Date().toISOString();
        console.log(`Submitting StoreSignature for signature ${signatureId}...`);
        
        const commit = await contract.submitAsync('StoreSignature', {
            arguments: [String(signatureId), String(stepId), String(userId), certificateSerial, signatureHash, timestamp]
        });
        console.log(`Transaction submitted to orderer.`);

        const status = await commit.getStatus();
        if (!status.successful) {
            throw new Error(`Transaction validation failed with code: ${status.code}`);
        }
        const txId = status.transactionId;

        console.log(`StoreSignature transaction ${txId} committed. Querying block info...`);
        const blockInfo = await getBlockInfoByTxId(txId);
        
        res.json({
            status: 'CONFIRMED',
            tx_hash: txId,
            block_number: blockInfo.blockNumber,
            block_hash: blockInfo.blockHash,
            gas_fee: 0.0,
            latency: 1.2
        });
    } catch (error) {
        console.error('Error storing signature:', error);
        res.status(500).json({ error: error.message });
    }
});

app.get('/user/:id', async (req, res) => {
    try {
        const { id } = req.params;
        if (!contract) {
            return res.status(503).json({ error: 'Fabric Gateway not initialized' });
        }
        
        console.log(`Querying GetUser for user ${id}...`);
        const resultBytes = await contract.evaluateTransaction('GetUser', String(id));
        const decodedStr = Buffer.from(resultBytes).toString('utf8');
        console.log("Decoded GetUser result:", decodedStr);
        const resultJson = JSON.parse(decodedStr);
        res.json(resultJson);
    } catch (error) {
        console.error('Error querying user:', error);
        res.status(500).json({ error: error.message });
    }
});

app.get('/signature/:id', async (req, res) => {
    try {
        const { id } = req.params;
        if (!contract) {
            return res.status(503).json({ error: 'Fabric Gateway not initialized' });
        }
        
        console.log(`Querying GetSignature for signature ${id}...`);
        const resultBytes = await contract.evaluateTransaction('GetSignature', String(id));
        const decodedStr = Buffer.from(resultBytes).toString('utf8');
        console.log("Decoded GetSignature result:", decodedStr);
        const resultJson = JSON.parse(decodedStr);
        res.json(resultJson);
    } catch (error) {
        console.error('Error querying signature:', error);
        res.status(500).json({ error: error.message });
    }
});

app.get('/health', async (req, res) => {
    try {
        if (!contract) throw new Error('Fabric Gateway not initialized');
        await contract.evaluateTransaction('HashExists', '__health_check__');
        res.json({ status: 'healthy', channel: channelName, chaincode: chaincodeName });
    } catch (error) {
        res.status(503).json({ status: 'disconnected', error: error.message });
    }
});

// Start Server
async function enterpriseRecord(id) {
    const bytes = await contract.evaluateTransaction('GetEnterpriseOperation', id);
    const record = JSON.parse(Buffer.from(bytes).toString());
    const block = await getBlockInfoByTxId(record.tx_id);
    return { ...record, block_number: block.blockNumber, block_hash: block.blockHash };
}

app.get('/enterprise/operations/:id', async (req, res) => {
    try {
        if (!contract) return res.status(503).json({ error: 'Gateway disconnected' });
        res.json(await enterpriseRecord(req.params.id));
    } catch (error) {
        res.status(error.message.includes('does not exist') ? 404 : 503).json({ error: error.message });
    }
});

app.post('/enterprise/commit', async (req, res) => {
    try {
        if (!contract) return res.status(503).json({ error: 'Gateway disconnected' });
        const raw = req.body.payload;
        if (typeof raw !== 'string') return res.status(400).json({ error: 'Payload string required' });
        const envelope = JSON.parse(raw);
        const manifest = JSON.parse(envelope.manifest);
        let existing;
        try { existing = await enterpriseRecord(manifest.operation_id); }
        catch (error) { if (!error.message.includes('does not exist')) throw error; }
        if (existing) {
            if (existing.payload !== raw) return res.status(409).json({ error: 'Idempotency payload conflict' });
            return res.json(existing);
        }
        const commit = await contract.submitAsync('CommitEnterpriseOperation', { arguments: [raw] });
        const status = await commit.getStatus();
        if (!status.successful) throw new Error('Transaction rejected: ' + status.code);
        res.json(await enterpriseRecord(manifest.operation_id));
    } catch (error) {
        res.status(503).json({ error: error.message });
    }
});

initGateway().then(() => {
    app.listen(PORT, () => {
        console.log(`Fabric Gateway REST API listening on port ${PORT}`);
    });
});
