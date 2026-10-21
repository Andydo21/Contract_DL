from django.urls import path
from . import case_library
urlpatterns = [path('cases/', case_library.case_library), path('api/cases/', case_library.case_api)]
