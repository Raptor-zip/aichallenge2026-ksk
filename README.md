# 自動運転AIチャレンジ2026 チーム KSK — 記事・動画の図と道具

高専生1人のチーム **KSK** が、自動運転AIチャレンジ2026（主催：公益社団法人 自動車技術会）の2部門に出場した記録の、図・アニメーション・検証用の小さな道具を置いています。

- **End to End AI 部門：準優勝**（2D LiDAR の 750 個の距離だけを見るモデル。本番コースの走行データは学習に入れていない）
- **Sim to Real（SW）部門**：予選 学生クラス2位、SIM 選抜戦で敗退（Pure Pursuit と サンプリング型 MPC）

## 記事・動画

記事と動画の一覧は [LINKS.md](LINKS.md) にあります（公開のたびに追記します）。

## このリポジトリの中身

| パス | 中身 |
| --- | --- |
| `images/<記事>/` | 記事で使っている図・GIF（Qiita から参照） |
| `anim/` | Pure Pursuit と MPC の計算を可視化する Manim のシーン（記事・X 用のループ GIF） |
| `tools/check_image_urls.py` | Markdownの画像URLをGETし、PNGやGIFの全フレームを検査する道具 |

## 画像の参照と確認

記事の画像は、GitHub RawのURLをコミットに固定して参照します。

```text
https://raw.githubusercontent.com/Raptor-zip/aichallenge2026-ksk/<commit>/images/<article>/<image>
```

2026-10-05の確認では、旧jsDelivr経由のURLにタイムアウトやコミット取得の404が出ました。画像の総容量も約120 MBあり、[jsDelivrが公表するGitHubパッケージの50 MB制限](https://github.com/jsdelivr/data.jsdelivr.com#restrictions)を超えています。指定された画像の表示失敗そのものは再現できませんでしたが、配信経路を変更し、20原稿の197画像をGitHub Rawで取得・デコードできることを確認しました。

確認するMarkdownとレポートの出力先を指定して使えます。Pillowが必要です。

```bash
python3 tools/check_image_urls.py article.md --report image-check.json
```

HTTPのステータスとContent-Typeに加え、実際の画像データを検査します。失敗したURLは一度再確認し、最初の失敗と再確認結果を両方レポートに残します。

## ライセンス

- 図・GIF・文章：[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.ja)（「チーム KSK / 自動運転AIチャレンジ2026」と表記してください）
- コード（`anim/` など）：MIT License（[LICENSE](LICENSE)）

大会のロゴ・名称の権利は主催者に帰属します。シミュレータ画面の映像は、KSK 自身の車の走行だけを使っています。
図の数値は筆者の環境での実測、または提出コードと同じ式で計算した例です（各記事に条件を書いています）。
