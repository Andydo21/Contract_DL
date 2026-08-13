import os
import hashlib
import difflib

def get_file_hash(file_path):
    hasher = hashlib.sha256()
    try:
        if os.path.getsize(file_path) > 5 * 1024 * 1024:
            return None
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None

def compare_directories(dir_a, dir_b):
    ignore_dirs = {
        'Contract_DL-AI_summery', '.git', 'venv', 'scratch', 
        '__pycache__', '.idea', '.vscode', '.ipynb_checkpoints',
        'media', 'node_modules', 'crypto-config'
    }
    
    ignore_files = {
        'Bao_Cao_He_Thong_Quan_Ly_Hop_Dong_AI.docx',
        'Bao_Cao_Ky_Thuat_Ba_Model_AI_Chi_Tiet.docx',
        'Bao_Cao_Ky_Thuat_Blockchain_Integration_Chi_Tiet.docx',
        'Bao_Cao_Ky_Thuat_Hai_Model_AI.docx',
        'Bao_Cao_Ky_Thuat_Hai_Model_AI_Hoan_Chinh.docx',
        'ClauseExtractedModelAndAISearch.docx',
        'Risk_Analysis.docx',
        'contracts-channel.block',
        'package_id.txt',
        'code.tar.gz',
        'contract_verify.tar.gz',
        'log.txt',
        'avatar.jpg',
        'avatar.png',
        'adventure-works-2008r2-oltp.bak',
        'AdventureWorks2008R2.mdf',
        'AdventureWorks2008R2_log.ldf'
    }

    diff_files = []
    only_in_a = []
    only_in_b = []

    def should_ignore(rel_path):
        parts = rel_path.split(os.sep)
        for part in parts:
            if part in ignore_dirs or part in ignore_files:
                return True
        filename = parts[-1]
        if filename.endswith('.pyc') or filename.endswith('.log') or filename.endswith('.db') or filename.endswith('.sqlite3'):
            return True
        if filename.endswith('.ipynb') or filename.endswith('.jsonl') or filename.endswith('.docx') or filename.endswith('.zip') or filename.endswith('.pdf'):
            return True
        return False

    # Walk through dir_a
    for root, dirs, files in os.walk(dir_a):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            full_path_a = os.path.join(root, file)
            rel_path = os.path.relpath(full_path_a, dir_a)
            
            if should_ignore(rel_path):
                continue
            
            path_b = os.path.join(dir_b, rel_path)
            
            if not os.path.exists(path_b):
                only_in_a.append(rel_path)
            else:
                hash_a = get_file_hash(full_path_a)
                hash_b = get_file_hash(path_b)
                if hash_a and hash_b and hash_a != hash_b:
                    diff_files.append(rel_path)

    # Walk through dir_b
    for root, dirs, files in os.walk(dir_b):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            full_path_b = os.path.join(root, file)
            rel_path = os.path.relpath(full_path_b, dir_b)
            
            if should_ignore(rel_path):
                continue
            
            path_a = os.path.join(dir_a, rel_path)
            if not os.path.exists(path_a):
                only_in_b.append(rel_path)

    return only_in_a, only_in_b, diff_files

if __name__ == '__main__':
    dir_inner = r"d:\Django_project\RiskDL\Contract_DL-AI_summery"
    dir_outer = r"d:\Django_project\RiskDL"
    
    only_in_inner, only_in_outer, diff_files = compare_directories(dir_inner, dir_outer)
    
    print("=== FILES ONLY IN INNER (Contract_DL-AI_summery) ===")
    for f in sorted(only_in_inner):
        print(f"  - {f}")
        
    print("\n=== FILES ONLY IN OUTER (RiskDL) ===")
    for f in sorted(only_in_outer):
        print(f"  - {f}")
        
    print("\n=== DIFFERENT CONTENT ===")
    for f in sorted(diff_files):
        print(f"  - {f}")
        
    # Print unified diff for a few key files to understand differences
    key_files = ['docker-compose.yml', 'contracts/views.py', 'contracts/models.py']
    for kf in key_files:
        path_inner = os.path.join(dir_inner, kf)
        path_outer = os.path.join(dir_outer, kf)
        if os.path.exists(path_inner) and os.path.exists(path_outer):
            print(f"\n=================== DIFF FOR: {kf} ===================")
            with open(path_inner, 'r', encoding='utf-8', errors='ignore') as f1, \
                 open(path_outer, 'r', encoding='utf-8', errors='ignore') as f2:
                diff = difflib.unified_diff(
                    f1.readlines(), f2.readlines(),
                    fromfile=f'inner/{kf}', tofile=f'outer/{kf}',
                    n=2
                )
                print(''.join(list(diff)[:20])) # show first 20 lines of diff
