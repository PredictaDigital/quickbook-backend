from django.urls import path
from .views import *

urlpatterns = [
    path('login/', AuthURLView.as_view(), name='auth_url'),
    path('callback/', CallbackView.as_view(), name='callback'),
    path('refresh-token/<str:realm_id>/', RefreshQuickBooksTokenView.as_view(), name='refresh-token'),
    path('create-account/<str:realm_id>/', CreateAccountView.as_view(), name='create_account'),
    path('get-account/<str:realm_id>/<str:account_id>/', GetAccountView.as_view(), name='get_account'),
    path('list-accounts/<str:realm_id>/', ListAccountsView.as_view(), name='list_accounts'),
    path('update-account/<str:realm_id>/<str:account_id>/', UpdateAccountView.as_view(), name='update_account'),
    path('create-customer/<str:realm_id>/', CreateCustomerView.as_view(), name='CreateCustomerView'),
    path('list-customer/<str:realm_id>/', ListCustomerView.as_view(), name='ListCustomerView'),
    path('get-customer/<str:realm_id>/<str:customer_id>/', GetCustomerView.as_view(), name='GetCustomerView'),
    path('update-customer/<str:realm_id>/', UpdateCustomerView.as_view(), name='UpdateCustomerView'),
    path('update-sparse-customer/<str:realm_id>/', UpdateSparseCustomerView.as_view(), name='UpdateSparseCustomerView'),
    path('create-employee/<str:realm_id>/', CreateEmployeeView.as_view(), name='CreateEmployeeView'),
    path('get-employee/<str:realm_id>/<str:employee_id>/', GetEmployeeView.as_view(), name='GetEmployeeView'),
    path('update-employee/<str:realm_id>/', UpdateEmployeeView.as_view(), name='UpdateEmployeeView'),
    path('list-employes/<str:realm_id>/', ListEmployesView.as_view(), name='list_employes'),

    path('create-company-info/<str:realm_id>/', CreateCompanyifoView.as_view(), name='CreateCompanyifoView'),
    
    path('get-companyinfo/<str:realm_id>/<str:company_info_id>/', GetCompanyInfoView.as_view(), name='GetCompanyifoView'),
    path('update-company-info/<str:realm_id>/', UpdateCompanyifoView.as_view(), name='UpdateCompanyifoView'),
    path('update-sparse-company-info/<str:realm_id>/', UpdateSparseCompanyifoView.as_view(), name='UpdateSparseCompanyifoView'),
]
