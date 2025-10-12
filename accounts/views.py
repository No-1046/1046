# accounts/views.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
# UserCreationForm と AuthenticationForm の両方をインポート
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
# login関数をインポート
from django.contrib.auth import login as auth_login

# --- サインアップビュー ---
# @login_required は削除する
def signup(request):
    if request.method == "POST":
        # サインアップなので UserCreationForm を使う
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # サインアップ後、自動的にログインさせる
            auth_login(request, user)
            return redirect('satock_analyzer:home')
    else:
        # GETリクエストでも UserCreationForm を使う
        form = UserCreationForm()
    # テンプレート名は 'signup.html' に修正
    return render(request, "accounts/signup.html", {"form": form})

# --- ログインビュー ---
def login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            # ログイン後、次のページ（例: secret_page）にリダイレクトさせる
            # もしくは、クエリパラメータで指定されたページへ
            if 'next' in request.POST:
                return redirect(request.POST.get('next'))
            else:
                return redirect('satock_analyzer:home')
    else:
        form = AuthenticationForm()
    return render(request, "accounts/login.html", {'form': form})

# --- ホームビュー ---
def home(request):
    return render(request, "accounts/home.html")



# --- シークレットページ ---
# ログイン必須にする
@login_required
def secret_page(request):
    return render(request, "stock_analyzer/main.html")