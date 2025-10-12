"""
URL configuration for myproject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('', include('entrance.urls')),  # サイト基本機能はルートURLに
    path('admin/', admin.site.urls),
    path('analyzer/', include('stock_analyzer.urls')), # 株価分析機能は /analyzer/ 以下に
    path('accounts/', include('accounts.urls')), 
    #path('accounts/home', include('accounts.urls')),  
    #path('accounts/logout', include('accounts.urls')),       # 認証機能は /accounts/ 以下に

]