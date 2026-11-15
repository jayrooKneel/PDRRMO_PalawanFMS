# pdrrmo_fleet/pdrrmo_fleet/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.http import HttpResponseRedirect
from urllib.parse import urlencode
from fleet.admin import system_console
from fleet import views


def admin_redirect_to_login(request):
    next_url = request.GET.get('next')
    login_url = '/login/'
    if next_url:
        login_url = f'{login_url}?{urlencode({"next": next_url})}'
    return HttpResponseRedirect(login_url)


urlpatterns = [
    path('', include(('fleet.urls', 'dashboard_portal'), namespace='dashboard_portal')),
    path('admin/system-console/', admin.site.admin_view(system_console), name='admin_system_console'),
    path('admin/login/', admin_redirect_to_login),
    path('admin/fleet/vehicletype/', RedirectView.as_view(url='/admin/', permanent=False), name='admin_vehicletype_redirect'),
    path('admin/', admin.site.urls),
    path('login/', views.login_view, name='login'),
]