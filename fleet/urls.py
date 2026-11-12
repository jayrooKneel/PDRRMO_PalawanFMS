from django.urls import path
from . import views

app_name = 'dashboard_portal'

urlpatterns = [
    path('manifest.webmanifest', views.pwa_manifest, name='pwa_manifest'),
    path('service-worker.js', views.pwa_service_worker, name='pwa_service_worker'),
    # 🏠 Root URL loads the login screen.
    path('', views.login_view, name='login'),

    # 📑 Public/internal home dashboard.
    path('home/', views.homepage, name='homepage'),
    path('home/deployments/', views.deployment_activity_log, name='deployment_activity_log'),
    path('logistics/reports/deployments/', views.logistics_generate_report, name='logistics_generate_report'),
    path('logistics/registration-ocr/', views.logistics_registration_ocr, name='logistics_registration_ocr'),
    path(
        'logistics/operator-document-ocr/',
        views.logistics_operator_document_ocr,
        name='logistics_operator_document_ocr',
    ),
    path(
        'logistics/drivers/<int:driver_id>/license/',
        views.logistics_driver_license_document,
        name='logistics_driver_license_document',
    ),
    path(
        'logistics/registration-documents/<int:document_id>/',
        views.logistics_registration_document,
        name='logistics_registration_document',
    ),
    path('fleet/reports/activity/', views.logistics_generate_report, name='fleet_activity_report'),
    path('fleet/reports/incidents/', views.fleet_report_incident, name='fleet_report_incident'),
    path('fleet/reports/incidents/<int:incident_id>/edit/', views.fleet_edit_incident, name='fleet_edit_incident'),

    # 🔀 Central Gateway Router
    path('portal/dispatch/', views.dashboard_router, name='dashboard_portal'),

    # 🔒 Authentication Utilities
    path('logout/', views.custom_user_logout, name='custom_logout'),
    path('logout/', views.custom_user_logout, name='custom_user_logout'),

    # 📊 Portal Operational Interfaces
    path('repair/', views.repairman_dashboard, name='repairman_dashboard'),
    path('maritime/dispatch/', views.seacraft_dispatch_view, name='seacraft_dispatch'),
    path('maritime/', views.seacraft_dashboard, name='seacraft_dashboard'),
    path('logistics/', views.logistics_dashboard, name='logistics_dashboard'),
]