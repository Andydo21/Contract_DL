from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('workflows/', views.create_workflow, name='create_workflow'),
    path('workflows/all/', views.list_all_workflows, name='list_all_workflows'),
    path('workflows/<int:version_id>/', views.get_workflow, name='get_workflow'),
    path('workflows/steps/<int:step_id>/approve/', views.approve_step, name='approve_step'),
]
