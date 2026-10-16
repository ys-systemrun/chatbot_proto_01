"""評価ランナーの CLI（ADR-0099 §5）。evals\\eval.bat から `python -m runner <コマンド>` で呼ばれる。

- pull-feedback : 人手評価の増分を evals/feedback/ に取り込む（段階①）
- build-golden  : 初版のゴールデンセットを作る（段階③）
- run           : ゴールデンセットを AWS 検証環境に送り、出典と回答を採点する（段階③）
- compare       : 2回の実行結果を質問単位で比較する（段階③）
- judge         : 保存済みの回答を採点する（ADR-0101。使用量の上限で止まった続き・採点方式を変えた再採点）
`run --repeat N` は同じ構成を N 回実行し、揺れを考慮して比べられるようにする（runner/repeat.py）。
`snapshot` は段階④で追加する。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import feedback
from . import golden as golden_mod

EVALS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EVALS_DIR.parent

# 評価データ（質問・回答・参考情報を含む）は git ではなく DVC で管理する（ADR-0099 §5）。
DVC_REMINDER = """
評価データ（evals/feedback/・evals/runs/）は git ではなく DVC で管理します。共有・保存するには:
  terraform\\dvc.bat add evals/feedback evals/runs
  git add evals/feedback.dvc evals/runs.dvc evals/history.csv
  git commit -m "evals: <内容>"
  terraform\\dvc.bat push"""


def _load_env(path: Path) -> dict[str, str]:
    """evals/.env（KEY=VALUE, '#' コメント）を読む。無ければ空。"""
    values: dict[str, str] = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _setting(name: str) -> str | None:
    return os.environ.get(name) or _load_env(EVALS_DIR / ".env").get(name)


def _base_url(arg: str | None) -> str:
    url = arg or _setting("EVAL_BASE_URL")
    if not url:
        sys.exit(
            "EVAL_BASE_URL が未設定です。evals/.env.example を evals/.env にコピーし、admin_ui の URL"
            "（apply-app の出力 admin_ui_alb_dns_name に http:// を付けたもの）を記入してください。"
        )
    return url


def _resolve_run(name: str) -> Path:
    path = Path(name)
    if not path.is_absolute() and not path.exists():
        path = EVALS_DIR / "runs" / name
    if not (path / "results.jsonl").exists():
        sys.exit(f"実行結果が見つかりません: {name}（evals/runs/ のディレクトリ名を指定してください）")
    return path


def _make_judge(backend: str | None):
    """採点バックエンド（既定: evals/.env の EVAL_JUDGE_BACKEND、無ければ bedrock）に応じた Judge を作る。"""
    from .judge import BACKENDS, JudgeSetupError, load_aws_credentials, make_judge

    backend = backend or _setting("EVAL_JUDGE_BACKEND") or "bedrock"
    if backend not in BACKENDS:
        sys.exit(f"EVAL_JUDGE_BACKEND は {' / '.join(BACKENDS)} のいずれかです: {backend}")
    if backend == "bedrock":
        load_aws_credentials(REPO_ROOT / "terraform" / ".env")
    try:
        judge = make_judge(backend, _setting("EVAL_JUDGE_MODEL_ID"), oauth_token=_setting("CLAUDE_CODE_OAUTH_TOKEN"))
    except JudgeSetupError as exc:
        sys.exit(f"採点を始められません: {exc}")
    version = judge.meta().get("cli_version")
    print(f"採点: {judge.model}（{backend}{', Claude Code ' + version if version else ''}）")
    return judge


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="eval", description="chatbot_invitro 評価ランナー（ADR-0099）")
    sub = parser.add_subparsers(dest="command", required=True)

    pf = sub.add_parser("pull-feedback", help="人手評価（👍/👎・理由・リリース）の増分を evals/feedback/ に取り込む")
    pf.add_argument("--base-url", default=None, help="admin_ui の URL（既定: evals/.env の EVAL_BASE_URL）")

    bg = sub.add_parser("build-golden", help="初版のゴールデンセットを evals/golden/<名前>.csv に作る")
    bg.add_argument("--name", default="v1")
    bg.add_argument("--sample", type=int, default=20, help="言い換え質問文から抽出する問数（既定 20）")
    bg.add_argument("--seed", type=int, default=42)
    bg.add_argument("--force", action="store_true", help="既存のファイルを上書きする")

    rn = sub.add_parser("run", help="ゴールデンセットを送り、出典と回答を採点する")
    rn.add_argument("--set", dest="golden", default="v2", help="ゴールデンセット名（evals/golden/<名前>.csv, 既定 v2）")
    rn.add_argument("--mode", choices=["pipeline", "agentic", "both"], default="both")
    rn.add_argument("--limit", type=int, default=None, help="先頭から N 問だけ実行する（試行用）")
    rn.add_argument("--repeat", type=int, default=1,
                    help="同じ構成を N 回実行し、指標の平均とばらつきを evals/runs/groups/ に出す（既定 1。"
                         "比較の基準や改善の判定には 3 を推奨。回答と採点の費用は N 倍）")
    rn.add_argument("--no-judge", action="store_true", help="LLM 採点をしない（出典と回答控えのみ採点）")
    rn.add_argument("--judge-backend", choices=["bedrock", "claude-code"], default=None,
                    help="採点の実行方法（既定: evals/.env の EVAL_JUDGE_BACKEND、無ければ bedrock）")
    rn.add_argument("--base-url", default=None)

    jd = sub.add_parser("judge", help="保存済みの回答を採点する（evals/runs/ のディレクトリ名を指定）")
    jd.add_argument("run", help="採点する実行（evals/runs/ のディレクトリ名）")
    jd.add_argument("--only-missing", action="store_true",
                    help="未採点の質問だけを同じ実行に書き足す（使用量の上限で止まった続き）。"
                         "付けなければ全問を採点し直し、新しい実行として保存する")
    jd.add_argument("--judge-backend", choices=["bedrock", "claude-code"], default=None)

    cp = sub.add_parser("compare", help="2つの実行結果を比較する（evals/runs/ のディレクトリ名か、繰り返しのグループ ID）")
    cp.add_argument("before")
    cp.add_argument("after")

    args = parser.parse_args(argv)

    if args.command == "pull-feedback":
        base_url = _base_url(args.base_url)
        print(f"取得元: {base_url}/api/evaluated_messages")
        path = feedback.pull(base_url, EVALS_DIR / "feedback")
        if path is None:
            print("新しい評価はありません。")
            return
        print(feedback.summarize(path))
        print(f"保存先: evals/feedback/{path.name}")
        print(DVC_REMINDER)

    elif args.command == "build-golden":
        path = EVALS_DIR / "golden" / f"{args.name}.csv"
        if path.exists() and not args.force:
            sys.exit(f"{path} は既にあります。作り直す場合は --force を付けてください（比較の基準が変わります）。")
        items = golden_mod.build_initial(REPO_ROOT, args.sample, args.seed)
        golden_mod.write(path, items)
        print(f"保存先: evals/golden/{path.name}（{len(items)} 問）")

    elif args.command == "run":
        from . import run as run_mod

        base_url = _base_url(args.base_url)
        golden_path = EVALS_DIR / "golden" / f"{args.golden}.csv"
        if not golden_path.exists():
            sys.exit(f"{golden_path} がありません。先に build-golden を実行してください。")
        if args.repeat < 1:
            sys.exit("--repeat は 1 以上を指定してください。")
        from . import repeat as repeat_mod

        judge = None if args.no_judge else _make_judge(args.judge_backend)
        modes = run_mod.MODES if args.mode == "both" else (args.mode,)
        runs_dir = EVALS_DIR / "runs"
        for mode in modes:
            gid = repeat_mod.group_id(run_mod.now_jst(), args.golden, mode, args.repeat) if args.repeat > 1 else None
            for index in range(1, args.repeat + 1):
                label = f"（{index}/{args.repeat} 回目）" if gid else ""
                print(f"== {mode}{label}: {golden_path.name} → {base_url}")
                run_dir = run_mod.run(base_url, golden_path, mode, runs_dir, REPO_ROOT, judge=judge, limit=args.limit,
                                      repeat={"group": gid, "index": index, "of": args.repeat} if gid else None)
                print(f"保存先: evals/runs/{run_dir.name}/summary.md")
            if gid:
                out = repeat_mod.write_group_summary(runs_dir, gid, run_mod.load_run)
                print(f"繰り返しの集計: evals/runs/{repeat_mod.GROUPS_DIR}/{out.name}（比較には グループ ID {gid} を使う）")
        print("数値の推移: evals/history.csv（git 管理）")
        print(DVC_REMINDER)

    elif args.command == "judge":
        from . import run as run_mod

        source = _resolve_run(args.run)
        judge = _make_judge(args.judge_backend)
        try:
            run_dir = run_mod.rejudge(source, judge, EVALS_DIR / "runs", REPO_ROOT, only_missing=args.only_missing)
        except ValueError as exc:
            sys.exit(str(exc))
        print(f"保存先: evals/runs/{run_dir.name}/summary.md")
        print("数値の推移: evals/history.csv（git 管理）")
        print(DVC_REMINDER)

    elif args.command == "compare":
        from . import repeat as repeat_mod
        from . import run as run_mod
        from .scoring import compare_markdown, compare_warnings

        runs_dir = EVALS_DIR / "runs"
        (b_name, b_dirs), (a_name, a_dirs) = repeat_mod.resolve(runs_dir, args.before), repeat_mod.resolve(runs_dir, args.after)
        for name, dirs in ((b_name, b_dirs), (a_name, a_dirs)):
            if not dirs:
                sys.exit(f"実行結果が見つかりません: {name}（evals/runs/ のディレクトリ名か、繰り返しのグループ ID を指定してください）")
        b_loaded, a_loaded = [run_mod.load_run(d) for d in b_dirs], [run_mod.load_run(d) for d in a_dirs]
        for warning in compare_warnings(b_loaded[0][1], a_loaded[0][1]):
            print(f"> {warning}")
        print(repeat_mod.compare_markdown(b_name, [r for r, _ in b_loaded], a_name, [r for r, _ in a_loaded]))
        if len(b_dirs) == 1 and len(a_dirs) == 1:
            # 1回ずつの比較では、従来どおり質問ごとの採点理由も出す（揺れとの区別は付かない点に注意）。
            print(compare_markdown(b_loaded[0][0], a_loaded[0][0], b_name, a_name, b_loaded[0][1], a_loaded[0][1]))


if __name__ == "__main__":
    main()
