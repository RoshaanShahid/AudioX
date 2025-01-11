# views.py
from django.shortcuts import render

def Index(request):
    context = {}  # Define an empty context or add your context data
    return render(request, 'Index.html', context)
