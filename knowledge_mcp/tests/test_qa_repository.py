"""QARepository の単体テスト（実装指示書 9.1、IMPL-202608261450 T1 で更新）。

- スコア変換式の境界値（distance=0, distance大）。
- Jaccard 係数ヘルパ。
- category フィルタ有無による WHERE 条件・名前付きパラメータの差分。
- 取得行から Document への変換（tags 未指定時は metadata に tags/category/guid のみ）。
- tags 指定時のタグ構成類似度スコアリング（祖先閉包の Jaccard と埋め込みスコアの重み付き合成、
  metadata への embedding_score / tag_similarity / tag_similarity_weight 追加）。

DB非依存のため、FakeDatabase がSQL/パラメータを記録し、固定行を返す。
IMPL-202608261450 以降、params は dict（名前付きプレースホルダ）である点に注意。

行のカラム順（5.1節）:
    (qa_id, title, answer, category_name, tag_names, qa_closure, input_closure, distance)
"""

import os
import sys
from contextlib import contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from knowledge_mcp.repository.qa_repository import (  # noqa: E402
    QARepository,
    _jaccard,
    distance_to_score,
)


class FakeCursor:
    def __init__(self, rows, log):
        self._rows = rows
        self._log = log

    def execute(self, sql, params=None):
        self._log.append({"sql": sql, "params": params})

    def fetchall(self):
        return self._rows


class FakeDatabase:
    def __init__(self, rows):
        self._rows = rows
        self.log = []

    @contextmanager
    def cursor(self):
        yield FakeCursor(self._rows, self.log)


def _embed(_text):
    return [0.1, 0.2, 0.3]


def test_distance_to_score_boundaries():
    assert distance_to_score(0.0) == 1.0          # 最も類似
    assert distance_to_score(1.0) == 0.5
    assert 0.0 < distance_to_score(1000.0) < 0.01  # distance大 -> 0 に近づく


def test_jaccard():
    assert _jaccard(set(), set()) == 0.0           # 両方空 -> 0（要件6.2節）
    assert _jaccard({1, 2}, {2, 3}) == 1 / 3
    assert _jaccard({1, 2}, {1, 2}) == 1.0
    assert _jaccard({1}, {2}) == 0.0


def test_row_maps_to_document_with_metadata_no_tags():
    row = (
        "guid-1",          # qa_id
        "タイトル",         # title
        "回答本文",         # answer
        "カテゴリA",        # category_name
        ["tagX", "tagY"],  # tag_names
        [1, 2],            # qa_closure
        None,              # input_closure（tags 未指定なので空）
        0.0,               # distance
    )
    db = FakeDatabase([row])
    repo = QARepository(db, _embed)

    docs = repo.search("q")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.id == "guid-1"
    assert doc.source_type == "qa"
    assert doc.title == "タイトル"
    assert doc.content == "回答本文"
    assert doc.score == 1.0
    # tags 未指定時は embedding_score / tag_similarity 等は metadata に含めない（0章）
    assert doc.metadata == {
        "tags": ["tagX", "tagY"],
        "category": "カテゴリA",
        "guid": "guid-1",
    }


def test_no_filters_uses_named_params_without_category_condition():
    db = FakeDatabase([])
    repo = QARepository(db, _embed)
    repo.search("q", top_k=5)

    entry = db.log[0]
    assert isinstance(entry["params"], dict)  # 名前付きプレースホルダ（dict）
    # category フィルタは付かない
    assert "category_id = (SELECT id FROM hiroba_category WHERE name = %(category)s)" not in entry["sql"]
    assert "category" not in entry["params"]
    # 既定の候補プールサイズ max(top_k*10, 50)
    assert entry["params"]["pool_size"] == 50
    # tags 未指定時は [None] を渡す（空配列と None を区別）
    assert entry["params"]["tag_names"] == [None]


def test_candidate_pool_size_default_scales_with_top_k():
    db = FakeDatabase([])
    repo = QARepository(db, _embed)
    repo.search("q", top_k=10)  # max(100, 50) = 100
    assert db.log[0]["params"]["pool_size"] == 100


def test_candidate_pool_size_override():
    db = FakeDatabase([])
    repo = QARepository(db, _embed, candidate_pool_size=7)
    repo.search("q", top_k=100)
    assert db.log[0]["params"]["pool_size"] == 7


def test_category_filter_adds_condition_and_named_param():
    db = FakeDatabase([])
    repo = QARepository(db, _embed)
    repo.search("q", category="カテゴリA", top_k=3)

    entry = db.log[0]
    assert "category_id = (SELECT id FROM hiroba_category WHERE name = %(category)s)" in entry["sql"]
    assert entry["params"]["category"] == "カテゴリA"


def test_tags_present_passes_names_and_scores_by_similarity():
    # input_closure = {1, 2}, qa_closure = {2, 3} -> jaccard = 1/3
    row = (
        "guid-1", "タイトル", "回答本文", "カテゴリA",
        ["tagX"],   # tag_names
        [2, 3],     # qa_closure
        [1, 2],     # input_closure（rows[0][6] から入力閉包を復元する）
        1.0,        # distance -> embedding_score = 0.5
    )
    db = FakeDatabase([row])
    repo = QARepository(db, _embed)  # tag_similarity_weight 既定 0.5

    docs = repo.search("q", tags=["t1", "t2"], top_k=3)

    entry = db.log[0]
    assert entry["params"]["tag_names"] == ["t1", "t2"]

    doc = docs[0]
    expected_embedding = 0.5
    expected_tag_sim = 1 / 3
    expected_combined = 0.5 * expected_embedding + 0.5 * expected_tag_sim
    assert doc.score == expected_combined
    assert doc.metadata["embedding_score"] == expected_embedding
    assert doc.metadata["tag_similarity"] == expected_tag_sim
    assert doc.metadata["tag_similarity_weight"] == 0.5


def test_tags_dedup_preserves_order():
    db = FakeDatabase([])
    repo = QARepository(db, _embed)
    repo.search("q", tags=["a", "b", "a"], top_k=3)
    assert db.log[0]["params"]["tag_names"] == ["a", "b"]


def test_results_sorted_by_combined_score_desc_and_truncated_to_top_k():
    rows = [
        ("g1", "t1", "a1", None, [], [], None, 3.0),  # score = 0.25
        ("g2", "t2", "a2", None, [], [], None, 0.0),  # score = 1.0
        ("g3", "t3", "a3", None, [], [], None, 1.0),  # score = 0.5
    ]
    db = FakeDatabase(rows)
    repo = QARepository(db, _embed)
    docs = repo.search("q", top_k=2)
    assert [d.id for d in docs] == ["g2", "g3"]  # 降順・上位2件
