from django.shortcuts import render

def home(request):
    """Render the Home page."""
    return render(request, 'core/home.html')

def about(request):
    """Render the About page."""
    return render(request, 'core/about.html')

def contact(request):
    """Render the Contact page."""
    return render(request, 'core/contact.html')
