---
date: 2026-10-07 23:22:23
phase: "公開"
iteration: 1
status: partial
---

## やろうとしたこと

設定済みの公開先 `Raptor-zip/aichallenge2026-ksk` のmainに、検証したツールと文書だけをコミットする。既存PNGの削除は含めない。

## 実際に起きたこと

`git diff --check` は成功。通常の接続を確認するために以下を実行した。

```bash
git -c core.sshCommand='ssh -o ConnectTimeout=10 -o BatchMode=yes' ls-remote origin refs/heads/main
```

終了コード128、出力全文:

```text
ssh: Could not resolve hostname github.com: Temporary failure in name resolution
fatal: Could not read from remote repository.

Please make sure you have the correct access rights
and the repository exists.
```

接続済みGitHub機能では、公開先のmainがローカルと同じ `19a67acb418014d8a756f2d33768f69350b3e08c` であることを取得できた。

## 原因

CLIからはgithub.comの名前解決ができない。認証に到達する前の失敗であり、SSH鍵の問題と断定しない。

## 試して却下した方法

| 方法 | 結果 | 却下理由 |
| --- | --- | --- |
| CLIで公開先に接続する | 名前解決に失敗 | 接続済みGitHub機能を使う |

## 最終的な対応

GitHubのGitデータ操作で検証済みのファイルだけをtreeとcommitにし、公開先のSHAを再確認してfast-forwardでmainに反映する。更新時はexpected_shaを指定し、強制更新しない。ローカルも同一Gitオブジェクトで同期する。

## 次にやる人が知っておくべきこと

このログは公開直前の接続障害と対応方針の記録。公開結果はGitHubのmainとコミットで確認する。ユーザーの既存 `images/pp-vs-mpc/pp_formula.png` の削除は維持し、コミットに含めない。実データ、出力レポート、競合調査の私的メモは公開しない。
