# terraform/modules/cost-alert — Bedrock 月額予算アラート

AWS Budgets で Service=Amazon Bedrock の月額コストを監視し、しきい値超過時にメール通知するモジュール。
Bedrock 利用料はリソースタグで按分できないため、Service ディメンションで絞る。
`terraform/main/app` から、`budget_alert_emails` が指定されたときだけ（count）呼ばれる。

## 構成

| 名前 | 説明 |
|---|---|
| [`main.tf`](main.tf) | 変数（`name` / `monthly_limit_usd` / `alert_emails`）、`aws_budgets_budget`（Bedrock の月額予算と通知）、出力 `budget_name` |
