import os
import difflib

dir_inner = r"d:\Django_project\RiskDL\Contract_DL-AI_summery"
dir_outer = r"d:\Django_project\RiskDL"

different_files = [
    "Dockerfile",
    "ai_service\\Dockerfile",
    "ai_service\\kaggle_server.py",
    "ai_service\\main.py",
    "ai_service\\requirements.txt",
    "blockchain_service\\Dockerfile",
    "blockchain_service\\blockchain\\__init__.py",
    "blockchain_service\\blockchain\\apps.py",
    "blockchain_service\\blockchain\\migrations\0001_initial.py",
    "blockchain_service\\config\\settings.py",
    "blockchain_service\\config\\urls.py",
    "blockchain_service\\config\\wsgi.py",
    "blockchain_service\\manage.py",
    "blockchain_service\\requirements.txt",
    "config\\settings.py",
    "config\\urls.py",
    "contracts\\admin.py",
    "contracts\\migrations\\0001_initial.py",
    "contracts\\migrations\\0002_company_permission_tag_clause_clause_type_and_more.py",
    "contracts\\migrations\\0003_blockchainnetwork_blockchainnode_and_more.py",
    "contracts\\migrations\\0004_remove_blockchainnode_network_and_more.py",
    "contracts\\migrations\\0005_remove_digitalsignature_key_and_more.py",
    "contracts\\migrations\\0006_riskfinding_disadvantaged_party.py",
    "contracts\\models.py",
    "contracts\\repositories.py",
    "contracts\\services.py",
    "contracts\\static\\contracts\\css\\contract_detail.css",
    "contracts\static\\contracts\\css\\dashboard.css",
    "contracts\\static\\contracts\\js\\analysis_history.js",
    "contracts\\static\\contracts\\js\\contract_detail.js",
    "contracts\\static\\contracts\\js\\dashboard.js",
    "contracts\\templates\\contracts\\contract_detail.html",
    "contracts\\templates\\contracts\dashboard.html",
    "contracts\\templates\\contracts\\developer_test.html",
    "contracts\\templates\\contracts\\identity_registry.html",
    "contracts\\urls.py",
    "contracts\\views.py",
    "db-init\\init-databases.sh",
    "docker-compose.yml",
    "gateway\\nginx.conf",
    "requirements.txt",
    "workflow_service\\Dockerfile",
    "workflow_service\\config\\settings.py",
    "workflow_service\\config\\urls.py",
    "workflow_service\\config\\wsgi.py",
    "workflow_service\\manage.py",
    "workflow_service\\requirements.txt",
    "workflow_service\\workflow\\apps.py",
    "workflow_service\\workflow\\migrations\\0001_initial.py",
    "workflow_service\\workflow\\models.py"
]

report_path = r"d:\Django_project\RiskDL\scratch\diff_report.txt"

with open(report_path, 'w', encoding='utf-8') as report:
    for f in different_files:
        path_inner = os.path.join(dir_inner, f)
        path_outer = os.path.join(dir_outer, f)
        if os.path.exists(path_inner) and os.path.exists(path_outer):
            with open(path_inner, 'r', encoding='utf-8', errors='ignore') as fi, \
                 open(path_outer, 'r', encoding='utf-8', errors='ignore') as fo:
                inner_lines = fi.readlines()
                outer_lines = fo.readlines()
                
                diff = list(difflib.unified_diff(
                    inner_lines, outer_lines,
                    fromfile=f'inner/{f}', tofile=f'outer/{f}',
                    n=1
                ))
                
                if diff:
                    report.write(f"\n=================== DIFF FOR: {f} ===================\n")
                    report.write(''.join(diff))

print(f"[SUCCESS] Generated diff report at: {report_path}")
