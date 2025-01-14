# views.py
from django.shortcuts import render

def home(request):
    return render(request, 'homepage.html')

def signup(request):
    return render(request, 'signup.html')


def login(request):
    return render(request, 'login.html')

def team(request):
    return render(request, 'team.html')
