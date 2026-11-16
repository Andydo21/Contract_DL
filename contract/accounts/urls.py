from django.urls import path
from contract.accounts.views import authentication_views as auth, identity_views as identity

urlpatterns = [
    path('login/', auth.login_user, name='login'),
    path('signup/', auth.signup_user, name='signup'),
    path('logout/', auth.logout_user, name='logout'),
    path('api/token/', auth.api_obtain_token, name='api_obtain_token'),
    path('identity/', identity.identity_registry, name='identity_registry'),
    path('api/identity/companies/', identity.api_companies_list, name='api_companies_list'),
    path('api/identity/companies/register/', identity.api_register_company, name='api_register_company'),
    path('api/identity/users/', identity.api_users_list, name='api_users_list'),
    path('api/identity/users/register/', identity.api_register_user, name='api_register_user'),
    path('api/identity/roles/', identity.api_roles_list, name='api_roles_list'),
]
