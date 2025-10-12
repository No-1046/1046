from django.urls import path
from . import views

app_name = 'satock_analyzer'
urlpatterns = [ 
    path('api/series/', views.get_series, name='api_series'),
    path('api/predict/', views.get_predict, name='api_predict'),
    path('api/home/', views.index, name='home'),
    
] 