from django.urls import path
from .views import tenant_signup, tenant_login, verify_email  # function, not class

urlpatterns = [
    path('signup/', tenant_signup, name='tenant_signup'),
    path("login/", tenant_login, name="tenant_login"),   
    path("verify-email/", verify_email, name="verify-email"), 
]
