---
date: 2026-10-07 23:16:40
phase: "検証"
iteration: 1
status: success
---

## やろうとしたこと

TinyLidarNetの学習前検査CLI、JSON、単独HTML、正常・異常デモ、READMEを仕上げ、実際の抽出済み配列で動作を確認した。

## 実際に起きたこと

`python3 -W error -m unittest discover -s tools/tln_dataset_check -p 'test_*.py' -v` は19件成功。正常デモは0エラー・0警告、異常デモは2エラー・3警告。実データ24走行・13,094フレームは加速度重み1で3エラー・42警告、重み0で0エラー・21警告。検証の条件は `tools/tln_dataset_check/VALIDATION.md` に記載した。

HTMLの画面確認に使ったコマンド:

```bash
google-chrome --headless --no-sandbox --disable-gpu --disable-dev-shm-usage --hide-scrollbars --window-size=1200,1800 --screenshot=/tmp/ksk-tln-preview-20261007.png file:///tmp/ksk-tln-bad-preview-20261007.html
```

終了コード1、出力全文:

```text
[1007/231624.534641:ERROR:chrome/app/chrome_main.cc:210] Failed to create a unique user data directory for headless.
```

同じコマンドに `--user-data-dir=/tmp/ksk-tln-chrome-20261007` を追加して実行した。終了コード133、出力全文:

```text
[2:2:1007/231640.045370:ERROR:third_party/crashpad/crashpad/util/linux/socket.cc:45] setsockopt: Operation not permitted (1)
```

スクリーンショットは生成されず、目視検証は未実施。

## 原因

加速度倍率1で約-1.45/-1.6の教師を使うと、tanhの出力範囲を超える。加速度を学習しないときは情報扱いにすべきため、その設定分岐も実データで確認した。Chromeはユーザーディレクトリを指定後もsocket操作が拒否されて起動しなかった。拒否した機構の詳細は不明。

## 試して却下した方法

| 方法 | 結果 | 却下理由 |
| --- | --- | --- |
| Chromeに専用user-data-dirを渡してスクリーンショットを取得 | socket操作が拒否されて終了 | 現在の実行環境では画面を検証できない。権限を迂回しない |

## 最終的な対応

CLIの検証とHTMLの生成・エスケープのテストを完了。画面の目視検証ができていないことを検証記録に明記した。元のデータは変更せず、実データとレポートは `/tmp` に置き、公開対象に含めない。

## 次にやる人が知っておくべきこと

24走行の分割は診断のための便宜的な分割であり、検証データの独立性は未確認。同一入力は静止中にも生じる。合成データのデモは再現可能だが、実データの配列は公開リポジトリに含まない。ブラウザを使える環境でHTMLの見た目を確認する余地が残る。ユーザーの既存PNG削除を今回のコミットに含めない。
