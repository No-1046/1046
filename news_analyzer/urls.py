from django.urls import path
from . import views

app_name = 'news_analyzer'

urlpatterns = [ 
    # === 画面表示用 ===
    path('', views.index, name='index'),
    path('dashboard', views.dashboard, name='dashboard'),

    # === API用 (JavaScriptが裏で呼ぶURL) ===
    # ニュース収集実行
    path('crawl', views.api_crawl, name='crawl'),
    
    # 感情分析実行
    path('analyze', views.api_analyze, name='analyze'),
    
    # 会社一覧取得
    path('list-companies', views.api_list_companies, name='list_companies'),
    
    # システム診断
    path('diag', views.api_diag, name='diag'),

    # ダッシュボード用：株価・感情スコア時系列データ
    path('daily', views.api_daily, name='daily'),

    # ダッシュボード用：指定日のニュース詳細（ここが足りていませんでした！）
    path('headlines', views.api_headlines, name='headlines'),
    
    
    path('series', views.news_series, name='news_series'),  # 株価データ取得
]