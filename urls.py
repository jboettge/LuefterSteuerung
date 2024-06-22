from django.urls import path
from .views import set_special_mode

urlpatterns = [
    path('set_special_mode/', set_special_mode, name='set_special_mode'),
    # other paths...
]