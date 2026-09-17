"""QaManagementRepository の単体テスト（実装指示書 IMPL-202608060837 8.1 / T5）。

SQL を部分一致で解釈するインメモリ Fake DB を用い、create_qa / update_qa / get_qa /
list_qa のロジック（必須項目検証、存在しない category/tag の検出、question_text 変更時の
is_primary 行のみ再計算、tag_ids の None/[] 区別、ページング）を DB 非依存で検証する。
"""

import os
import sys
from contextlib import contextmanager

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from knowledge_mcp.repository.qa_management_repository import QaManagementRepository
from knowledge_mcp.models.qa import QaError


# --------------------------------------------------------------------------- #
# インメモリ Fake DB
# --------------------------------------------------------------------------- #
class FakeCursor:
    def __init__(self, s):
        self.s = s
        self._result = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        q = " ".join(sql.split())
        p = params or ()
        self._result = []
        self.rowcount = 0

        if q.startswith("INSERT INTO hiroba_qa_original"):
            uuid, question_text, answer_text, category_id, title, is_searchable = p
            self.s["qa"][uuid] = {
                "question_text": question_text,
                "answer_text": answer_text,
                "category_id": category_id,
                "title": title,
                "is_searchable": is_searchable,
            }
            return
        if q.startswith("INSERT INTO hiroba_question_altered"):
            qa_id, text, _emb = p
            self.s["altered"].append(
                {"qa_id": qa_id, "text": text, "is_primary": True}
            )
            return
        if q.startswith("DELETE FROM hiroba_qa_tag"):
            qa_id = p[0]
            self.s["qa_tag"] = {t for t in self.s["qa_tag"] if t[0] != qa_id}
            return
        if q.startswith("DELETE FROM hiroba_question_altered"):
            qa_id = p[0]
            self.s["altered"] = [a for a in self.s["altered"] if a["qa_id"] != qa_id]
            return
        if q.startswith("DELETE FROM hiroba_qa_original"):
            self.s["qa"].pop(p[0], None)
            return
        if q.startswith("UPDATE hiroba_qa_original"):
            cols = [
                c
                for c in (
                    "title",
                    "question_text",
                    "answer_text",
                    "category_id",
                    "is_searchable",
                )
                if f"{c} = %s" in q
            ]
            uuid = p[-1]
            for i, c in enumerate(cols):
                self.s["qa"][uuid][c] = p[i]
            return
        if q.startswith("UPDATE hiroba_question_altered"):
            text, _emb, qa_id = p
            n = 0
            for a in self.s["altered"]:
                if a["qa_id"] == qa_id and a["is_primary"]:
                    a["text"] = text
                    n += 1
            self.rowcount = n
            return

        # --- 参照系 --- #
        if "FROM hiroba_category WHERE id = %s" in q:
            self._result = [(1,)] if p[0] in self.s["categories"] else []
        elif "SELECT id FROM tag WHERE id = ANY(%s)" in q:
            wanted = set(p[0])
            self._result = [(tid,) for tid in self.s["tags"] if tid in wanted]
        elif "FROM hiroba_category ORDER BY id" in q:
            self._result = [
                (cid, name) for cid, name in sorted(self.s["categories"].items())
            ]
        elif "COUNT(*) FROM hiroba_question_altered WHERE qa_id = %s" in q:
            self._result = [
                (sum(1 for a in self.s["altered"] if a["qa_id"] == p[0]),)
            ]
        elif "COUNT(*) FROM hiroba_qa_original" in q:
            self._result = [(len(self.s["qa"]),)]
        elif "array_agg" in q:
            # list_qa の一覧SELECT。フィルタは割愛し、全件を uuid 順にページングする。
            limit, offset = p[-2], p[-1]
            rows = []
            for uuid, r in sorted(self.s["qa"].items()):
                tags = sorted(
                    self.s["tags"][tid]
                    for (qid, tid) in self.s["qa_tag"]
                    if qid == uuid
                )
                cnt = sum(1 for a in self.s["altered"] if a["qa_id"] == uuid)
                cname = (
                    self.s["categories"].get(r["category_id"])
                    if r["category_id"] is not None
                    else None
                )
                rows.append((uuid, r["title"], cname, tags, cnt, r["is_searchable"]))
            self._result = rows[offset : offset + limit]
        elif "FROM hiroba_qa_tag JOIN tag" in q:
            qa_id = p[0]
            self._result = sorted(
                (
                    (tid, self.s["tags"][tid])
                    for (qid, tid) in self.s["qa_tag"]
                    if qid == qa_id
                ),
                key=lambda r: r[1],
            )
        elif "WHERE hiroba_qa_original.uuid = %s" in q:
            uuid = p[0]
            if uuid in self.s["qa"]:
                r = self.s["qa"][uuid]
                cid = r["category_id"]
                cname = self.s["categories"].get(cid) if cid is not None else None
                self._result = [
                    (
                        uuid,
                        r["title"],
                        r["question_text"],
                        r["answer_text"],
                        cid,
                        cname,
                        r["is_searchable"],
                    )
                ]

    def executemany(self, sql, seq):
        q = " ".join(sql.split())
        if q.startswith("INSERT INTO hiroba_qa_tag"):
            for qa_id, tag_id in seq:
                self.s["qa_tag"].add((qa_id, tag_id))

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


