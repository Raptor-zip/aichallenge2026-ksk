# TinyLidarNet Dataset Check

TinyLidarNetの学習を始める前に、抽出したデータと設定をまとめて点検する道具です。学習を起動せず、元のデータや重みを変更しません。ROS 2・PyTorch・GPUは不要で、NumPyとPyYAMLだけで動きます。

## 最初に試す

```bash
git clone https://github.com/Raptor-zip/aichallenge2026-ksk.git
cd aichallenge2026-ksk
python3 -m venv .venv-tln
. .venv-tln/bin/activate
python3 -m pip install -r tools/tln_dataset_check/requirements.txt

# 自分のデータなしで、合成した正常・異常データを確認
python3 tools/tln_dataset_check/make_demo.py /tmp/tln-demo
python3 tools/tln_dataset_check/check.py \
  --train /tmp/tln-demo/good/train --val /tmp/tln-demo/good/val \
  --common-params /tmp/tln-demo/common.yaml \
  --json /tmp/tln-good.json --html /tmp/tln-good.html
```

正常例は終了コード0です。`/tmp/tln-good.html` をブラウザで開くと、走行ごとのラベル分布を確認できます。HTMLは単独ファイルで、外部スクリプト・CDN・サーバーを使いません。

```bash
# NaN・加速度の範囲外・検証側へのコピーを含む異常例
python3 tools/tln_dataset_check/check.py \
  --train /tmp/tln-demo/bad/train --val /tmp/tln-demo/bad/val \
  --common-params /tmp/tln-demo/common.yaml \
  --json /tmp/tln-bad.json --html /tmp/tln-bad.html
```

異常例は終了コード1になり、各指摘に原因を調べる場所と対処方法が付きます。出力ファイルが既にある場合は上書きせず、終了コード2で止まります。再実行時は新しい出力名にしてください。デモ用ディレクトリも既存のものを上書きしません。

JSONとHTMLのどちらかの出力に失敗した場合、その実行で新しく作ったレポートを削除します。既存ファイルは保持します。JSONとHTMLには別々の出力先を指定してください。

## 自分の抽出済みデータを調べる

`dataset/train/<走行名>/` と `dataset/val/<走行名>/` に、公式の抽出スクリプトが出す `scans.npy`、`steers.npy`、`accelerations.npy` がある状態で実行します。走行ディレクトリはルート直下を調べ、入れ子の走行は探しません。これは公式の `MultiSeqConcatDataset` と同じ探索方法です。

```bash
# パスは自分のホスト環境の実際の保存先に置き換えてください
python3 tools/tln_dataset_check/check.py \
  --train ~/aichallenge-racingkart/aichallenge/ml_workspace/tiny_lidar_net/dataset/train \
  --val ~/aichallenge-racingkart/aichallenge/ml_workspace/tiny_lidar_net/dataset/val \
  --common-params ~/aichallenge-racingkart/aichallenge/workspace/src/aichallenge_submit/tiny_lidar_net_controller/config/tiny_lidar_net_common.param.yaml \
  --accel-weight 0 --batch-size 64 \
  --json /tmp/tln-check.json --html /tmp/tln-check.html
```

上の例は**舵だけを学習する**場合です。加速度も学習するなら、`--accel-weight` に実際の `train.loss.accel_weight` を指定します。`--batch-size` も学習設定に合わせます。学習の `data.include` / `data.exclude` に相当する名前の絞り込みは、`--include mpc --exclude debug` のように指定できます。どちらも繰り返し指定でき、includeはOR、excludeはどれかに一致したら除外です。

共通YAMLを使わない旧版では `--input-dim 750 --max-range 30 --accel-scale 1 --decel-scale 1` で値を指定できます。指定しなかった値はこの値に戻ります。CLIの値はYAMLより優先され、レポートに診断に使った最終値が残ります。実際の重みを作った設定と一致しているかは利用者が確認してください。

別の共通YAMLで推論しようとしている場合は、`--inference-common-params <推論側YAML>` も渡すと点数・正規化・倍率の食い違いを検出できます。ノード固有の設定ファイルではなく、共通設定ファイルを渡してください。

## 調べることと、結果の意味

