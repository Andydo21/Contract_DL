"""Workflow database reads and transactional synchronization after Fabric confirmation."""
import hashlib
from django.db import connections, transaction


def signature_steps(version):
    with connections['workflow'].cursor() as cursor:
        cursor.execute('SELECT s.id,s.step_name,s.status,s.role_id FROM workflow_workflowstep s JOIN workflow_workflow w ON w.id=s.workflow_id WHERE w.version_id=%s AND s.requires_signature=TRUE ORDER BY s.step_order', [version.pk])
        return cursor.fetchall()


def signing_step(step_id):
    with connections['workflow'].cursor() as cursor:
        cursor.execute('SELECT s.role_id,s.status,w.version_id FROM workflow_workflowstep s JOIN workflow_workflow w ON w.id=s.workflow_id WHERE s.id=%s', [step_id])
        row=cursor.fetchone()
        cursor.execute("SELECT 1 FROM workflow_stepdependency d JOIN workflow_workflowstep p ON p.id=d.prerequisite_step_id WHERE d.dependent_step_id=%s AND p.status <> 'APPROVED' LIMIT 1", [step_id])
        return row, bool(cursor.fetchone())


def synchronize_confirmed_signature(op):
    with transaction.atomic(using='workflow'):
        with connections['workflow'].cursor() as c:
            c.execute('SELECT s.workflow_id, w.version_id FROM workflow_workflowstep s JOIN workflow_workflow w ON w.id=s.workflow_id WHERE s.id=%s FOR UPDATE OF s', [op.step_id])
            row = c.fetchone()
            if not row or row[1] != op.version_id:
                raise ValueError('Không thể đồng bộ bước ký sang workflow.')
            c.execute("UPDATE workflow_workflowstep SET status='APPROVED', completed_at=%s WHERE id=%s", [op.confirmed_at, op.step_id])
            c.execute("SELECT 1 FROM workflow_approval WHERE step_id=%s AND user_id=%s AND status='APPROVED'", [op.step_id, op.actor_id])
            if not c.fetchone():
                c.execute("INSERT INTO workflow_approval (step_id,user_id,status,comment,approved_at) VALUES (%s,%s,'APPROVED',%s,%s)", [op.step_id, op.actor_id, 'RSA verified; Fabric tx ' + op.tx_id, op.confirmed_at])
            # The signature itself, with the Fabric transaction that holds it (once per transaction).
            c.execute('SELECT 1 FROM workflow_digitalsignature WHERE step_id=%s AND user_id=%s AND tx_hash=%s', [op.step_id, op.actor_id, op.tx_id])
            if not c.fetchone():
                c.execute('INSERT INTO workflow_digitalsignature (step_id,user_id,signature_hash,signed_at,key_id,algorithm,block_hash,'
                          'block_number,tx_hash,verified,verified_at) VALUES (%s,%s,%s,%s,NULL,%s,%s,%s,%s,true,%s)',
                          [op.step_id, op.actor_id, hashlib.sha256(op.signature_base64.encode()).hexdigest(), op.accepted_at or op.confirmed_at,
                           'RSA-3072 PKCS#1 v1.5 SHA-256', op.block_hash, op.block_number, op.tx_id, op.confirmed_at])
            c.execute("SELECT count(*) FROM workflow_workflowstep WHERE workflow_id=%s AND status <> 'APPROVED'", [row[0]])
            complete = c.fetchone()[0] == 0
            c.execute('UPDATE workflow_workflow SET status=%s, completed_at=%s WHERE id=%s', ['COMPLETED' if complete else 'IN_PROGRESS', op.confirmed_at if complete else None, row[0]])
