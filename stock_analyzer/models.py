# (app名)/models.py

from django.db import models
# もしDjango標準のUserモデルを拡張している場合は、以下のように import します
# from django.contrib.auth.models import AbstractUser

# (例) もし 'Users' という名前のカスタムモデルを使っている場合
# class Users(AbstractUser): # もし標準Userを継承している場合
class Users(models.Model): # もし独自のモデルの場合
    # ... 既存のフィールド (username, email など) ...

    # ↓ ここに新しいカラム（フィールド）を追加
    usage_count = models.IntegerField(default=0, verbose_name="利用回数")

    # ...