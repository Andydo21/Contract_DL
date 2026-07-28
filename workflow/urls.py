from django.urls import path
from . import views

urlpatterns = [
    # Page routes
    path('', views.workflow_dashboard, name='workflow_dashboard'),
    path('recommend/', views.workflow_recommendation, name='workflow_recommendation'),
    path('builder/', views.workflow_builder, name='workflow_builder'),
    # API routes
    path('api/recommend/', views.api_workflow_recommend, name='api_workflow_recommend'),
    path('api/build/', views.api_workflow_build, name='api_workflow_build'),
]
