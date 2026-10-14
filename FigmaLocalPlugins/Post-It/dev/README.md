# Post-It

ポストイット（付箋）を生成する Figma ローカルプラグインです。

- ラベル（初期値 `memo`）と本文を入力して生成する。本文が空欄なら `Enter Text...` で生成する
- 生成日（`YYYY-MM-DD`）と、実行したアカウントのアイコン・名前が入った状態で生成される
- カラーは 8 色のプリセットから選ぶ。生成後も、選択中のポストイットの色をプリセット内で変更できる

## ディレクトリ構成

```
Post-It/
├── build/   Figma に import するファイル（npm run build で生成。直接編集しない）
│   ├── manifest.json
│   ├── code.js
│   └── ui.html
└── dev/     開発用
    ├── code.ts         プラグイン本体（build/code.js にコンパイルされる）
    ├── ui.html         プラグインの UI（build/ にコピーされる）
    ├── manifest.json   プラグイン設定（build/ にコピーされる）
    └── package.json, tsconfig.json, eslint.config.js など
```

`build/` はコミット対象です。clone 後すぐに import できるよう、`dev/` を変更したら `npm run build` してから一緒にコミットしてください。

## Figma への import

1. Figma デスクトップアプリでデザインファイルを開く
2. メニューから Plugins > Development > Import plugin from manifest...
3. `Post-It/build/manifest.json` を選択する

## 開発

Node.js が必要です。以下は `dev/` で実行します。

```sh
npm install      # 初回のみ
npm run build    # build/ を更新
npm run watch    # code.ts の変更を監視して build/code.js を自動更新
npm run lint     # ESLint
```

`watch` が自動で更新するのは `code.js` だけです。`ui.html` や `manifest.json` を変更したときは `npm run build` を実行してください。