class FakeDB:
    def __init__(self):
        self.s = {
            "qa": {},
            "altered": [],
            "qa_tag": set(),
            "categories": {1: "カテゴリA", 3: "積算"},
            "tags": {12: "操作方法", 3: "積算システム"},
        }

    @contextmanager
    def cursor(self):
        yield FakeCursor(self.s)


class EmbedSpy:
    def __init__(self):
        self.calls = []

    def __call__(self, text):
        self.calls.append(text)
        return [0.1, 0.2, 0.3]


@pytest.fixture
def embed():
    return EmbedSpy()


@pytest.fixture
def repo(embed):
    return QaManagementRepository(FakeDB(), embed)


# --------------------------------------------------------------------------- #
# create_qa
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field", ["title", "question_text", "answer_text"])
def test_create_qa_requires_fields(repo, field):
    kwargs = {"title": "t", "question_text": "q", "answer_text": "a"}
    kwargs[field] = ""
    with pytest.raises(QaError):
        repo.create_qa(**kwargs)


def test_create_qa_missing_category_rejected(repo):
    with pytest.raises(QaError):
        repo.create_qa("t", "q", "a", category_id=999)


def test_create_qa_missing_tag_rejected(repo):
    with pytest.raises(QaError):
        repo.create_qa("t", "q", "a", tag_ids=[999])


def test_create_qa_happy_path(repo, embed):
    detail = repo.create_qa("題", "質問", "回答", category_id=3, tag_ids=[12, 3])
    assert detail.title == "題"
    assert detail.question_text == "質問"
    assert detail.category == {"id": 3, "name": "積算"}
    assert {t["id"] for t in detail.tags} == {12, 3}
    # 主となる question_altered が1件生成され、embedding が計算されている
    assert detail.hiroba_question_altered_count == 1
    assert embed.calls == ["質問"]
    assert repo.db.s["altered"][0]["is_primary"] is True


# --------------------------------------------------------------------------- #
# get_qa
# --------------------------------------------------------------------------- #
def test_get_qa_not_found(repo):
    with pytest.raises(QaError):
        repo.get_qa("nope")


# --------------------------------------------------------------------------- #
# update_qa
# --------------------------------------------------------------------------- #
def test_update_qa_question_text_recomputes_only_primary(repo, embed):
    detail = repo.create_qa("t", "q", "a")
    qa_id = detail.id
    # 既存パラフレーズ行（is_primary=false）を混在させる
    repo.db.s["altered"].append({"qa_id": qa_id, "text": "paraphrase", "is_primary": False})
    embed.calls.clear()

    repo.update_qa(qa_id, question_text="new-q")
    assert embed.calls == ["new-q"]
    primary = [a for a in repo.db.s["altered"] if a["is_primary"]]
    paraphrase = [a for a in repo.db.s["altered"] if not a["is_primary"]]
    assert primary[0]["text"] == "new-q"
    assert paraphrase[0]["text"] == "paraphrase"  # 既存行は不変


def test_update_qa_tag_ids_none_vs_empty(repo):
    detail = repo.create_qa("t", "q", "a", tag_ids=[12])
    qa_id = detail.id
    # None: 変更なし
    repo.update_qa(qa_id, title="t2")
    assert {tid for (qid, tid) in repo.db.s["qa_tag"] if qid == qa_id} == {12}
    # []: 全解除
    repo.update_qa(qa_id, tag_ids=[])
    assert {tid for (qid, tid) in repo.db.s["qa_tag"] if qid == qa_id} == set()


def test_update_qa_not_found(repo):
    with pytest.raises(QaError):
        repo.update_qa("nope", title="x")


# --------------------------------------------------------------------------- #
# delete_qa（ADR-0067）
# --------------------------------------------------------------------------- #
def test_delete_qa_not_found(repo):
    with pytest.raises(QaError):
        repo.delete_qa("nope")


def test_delete_qa_cascades_tags_and_altered(repo):
    """QA削除で、紐づく qa_tag・question_altered（主質問文・言い換え行の両方）も削除される。"""
    detail = repo.create_qa("t", "q", "a", tag_ids=[12, 3])
    qa_id = detail.id
    # 言い換え行（is_primary=false）を混在させる
    repo.db.s["altered"].append({"qa_id": qa_id, "text": "paraphrase", "is_primary": False})

    repo.delete_qa(qa_id)

    assert qa_id not in repo.db.s["qa"]
    assert [a for a in repo.db.s["altered"] if a["qa_id"] == qa_id] == []
    assert {tid for (qid, tid) in repo.db.s["qa_tag"] if qid == qa_id} == set()


