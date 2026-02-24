# ファイルの説明
- requirements.txt
    - Streamlit Cloudに公開するために必要なライブラリとバージョンそのバージョンをまとめたファイル
    

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

# 起動
```
streamlit run app.py
```
                    
