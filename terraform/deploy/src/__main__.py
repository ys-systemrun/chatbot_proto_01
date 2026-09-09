"""CLI エントリポイント（argparse ディスパッチ）。"""

from __future__ import annotations

import argparse
import sys

from . import commands, log
from .errors import DeployError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deploy", description="chatbot_invitro Terraform デプロイオーケストレータ")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, with_yes: bool = False):
        sp = sub.add_parser(name)
        if with_yes:
            sp.add_argument("--yes", "-y", action="store_true", help="確認プロンプトを省略（無人/CI 用）")
        return sp

    add("bootstrap", with_yes=True)
    add("apply-database", with_yes=True)
    ap = add("apply-app", with_yes=True)
    ap.add_argument("--knowledge-mcp-desired-count", type=int, default=1)
    add("apply-all", with_yes=True)
    sd = add("seed", with_yes=True)
    sd.add_argument(
        "--skip-seed",
        action="store_true",
        help="シード投入をスキップしマイグレーション専用モードで起動（MIGRATE_ONLY=true, ADR-0075）",
    )
    add("migrate")
    imp = add("import-data")
    imp.add_argument(
        "--target",
        choices=["chatbot", "conversation", "both"],
        default="both",
        help="全消去→上書きの対象データベース（既定: both, ADR-0066）",
    )
    imp.add_argument("--chatbot-sql", default=None, help="chatbot 投入ダンプのパス（既定: chatbot.sql）")
    imp.add_argument(
        "--conversation-sql", default=None, help="conversation 投入ダンプのパス（既定: conversation.sql）"
    )
    qry = add("query")
    qry.add_argument(
        "--target",
        choices=["chatbot", "conversation", "both"],
        default="chatbot",
        help="アドホック SQL の実行対象データベース（既定: chatbot, ADR-0083）",
    )
    qry.add_argument("--sql-file", default=None, help="実行する SQL ファイルのパス（既定: query.sql）")
    add("destroy-app")
    add("destroy-database")
    add("shell")
    return parser


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "bootstrap":
            commands.cmd_bootstrap(args.yes)
        elif args.command == "apply-database":
            commands.cmd_apply_database(args.yes)
        elif args.command == "apply-app":
            commands.cmd_apply_app(args.yes, args.knowledge_mcp_desired_count)
        elif args.command == "apply-all":
            commands.cmd_apply_all(args.yes)
        elif args.command == "seed":
            commands.cmd_seed(args.yes, skip_seed=args.skip_seed)
        elif args.command == "migrate":
            commands.cmd_migrate()
        elif args.command == "import-data":
            commands.cmd_import_data(
                target=args.target,
                chatbot_sql=args.chatbot_sql,
                conversation_sql=args.conversation_sql,
            )
        elif args.command == "query":
            commands.cmd_query(target=args.target, sql_file=args.sql_file)
        elif args.command == "destroy-app":
            commands.cmd_destroy_app()
        elif args.command == "destroy-database":
            commands.cmd_destroy_database()
        elif args.command == "shell":
            commands.cmd_shell()
    except DeployError as exc:
        log.error(str(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n中断しました。")
        sys.exit(130)


if __name__ == "__main__":
    main()