def test_delete_qa_leaves_other_qa_intact(repo):
    """削除対象以外のQA・タグ・言い換え行は影響を受けない。"""
    keep = repo.create_qa("keep", "q", "a", tag_ids=[12])
    target = repo.create_qa("target", "q", "a", tag_ids=[3])

    repo.delete_qa(target.id)

    assert keep.id in repo.db.s["qa"]
    assert {tid for (qid, tid) in repo.db.s["qa_tag"] if qid == keep.id} == {12}
    assert [a for a in repo.db.s["altered"] if a["qa_id"] == keep.id]


# --------------------------------------------------------------------------- #
# list_qa / list_categories
# --------------------------------------------------------------------------- #
def test_list_qa_paging(repo):
    repo.create_qa("a", "q", "a")
    repo.create_qa("b", "q", "a")
    items, total = repo.list_qa(limit=1, offset=0)
    assert total == 2
    assert len(items) == 1


def test_list_categories(repo):
    cats = repo.list_categories()
    assert {c["id"] for c in cats} == {1, 3}


# --------------------------------------------------------------------------- #
# 検索対象フラグ（ADR-0092 / ADR-0093 / ADR-0094）
# --------------------------------------------------------------------------- #
def test_create_qa_defaults_to_searchable(repo):
    detail = repo.create_qa("t", "q", "a")
    assert detail.is_searchable is True


def test_create_qa_can_be_unsearchable(repo):
    detail = repo.create_qa("t", "q", "a", is_searchable=False)
    assert detail.is_searchable is False


def test_update_qa_is_searchable_only_does_not_recompute_embedding(repo, embed):
    """フラグのみの更新では embedding を再計算しない（ADR-0093 決定2）。"""
    detail = repo.create_qa("t", "q", "a")
    embed.calls.clear()

    updated = repo.update_qa(detail.id, is_searchable=False)

    assert updated.is_searchable is False
    assert embed.calls == []


def test_update_qa_is_searchable_none_keeps_current_value(repo):
    detail = repo.create_qa("t", "q", "a", is_searchable=False)
    updated = repo.update_qa(detail.id, title="t2")
    assert updated.is_searchable is False  # None=変更なし


def test_list_qa_returns_is_searchable(repo):
    repo.create_qa("t", "q", "a", is_searchable=False)
    items, _ = repo.list_qa()
    assert items[0].is_searchable is False


def test_import_qa_batch_omitted_column_keeps_existing_value(repo):
    """列なし・空欄は「新規は true・既存は変更なし」（ADR-0094 決定3）。"""
    detail = repo.create_qa("t", "q", "a", is_searchable=False)

    # is_searchable 列を持たない旧形式のCSV行で更新しても、除外設定は解除されない。
    results = repo.import_qa_batch(
        [{"uuid": detail.id, "title": "更新後"}], _FakeTagRepository()
    )
    assert results[0]["status"] == "success"
    assert repo.get_qa(detail.id).is_searchable is False

    # 空欄も同じ扱い。
    repo.import_qa_batch(
        [{"uuid": detail.id, "title": "更新後2", "is_searchable": ""}],
        _FakeTagRepository(),
    )
    assert repo.get_qa(detail.id).is_searchable is False


def test_import_qa_batch_new_row_defaults_to_true(repo):
    results = repo.import_qa_batch(
        [{"uuid": "", "title": "t", "question_text": "q", "answer_text": "a"}],
        _FakeTagRepository(),
    )
    assert results[0]["status"] == "success"
    assert repo.get_qa(results[0]["qa_id"]).is_searchable is True


@pytest.mark.parametrize(
    "value,expected", [("true", True), ("TRUE", True), ("1", True),
                       ("false", False), ("False", False), ("0", False)]
)
def test_import_qa_batch_accepts_true_false_1_0(repo, value, expected):
    detail = repo.create_qa("t", "q", "a")
    repo.import_qa_batch(
        [{"uuid": detail.id, "is_searchable": value}], _FakeTagRepository()
    )
    assert repo.get_qa(detail.id).is_searchable is expected


def test_import_qa_batch_invalid_value_is_row_error(repo):
    detail = repo.create_qa("t", "q", "a")
    results = repo.import_qa_batch(
        [
            {"uuid": detail.id, "is_searchable": "はい"},   # 不正値 → 当該行のみエラー
            {"uuid": detail.id, "is_searchable": "false"},  # 他行は処理を継続する
        ],
        _FakeTagRepository(),
    )
    assert results[0]["status"] == "error"
    assert "is_searchable" in results[0]["error"]
    assert results[1]["status"] == "success"
    assert repo.get_qa(detail.id).is_searchable is False


class _FakeTagRepository:
    """import_qa_batch がタグ解決に使う TagRepository のスタブ（tags 列は未使用）。"""

    def find_by_name(self, name):  # pragma: no cover - tags 列を使うテストがないため
        raise AssertionError("tags column is not used in these tests")

    def create_tag(self, name):  # pragma: no cover
        raise AssertionError("tags column is not used in these tests")