| 検査 | 判定・次に確認すること |
| --- | --- |
| ファイル欠損・読み込み失敗・空配列 | エラー。センサーや制御トピックの有無と抽出処理を確認 |
| 点数・軸・件数の不一致 | エラー。`scans=(N,input_dim)`、ラベルは`(N,)`が必要 |
| ラベルのNaN・inf／スキャンのNaN | エラー。元のトピックと無効値処理を確認 |
| 加速度・舵がtanhの範囲を超える | 学習する出力ならエラー。加速度は正側を`accel_scale`、負側を`decel_scale`で割って判定 |
| ±1のラベル・ほぼ一定のラベル | 警告。飽和や収録条件を点検。学習失敗とは断定しない |
| 負のスキャン・全点同一のフレーム | 警告。センサーと無反射処理を確認。`+inf`は公式ローダーが最大距離にクリップするため、それだけでエラーにはしない |
| 訓練・検証の同一入力／同一入力＋ラベル／全走行の一致 | 警告。入力はclip→正規化→float32で照合。走行名が違っても検出。収録元と分割を確認 |
| 補助の`delta_times.npy` | センサーと制御指令の同期誤差の絶対値（秒）。あれば件数・非負・有限値を確認。0は厳密同期で正常。フレーム間隔としては扱わない |
| 学習件数がbatch_size未満 | 警告。`drop_last=True`の版では0バッチになるため、実際のローダーを確認 |
| 学習と推論の共通設定が違う | エラー。重みと設定を組にして管理 |

終了コードは `0=検査エラーなし`、`1=データ・設定のエラーあり`、`2=引数・YAML・出力先などの実行エラー` です。警告も終了コード1にしたい場合は `--strict` を追加します。構造の判定`usable`は読み取り・形状・数値を検査できたことを示すだけで、学習が成功するという意味ではありません。

重複検査はすべての有効なフレームを調べます。スキャンはメモリマップ＋1024フレームごとの処理、照合用のハッシュは一時SQLiteに置きます。一時領域にはフレーム数に応じた空き容量が必要です。走行ごとの少量のラベル統計はメモリ上で集計します。レポートにはサンプルの値そのものを埋め込まず、統計・走行名・フレーム位置を記録します。

**同じ入力は静止中や無反射の場面でも生じます。重複の検出だけで分割ミスを断定しません。** 逆に、時刻の近いフレームや同じコースからの収録は、値が完全一致しなくても独立性が弱い場合があります。この道具は近似重複、収録履歴、未知のコースでの性能、重みの学習履歴を検証しません。走行単位の分割と別コースでの評価を別に行ってください。

## 検証と参照した仕様

```bash
python3 -m unittest discover -s tools/tln_dataset_check -p 'test_*.py' -v
```

正常例、欠損、件数・点数・軸、NaNと`+inf`の違い、正負の倍率、加速度学習の無効化、前処理後の重複、設定不一致、フィルター、object配列の拒否、終了コード、HTMLのエスケープ、入力・既存出力の保護を検証します。

[検証記録](VALIDATION.md)には21件の自動テスト、合成データの正常・異常例、手元の24走行・13,094フレームに対する診断結果と検証の限界をまとめています。

仕様は2026-10-07に公式`dev`を取得して照合しました。参照先の固定版は以下です。

- [データの読み込み・正規化・加速度の換算](https://github.com/AutomotiveAIChallenge/aichallenge-racingkart/blob/50d6f65038b7ebd41620c442c25cfedcc1b3c7a6/aichallenge/ml_workspace/tiny_lidar_net/lib/data.py)
- [共通設定](https://github.com/AutomotiveAIChallenge/aichallenge-racingkart/blob/50d6f65038b7ebd41620c442c25cfedcc1b3c7a6/aichallenge/workspace/src/aichallenge_submit/tiny_lidar_net_controller/config/tiny_lidar_net_common.param.yaml)
- [公式の学習手順](https://automotiveaichallenge.github.io/aichallenge-documentation-racingkart/ml_sample/tiny_lidar_net.html)

## English quick start

Read-only pre-training checks for the extracted TinyLidarNet `.npy` dataset. Requires Python 3.10+, NumPy and PyYAML; no ROS, PyTorch or GPU. Use the installation and demo commands above, or pass your actual `--train`, `--val` and `--common-params` paths. Set `--accel-weight` and `--batch-size` to the values used by training. Optional `--inference-common-params` compares the inference YAML. `--include` and `--exclude` match the upstream sequence-name filters.

The JSON and standalone HTML reports cover structural defects, non-finite values, scaled target ranges, constant data and exact train/validation overlap after upstream preprocessing. Every finding includes a suggested next check. All valid frames are indexed with SHA-256 in a temporary SQLite database. Existing output files are never overwritten.

Exit codes: 0 = no errors (warnings may remain), 1 = data/settings errors (or warnings with `--strict`), 2 = execution/configuration errors. Shared frames are warnings: stationary or constant observations can match without a recording being copied. No matches does not prove independent recordings or performance on unseen courses. The tool does not alter data, start training or check weight provenance. Current schema uses `decel_scale`; legacy `brake_scale` is rejected so a version mismatch is visible.

MIT License. Team KSK. Drafting and implementation used Codex; the reported checks are executable regression tests and recorded dataset runs.
