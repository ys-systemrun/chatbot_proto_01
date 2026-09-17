"""LLM または外部AIサービスを呼び出し、実装を差し替えうる機能のサブパッケージ群（ADR-0091 決定1）。

1機能＝1サブパッケージ（`llm_tasks/<機能名>/`）とし、その下に更にディレクトリを掘らない
（ADR-0032・ADR-0090 決定8と同じ階層抑制）。`knowledge.py`・`config.py`・`llm.py`・
`mcp_clients/`・`graph/`・`usecases/`・`main/` は基盤・配線であり本パッケージの対象外。

ディレクトリ名を `tools` としないのは、MCP のツール（`tools/list`・`tools/call`, ADR-0002・
ADR-0021）および LangGraph がLLMへ渡すツール（ADR-0022）と字面が衝突するため（ADR-0091 決定1）。
"""
