from django.urls import path
from . import views

app_name = 'stock_analyzer'
urlpatterns = [ 
    path('', views.index, name='index'),
    path('series', views.get_series, name='get_series'),  # 株価データ取得
    path('predict', views.get_predict, name='get_predict'), # 予測結果取得   
    path('home', views.index, name='home'),
     # ★ 新機能
    path('api/top-stocks', views.get_top_stocks, name='top_stocks'),
    path('api/search-history', views.get_search_history, name='search_history'),
    path('api/trigger-scan', views.trigger_scan, name='trigger_scan'),  # 管理者のみ
]
