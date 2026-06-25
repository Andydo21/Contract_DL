#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE identity_db;
    CREATE DATABASE contract_db;
    CREATE DATABASE workflow_db;
    CREATE DATABASE blockchain_db;
    CREATE DATABASE ai_db;
EOSQL
