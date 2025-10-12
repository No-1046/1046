from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm


def index(request):
    return render(request, 'entrance/index.html')

def login(request):
    return render(request, 'accounts/login.html')

