# Sample API

## 利用制限
- 1つのAPIキーにつき **1分間に5回** まで呼び出せます。
- 超えた場合は HTTP 429 (Too Many Requests) を返し、`Retry-After` ヘッダで再試行までの秒数を通知します。
