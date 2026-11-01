-- Runs once, when the core Postgres volume is created. The web app also opens a 'workflow' connection
-- (WORKFLOW_DB_NAME, used by the ledger/workflow integration), so that database must exist.
CREATE DATABASE workflow_db;
