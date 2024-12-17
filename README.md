#ファイルの説明
-weapon.py
    - main page. 起動したときに開かれるpage. 防具のdataframeをいじるstreamlit
- pages
    - streamlitで別のpageを入れるためのフォルダ．streamlitのファイル名の頭に<01_><02_>とつけることでpageの順番を決められる
    - 中身
        - 01_armor.py
            - 防具のdataframeをいじるstreamlit
        - 02_accessary.py
            - 装飾のdataframeをいじるstreamlit
        - 表示バグったらなんか解決するページ.py
            - 本当に解決しました
            - 言うまでもありませんがこのページに頼ることなく解決したいです．weapon,armor,accesaryにうまく取り入れてみたいがスプレッドシートを読み込んだキャッシュごと削除してしまったため断念
- ryuon-equipment-38a59fa0f789.json
    - 流用禁止，スプレッドシートにアクセスし，sobiフォルダのcsvを更新するためのもの．今は直接読み取るために使っている

- requirements.txt
    - Streamlit Cloudに公開するために必要なライブラリとバージョンそのバージョンをまとめたファイル
    
以下動作には関係なし
- version.py
    - requirements.txtを書くための結果を出力するもの．動作環境によって書き換えられたくないのでファイルの書き換えではなく，結果の出力のみにしてある
- log.yml
    - 過去のvol03,04での試行をまとめたもの．経緯や制作意図も含めてこのREADMEより詳細なことが書いているので，むしろそちらを確認してほしい
- create_csv.py
    - 今回は不要．sobiフォルダにスプレッドシートをcsvにして出力するためのもの(今はスプレッドシートから直接datafreamにしている)
- sobi 
    - databaseの保管場所(だった)
    - 中身
        - ksr_accesary.csv
        - ksr_weapon.csv
        - ksr_armor.csv
        - ssr_accesary.csv
        - ssr_weapon.csv
        - ssr_armor.csv
        - ability-category.csv #装備を検索するためのカテゴリをまとめたもの
- test.ipynb
    - 私がバグ検証等に使っていた作業ファイル．邪魔なら消してください

#streamlitの起動の仕方

'''
streamlit run app.py
'''

- バージョンの環境によって動かない場合，仮想環境に作って対処する方法を記す
    - 仮想環境の生成(myenvのところはすきな名前で)
      '''
      python -m venv myenv
      '''
    - 仮想環境のアクティベート(macOSの場合)
      '''
      source myenv/bin/activate
      '''
    - 仮想環境のアクティベート(Windowsの場合)
      '''
      myenv\Scripts\activate
      '''
    - 必要なパッケージをインストール(requirements.txtにもう記述してます)
      '''
      pip install -r requirements.txt
      '''
    - 出る時
      '''
      deactivate
      '''

```
streamlit run weapon.py
```

- バージョンの環境によって動かない場合，仮想環境に作って対処する方法を記す
    - 仮想環境の生成(myenvのところはすきな名前で)
      ```
      python -m venv myenv
      ```
    - 仮想環境のアクティベート(macOSの場合)
      ```
      source myenv/bin/activate
      ```
    - 仮想環境のアクティベート(Windowsの場合)
      ```
      myenv\Scripts\activate
      ```
    - 必要なパッケージをインストール(requirements.txtにもう記述してます)
      ```
      pip install -r requirements.txt
      ```
    - 出る時
      ```
      deactivate
      ```

                    
