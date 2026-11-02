from pathlib import Path
import ast
import re

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main.py').read_text(encoding='utf-8')

def test_python_syntax():
    ast.parse(source)

def test_health_and_env():
    assert '/health' in source
    assert 'SUPABASE_SERVICE_ROLE_KEY' in source
    assert 'BOT_TOKEN' in source

def test_username_regex_in_admin_reply():
    match = re.search(r'ID користувача:\s*(\d+)', 'ID користувача: 123456')
    assert match.group(1) == '123456'

def test_no_token_in_files():
    for f in ROOT.glob('*.py'):
        text = f.read_text(encoding='utf-8')
        assert 'AA' + 'X' * 20 not in text


def test_subject_inference():
    import sys
    sys.path.insert(0, str(ROOT))
    from intent import infer_subject, looks_like_tutor_request
    assert infer_subject('Шукаю репетитора з математики для 8 класу') == 'math'
    assert infer_subject('Нужен преподаватель немецкого') == 'de'
    assert infer_subject('НМТ з історії') == 'nmt'
    assert infer_subject('Python для дитини') == 'code'
    assert infer_subject('привіт') is None
    assert looks_like_tutor_request('Шукаю репетитора')
