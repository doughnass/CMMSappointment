from django.urls import path
from . import views

app_name = 'appointments'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Calendar / Schedule
    path('schedule/', views.schedule, name='schedule'),
    path('dispatch/', views.dispatch_board, name='dispatch_board'),
    path('ot-schedule/', views.ot_schedule, name='ot_schedule'),

    # Appointment list & CRUD
    path('appointments/', views.appointment_list, name='appointment_list'),
    path('appointments/create/', views.appointment_create, name='appointment_create'),
    path('appointments/reports/', views.reports, name='reports'),
    path('appointments/<int:pk>/', views.appointment_detail, name='appointment_detail'),
    path('appointments/<int:pk>/edit/', views.appointment_update, name='appointment_update'),
    path('appointments/<int:pk>/delete/', views.appointment_delete, name='appointment_delete'),
    path('appointments/<int:pk>/receive/', views.appointment_receive, name='appointment_receive'),
    path('appointments/<int:pk>/assign/', views.appointment_assign, name='appointment_assign'),
    path('appointments/<int:pk>/complete/', views.appointment_complete_action, name='appointment_complete_action'),

    # Equipment
    path('equipment/', views.equipment_list, name='equipment_list'),
    path('equipment/import/', views.equipment_import, name='equipment_import'),
    path('equipment/import/template/', views.equipment_import_template, name='equipment_import_template'),
    path('equipment/create/', views.equipment_create, name='equipment_create'),
    path('equipment/<int:pk>/', views.equipment_detail, name='equipment_detail'),
    path('equipment/<int:pk>/edit/', views.equipment_update, name='equipment_update'),
     path('equipment/<int:pk>/delete/', views.equipment_delete, name='equipment_delete'),

    # Technicians
    path('technicians/', views.technician_list, name='technician_list'),
    path('technicians/skills/', views.technician_skill, name='technician_skill'),
    path('technicians/create/', views.technician_create, name='technician_create'),
    path('technicians/<int:pk>/', views.technician_detail, name='technician_detail'),
    path('technicians/<int:pk>/edit/', views.technician_update, name='technician_update'),
    path('technicians/<int:pk>/add-leave/', views.technician_add_leave, name='technician_add_leave'),
    path('technicians/<int:pk>/add-overtime/', views.technician_add_overtime, name='technician_add_overtime'),
    path('technicians/<int:pk>/overtime/<int:ot_pk>/remove/', views.technician_remove_overtime, name='technician_remove_overtime'),

    # Customers
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/create/', views.customer_create, name='customer_create'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('customers/<int:pk>/edit/', views.customer_update, name='customer_update'),
    path('customers/<int:pk>/delete/', views.customer_delete, name='customer_delete'),
    path('customers/<int:pk>/contacts/add/', views.customer_contact_add, name='customer_contact_add'),
    path('customers/<int:pk>/contacts/<int:contact_pk>/delete/', views.customer_contact_delete, name='customer_contact_delete'),

    # JSON APIs
    path('api/appointments/', views.api_appointments, name='api_appointments'),
    path('api/equipment/<int:pk>/info/', views.api_equipment_info, name='api_equipment_info'),
    path('api/equipment-search/', views.api_equipment_search, name='api_equipment_search'),
     path('api/skill-search/', views.api_skill_search, name='api_skill_search'),
    path('api/technician-availability/', views.api_technician_availability,
         name='api_technician_availability'),
    path('api/technician-suggestions/', views.api_technician_suggestions,
         name='api_technician_suggestions'),
    path('api/calendar-availability/', views.api_calendar_availability,
         name='api_calendar_availability'),
]
