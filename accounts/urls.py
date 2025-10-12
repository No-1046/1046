from django.urls import path
from django.contrib.auth import views as auth_views # Djangoの認証ビューをインポート
from . import views

app_name = 'accounts'
urlpatterns = [
    path('signup/', views.signup,name='signup'),
    path('login/', views.login, name='login'),
    path('home/', views.home, name='home'),

]
