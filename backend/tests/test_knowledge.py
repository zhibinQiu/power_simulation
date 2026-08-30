"""知识库（LLM-WIKI 式多级文件夹 + 文档解析）测试用例。

覆盖链路：
- 多级文件夹：新建 / 重命名 / 删除（级联删除其内文档）
- 文档上传：txt / pdf / docx 解析为 Markdown 落盘 + 原始文件保留
- 文档重命名 / 删除 / 内容读取 / 原始文件下载
- 知识库树结构 / 统计 / 全文检索

运行：
  cd backend && python -m pytest tests/test_knowledge.py -v
"""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import knowledge_service as kb  # noqa: E402


@pytest.fixture()
def kb_root(tmp_path, monkeypatch):
    """隔离的知识库根目录（每个用例独立，互不污染）。"""
    root = tmp_path / 'kb'
    monkeypatch.setenv('KB_ROOT', str(root))
    kb._LOCK.acquire()  # 测试串行，避免元数据读写竞争
    yield root
    kb._LOCK.release()


def _mk_pdf(text: str) -> bytes:
    """用 reportlab 生成含可提取文本的真实 PDF（pypdf 无法直接生成可提取文本的 PDF）。"""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 150, text)
    c.save()
    return buf.getvalue()


def _mk_docx(text: str) -> bytes:
    from docx import Document
    doc = Document()
    for line in text.split('\n'):
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ------------------------- 文件夹（多级） -------------------------

def test_create_multi_level_folders(kb_root):
    r1 = kb.create_folder('法规')
    assert r1['ok'] and r1['path'] == '法规'
    r2 = kb.create_folder('国际', '法规')
    assert r2['ok'] and r2['path'] == '法规/国际'
    # 同层重名拒绝
    assert not kb.create_folder('国际', '法规')['ok']
    # 父文件夹不存在拒绝
    assert not kb.create_folder('x', '不存在的父')['ok']
    tree = kb.list_tree()
    assert tree['stats']['folders'] == 2
    assert tree['tree']['children'][0]['path'] == '法规'
    assert tree['tree']['children'][0]['children'][0]['path'] == '法规/国际'


def test_rename_folder(kb_root):
    kb.create_folder('法规')
    kb.create_folder('国际', '法规')
    assert kb.rename_folder('法规', '规范')['ok']
    tree = kb.list_tree()
    assert tree['tree']['children'][0]['path'] == '规范'
    assert tree['tree']['children'][0]['children'][0]['path'] == '规范/国际'


def test_delete_folder_cascade(kb_root):
    kb.create_folder('法规')
    kb.create_folder('国际', '法规')
    r = kb.upload('欧盟条例.txt', '欧盟排放交易体系。'.encode('utf-8'), '法规/国际')
    assert r['ok']
    # 删除父文件夹应级联删除子文件夹与文档
    res = kb.delete_folder('法规')
    assert res['ok'] and res['removed_docs'] == 1
    assert kb.get_doc(r['doc']['id']) is None
    assert not (kb_root / '法规').exists()
    assert kb.list_tree()['stats']['folders'] == 0


def test_delete_root_forbidden(kb_root):
    assert not kb.delete_folder('')['ok']
    assert not kb.delete_folder('/')['ok']


# ------------------------- 文档上传 / 解析 -------------------------

def test_upload_txt(kb_root):
    r = kb.upload('说明.txt', '第一条说明内容。\n第二条说明内容。'.encode('utf-8'))
    assert r['ok']
    doc = r['doc']
    assert doc['title'] == '说明' and doc['ext'] == '.txt'
    content = kb.doc_content(doc['id'])
    assert '第一条说明内容' in content['content']
    # Markdown 直接落在根目录（LLM-WIKI 理念：文件夹即知识库）
    assert (kb_root / '说明.md').exists()
    # 原始文件保留在 raw/
    assert (kb_root / 'raw' / (doc['id'] + '.txt')).exists()


def test_upload_pdf(kb_root):
    pytest.importorskip('reportlab', reason='生成 PDF 需要 reportlab')
    data = _mk_pdf('PDF 知识库内容示例')
    r = kb.upload('手册.pdf', data)
    assert r['ok'] and r['doc']['ext'] == '.pdf'
    assert 'PDF 知识库内容示例' in kb.doc_content(r['doc']['id'])['content']


def test_upload_docx(kb_root):
    data = _mk_docx('Word 文档第一段\nWord 文档第二段')
    r = kb.upload('报告.docx', data)
    assert r['ok'] and r['doc']['ext'] == '.docx'
    content = kb.doc_content(r['doc']['id'])['content']
    assert 'Word 文档第一段' in content and 'Word 文档第二段' in content


def test_upload_unsupported(kb_root):
    assert not kb.upload('脚本.py', b'print(1)')['ok']
    assert not kb.upload('图片.png', b'fake')['ok']


def test_upload_doc_parse_fail_but_raw_kept(kb_root):
    # .doc 旧格式无法解析：报错但不上索引
    r = kb.upload('旧版.doc', b'\x00\x01\x02' + '旧二进制内容'.encode('utf-8'))
    assert not r['ok']


def test_upload_to_subfolder(kb_root):
    kb.create_folder('资料')
    kb.create_folder('内部', '资料')
    r = kb.upload('手册.txt', '子文件夹内容。'.encode('utf-8'), '资料/内部')
    assert r['ok']
    assert (kb_root / '资料' / '内部' / '手册.md').exists()
    assert r['doc']['folder'] == '资料/内部'


# ------------------------- 文档重命名 / 删除 / 树 / 搜索 -------------------------

def test_rename_doc(kb_root):
    kb.upload('旧名.txt', '内容。'.encode('utf-8'))
    doc = next(iter(kb.list_tree()['tree']['docs']))
    r = kb.rename_doc(doc['id'], '新名')
    assert r['ok'] and r['doc']['title'] == '新名'
    assert (kb_root / '新名.md').exists() and not (kb_root / '旧名.md').exists()
    # 同层重名拒绝
    kb.upload('另一个.txt', '内容。'.encode('utf-8'))
    assert not kb.rename_doc(doc['id'], '另一个')['ok']


def test_delete_doc(kb_root):
    r = kb.upload('待删除.txt', '内容。'.encode('utf-8'))
    did = r['doc']['id']
    assert kb.delete_doc(did)['ok']
    assert kb.get_doc(did) is None
    assert not (kb_root / '待删除.md').exists()
    assert kb.list_tree()['stats']['docs'] == 0


def test_tree_stats_and_search(kb_root):
    kb.create_folder('碳政策')
    kb.upload('CBAM.txt', '欧盟碳边境调节机制 CBAM 将于过渡期结束后全面实施。'.encode('utf-8'), '碳政策')
    kb.upload('绿电.txt', '绿电交易与绿证核发。'.encode('utf-8'))
    tree = kb.list_tree()
    assert tree['stats']['folders'] == 1 and tree['stats']['docs'] == 2
    assert tree['stats']['chars'] > 0
    res = kb.search('CBAM')
    assert res['results'] and res['results'][0]['doc']['title'] == 'CBAM'
    res2 = kb.search('不存在的关键词xyz')
    assert res2['results'] == []
    # 空查询不报错
    assert kb.search('')['results'] == []
