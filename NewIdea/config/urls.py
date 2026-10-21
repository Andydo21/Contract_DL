from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views
from core import case_library

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.chat_view, name='home'),
    path('chat/', views.chat_view, name='chat_view'),
    
]

# Unsafe legacy writes are retired in every mode. Prototype case review is
# opt-in and has its own authenticated, CSRF-protected lifecycle.
if settings.NEWIDEA_MODE == 'prototype':
    urlpatterns += [path('cases/', case_library.case_library, name='case_library'),
                    path('api/cases/', case_library.case_api, name='case_api')]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
