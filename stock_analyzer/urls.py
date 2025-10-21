from django.urls import path
from . import views

app_name = 'satock_analyzer'
urlpatterns = [ 
    path('', views.index, name='index'),
    path('series/', views.get_series, name='get_series'),  # 株価データ取得
    path('predict/', views.get_predict, name='get_predict'), # 予測結果取得   
    path('home/', views.index, name='home'),
] 