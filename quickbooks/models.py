# quickbooks/models.py
from django.db import models

class QuickBooksToken(models.Model):
    realm_id = models.CharField(max_length=255, unique=True)
    access_token = models.TextField()
    refresh_token = models.CharField(max_length=500)
    expires_in = models.IntegerField()
    scope = models.CharField(max_length=255)

    def __str__(self):
        return f"Token for {self.realm_id}"


class Account(models.Model):
    name = models.CharField(max_length=100)
    sub_account = models.BooleanField(default=False)
    fully_qualified_name = models.CharField(max_length=200)
    active = models.BooleanField(default=True)
    classification = models.CharField(max_length=50)
    account_type = models.CharField(max_length=50)
    account_sub_type = models.CharField(max_length=50)
    current_balance = models.DecimalField(max_digits=15, decimal_places=2)
    current_balance_with_sub_accounts = models.DecimalField(max_digits=15, decimal_places=2)
    currency_value = models.CharField(max_length=10)
    currency_name = models.CharField(max_length=50)
    domain = models.CharField(max_length=50)
    sparse = models.BooleanField(default=False)
    id_ref = models.CharField(max_length=10, unique=True)
    sync_token = models.CharField(max_length=10)
    create_time = models.DateTimeField()
    last_updated_time = models.DateTimeField()

    def __str__(self):
        return self.name


class CustomerInfo(models.Model):
    taxable = models.BooleanField(default=False)
    bill_line1 = models.CharField(max_length=255, blank=True, null=True)
    bill_city = models.CharField(max_length=100, blank=True, null=True)
    bill_country_sub_division_code = models.CharField(max_length=10, blank=True, null=True)
    bill_postal_code = models.CharField(max_length=20, blank=True, null=True)
    ship_line1 = models.CharField(max_length=255, blank=True, null=True)
    ship_city = models.CharField(max_length=100, blank=True, null=True)
    ship_country_sub_division_code = models.CharField(max_length=10, blank=True, null=True)
    ship_postal_code = models.CharField(max_length=20, blank=True, null=True)
    job = models.BooleanField(default=False)
    bill_with_parent = models.BooleanField(default=False)
    balance = models.DecimalField(max_digits=15, decimal_places=2)
    balance_with_jobs = models.DecimalField(max_digits=15, decimal_places=2)
    currency_value = models.CharField(max_length=10)
    currency_name = models.CharField(max_length=50)
    preferred_delivery_method = models.CharField(max_length=50)
    domain = models.CharField(max_length=50)
    sparse = models.BooleanField(default=False)
    id_ref = models.CharField(max_length=10, unique=True)
    sync_token = models.CharField(max_length=10)
    create_time = models.DateTimeField()
    last_updated_time = models.DateTimeField()
    given_name = models.CharField(max_length=100)
    family_name = models.CharField(max_length=100)
    fully_qualified_name = models.CharField(max_length=200)
    company_name = models.CharField(max_length=200)
    display_name = models.CharField(max_length=200)
    print_on_check_name = models.CharField(max_length=200)
    active = models.BooleanField(default=True)
    primary_phone = models.CharField(max_length=20, blank=True, null=True)
    primary_email_addr = models.EmailField(blank=True, null=True)
    default_tax_code_ref = models.CharField(max_length=10, blank=True, null=True)

    def __str__(self):
        return self.display_name


class Employee(models.Model):
    billable_time = models.BooleanField(default=False)
    domain = models.CharField(max_length=50)
    sparse = models.BooleanField(default=False)
    id_ref = models.CharField(max_length=10, unique=True)
    sync_token = models.CharField(max_length=10)
    create_time = models.DateTimeField()
    last_updated_time = models.DateTimeField()
    given_name = models.CharField(max_length=100)
    family_name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=200)
    print_on_check_name = models.CharField(max_length=200)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.display_name


class CompanyInfo(models.Model):
    company_name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=200)
    company_line1 = models.CharField(max_length=255)
    company_city = models.CharField(max_length=100)
    company_country_sub_division_code = models.CharField(max_length=10)
    company_postal_code = models.CharField(max_length=20)
    customer_communication_line1 = models.CharField(max_length=255, blank=True, null=True)
    customer_communication_city = models.CharField(max_length=100, blank=True, null=True)
    customer_communication_country_sub_division_code = models.CharField(max_length=10, blank=True, null=True)
    customer_communication_postal_code = models.CharField(max_length=20, blank=True, null=True)
    customer_communication_email_addr = models.EmailField(blank=True, null=True)
    legal_line1 = models.CharField(max_length=255, blank=True, null=True)
    legal_city = models.CharField(max_length=100, blank=True, null=True)
    legal_country_sub_division_code = models.CharField(max_length=10, blank=True, null=True)
    legal_postal_code = models.CharField(max_length=20, blank=True, null=True)
    primary_phone = models.CharField(max_length=20, blank=True, null=True)
    company_start_date = models.DateField()
    fiscal_year_start_month = models.CharField(max_length=20)
    country = models.CharField(max_length=50)
    email = models.EmailField(blank=True, null=True)
    web_addr = models.URLField(blank=True, null=True)
    supported_languages = models.CharField(max_length=20)
    domain = models.CharField(max_length=50)
    sparse = models.BooleanField(default=False)
    id_ref = models.CharField(max_length=10, unique=True)
    sync_token = models.CharField(max_length=10)
    create_time = models.DateTimeField()
    last_updated_time = models.DateTimeField()

    def __str__(self):
        return self.company_name
