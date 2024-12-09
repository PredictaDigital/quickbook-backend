from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view
from rest_framework import status
from django.conf import settings
from .models import *
import json
import requests
from requests_oauthlib import OAuth2Session
import logging
logger = logging.getLogger('quickbooks')

def get_oauth_session():
    return OAuth2Session(client_id=settings.CLIENT_ID, redirect_uri=settings.REDIRECT_URI, scope=settings.SCOPE)



class RefreshToken:
    """Handles refreshing the access token when it expires."""

    @staticmethod
    def refresh(realm_id):
        token_obj = QuickBooksToken.objects.filter(realm_id=realm_id).first()
        if not token_obj or not token_obj.refresh_token:
            return {"error": "Refresh token not found"}

        token_url = settings.TOKEN_URL
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": token_obj.refresh_token,
            "client_id": settings.CLIENT_ID,
            "client_secret": settings.CLIENT_SECRET,
        }

        try:
            response = requests.post(token_url, data=payload)
            response.raise_for_status()
            token_data = response.json()

            # Update stored token information
            StoreToken.store(realm_id, token_data)
            return {"message": "Token refreshed successfully", "token_data": token_data}
        except requests.exceptions.RequestException as e:
            return {"error": "Failed to refresh token", "details": str(e)}


class StoreToken:
    @staticmethod
    def store(realm_id, token):
        token_obj, created = QuickBooksToken.objects.update_or_create(
            realm_id=realm_id,
            defaults={
                'access_token': token.get('access_token'),
                'refresh_token': token.get('refresh_token'),
                'expires_in': token.get('expires_in'),
                'scope': token.get('scope', 'com.intuit.quickbooks.accounting'),
            }
        )
        return token_obj


class AuthURLView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        logger.info("GET request received at DemoLoggingView")
        try:
            oauth = get_oauth_session()
            auth_url, state = oauth.authorization_url(settings.AUTHORIZATION_BASE_URL)
            logger.debug(f"Operation result auth url: {auth_url}")
            return Response({"auth_url": auth_url}, status=status.HTTP_200_OK)
        except Exception as e:
            ogger.error(f"auth url An error occurred: {e}")
            return Response({"error": str(e)}, status=status.HTTP_200_OK)



class CallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        logger.info("GET request received at CallbackView")
        code = request.query_params.get("code")
        realm_id = request.query_params.get("realmId")

        if not code or not realm_id:
            return Response({"error": "Missing authorization code or realmId"}, status=status.HTTP_400_BAD_REQUEST)

        token_url = settings.TOKEN_URL
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.REDIRECT_URI,
            "client_id": settings.CLIENT_ID,
            "client_secret": settings.CLIENT_SECRET,
            
        }

        try:
            response = requests.post(token_url, data=payload)
            response.raise_for_status()
            token_data = response.json()
            
            StoreToken.store(realm_id, token_data)
            token_data['realmId'] = realm_id
            logger.debug(f"Operation result callback: {token_data}")
            return Response({"message": "Token saved successfully", "token_data": token_data}, status=status.HTTP_200_OK)
        except requests.exceptions.RequestException as e:
            logger.error(f"An error occurred callback: {e}")
            return Response({"error": "Failed to fetch token", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class RefreshQuickBooksTokenView(APIView):
    """
    API to refresh the QuickBooks access token using the stored refresh token.
    """
    permission_classes = [AllowAny]

    def get(self, request, realm_id):
        logger.info("GET request received at refreshtokenview")
        """
        Handles GET request to refresh the token for the given realm_id.
        """
        try:
            # Call the refresh method from the RefreshToken class
            refresh_response = RefreshToken.refresh(realm_id)

            if "error" in refresh_response:
                return Response(
                    {
                        "error": refresh_response["error"],
                        "details": refresh_response.get("details", "No additional details provided.")
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            logger.debug(f"Operation result refreshtokenview: {refresh_response}")
            return Response(
                {
                    "message": refresh_response["message"],
                    "token_data": refresh_response["token_data"]
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"An error occurred refreshtokenview: {e}")
            return Response(
                {"error": "Unexpected error occurred while refreshing token", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CreateAccountView(APIView):
    def post(self, request, realm_id):
        logger.info("post request received at create account")
        name = request.data.get('name')
        account_type = request.data.get('account_type')
        if not name and not account_type:
            return Response({"error": "Name and Account Type is required in the request body."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred create account : realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        payload = json.dumps({
            "Name": name,
            "AccountType": account_type
        })

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {token.access_token}'
        }

        url = f'{settings.QUICKBOOKURL}/{realm_id}/account'
        response = requests.post(url, headers=headers, data=payload)

        try:
            if response.status_code == 200:
                logger.debug(f"Operation result create account: {response.json()}")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred create account: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred create account: {e}")
            return Response({'error': str(e)}, status=response.status_code)



def insert_accounts(api_response):
    try:
        # Extract accounts from the API response
        accounts = api_response.get("QueryResponse", {}).get("Account", [])
        if not accounts:
            return {"status": "error", "message": "No accounts found in the response"}

        for account_data in accounts:
            # Insert or update the Account
            Account.objects.update_or_create(
                id_ref=account_data["Id"],  # Unique identifier
                defaults={
                    "name": account_data["Name"],
                    "sub_account": account_data.get("SubAccount", False),
                    "fully_qualified_name": account_data["FullyQualifiedName"],
                    "active": account_data.get("Active", True),
                    "classification": account_data["Classification"],
                    "account_type": account_data["AccountType"],
                    "account_sub_type": account_data["AccountSubType"],
                    "current_balance": account_data["CurrentBalance"],
                    "current_balance_with_sub_accounts": account_data.get("CurrentBalanceWithSubAccounts", 0),
                    "currency_value": account_data.get("CurrencyRef", {}).get("value", ""),
                    "currency_name": account_data.get("CurrencyRef", {}).get("name", ""),
                    "domain": account_data["domain"],
                    "sparse": account_data.get("sparse", False),
                    "sync_token": account_data["SyncToken"],
                    "create_time": account_data.get("MetaData", {}).get("CreateTime"),
                    "last_updated_time": account_data.get("MetaData", {}).get("LastUpdatedTime"),
                }
            )

        return {"status": "success", "message": "Accounts inserted successfully"}
    except Exception as e:
        return {"status": "fail", "error": str(e)}



class ListAccountsView(APIView):
    def get(self, request, realm_id):
        logger.info("GET request received at listaccountview")
        query = request.query_params.get('query')
        if not query:
            return Response({"error": "Query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred listaccountview: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        url = f'{settings.QUICKBOOKURL}/{realm_id}/query?query={query}'
        headers = {
            'Authorization': f'Bearer {token.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        response = requests.get(url, headers=headers)
        try:
            if response.status_code == 200:
                insert_accounts(response.json())
                logger.debug(f"Operation result listaccountview: {response.json()}")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred listaccountview: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            print(e,'dsdddddddddddd')
            logger.error(f"An error occurred listaccountview: {e}")
            return Response({'error': str(e)}, status=response.status_code)


class GetAccountView(APIView):
    def get(self, request, realm_id, account_id):
        logger.info("GET request received at GetAccountView")
        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred GetAccountView: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        url = f'{settings.QUICKBOOKURL}/{realm_id}/account/{account_id}'
        headers = {
            'Authorization': f'Bearer {token.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        response = requests.get(url, headers=headers)
        try:
            if response.status_code == 200:
                logger.debug(f"Operation result GetAccountView:")

                # try:
                #     response.raise_for_status()
                #     account_data = response.json().get('Account', {})
                #     currency_ref = CurrencyRef.objects.create(
                #         value=account_data['CurrencyRef']['value'],
                #         name=account_data['CurrencyRef']['name']
                #     )

                #     metadata = MetaData.objects.create(
                #         create_time=account_data['MetaData']['CreateTime'],
                #         last_updated_time=account_data['MetaData']['LastUpdatedTime']
                #     )

                #     Account.objects.update_or_create(
                #     id_ref=account_data['Id'],
                #     defaults={
                #         'name': account_data['Name'],
                #         'sub_account': account_data['SubAccount'],
                #         'fully_qualified_name': account_data['FullyQualifiedName'],
                #         'active': account_data['Active'],
                #         'classification': account_data['Classification'],
                #         'account_type': account_data['AccountType'],
                #         'account_sub_type': account_data['AccountSubType'],
                #         'current_balance': account_data['CurrentBalance'],
                #         'current_balance_with_sub_accounts': account_data['CurrentBalanceWithSubAccounts'],
                #         'currency_ref': currency_ref,
                #         'domain': account_data['domain'],
                #         'sparse': account_data['sparse'],
                #         'sync_token': account_data['SyncToken'],
                #         'metadata': metadata,
                #     }
                # )
                # except Exception as e:
                #     print(e)
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred GetAccountView: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred GetAccountView: {e}")
            return Response({'error': str(e)}, status=response.status_code)


class UpdateAccountView(APIView):
    def put(self, request, realm_id, account_id):
        logger.info("put request received at UpdateAccountView")
        data = request.data
        if not data:
            return Response({"error": "Request body is missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred UpdateAccountView: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)
        payload =  {
                "Name": request.data.get('Name'),
                "SubAccount": request.data.get('SubAccount'),
                "FullyQualifiedName": request.data.get('FullyQualifiedName'),
                "Active": request.data.get('Active'),
                "Classification": request.data.get('Classification'),
                "AccountType": request.data.get('AccountType'),
                "AccountSubType": request.data.get('AccountSubType'),
                "CurrentBalance": request.data.get('CurrentBalance'),
                "CurrentBalanceWithSubAccounts": request.data.get('CurrentBalanceWithSubAccounts'),
                "CurrencyRef": {
                    "value": request.data.get('PrimaryEmailAddr', {}).get('value'),
                    "name": request.data.get('PrimaryEmailAddr', {}).get('name'),
                },
                "domain": request.data.get('domain'),
                "sparse": request.data.get('sparse'),
                "Id": account_id,
                "SyncToken": request.data.get('SyncToken'),
                "MetaData": {
                    "CreateTime": request.data.get('PrimaryEmailAddr', {}).get('CreateTime'),
                    "LastUpdatedTime": request.data.get('PrimaryEmailAddr', {}).get('LastUpdatedTime'),
                }
        }

        url = f'{settings.QUICKBOOKURL}/{realm_id}/account'
        headers = {
            'Authorization': f"Bearer {token.access_token}",
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        try:
            if response.status_code == 200:
                logger.debug(f"Operation result UpdateAccountView:")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred UpdateAccountView: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred UpdateAccountView: {e}")
            return Response({'error': str(e)}, status=response.status_code)


class CreateCustomerView(APIView):
    def post(self, request, realm_id):
        logger.info("POST request received at Create Customer")
        data = request.data
        if not data:
            return Response({"error": "Request body is missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred Create Customer: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)


        data = {
            "FullyQualifiedName": request.data.get('FullyQualifiedName'),
            "PrimaryEmailAddr": {
                "Address": request.data.get('PrimaryEmailAddr', {}).get('Address')
            },
            "DisplayName": request.data.get('DisplayName'),
            "Suffix": request.data.get('Suffix'),
            "Title": request.data.get('Title'),
            "MiddleName": request.data.get('MiddleName'),
            "Notes": request.data.get('Notes'),
            "FamilyName": request.data.get('FamilyName'),
            "PrimaryPhone": {
                "FreeFormNumber":request.data.get('PrimaryPhone', {}).get('FreeFormNumber')
            },
            "CompanyName": request.data.get('CompanyName'),
            "BillAddr": {
                "CountrySubDivisionCode": request.data.get('BillAddr', {}).get('CountrySubDivisionCode'),
                "City": request.data.get('BillAddr', {}).get('City'),
                "PostalCode": request.data.get('BillAddr', {}).get('PostalCode'),
                "Line1": request.data.get('BillAddr', {}).get('Line1'),
                "Country": request.data.get('BillAddr', {}).get('Country')
            },
            "GivenName":request.data.get('GivenName')
        }

        payload = json.dumps(data)

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {token.access_token}'
        }

        url = f'{settings.QUICKBOOKURL}/{realm_id}/customer'
        response = requests.post(url, headers=headers, data=payload)

        try:
            if response.status_code == 200:
                logger.debug(f"Operation result Create Customer:")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred Create Customer:: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred Create Customer: {e}")
            return Response({'error': str(e)}, status=response.status_code)



def insert_customer_list(customer_data):
    try:
        for customer in customer_data:
            # Extract BillAddr details
            bill_addr_data = customer.get("BillAddr", {})
            bill_line1 = bill_addr_data.get("Line1", "")
            bill_city = bill_addr_data.get("City", "")
            bill_country_sub_division_code = bill_addr_data.get("CountrySubDivisionCode", "")
            bill_postal_code = bill_addr_data.get("PostalCode", "")

            # Extract ShipAddr details
            ship_addr_data = customer.get("ShipAddr", {})
            ship_line1 = ship_addr_data.get("Line1", "")
            ship_city = ship_addr_data.get("City", "")
            ship_country_sub_division_code = ship_addr_data.get("CountrySubDivisionCode", "")
            ship_postal_code = ship_addr_data.get("PostalCode", "")

            # Extract Currency details
            currency_data = customer.get("CurrencyRef", {})
            currency_value = currency_data.get("value", "")
            currency_name = currency_data.get("name", "")

            # Extract Metadata
            metadata_data = customer.get("MetaData", {})
            create_time = metadata_data.get("CreateTime")
            last_updated_time = metadata_data.get("LastUpdatedTime")

            # Create or update CustomerInfo
            CustomerInfo.objects.update_or_create(
                id_ref=customer.get("Id"),
                defaults={
                    "taxable": customer.get("Taxable", False),
                    "bill_line1": bill_line1,
                    "bill_city": bill_city,
                    "bill_country_sub_division_code": bill_country_sub_division_code,
                    "bill_postal_code": bill_postal_code,
                    "ship_line1": ship_line1,
                    "ship_city": ship_city,
                    "ship_country_sub_division_code": ship_country_sub_division_code,
                    "ship_postal_code": ship_postal_code,
                    "job": customer.get("Job", False),
                    "bill_with_parent": customer.get("BillWithParent", False),
                    "balance": customer.get("Balance", 0.00),
                    "balance_with_jobs": customer.get("BalanceWithJobs", 0.00),
                    "currency_value": currency_value,
                    "currency_name": currency_name,
                    "preferred_delivery_method": customer.get("PreferredDeliveryMethod", ""),
                    "domain": customer.get("domain", ""),
                    "sparse": customer.get("sparse", False),
                    "sync_token": customer.get("SyncToken", ""),
                    "create_time": create_time,
                    "last_updated_time": last_updated_time,
                    "given_name": customer.get("GivenName", ""),
                    "family_name": customer.get("FamilyName", "predicta"),
                    "fully_qualified_name": customer.get("FullyQualifiedName", ""),
                    "company_name": customer.get("CompanyName", "predicta"),
                    "display_name": customer.get("DisplayName", ""),
                    "print_on_check_name": customer.get("PrintOnCheckName", ""),
                    "active": customer.get("Active", True),
                    "primary_phone": customer.get("PrimaryPhone", {}).get("FreeFormNumber", ""),
                    "primary_email_addr": customer.get("PrimaryEmailAddr", {}).get("Address", ""),
                    "default_tax_code_ref": customer.get("DefaultTaxCodeRef", ""),
                },
            )

        return Response({"message": "Customers successfully inserted or updated."}, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.error(f"Error saving customers: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class ListCustomerView(APIView):
    def get(self, request, realm_id):
        logger.info("GET request received at list customer view")
        query = request.query_params.get('query')
        if not query:
            return Response({"error": "Query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred list customer view: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        url = f'{settings.QUICKBOOKURL}/{realm_id}/query?query={query}'
        headers = {
            'Authorization': f'Bearer {token.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        response = requests.get(url, headers=headers)
        try:
            if response.status_code == 200:
                customer_data = response.json().get("QueryResponse", {}).get("Customer", [])
                insert_customer_list(customer_data)
                logger.debug(f"Operation result list customer: { response.json()}")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred list customer: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred list customer: {e}")
            return Response({'error': str(e)}, status=response.status_code)



class GetCustomerView(APIView):
    def get(self, request, realm_id, customer_id):
        logger.info("GET request received at GetCustomerView")
        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred GetCustomerView: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        url = f'{settings.QUICKBOOKURL}/{realm_id}/customer/{customer_id}'
        headers = {
            'Authorization': f'Bearer {token.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        response = requests.get(url, headers=headers)
        try:
            if response.status_code == 200:
                # customer_data = response.json().get('Customer', {})

                # currency_ref = CurrencyRef.objects.create(
                #         value=customer_data['CurrencyRef']['value'],
                #         name=customer_data['CurrencyRef']['name']
                #     )

                # metadata = MetaData.objects.create(
                #         create_time=customer_data['MetaData']['CreateTime'],
                #         last_updated_time=customer_data['MetaData']['LastUpdatedTime']
                #     )
                # # Save BillAddr
                # bill_addr, _ = Address.objects.update_or_create(
                #     id_ref=customer_data['BillAddr']['Id'],
                #     defaults={
                #         'line1': customer_data['BillAddr']['Line1'],
                #         'city': customer_data['BillAddr']['City'],
                #         'country_sub_division_code': customer_data['BillAddr']['CountrySubDivisionCode'],
                #         'postal_code': customer_data['BillAddr']['PostalCode'],
                #         'lat': customer_data['BillAddr'].get('Lat', None),
                #         'long': customer_data['BillAddr'].get('Long', None),
                #     }
                # )

                # # Save ShipAddr
                # ship_addr, _ = Address.objects.update_or_create(
                #     id_ref=customer_data['ShipAddr']['Id'],
                #     defaults={
                #         'line1': customer_data['ShipAddr']['Line1'],
                #         'city': customer_data['ShipAddr']['City'],
                #         'country_sub_division_code': customer_data['ShipAddr']['CountrySubDivisionCode'],
                #         'postal_code': customer_data['ShipAddr']['PostalCode'],
                #         'lat': customer_data['ShipAddr'].get('Lat', None),
                #         'long': customer_data['ShipAddr'].get('Long', None),
                #     }
                # )
                # # Save CustomerInfo
                # CustomerInfo.objects.update_or_create(
                #     id_ref=customer_data['Id'],
                #     defaults={
                #         'taxable': customer_data['Taxable'],
                #         'bill_addr': bill_addr,
                #         'ship_addr': ship_addr,
                #         'job': customer_data['Job'],
                #         'bill_with_parent': customer_data['BillWithParent'],
                #         'balance': customer_data['Balance'],
                #         'balance_with_jobs': customer_data['BalanceWithJobs'],
                #         'currency_ref': currency_ref,
                #         'preferred_delivery_method': customer_data['PreferredDeliveryMethod'],
                #         'domain': customer_data['domain'],
                #         'sparse': customer_data['sparse'],
                #         'sync_token': customer_data['SyncToken'],
                #         'metadata': metadata,
                #         'given_name': customer_data['GivenName'],
                #         'family_name': customer_data['FamilyName'],
                #         'fully_qualified_name': customer_data['FullyQualifiedName'],
                #         'company_name': customer_data.get('CompanyName', 'predicta'),
                #         'display_name': customer_data['DisplayName'],
                #         'print_on_check_name': customer_data['PrintOnCheckName'],
                #         'active': customer_data['Active'],
                #         'primary_phone': customer_data['PrimaryPhone'].get('FreeFormNumber', None) if 'PrimaryPhone' in customer_data else None,
                #         'primary_email_addr': customer_data['PrimaryEmailAddr'].get('Address', None) if 'PrimaryEmailAddr' in customer_data else None,
                #         'default_tax_code_ref': customer_data['DefaultTaxCodeRef'].get('value', None) if 'DefaultTaxCodeRef' in customer_data else None,
                #     }
                # )
                # logger.debug(f"Operation result GetCustomerView:")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred GetCustomerView: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred GetCustomerView: {e}")
            return Response({'error': str(e)}, status=response.status_code)


class UpdateCustomerView(APIView):
    def put(self, request, realm_id):
        logger.info("PUT request received at update customer")
        data = request.data
        if not data:
            return Response({"error": "Request body is missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred update customer: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "Taxable": request.data.get('Taxable'),
            "BillAddr": {
                "Id": request.data.get('BillAddr', {}).get('Id'),
                "Line1": request.data.get('BillAddr', {}).get('Line1'),
                "City": request.data.get('BillAddr', {}).get('City'),
                "CountrySubDivisionCode": request.data.get('BillAddr', {}).get('CountrySubDivisionCode'),
                "PostalCode": request.data.get('BillAddr', {}).get('PostalCode'),
                "Lat": request.data.get('BillAddr', {}).get('Lat'),
                "Long": request.data.get('BillAddr', {}).get('Long')
            },
            "Job": request.data.get('Job'),
            "BillWithParent": request.data.get('BillWithParent'),
            "Balance": request.data.get('Balance'),
            "BalanceWithJobs": request.data.get('BalanceWithJobs'),
            "CurrencyRef": {
                "value": request.data.get('CurrencyRef', {}).get('value'),
                "name": request.data.get('CurrencyRef', {}).get('name')
            },
            "PreferredDeliveryMethod": request.data.get('PreferredDeliveryMethod'),
            "domain": request.data.get('domain'),
            "sparse": request.data.get('sparse'),
            "Id": request.data.get('Id'),
            "SyncToken": request.data.get('SyncToken'),
            "MetaData": {
                "CreateTime": request.data.get('MetaData', {}).get('CreateTime'),
                "LastUpdatedTime": request.data.get('MetaData', {}).get('LastUpdatedTime')
            },
            "GivenName": request.data.get('GivenName'),
            "FamilyName": request.data.get('FamilyName'),
            "FullyQualifiedName": request.data.get('FullyQualifiedName'),
            "CompanyName": request.data.get('CompanyName'),
            "DisplayName": request.data.get('DisplayName'),
            "PrintOnCheckName": request.data.get('PrintOnCheckName'),
            "Active": request.data.get('Active'),
            "PrimaryPhone": {
                "FreeFormNumber": request.data.get('PrimaryPhone', {}).get('FreeFormNumber')
            },
            "PrimaryEmailAddr": {
                "Address": request.data.get('PrimaryEmailAddr', {}).get('Address')
            }
        }

        url = f'{settings.QUICKBOOKURL}/{realm_id}/customer'
        headers = {
            'Authorization': f"Bearer {token.access_token}",
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        try:
            if response.status_code == 200:
                logger.debug(f"Operation result update customer:")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred update customer: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred update customer: {e}")
            return Response({'error': str(e)}, status=response.status_code)




class UpdateSparseCustomerView(APIView):
    def put(self, request, realm_id):
        logger.info("PUT request received at update Sparse customer")
        data = request.data
        if not data:
            return Response({"error": "Request body is missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred update Sparse customer: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            "MiddleName": request.data.get('MiddleName'), 
            "SyncToken": request.data.get('SyncToken'), 
            "Id": request.data.get('Id'), 
            "sparse": request.data.get('sparse')
        }

        url = f'{settings.QUICKBOOKURL}/{realm_id}/customer'
        headers = {
            'Authorization': f"Bearer {token.access_token}",
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        try:
            if response.status_code == 200:
                logger.debug(f"Operation result update Sparse customer:")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred update Sparse customer: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred update Sparse customer: {e}")
            return Response({'error': str(e)}, status=response.status_code)



class CreateEmployeeView(APIView):
    def post(self, request, realm_id):
        logger.info("GET request received at create employee")
        data = request.data
        if not data:
            return Response({"error": "Request body is missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred create employee: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        data = {
            "GivenName": request.data.get('GivenName'), 
            "SSN": request.data.get('SSN'), 
            "PrimaryAddr": {
                "CountrySubDivisionCode": request.data.get('PrimaryAddr', {}).get('CountrySubDivisionCode'), 
                "City": request.data.get('PrimaryAddr', {}).get('City'), 
                "PostalCode": request.data.get('PrimaryAddr', {}).get('PostalCode'), 
                "Id": request.data.get('PrimaryAddr', {}).get('Id'), 
                "Line1": request.data.get('PrimaryAddr', {}).get('Line1')
            }, 
            "PrimaryPhone": {
                "FreeFormNumber": request.data.get('PrimaryPhone', {}).get('FreeFormNumber')
            }, 
            "FamilyName": request.data.get('FamilyName')
        }

        payload = json.dumps(data)

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {token.access_token}'
        }

        url = f'{settings.QUICKBOOKURL}/{realm_id}/employee'
        response = requests.post(url, headers=headers, data=payload)

        try:
            if response.status_code == 200:
                logger.debug(f"Operation result create employee:")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred create employee: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred create employee: {e}")
            return Response({'error': str(e)}, status=response.status_code)



class GetEmployeeView(APIView):
    def get(self, request, realm_id, employee_id):
        logger.info("GET request received at Get employee")
        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred Get employee: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        url = f'{settings.QUICKBOOKURL}/{realm_id}/employee/{employee_id}'
        headers = {
            'Authorization': f'Bearer {token.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        response = requests.get(url, headers=headers)
        try:
            if response.status_code == 200:
                # employee_data = response.json().get('Employee', {})
                # metadata_data = employee_data.get('MetaData', {})

                # metadata = MetaData.objects.create(
                #     create_time=metadata_data.get('CreateTime'),
                #     last_updated_time=metadata_data.get('LastUpdatedTime')
                # )
                # # Create or update Employee instance
                # employee, created = Employee.objects.update_or_create(
                #     id_ref=employee_data.get('Id'),
                #     defaults={
                #         'billable_time': employee_data.get('BillableTime', False),
                #         'domain': employee_data.get('domain', ''),
                #         'sparse': employee_data.get('sparse', False),
                #         'sync_token': employee_data.get('SyncToken', ''),
                #         'metadata': metadata,
                #         'given_name': employee_data.get('GivenName', ''),
                #         'family_name': employee_data.get('FamilyName', ''),
                #         'display_name': employee_data.get('DisplayName', ''),
                #         'print_on_check_name': employee_data.get('PrintOnCheckName', ''),
                #         'active': employee_data.get('Active', True),
                #     }
                # )
                logger.debug(f"Operation result Get employee:")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred Get employee: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred Get employee: {e}")
            return Response({'error': str(e)}, status=response.status_code)



class UpdateEmployeeView(APIView):
    def put(self, request, realm_id):
        logger.info("PUT request received at Update employee")
        data = request.data
        if not data:
            return Response({"error": "Request body is missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred Update employee: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)


        payload =  {
            "SyncToken": request.data.get('SyncToken'), 
            "domain": request.data.get('domain'), 
            "DisplayName": request.data.get('DisplayName'), 
            "PrimaryPhone": {
                "FreeFormNumber": request.data.get('PrimaryPhone', {}).get('FreeFormNumber')
            }, 
            "PrintOnCheckName": request.data.get('PrintOnCheckName'),  
            "FamilyName": request.data.get('FamilyName'), 
            "Active": request.data.get('Active'), 
            "SSN": request.data.get('SSN'),
            "PrimaryAddr": {
                "CountrySubDivisionCode": request.data.get('PrimaryAddr', {}).get('CountrySubDivisionCode'), 
                "City": request.data.get('PrimaryAddr', {}).get('City'), 
                "PostalCode": request.data.get('PrimaryAddr', {}).get('PostalCode'), 
                "Id": request.data.get('PrimaryAddr', {}).get('Id'), 
                "Line1": request.data.get('PrimaryAddr', {}).get('Line1')
            }, 
            "sparse": request.data.get('sparse'),
            "BillableTime": request.data.get('BillableTime'), 
            "GivenName": request.data.get('GivenName'), 
            "Id": request.data.get('Id'), 
            "MetaData": {
                "CreateTime": request.data.get('MetaData', {}).get('CreateTime'), 
                "LastUpdatedTime": request.data.get('MetaData', {}).get('LastUpdatedTime')
            }
        }

        url = f'{settings.QUICKBOOKURL}/{realm_id}/employee'
        headers = {
            'Authorization': f"Bearer {token.access_token}",
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        try:
            if response.status_code == 200:
                logger.debug(f"Operation result  Update employee:")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred Update employee: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred Update employee: {e}")
            return Response({'error': str(e)}, status=response.status_code)




class ListEmployesView(APIView):
    def get(self, request, realm_id):
        logger.info("GET request received at ListEmployeesView")
        query = request.query_params.get('query')
        if not query:
            return Response({"error": "Query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch the QuickBooks token for the provided realm_id
        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"realm_id {realm_id} does not exist in QuickBooksToken")
            return Response({"error": "Invalid realm_id"}, status=status.HTTP_400_BAD_REQUEST)

        url = f'{settings.QUICKBOOKURL}/{realm_id}/query?query={query}'
        headers = {
            'Authorization': f'Bearer {token.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        # Perform the request to QuickBooks API
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Error making request to QuickBooks API: {e}")
            return Response({"error": "Error connecting to QuickBooks API"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Process the response
        try:
            response_data = response.json()
            employees = response_data.get("QueryResponse", {}).get("Employee", [])

            if not employees:
                logger.info("No employees found in the response")
                return Response({"message": "No employees found"}, status=status.HTTP_200_OK)

            with transaction.atomic():
                for emp in employees:
                    # Update or create Employee records directly
                    Employee.objects.update_or_create(
                        id_ref=emp.get("Id"),
                        defaults={
                            "billable_time": emp.get("BillableTime", False),
                            "domain": emp.get("domain", ""),
                            "sparse": emp.get("sparse", False),
                            "sync_token": emp.get("SyncToken", ""),
                            "create_time": emp.get("MetaData", {}).get("CreateTime"),
                            "last_updated_time": emp.get("MetaData", {}).get("LastUpdatedTime"),
                            "given_name": emp.get("GivenName", ""),
                            "family_name": emp.get("FamilyName", ""),
                            "display_name": emp.get("DisplayName", ""),
                            "print_on_check_name": emp.get("PrintOnCheckName", ""),
                            "active": emp.get("Active", True),
                        },
                    )

            logger.info("Employee data saved successfully")
            return Response({"message": "Employees saved successfully"}, status=status.HTTP_200_OK)

        except KeyError as e:
            logger.error(f"Missing key in API response: {e}")
            return Response({"error": f"Missing data key: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"Unexpected error in ListEmployeesView: {e}")
            return Response({"error": "An unexpected error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)







class CreateCompanyifoView(APIView):
    def post(self, request, realm_id):
        logger.info("post request received at create-company-info")
        data = request.data
        if not data:
            return Response({"error": "Request body is missing."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred create-company-info: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)


        name_value_list = request.data.get('NameValue', [])
        name_values = []
        if isinstance(name_value_list, list):
            for item in name_value_list:
                name = item.get('Name')
                value = item.get('Value')
                name_values.append({"Name": name, "Value": value})


        data =  {
            "SyncToken": request.data.get('SyncToken'), 
            "domain": request.data.get('domain'), 
            "LegalAddr": {
                "City": request.data.get('LegalAddr', {}).get('City'), 
                "Country": request.data.get('LegalAddr', {}).get('Country'), 
                "Line1": request.data.get('LegalAddr', {}).get('Line1'), 
                "PostalCode": request.data.get('LegalAddr', {}).get('PostalCode'), 
                "CountrySubDivisionCode": request.data.get('LegalAddr', {}).get('CountrySubDivisionCode'), 
                "Id": request.data.get('LegalAddr', {}).get('Id')
            }, 
            "SupportedLanguages":request.data.get('SupportedLanguages'), 
            "CompanyName": request.data.get('CompanyName'), 
            "Country":request.data.get('Country'), 
            "CompanyAddr": {
                "City": request.data.get('CompanyAddr', {}).get('City'), 
                "Country": request.data.get('CompanyAddr', {}).get('Country'), 
                "Line1": request.data.get('CompanyAddr', {}).get('Line1'), 
                "PostalCode": request.data.get('CompanyAddr', {}).get('PostalCode'), 
                "CountrySubDivisionCode": request.data.get('CompanyAddr', {}).get('CountrySubDivisionCode'), 
                "Id": request.data.get('CompanyAddr', {}).get('Id')
            }, 
            "sparse": request.data.get('sparse'), 
            "Id": request.data.get('Id'), 
            "WebAddr": {}, 
            "FiscalYearStartMonth": request.data.get('FiscalYearStartMonth'), 
            "CustomerCommunicationAddr": {
                "City": request.data.get('CustomerCommunicationAddr', {}).get('City'), 
                "Country":request.data.get('CustomerCommunicationAddr', {}).get('Country'), 
                "Line1": request.data.get('CustomerCommunicationAddr', {}).get('Line1'),
                "PostalCode": request.data.get('CustomerCommunicationAddr', {}).get('PostalCode'),
                "CountrySubDivisionCode": request.data.get('CustomerCommunicationAddr', {}).get('CountrySubDivisionCode'), 
                "Id": request.data.get('CustomerCommunicationAddr', {}).get('Id')
            }, 
            "PrimaryPhone": {
                "FreeFormNumber": request.data.get('PrimaryPhone', {}).get('FreeFormNumber')
            }, 
            "LegalName": request.data.get('LegalName'),
            "CompanyStartDate": request.data.get('CompanyStartDate'),
            "Email": {
                "Address":request.data.get('Email', {}).get('Address')
            }, 
            "NameValue": name_values,
            "MetaData": {
                "CreateTime": request.data.get('MetaData', {}).get('CreateTime'), 
                "LastUpdatedTime": request.data.get('MetaData', {}).get('LastUpdatedTime')
            }
        }

        payload = json.dumps(data)

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {token.access_token}'
        }

        url = f'{settings.QUICKBOOKURL}/{realm_id}/companyinfo'
        response = requests.post(url, headers=headers, data=payload)
        try:
            if response.status_code == 200:
                logger.debug(f"Operation result create-company-info:")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred create-company-info: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred create-company-info: {e}")
            return Response({'error': str(e)}, status=response.status_code)



class GetCompanyInfoView(APIView):
    def get(self, request, realm_id, company_info_id):
        logger.info("GET request received at get-company-info")

        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error("Realm ID does not exist")
            return Response({"error": "Realm ID does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        url = f'{settings.QUICKBOOKURL}/{realm_id}/companyinfo/{company_info_id}'
        headers = {
            'Authorization': f'Bearer {token.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            try:
                company_info = response.json().get('CompanyInfo', {})
                company_info_instance, created = CompanyInfo.objects.update_or_create(
                    id_ref=company_info['Id'],
                    defaults={
                        'company_name': company_info.get('CompanyName'),
                        'legal_name': company_info.get('LegalName'),
                        'company_line1': company_info.get('CompanyAddr', {}).get('Line1'),
                        'company_city': company_info.get('CompanyAddr', {}).get('City'),
                        'company_country_sub_division_code': company_info.get('CompanyAddr', {}).get('CountrySubDivisionCode'),
                        'company_postal_code': company_info.get('CompanyAddr', {}).get('PostalCode'),
                        'customer_communication_line1': company_info.get('CustomerCommunicationAddr', {}).get('Line1'),
                        'customer_communication_city': company_info.get('CustomerCommunicationAddr', {}).get('City'),
                        'customer_communication_country_sub_division_code': company_info.get('CustomerCommunicationAddr', {}).get('CountrySubDivisionCode'),
                        'customer_communication_postal_code': company_info.get('CustomerCommunicationAddr', {}).get('PostalCode'),
                        'customer_communication_email_addr': company_info.get('CustomerCommunicationEmailAddr', {}).get('Address'),
                        'legal_line1': company_info.get('LegalAddr', {}).get('Line1'),
                        'legal_city': company_info.get('LegalAddr', {}).get('City'),
                        'legal_country_sub_division_code': company_info.get('LegalAddr', {}).get('CountrySubDivisionCode'),
                        'legal_postal_code': company_info.get('LegalAddr', {}).get('PostalCode'),
                        'primary_phone': company_info.get('PrimaryPhone', {}).get('FreeFormNumber'),
                        'company_start_date': company_info.get('CompanyStartDate'),
                        'fiscal_year_start_month': company_info.get('FiscalYearStartMonth'),
                        'country': company_info.get('Country'),
                        'email': company_info.get('Email', {}).get('Address'),
                        'web_addr': company_info.get('WebAddr'),
                        'supported_languages': company_info.get('SupportedLanguages'),
                        'domain': company_info.get('domain'),
                        'sparse': company_info.get('sparse'),
                        'sync_token': company_info.get('SyncToken'),
                        'create_time': company_info.get('MetaData', {}).get('CreateTime'),
                        'last_updated_time': company_info.get('MetaData', {}).get('LastUpdatedTime')
                    }
                )
                return Response({'success': 'Company Info updated successfully'}, status=status.HTTP_200_OK)
            except Exception as e:
                logger.error(f"Error processing company info: {e}")
                return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            error_message = response.json().get('Fault', {}).get('Error', [{}])[0].get('Message', 'Unknown error')
            logger.error(f"QuickBooks API Error: {error_message}")
            return Response({'error': error_message}, status=response.status_code)




class UpdateCompanyifoView(APIView):
    def put(self, request, realm_id):
        logger.info("put request received at update-company-info")
        data = request.data
        if not data:
            return Response({"error": "Request body is missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred update-company-info: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)


        name_value_list = request.data.get('NameValue', [])
        name_values = []
        if isinstance(name_value_list, list):
            for item in name_value_list:
                name = item.get('Name')
                value = item.get('Value')
                name_values.append({"Name": name, "Value": value})


        payload = {
            "SyncToken": request.data.get('SyncToken'), 
            "domain": request.data.get('domain'), 
            "LegalAddr": {
                "City": request.data.get('LegalAddr', {}).get('City'), 
                "Country": request.data.get('LegalAddr', {}).get('Country'), 
                "Line1": request.data.get('LegalAddr', {}).get('Line1'), 
                "PostalCode": request.data.get('LegalAddr', {}).get('PostalCode'), 
                "CountrySubDivisionCode": request.data.get('LegalAddr', {}).get('CountrySubDivisionCode'), 
                "Id": request.data.get('LegalAddr', {}).get('Id'),
            }, 
            "SupportedLanguages": request.data.get('SupportedLanguages'), 
            "CompanyName": request.data.get('CompanyName'), 
            "Country": request.data.get('Country'), 
            "CompanyAddr": {
                "City": request.data.get('CompanyAddr', {}).get('City'),
                "Country": request.data.get('CompanyAddr', {}).get('Country'), 
                "Line1": request.data.get('CompanyAddr', {}).get('Line1'),  
                "PostalCode":request.data.get('CompanyAddr', {}).get('PostalCode'), 
                "CountrySubDivisionCode": request.data.get('CompanyAddr', {}).get('CountrySubDivisionCode'), 
                "Id": request.data.get('CompanyAddr', {}).get('Id'), 
            }, 
            "sparse": request.data.get('sparse'),
            "Id": request.data.get('Id'),
            "WebAddr": {}, 
            "FiscalYearStartMonth": request.data.get('FiscalYearStartMonth'),
            "CustomerCommunicationAddr": {
                "City": request.data.get('CustomerCommunicationAddr', {}).get('City'), 
                "Country":request.data.get('CustomerCommunicationAddr', {}).get('Country'), 
                "Line1": request.data.get('CustomerCommunicationAddr', {}).get('Line1'), 
                "PostalCode": request.data.get('CustomerCommunicationAddr', {}).get('PostalCode'),
                "CountrySubDivisionCode": request.data.get('CustomerCommunicationAddr', {}).get('CountrySubDivisionCode'),  
                "Id": request.data.get('CustomerCommunicationAddr', {}).get('Id')
            }, 
            "PrimaryPhone": {
                "FreeFormNumber": request.data.get('PrimaryPhone', {}).get('FreeFormNumber')
            }, 
            "LegalName": request.data.get('LegalName'),
            "CompanyStartDate": request.data.get('CompanyStartDate'),
            "Email": {
                "Address":  request.data.get('Email', {}).get('Address')
            }, 
            "NameValue": name_values,
            "MetaData": {
                "CreateTime": request.data.get('MetaData', {}).get('CreateTime'),
                "LastUpdatedTime":request.data.get('MetaData', {}).get('LastUpdatedTime'),
            }
        }

        url = f'{settings.QUICKBOOKURL}/{realm_id}/companyinfo'
        headers = {
            'Authorization': f"Bearer {token.access_token}",
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        try:
            if response.status_code == 200:
                logger.debug(f"Operation result update-company-info:")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred update-company-info: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred update-company-info: {e}")
            return Response({'error': str(e)}, status=response.status_code)



class UpdateSparseCompanyifoView(APIView):
    def put(self, request, realm_id):
        logger.info("put request received at update-sparse-company-info")
        data = request.data
        if not data:
            return Response({"error": "Request body is missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = QuickBooksToken.objects.get(realm_id=realm_id)
        except QuickBooksToken.DoesNotExist:
            logger.error(f"An error occurred update-sparse-company-info: realm_id does not exist")
            return Response({"error": "realm_id does not exist"}, status=status.HTTP_400_BAD_REQUEST)


        payload = {
            "SyncToken": request.data.get('SyncToken'), 
            "CompanyName": request.data.get('CompanyName'), 
            "CompanyAddr": {
                "City": request.data.get('CompanyAddr', {}).get('City'), 
                "Country": request.data.get('CompanyAddr', {}).get('Country'), 
                "Line1":  request.data.get('CompanyAddr', {}).get('Line1'),
                "PostalCode": request.data.get('CompanyAddr', {}).get('PostalCode'), 
                "CountrySubDivisionCode": request.data.get('CompanyAddr', {}).get('CountrySubDivisionCode'),  
                "Id": request.data.get('CompanyAddr', {}).get('Id'),
            }, 
            "sparse":  request.data.get('sparse'), 
            "LegalName": request.data.get('LegalName'), 
            "Id": request.data.get('Id'), 
        }

        url = f'{settings.QUICKBOOKURL}/{realm_id}/companyinfo'
        headers = {
            'Authorization': f"Bearer {token.access_token}",
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        try:
            if response.status_code == 200:
                logger.debug(f"Operation result update-sparse-company-info:")
                return Response({'success': response.json()}, status=status.HTTP_200_OK)
            else:
                data = response.json()
                message = data['Fault']['Error'][0]['Message']
                logger.error(f"An error occurred update-sparse-company-info: {message}")
                return Response({'error': message}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred update-sparse-company-info: {e}")
            return Response({'error': str(e)}, status=response.status_code)
