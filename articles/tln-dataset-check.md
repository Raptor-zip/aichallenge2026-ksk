<!-- タイトル: TinyLidarNetの学習前チェックを自動化した：NaN・ラベルの範囲・訓練と検証の重複を点検する / 推奨タグ: 自動運転AIチャレンジ, Python, 機械学習, ROS2, データ分析 -->

この記事とツールの作成にはAI（Codex）を使用しています。コードは自動テストと抽出済みデータで動作確認しました。

TinyLidarNetを学習する前に、抽出した配列と設定をまとめて点検するツールを作りました。ファイル欠損、NaN、出力範囲を超える教師ラベル、訓練・検証の同一入力を調べ、原因を追う場所をJSONとHTMLに出します。

**ROS 2・PyTorch・GPUは不要**です。Python 3.10以降、NumPy、PyYAMLで動きます。元のデータと設定は変更しません。MITライセンスで公開しています。

[ソースコードと使用手順](https://github.com/Raptor-zip/aichallenge2026-ksk/tree/main/tools/tln_dataset_check)

![異常デモの診断結果。スキャンのNaNと出力範囲外の加速度について、走行名と次に調べる場所を表示](https://raw.githubusercontent.com/Raptor-zip/aichallenge2026-ksk/2e1f7979b4b25c4afff966a69672fce2c99b5728/images/tln-dataset-check/report-errors.png)

*ツールが生成したHTMLをブラウザで表示した画面です。この画像の入力は、問題を意図的に入れた合成データです。*

## 何を調べる道具か

公式サンプルのデータローダーは、走行ディレクトリの `scans.npy`、`steers.npy`、`accelerations.npy` を読みます。この道具も同じ構造を対象にしています。[参照した公式実装](https://github.com/AutomotiveAIChallenge/aichallenge-racingkart/blob/50d6f65038b7ebd41620c442c25cfedcc1b3c7a6/aichallenge/ml_workspace/tiny_lidar_net/lib/data.py)

| 点検するもの | 指摘されたら確認すること |
| --- | --- |
| 必要なファイル・配列の軸・件数・LiDARの点数 | 抽出処理、必要なトピック、モデルの入力点数 |
| ラベルのNaN・inf、スキャンのNaN | 元の制御指令、センサーの無効値処理 |
| 加速度の倍率を適用した教師と、舵の教師の範囲 | 学習する出力、ラベルの単位、学習と推論の共通設定 |
| 訓練・検証の同一入力や、走行名を変えたコピー | 収録元と走行の分割方法 |
| 学習と推論で異なる共通YAML | 重みを学習した設定と推論の組み合わせ |

加速度は、正の値を `accel_scale`、負の値を `decel_scale` で割ってから範囲を調べます。倍率は[公式の共通設定](https://github.com/AutomotiveAIChallenge/aichallenge-racingkart/blob/50d6f65038b7ebd41620c442c25cfedcc1b3c7a6/aichallenge/workspace/src/aichallenge_submit/tiny_lidar_net_controller/config/tiny_lidar_net_common.param.yaml)と合わせます。加速度を学習しない場合の指定も、後で説明します。

## 自分のデータがなくても試せる

最初に、正常な合成データを点検します。作業用のディレクトリで次を実行してください。

```bash
git clone --depth 1 https://github.com/Raptor-zip/aichallenge2026-ksk.git
cd aichallenge2026-ksk
python3 -m venv .venv-tln
. .venv-tln/bin/activate
python3 -m pip install -r tools/tln_dataset_check/requirements.txt

python3 tools/tln_dataset_check/make_demo.py /tmp/tln-article-demo

python3 tools/tln_dataset_check/check.py \
  --train /tmp/tln-article-demo/good/train \
  --val /tmp/tln-article-demo/good/val \
  --common-params /tmp/tln-article-demo/common.yaml \
  --json /tmp/tln-article-good.json \
  --html /tmp/tln-article-good.html
```

検証したv0.1.1では、正常デモの結果は次のようになります。終了コードは0です。

```text
Train 96 / Val 80 frames; 0 errors, 0 warnings
```

`/tmp/tln-article-good.html` をブラウザで開くと、走行ごとのラベル分布も見られます。HTMLは単独ファイルで、外部スクリプトやCDNを読み込みません。

次は、NaN、範囲外の加速度ラベル、訓練データのコピーを含む異常デモです。

```bash
python3 tools/tln_dataset_check/check.py \
  --train /tmp/tln-article-demo/bad/train \
  --val /tmp/tln-article-demo/bad/val \
  --common-params /tmp/tln-article-demo/common.yaml \
  --json /tmp/tln-article-bad.json \
  --html /tmp/tln-article-bad.html
```

```text
Train 192 / Val 96 frames; 2 errors, 3 warnings
```

終了コードは1になります。これは意図した診断結果です。異常デモのtrainには288フレームありますが、NaNのある走行96フレームを有効件数から外すため、表示は192です。

`nan_scans` と `acceleration_target_range` がエラー、ほぼ一定の加速度ラベル、全走行の一致、同一入力が警告になります。どの走行のどの検査で問題が見つかったかを確認してください。

注意：デモのディレクトリと出力ファイルは上書きしません。同じコマンドを再実行する場合は、新しい保存先に変えてください。JSONとHTMLには別々の出力先を指定します。

## 自分のデータで使う

公式の抽出手順で作ったデータを使います。trainとvalのルート直下に走行ディレクトリを置き、その中に3つの `.npy` が必要です。入れ子の走行ディレクトリを自動で探すことはしません。

次のパスを、自分のホスト環境の保存先に置き換えて実行します。公式リポジトリの更新前には、自分が使っている版も確認してください。

```bash
python3 tools/tln_dataset_check/check.py \
  --train ~/aichallenge-racingkart/aichallenge/ml_workspace/tiny_lidar_net/dataset/train \
  --val ~/aichallenge-racingkart/aichallenge/ml_workspace/tiny_lidar_net/dataset/val \
  --common-params ~/aichallenge-racingkart/aichallenge/workspace/src/aichallenge_submit/tiny_lidar_net_controller/config/tiny_lidar_net_common.param.yaml \
  --accel-weight 0 --batch-size 64 \
  --json /tmp/tln-my-check.json \
  --html /tmp/tln-my-check.html
```

**この例は舵だけを学習する設定です。** `--accel-weight` は実際の `train.loss.accel_weight`、`--batch-size` は学習のバッチサイズに合わせます。加速度も学習するなら、その損失重みを渡してください。加速度の損失重み0では、加速度の範囲外をエラーではなく情報として残します。

| 必要に応じて付ける引数 | 用途 |
| --- | --- |
| `--inference-common-params <推論側YAML>` | 学習側と推論側の共通設定を比較する |
| `--include mpc --exclude debug` | 学習対象の走行名に合わせて絞り込む。どちらも繰り返し指定可能 |
| `--strict` | 警告も終了コード1にする |

includeは指定した文字列のどれかを含む走行を選び、excludeはどれかを含む走行を除きます。学習時に絞り込むなら、点検する集合もそろえてください。

終了コードは `0=検査エラーなし`、`1=データ・設定のエラーあり`、`2=引数・YAML・出力先などの実行エラー` です。通常は警告が残っていても0になります。0でも学習の成功や走行性能を保証しません。

## 手元の24走行では何が見つかったか

既存の抽出済みサンプル24走行・13,094フレームを点検しました。診断用に19走行をtrain、5走行をvalに置いた結果です。倍率は加速・減速とも1で、学習する出力を切り替えました。

| 加速度の損失重み | エラー | 警告 |
| --- | ---: | ---: |
| 1（加速度も学習） | 3 | 42 |
| 0（舵のみ学習） | 0 | 21 |

重み1では、ファイル名に `mpc` を含む3走行で、加速度の最小値が約-1.45または-1.6になり、倍率1では出力範囲を超えることを検出しました。重み0では、この指摘を情報扱いに変えています。舵の±1到達に関する警告21件は両方で残りました。

これは「このサンプルでは学習できない」という結論ではありません。学習する出力と倍率に合わせて確認するための結果です。この便宜的なtrain/valの分割について、収録の独立性は検証していません。新たな走行性能の比較も行っていません。

詳細な条件と検証範囲は[検証記録](https://github.com/Raptor-zip/aichallenge2026-ksk/blob/main/tools/tln_dataset_check/VALIDATION.md)に残しています。元のbagと抽出済み配列は、このツールのリポジトリには含めていません。

## 同一入力を見つけても、分割ミスとは即断しない

重複検査では、公式ローダーと同じ順序で距離をclip・正規化し、float32に変換して照合します。生の値が違っても、モデルに渡す入力が同じになる場合を点検するためです。

たとえば、最大距離を30とした場合、`+inf` と30はどちらも正規化後に1になります。`+inf` だけでエラーにしないのも、公式ローダーの処理に合わせています。一方、NaNはエラーとして扱います。

ただし、**同じ入力は静止中や無反射の場面でも生じます。** 同一入力の検出だけで、収録データがコピーされたと断定しません。指摘された走行名とフレーム位置から収録元を確認してください。

逆に、完全一致がなくても、近い時刻のフレームや同じコースの収録を両方に入れていれば、独立した検証として弱い場合があります。この道具は近似重複や未知のコースでの性能まで検証しません。

## テストと、不具合の報告

v0.1.1では21件の自動テストを実行しました。正常・異常データ、正負の倍率、同一入力、設定不一致、終了コード、入力の保持、既存出力の保持、HTMLのエスケープなどを確認しています。

```bash
python3 -W error -m unittest discover -s tools/tln_dataset_check -p 'test_*.py' -v
```

診断結果が実際の学習処理と合わない場合は、[GitHub Issues](https://github.com/Raptor-zip/aichallenge2026-ksk/issues)から報告してもらえると助かります。ツールの版、公式コードのコミット、実行引数、該当する配列のshapeとdtype、指摘コードがあると再現しやすくなります。版は `python3 tools/tln_dataset_check/check.py --version` で確認できます。

## 参考文献・出典

仕様の照合先は公式リポジトリのコミット `50d6f65038b7ebd41620c442c25cfedcc1b3c7a6` です。記事の画面はツールのコミット `2e1f7979b4b25c4afff966a69672fce2c99b5728` に固定しています。

- 公式データローダー：<https://github.com/AutomotiveAIChallenge/aichallenge-racingkart/blob/50d6f65038b7ebd41620c442c25cfedcc1b3c7a6/aichallenge/ml_workspace/tiny_lidar_net/lib/data.py>
- 公式の共通設定：<https://github.com/AutomotiveAIChallenge/aichallenge-racingkart/blob/50d6f65038b7ebd41620c442c25cfedcc1b3c7a6/aichallenge/workspace/src/aichallenge_submit/tiny_lidar_net_controller/config/tiny_lidar_net_common.param.yaml>
- 公式の抽出・学習手順：<https://automotiveaichallenge.github.io/aichallenge-documentation-racingkart/ml_sample/tiny_lidar_net.html>
- ツールのソースと検証記録：<https://github.com/Raptor-zip/aichallenge2026-ksk/tree/main/tools/tln_dataset_check>

最終確認：2026年10月8日。
